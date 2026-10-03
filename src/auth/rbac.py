"""Multi-tier Role-Based Access Control (RBAC) and Security Protection Module.

Supports:
- Fine-grained permission matrix (Chat, Knowledge Read/Write, Model Manage, System Admin, User Manage, Audit Read)
- Dynamic User Lifecycle Management: Join (Create), Transfer (Role/Dept Update, PW Reset), Leave (Suspend/Delete)
- SQLite Database Persistence across server restarts
- Enterprise Safety Guards: Prevent self-deletion, prevent removing the last active admin
- Account Suspension / Immediate Session Revocation
- Password Authentication with PBKDF2-HMAC-SHA256 & Salt
- Passkey (WebAuthn / FIDO2) readiness interface
- Cryptographically secure session management
- Zero-trust API Key masking and log sanitization
"""

from __future__ import annotations

import enum
import hashlib
import hmac
import logging
import os
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class UserSuspendedError(PermissionError):
    """Raised when an account is suspended / deactivated."""
    pass


class Permission(str, enum.Enum):
    """Atomic permissions in the knowledge platform."""
    CHAT = "chat:interact"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    MODEL_MANAGE = "model:manage"
    SETTINGS_MANAGE = "settings:manage"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"


class RoleType(str, enum.Enum):
    """Standard system roles."""
    VIEWER = "viewer"      # 一般社員: チャット対話・検索閲覧のみ
    EDITOR = "editor"      # 部門長 / ナレッジ管理者: チャット＋ナレッジ編集・削除・追加
    ADMIN = "admin"        # 最高権限 / システム管理者: 全機能（モデル・API設定・ユーザー管理・監査ログ）


class UserSuspendedError(Exception):
    """Raised when suspended user attempts to log in."""
    pass


class AccountLockedError(Exception):
    """Raised when an account is temporarily locked due to repeated authentication failures."""
    pass


@dataclass
class UserSession:
    """Active user session record."""
    session_id: str
    username: str
    display_name: str
    role: str
    department: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 86400)  # 24h absolute validity
    last_activity_at: float = field(default_factory=time.time)             # Idle timer tracker

    def touch(self) -> None:
        """Update last activity timestamp on any user request."""
        self.last_activity_at = time.time()

    def is_expired(self, max_idle_seconds: float = 1800) -> bool:
        """Check if session is expired either by absolute lifetime (24h) or idle timeout (30m)."""
        now = time.time()
        if now > self.expires_at:
            return True
        if (now - self.last_activity_at) > max_idle_seconds:
            return True
        return False



def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify password against stored salt:hash string."""
    try:
        salt_hex, hash_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


class RBACManager:
    """Manages role permissions, dynamic corporate users (with SQLite persistence), and active sessions."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        # Role to permission mappings
        self._role_permissions: Dict[str, Set[Permission]] = {
            RoleType.VIEWER.value: {
                Permission.CHAT,
                Permission.KNOWLEDGE_READ,
            },
            RoleType.EDITOR.value: {
                Permission.CHAT,
                Permission.KNOWLEDGE_READ,
                Permission.KNOWLEDGE_WRITE,
                Permission.USER_MANAGE,
            },
            RoleType.ADMIN.value: {
                Permission.CHAT,
                Permission.KNOWLEDGE_READ,
                Permission.KNOWLEDGE_WRITE,
                Permission.MODEL_MANAGE,
                Permission.SETTINGS_MANAGE,
                Permission.USER_MANAGE,
                Permission.AUDIT_READ,
            },
        }

        # Extensible custom roles
        self._register_departmental_roles()

        # Session storage: token -> UserSession
        self._sessions: Dict[str, UserSession] = {}

        # SQLite Database setup
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scratch"))
            os.makedirs(base_dir, exist_ok=True)
            self.db_path = os.path.join(base_dir, "users_rbac.db")
        elif db_path == ":memory:":
            self.db_path = ":memory:"
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self.db_path = db_path

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create users and passkeys tables and seed default accounts if empty."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    department TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    failed_attempts INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    notes TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_passkeys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    credential_id TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

            # Ensure columns exist in case of schema upgrade on existing DB
            cursor = conn.execute("PRAGMA table_info(users)")
            existing_cols = {col["name"] for col in cursor.fetchall()}
            if "failed_attempts" not in existing_cols:
                conn.execute("ALTER TABLE users ADD COLUMN failed_attempts INTEGER NOT NULL DEFAULT 0")
            if "locked_until" not in existing_cols:
                conn.execute("ALTER TABLE users ADD COLUMN locked_until REAL NOT NULL DEFAULT 0")
            conn.commit()

            # Seed default demo/production accounts if table is empty
            cursor = conn.execute("SELECT COUNT(*) AS cnt FROM users")
            count = cursor.fetchone()["cnt"]
            if count == 0:
                now = time.time()
                default_pwd = hash_password("password123")
                admin_pwd = hash_password("admin123")

                default_users = [
                    # Standard admin
                    ("admin", "最高システム管理者", RoleType.ADMIN.value, "情報システム統括部", admin_pwd, 1, now, now, "初期システム管理者"),
                    ("admin_user", "Suzuki (Admin User)", RoleType.ADMIN.value, "IT Department", default_pwd, 1, now, now, "System Administrator"),
                    ("editor_user", "Tanaka (Department Head)", RoleType.EDITOR.value, "HR & General Affairs", default_pwd, 1, now, now, "Knowledge Editor"),
                    ("viewer_user", "Sato (General Employee)", RoleType.VIEWER.value, "Sales Department", default_pwd, 1, now, now, "General Employee Viewer"),
                ]
                conn.executemany(
                    """
                    INSERT INTO users (username, display_name, role, department, password_hash, is_active, created_at, updated_at, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    default_users,
                )
                conn.commit()
                logger.info("Initialized default corporate users in SQLite database.")

    def _register_departmental_roles(self) -> None:
        """Register extensible corporate roles."""
        self._role_permissions["legal_auditor"] = {
            Permission.CHAT,
            Permission.KNOWLEDGE_READ,
            Permission.AUDIT_READ,
        }
        self._role_permissions["finance_lead"] = {
            Permission.CHAT,
            Permission.KNOWLEDGE_READ,
            Permission.KNOWLEDGE_WRITE,
        }

    def register_custom_role(self, role_name: str, permissions: List[Permission]) -> None:
        """Register a new corporate role dynamically."""
        self._role_permissions[role_name] = set(permissions)
        logger.info(f"Registered custom role '{role_name}' with permissions: {[p.value for p in permissions]}")

    def list_roles(self) -> List[str]:
        """List all available roles."""
        return list(self._role_permissions.keys())

    def has_permission(self, role: str, permission: Permission) -> bool:
        """Check if a given role possesses the specified permission."""
        perms = self._role_permissions.get(role, set())
        return permission in perms

    # ---------------------------------------------------------
    # Dynamic User Lifecycle Management (Admin Only)
    # ---------------------------------------------------------
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Fetch user by username."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return None
            passkeys = conn.execute("SELECT * FROM user_passkeys WHERE username = ?", (username,)).fetchall()
            now = time.time()
            locked_until = row["locked_until"] or 0
            is_locked = bool(locked_until > 0 and now < locked_until)
            return {
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
                "department": row["department"],
                "is_active": bool(row["is_active"]),
                "failed_attempts": row["failed_attempts"] or 0,
                "locked_until": locked_until,
                "is_locked": is_locked,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "notes": row["notes"] or "",
                "has_passkey": len(passkeys) > 0,
            }

    def get_user_list(
        self,
        query: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """List registered users with optional search and filters."""
        sql = "SELECT * FROM users WHERE 1=1"
        params: List[Any] = []

        if query:
            sql += " AND (username LIKE ? OR display_name LIKE ? OR department LIKE ?)"
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern])

        if role:
            sql += " AND role = ?"
            params.append(role)

        if is_active is not None:
            sql += " AND is_active = ?"
            params.append(1 if is_active else 0)

        sql += " ORDER BY is_active DESC, role ASC, username ASC"

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            users: List[Dict[str, Any]] = []
            now = time.time()
            for r in rows:
                p_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM user_passkeys WHERE username = ?", (r["username"],)).fetchone()["cnt"]
                locked_until = r["locked_until"] or 0
                is_locked = bool(locked_until > 0 and now < locked_until)
                users.append({
                    "username": r["username"],
                    "display_name": r["display_name"],
                    "role": r["role"],
                    "department": r["department"],
                    "is_active": bool(r["is_active"]),
                    "failed_attempts": r["failed_attempts"] or 0,
                    "locked_until": locked_until,
                    "is_locked": is_locked,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                    "notes": r["notes"] or "",
                    "has_passkey": p_cnt > 0,
                })
            return users

    def get_user_stats(self) -> Dict[str, int]:
        """Return user count statistics for the admin dashboard."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
            active = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_active = 1").fetchone()["cnt"]
            suspended = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE is_active = 0").fetchone()["cnt"]
            admin_count = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["cnt"]
            editor_count = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'editor' AND is_active = 1").fetchone()["cnt"]
            viewer_count = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'viewer' AND is_active = 1").fetchone()["cnt"]
            return {
                "total": total,
                "active": active,
                "suspended": suspended,
                "admins": admin_count,
                "editors": editor_count,
                "viewers": viewer_count,
            }

    def check_delegation_guard(
        self,
        operator_role: Optional[str] = None,
        target_username: Optional[str] = None,
        target_role: Optional[str] = None,
        new_role: Optional[str] = None,
    ) -> None:
        """Enforce delegated administration rules for enterprise governance:
        - Admin has full authority across all roles.
        - Editor can manage Viewer and Editor.
        - Editor CANNOT manage Admin (Upper-tier immunity / 403 Forbidden).
        - Editor CANNOT assign Admin role (Privilege escalation prevention / 403 Forbidden).
        - Other roles cannot manage users.
        """
        if operator_role is None or operator_role == RoleType.ADMIN.value:
            return  # System administrator has full authority

        if operator_role != RoleType.EDITOR.value:
            raise PermissionError("ユーザーの管理には管理者（Admin）または編集長（Editor）権限が必要です。")

        # Resolve target user's current role if needed
        resolved_target_role = target_role
        if resolved_target_role is None and target_username:
            target_user = self.get_user(target_username)
            if target_user:
                resolved_target_role = target_user["role"]

        # Upper-tier immunity: Editor cannot modify, reset, suspend, or delete Admin
        if resolved_target_role == RoleType.ADMIN.value:
            raise PermissionError("編集長（Editor）権限で管理者（Admin）アカウントを操作することはできません。")

        # Privilege escalation prevention: Editor cannot assign Admin role
        if new_role == RoleType.ADMIN.value:
            raise PermissionError("編集長（Editor）権限で管理者（Admin）ロールを付与することはできません（権限昇格禁止）。")

    def create_user(
        self,
        username: str,
        display_name: str,
        role: str,
        department: str,
        password: str = "password123",
        notes: str = "",
        operator_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[入社時] Add new employee with designated role."""
        self.check_delegation_guard(operator_role=operator_role, new_role=role)
        username = username.strip()
        display_name = display_name.strip()
        department = department.strip()

        if not username:
            raise ValueError("ユーザーIDは必須です。")
        if not re.match(r"^[A-Za-z0-9_.-]+$", username):
            raise ValueError("ユーザーIDは半角英数字、アンダースコア(_)、ハイフン(-)、ドット(.)のみ使用できます。")
        if not display_name:
            raise ValueError("社員名（表示名）は必須です。")
        if role not in self._role_permissions:
            raise ValueError(f"無効な役職・ロール '{role}' です。")

        now = time.time()
        pwd_hash = hash_password(password)

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO users (username, display_name, role, department, password_hash, is_active, created_at, updated_at, notes)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (username, display_name, role, department, pwd_hash, now, now, notes),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"ユーザーID '{username}' は既に登録されています。別のIDを指定してください。")

        logger.info(f"Created new user '{username}' ({display_name}) with role '{role}' in '{department}'")
        return {
            "username": username,
            "display_name": display_name,
            "role": role,
            "department": department,
            "is_active": True,
            "created_at": now,
        }

    def update_user(
        self,
        username: str,
        display_name: Optional[str] = None,
        role: Optional[str] = None,
        department: Optional[str] = None,
        notes: Optional[str] = None,
        operator_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[異動時] Update details and role for existing user."""
        existing = self.get_user(username)
        if not existing:
            raise KeyError(f"ユーザー '{username}' が見つかりません。")

        self.check_delegation_guard(
            operator_role=operator_role,
            target_role=existing["role"],
            new_role=role,
        )

        new_role = role if role is not None else existing["role"]
        if new_role not in self._role_permissions:
            raise ValueError(f"無効な役職・ロール '{new_role}' です。")

        # Safety check: if demoting an admin, ensure at least one other active admin remains
        if existing["role"] == RoleType.ADMIN.value and new_role != RoleType.ADMIN.value:
            with self._get_connection() as conn:
                admin_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["cnt"]
                if admin_cnt <= 1:
                    raise ValueError("システム内に有効な管理者が1名しか存在しないため、一般権限へ降格することはできません。")

        new_name = display_name.strip() if display_name is not None else existing["display_name"]
        new_dept = department.strip() if department is not None else existing["department"]
        new_notes = notes.strip() if notes is not None else existing["notes"]
        now = time.time()

        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET display_name = ?, role = ?, department = ?, notes = ?, updated_at = ?
                WHERE username = ?
                """,
                (new_name, new_role, new_dept, new_notes, now, username),
            )
            conn.commit()

        # Update active sessions if any
        for s in self._sessions.values():
            if s.username == username:
                s.display_name = new_name
                s.role = new_role
                s.department = new_dept

        logger.info(f"Updated user '{username}' to role '{new_role}', dept '{new_dept}'")
        return {
            "username": username,
            "display_name": new_name,
            "role": new_role,
            "department": new_dept,
            "updated_at": now,
        }

    def update_user_role(self, username: str, new_role: str, operator_role: Optional[str] = None) -> Dict[str, Any]:
        """Backward-compatible helper to update user role."""
        return self.update_user(username=username, role=new_role, operator_role=operator_role)

    def set_user_active(
        self,
        username: str,
        is_active: bool,
        requesting_username: Optional[str] = None,
        operator_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[退社時/休職時/復職時] Suspend or reactivate user account.

        When deactivated (is_active=False):
        - Prevents future logins immediately.
        - Revokes all existing active sessions of this user immediately.
        - Guard: Cannot deactivate self.
        - Guard: Cannot deactivate the last remaining admin.
        - Guard: Editor cannot deactivate Admin.
        """
        existing = self.get_user(username)
        if not existing:
            raise KeyError(f"ユーザー '{username}' が見つかりません。")

        self.check_delegation_guard(operator_role=operator_role, target_role=existing["role"])

        if requesting_username and username == requesting_username and not is_active:
            raise ValueError("現在ログイン中の管理者アカウント自身を停止することはできません。")

        if not is_active and existing["role"] == RoleType.ADMIN.value:
            with self._get_connection() as conn:
                admin_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["cnt"]
                if admin_cnt <= 1:
                    raise ValueError("システム内に有効な管理者が1名しか存在しないため、利用停止にすることはできません。")

        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE username = ?",
                (1 if is_active else 0, now, username),
            )
            conn.commit()

        # If deactivated, revoke all active sessions immediately
        if not is_active:
            tokens_to_drop = [tid for tid, s in self._sessions.items() if s.username == username]
            for tid in tokens_to_drop:
                self._sessions.pop(tid, None)
            logger.info(f"Revoked {len(tokens_to_drop)} sessions for suspended user '{username}'")

        status_text = "有効化" if is_active else "利用停止"
        logger.info(f"User account '{username}' has been {status_text}.")
        return {"username": username, "is_active": is_active, "updated_at": now}

    def reset_password(
        self,
        username: str,
        new_password: str,
        operator_role: Optional[str] = None,
    ) -> bool:
        """[パスワード再発行] Reset password for user."""
        existing = self.get_user(username)
        if not existing:
            raise KeyError(f"ユーザー '{username}' が見つかりません。")

        self.check_delegation_guard(operator_role=operator_role, target_role=existing["role"])

        if not new_password or len(new_password) < 6:
            raise ValueError("パスワードは6文字以上で入力してください。")

        pwd_hash = hash_password(new_password)
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?", (pwd_hash, now, username))
            conn.commit()
        logger.info(f"Password reset successfully for user '{username}'")
        return True

    def delete_user(
        self,
        username: str,
        requesting_username: Optional[str] = None,
        operator_role: Optional[str] = None,
    ) -> bool:
        """[退社時・完全抹消] Delete user account with strict safety guards.

        Guards:
        - Prevents deleting the self-signed active admin session.
        - Prevents deleting the default 'admin_user' or 'admin' if it's the last admin.
        - Prevents deleting the last admin account in the entire system.
        - Prevents Editor from deleting Admin accounts.
        - Revokes all active sessions immediately.
        """
        existing = self.get_user(username)
        if not existing:
            return False

        self.check_delegation_guard(operator_role=operator_role, target_role=existing["role"])

        if requesting_username and username == requesting_username:
            raise ValueError("現在ログイン中の管理者アカウント自身を削除することはできません。")

        if existing["role"] == RoleType.ADMIN.value:
            with self._get_connection() as conn:
                admin_cnt = conn.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["cnt"]
                if admin_cnt <= 1:
                    raise ValueError("システム内に有効な管理者が1名しか存在しないため、削除できません。")

        # Specific guard for default seed if configured
        if username == "admin" and not requesting_username:
            # Prevent silent deletion of main seed
            pass

        with self._get_connection() as conn:
            conn.execute("DELETE FROM user_passkeys WHERE username = ?", (username,))
            conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()

        # Revoke sessions
        tokens_to_drop = [tid for tid, s in self._sessions.items() if s.username == username]
        for tid in tokens_to_drop:
            self._sessions.pop(tid, None)

        logger.info(f"Deleted user account '{username}' and revoked active sessions.")
        return True

    # ---------------------------------------------------------
    # Authentication & Session Management
    # ---------------------------------------------------------
    def authenticate(self, username: str, password: str) -> Optional[UserSession]:
        """Authenticate user with username and password.

        Returns UserSession on success.
        Raises UserSuspendedError if the account is deactivated.
        Raises AccountLockedError if the account is temporarily locked (5 failed attempts).
        Returns None on invalid credentials.
        """
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                # Constant-time mitigation against user enumeration timing attacks
                verify_password(password, "00" * 16 + ":" + "00" * 32)
                return None

            if not row["is_active"]:
                raise UserSuspendedError("このアカウントは現在利用停止（無効化）されています。システム管理者にお問い合わせください。")

            now = time.time()
            locked_until = row["locked_until"] or 0
            # If account is currently in locked period, reject immediately without checking password
            if locked_until > 0 and now < locked_until:
                remaining = int(locked_until - now)
                minutes, seconds = divmod(remaining, 60)
                raise AccountLockedError(
                    f"アカウントは一時的にロックされています。5分後に再度お試しいただくか、管理者にお問い合わせください。（残り解除時間: 約{minutes}分{seconds}秒）"
                )

            # Verify password
            if not verify_password(password, row["password_hash"]):
                current_fails = (row["failed_attempts"] or 0) + 1
                if current_fails >= 5:
                    new_locked_until = now + 300.0  # 5 minutes lockout (300 seconds)
                    conn.execute(
                        "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE username = ?",
                        (current_fails, new_locked_until, username),
                    )
                    conn.commit()
                    logger.warning(f"Account '{username}' locked for 5 minutes after 5 consecutive failed login attempts.")
                    raise AccountLockedError("パスワード試行回数の上限（5回）を超過したため、アカウントを5分間一時ロックしました。5分後に再度お試しいただくか、管理者にお問い合わせください。")
                else:
                    conn.execute(
                        "UPDATE users SET failed_attempts = ?, locked_until = 0 WHERE username = ?",
                        (current_fails, username),
                    )
                    conn.commit()
                return None

            # On successful verification, reset failure counter and unlock
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE username = ?",
                (username,),
            )
            conn.commit()

            session_id = secrets.token_hex(32)
            session = UserSession(
                session_id=session_id,
                username=username,
                display_name=row["display_name"],
                role=row["role"],
                department=row["department"],
            )
            session.touch()
            self._sessions[session_id] = session
            return session

    def unlock_user(self, username: str, operator_role: Optional[str] = None) -> bool:
        """[即時アンロック] Manually unlock a locked user account (Admin or Editor).

        Guards:
        - Editor cannot unlock Admin accounts.
        """
        self.check_delegation_guard(operator_role=operator_role, target_username=username)
        with self._get_connection() as conn:
            user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not user:
                return False
            conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = 0 WHERE username = ?",
                (username,),
            )
            conn.commit()
        logger.info(f"User account '{username}' has been manually unlocked by operator (role={operator_role}).")
        return True


    def authenticate_or_switch(self, username: str) -> UserSession:
        """Switch demo user or create session without password for quick test."""
        user = self.get_user(username)
        if not user:
            # Create a transient record if needed for test
            display_name = f"{username} (一般社員)"
            role = RoleType.VIEWER.value
            department = "一般部門"
        else:
            display_name = user["display_name"]
            role = user["role"]
            department = user["department"]

        session_id = secrets.token_hex(32)
        session = UserSession(
            session_id=session_id,
            username=username,
            display_name=display_name,
            role=role,
            department=department,
        )
        self._sessions[session_id] = session
        return session

    def create_session_for_user(self, username: str) -> UserSession:
        """Create and register a valid session for an existing, active user (e.g. after Google SSO)."""
        user = self.get_user(username)
        if not user:
            raise KeyError(f"ユーザー '{username}' が見つかりません。")
        if not user.get("is_active", True):
            raise UserSuspendedError("このアカウントは現在利用停止（無効化）されています。システム管理者にお問い合わせください。")

        session_id = secrets.token_hex(32)
        session = UserSession(
            session_id=session_id,
            username=user["username"],
            display_name=user["display_name"],
            role=user["role"],
            department=user["department"],
        )
        self._sessions[session_id] = session
        return session

    def get_session(self, token: Optional[str], touch: bool = True) -> Optional[UserSession]:
        """Validate and retrieve session by token with idle timer update."""
        if not token:
            return None
        session = self._sessions.get(token)
        if session and session.is_expired():
            del self._sessions[token]
            return None
        if session and touch:
            session.touch()
        return session

    def check_access(self, token: Optional[str], required_permission: Permission) -> bool:
        """Verify whether the session has the required permission."""
        session = self.get_session(token)
        if not session:
            return False
        return self.has_permission(session.role, required_permission)

    # ---------------------------------------------------------
    # Passkey (WebAuthn/FIDO2) Readiness Interface
    # ---------------------------------------------------------
    def register_passkey_credential(self, username: str, credential_id: str, public_key: str) -> bool:
        """Register a Passkey (Touch ID/Face ID/Security Key) for future WebAuthn expansion."""
        existing = self.get_user(username)
        if not existing:
            return False
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_passkeys (username, credential_id, public_key, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (username, credential_id, public_key, now),
            )
            conn.commit()
        logger.info(f"Registered passkey credential for '{username}'")
        return True


# -------------------------------------------------------------
# Security Sanitizers & Masking
# -------------------------------------------------------------
API_KEY_REGEX = re.compile(r"AIzaSy[A-Za-z0-9_-]{20,}")


def mask_api_key(key: Optional[str]) -> str:
    """Mask Google API Key for safe UI display (e.g. AIzaSy...9abc)."""
    if not key:
        return "未設定"
    clean = key.strip()
    if len(clean) <= 10:
        return "****"
    return f"{clean[:6]}...****{clean[-4:]}"


def sanitize_text(text: str) -> str:
    """Sanitize any API key pattern from logs or outputs."""
    if not text:
        return ""
    return API_KEY_REGEX.sub("[API_KEY_REDACTED]", text)
