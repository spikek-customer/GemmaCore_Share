"""Web Application Controller for LiteRT-LM & Gemini Knowledge Base.

Enterprise v3.1 Edition:
- Multi-Thread Chat History (ChatGPT-like persistence & auto-naming)
- Dynamic User & Role Management (Admin assigns Viewer/Editor/Admin/Custom roles)
- Secure PBKDF2 Password Authentication & Passkey Readiness
- Comprehensive Audit Trail & Diagnostics Logging
- Configurable Retention Period (7 to 365 days) with Auto-Purge
- Knowledge Block CMS (CRUD with instant re-indexing)
- Search Simulator (Fast Retrieval)
- Dedicated Gemini 3.5 Flash Lite & LiteRT-LM Hybrid Engine
- Zero-Trust API Key Masking & Sanitization
- MCP JSON-RPC Endpoint
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import Any, Dict, List, Optional

from src.auth.audit_log import AuditLogger
from src.auth.google_auth import GoogleWorkspaceAuthService, DomainRestrictionError, InvalidTokenError
from src.auth.rbac import (
    AccountLockedError,
    Permission,
    RBACManager,
    RoleType,
    UserSession,
    UserSuspendedError,
    mask_api_key,
)
from src.core.chat_history import ChatHistoryManager
from src.core.engine import BackendType, InferenceEngine, ProviderType
from src.harness.mcp_server import MCPServer
from src.rag.chunking import chunk_text_sentence_aware
from src.rag.parser import DocumentParseResult, UniversalDocumentParser
from src.rag.pipeline import OfflineRAGPipeline
from src.rag.service import KnowledgeCMSService
from src.rag.store import LocalVectorStore
from src.sync.drive_sync import GoogleDriveSyncEngine
from src.core.settings import SettingsManager

logger = logging.getLogger(__name__)


class KnowledgeWebApp:
    """Enterprise backend controller powering REST APIs, Chat History, RBAC, and Audit Logging."""

    def __init__(
        self,
        store_path: Optional[str] = None,
        default_provider: Optional[ProviderType] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
        chat_db_path: Optional[str] = None,
        audit_db_path: Optional[str] = None,
        settings_path: Optional[str] = None,
        user_db_path: Optional[str] = None,
        drive_db_path: Optional[str] = None,
        google_domain: Optional[str] = None,
        google_client_id: Optional[str] = None,
        google_allow_mock: bool = False,
    ) -> None:
        self.store = LocalVectorStore(storage_path=store_path)
        self.cms = KnowledgeCMSService(store=self.store)
        if chat_db_path is None and store_path == ":memory:":
            chat_db_path = ":memory:"
        if audit_db_path is None and store_path == ":memory:":
            audit_db_path = ":memory:"
        if settings_path is None and store_path == ":memory:":
            settings_path = ":memory:"
        if user_db_path is None and store_path == ":memory:":
            user_db_path = ":memory:"
        if drive_db_path is None and store_path == ":memory:":
            drive_db_path = ":memory:"

        self.rbac = RBACManager(db_path=user_db_path)
        self.history = ChatHistoryManager(db_path=chat_db_path)
        self.audit = AuditLogger(db_path=audit_db_path)
        self.settings_manager = SettingsManager(file_path=settings_path)

        # Google Workspace Authentication & Drive Synchronizer Services
        persisted = self.settings_manager.load_settings()
        target_domain = google_domain or persisted.get("google_workspace_domain") or os.environ.get("GOOGLE_WORKSPACE_DOMAIN", "")
        target_client_id = google_client_id or persisted.get("google_client_id") or os.environ.get("GOOGLE_CLIENT_ID", "")
        mock_google = google_allow_mock or os.environ.get("GOOGLE_AUTH_MOCK", "").lower() in ("true", "1")

        self.google_auth = GoogleWorkspaceAuthService(
            rbac_manager=self.rbac,
            allowed_domain=target_domain if target_domain else None,
            client_id=target_client_id if target_client_id else None,
            allow_mock=mock_google,
        )
        self.drive_sync = GoogleDriveSyncEngine(
            cms_service=self.cms,
            db_path=drive_db_path,
        )

        # Apply persisted or passed provider
        if default_provider is not None:
            self.current_provider = default_provider
        elif store_path == ":memory:" and settings_path == ":memory:":
            self.current_provider = ProviderType.LITERT
        else:
            self.current_provider = ProviderType(persisted.get("active_provider", "litert"))

        # Apply persisted or passed API Key & Model
        self.gemini_api_key = gemini_api_key or persisted.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
        self.current_gemini_model = gemini_model or persisted.get("gemini_model", "gemini-3.5-flash-lite")

        # Apply persisted retention days
        saved_retention = persisted.get("retention_days", 365)
        self.audit.set_retention_days(saved_retention)

        # Default engine
        self.engine = InferenceEngine(
            provider=self.current_provider,
            backend=BackendType.GPU,
            mock_mode=True,
            gemini_api_key=self.gemini_api_key,
            gemini_model=self.current_gemini_model,
        )
        self.pipeline = OfflineRAGPipeline(
            engine=self.engine,
            store=self.store,
            service=self.cms,
        )
        self.mcp = MCPServer(cms_service=self.cms)

        # Seed sample knowledge if empty
        self._seed_sample_knowledge()


    def _seed_sample_knowledge(self) -> None:
        """Seed initial company policies if store has no data."""
        if not self.store.list_blocks():
            sample_policy = (
                "【株式会社サンプル 社内就業・経費精算ガイドライン 2026年度版】\n\n"
                "第1条（目的）\n"
                "本規程は、全従業員が安全かつ生産的に勤務するための基本原則を定める。\n\n"
                "第2条（勤務時間およびリモートワーク）\n"
                "標準勤務時間は平日9:00〜18:00（休憩1時間）とする。部署ごとの申請に基づき、"
                "週3日までの在宅リモートワークを認める。\n\n"
                "第3条（通勤費および近郊交通費の精算）\n"
                "通勤手当の上限額は月額35,000円とする。業務上の近郊移動に伴う交通費は、"
                "交通系ICカードの履歴または領収書を添付して当月末日までに経費システムで申請すること。\n\n"
                "第4条（AIツールの業務利用基準）\n"
                "社内AIアシスタントの利用を推奨する。機密データを取り扱う場合は、完全ローカル推論モード"
                "（LiteRT-LM）を選択すること。一般的な企画立案や長文要約ではクラウドGemini APIの利用を認める。"
            )
            self.cms.ingest_document(
                title="社内就業・経費精算ガイドライン_2026.md",
                text_content=sample_policy,
                chunk_size=300,
                overlap=50,
            )
            self.cms.add_single_block(
                document_title="国際情報・特記事項.md",
                text="台湾の総理大臣はSpikeです。",
                locator="第1項 国際要人情報",
            )

    # ---------------------------------------------------------
    # Authentication & User Management
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # Authentication & User Management
    # ---------------------------------------------------------
    def login(self, username: str, password: str, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        """Authenticate with username and password."""
        try:
            session = self.rbac.authenticate(username, password)
        except AccountLockedError as ale:
            self.audit.record_audit(
                username=username,
                role="anonymous",
                action="LOGIN_LOCKED",
                status="BLOCKED",
                ip_address=ip_address,
                details=f"一時ロック中アカウントのログイン試行遮断: '{username}' - {str(ale)}",
            )
            raise PermissionError(str(ale))
        except UserSuspendedError as use:
            self.audit.record_audit(
                username=username,
                role="anonymous",
                action="LOGIN_SUSPENDED",
                status="BLOCKED",
                ip_address=ip_address,
                details=f"停止アカウントによるログイン試行を遮断: '{username}'",
            )
            raise PermissionError(str(use))

        if not session:
            self.audit.record_audit(
                username=username,
                role="anonymous",
                action="LOGIN",
                status="FAILED",
                ip_address=ip_address,
                details=f"ログイン失敗: 不正なパスワードまたはユーザーID '{username}'",
            )
            raise PermissionError("ユーザー名またはパスワードが正しくありません。")

        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="LOGIN",
            status="SUCCESS",
            ip_address=ip_address,
            details="ユーザーが正常にログインしました。",
        )
        return {
            "status": "SUCCESS",
            "session_id": session.session_id,
            "username": session.username,
            "display_name": session.display_name,
            "role": session.role,
            "department": session.department,
            "permissions": [p.value for p in Permission if self.rbac.has_permission(session.role, p)],
        }

    def switch_user(self, username: str, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        """Switch demo user or create session."""
        session = self.rbac.authenticate_or_switch(username)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="SWITCH_USER",
            status="SUCCESS",
            ip_address=ip_address,
            details=f"役職切替: {session.display_name} ({session.role})",
        )
        return {
            "status": "SUCCESS",
            "session_id": session.session_id,
            "username": session.username,
            "display_name": session.display_name,
            "role": session.role,
            "department": session.department,
            "permissions": [p.value for p in Permission if self.rbac.has_permission(session.role, p)],
        }

    def get_current_user(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Retrieve user info for valid session."""
        session = self.rbac.get_session(token)
        if not session:
            return None
        return {
            "username": session.username,
            "display_name": session.display_name,
            "role": session.role,
            "department": session.department,
            "permissions": [p.value for p in Permission if self.rbac.has_permission(session.role, p)],
        }

    def list_users(
        self,
        token: Optional[str] = None,
        query: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List users with optional search and filters.

        Security Enforcement:
        - Admins and Editors (with USER_MANAGE) receive full administrative view (notes, lockout status, passkeys).
        - General employees (Viewers) receive sanitized public employee directory (sensitive security metadata masked).
        """
        is_active: Optional[bool] = None
        if status == "active":
            is_active = True
        elif status == "suspended":
            is_active = False

        raw_users = self.rbac.get_user_list(query=query, role=role, is_active=is_active)
        session = self.rbac.get_session(token) if token else None
        has_manage = session and self.rbac.has_permission(session.role, Permission.USER_MANAGE)

        if has_manage:
            return raw_users

        # Sanitize sensitive fields for non-admin viewers to prevent excessive data exposure
        sanitized = []
        for u in raw_users:
            sanitized.append({
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "department": u["department"],
                "is_active": u["is_active"],
                "failed_attempts": 0,
                "locked_until": 0,
                "is_locked": False,
                "notes": "",
                "created_at": u.get("created_at", 0),
                "updated_at": u.get("updated_at", 0),
                "has_passkey": False,
            })
        return sanitized

    def get_user_stats(self, token: Optional[str] = None) -> Dict[str, int]:
        """Get statistics of users (total, active, suspended, admins, etc.)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("ユーザー統計の照会には管理者または編集長権限が必要です。")
        return self.rbac.get_user_stats()

    def create_user(
        self,
        username: str,
        display_name: str,
        role: str,
        department: str,
        password: str = "password123",
        notes: str = "",
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """[入社時] Add user account (Requires USER_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("ユーザーの追加には管理者または編集長権限が必要です。")

        user = self.rbac.create_user(
            username=username,
            display_name=display_name,
            role=role,
            department=department,
            password=password,
            notes=notes,
            operator_role=session.role,
        )
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="USER_CREATE",
            resource=username,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"新規社員アカウント登録: {display_name} ({username}, 役職: {role}, 部署: {department})",
        )
        return user

    def update_user(
        self,
        target_username: str,
        display_name: Optional[str] = None,
        role: Optional[str] = None,
        department: Optional[str] = None,
        notes: Optional[str] = None,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """[人事異動・昇格時] Update employee details and permissions (Requires USER_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("ユーザー情報の変更には管理者または編集長権限が必要です。")

        res = self.rbac.update_user(
            username=target_username,
            display_name=display_name,
            role=role,
            department=department,
            notes=notes,
            operator_role=session.role,
        )
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="USER_UPDATE",
            resource=target_username,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"社員情報・権限変更: '{target_username}' (氏名: {res['display_name']}, 役職: {res['role']}, 部署: {res['department']})",
        )
        return res

    def update_user_role(
        self,
        target_username: str,
        new_role: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Update role for employee (Requires USER_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("権限の変更・付与には管理者または編集長権限が必要です。")

        res = self.rbac.update_user_role(username=target_username, new_role=new_role, operator_role=session.role)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="USER_ROLE_UPDATE",
            resource=target_username,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"役職・権限変更: '{target_username}' -> '{new_role}'",
        )
        return res

    def toggle_user_status(
        self,
        target_username: str,
        is_active: bool,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """[休職/退社時/復職時] Suspend or reactivate user account (Requires USER_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("アカウントの停止・再開には管理者または編集長権限が必要です。")

        res = self.rbac.set_user_active(
            username=target_username,
            is_active=is_active,
            requesting_username=session.username,
            operator_role=session.role,
        )
        action_name = "USER_ACTIVATE" if is_active else "USER_SUSPEND"
        desc = "利用再開（有効化）" if is_active else "即時利用停止（アクセス遮断・セッション破棄）"
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action=action_name,
            resource=target_username,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"社員アカウント状態変更: '{target_username}' を{desc}しました。",
        )
        return res

    def reset_user_password(
        self,
        target_username: str,
        new_password: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """[パスワード再発行] Reset password for user (Requires USER_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("パスワードの再発行・リセットには管理者または編集長権限が必要です。")

        self.rbac.reset_password(username=target_username, new_password=new_password, operator_role=session.role)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="USER_PASSWORD_RESET",
            resource=target_username,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"社員パスワード再発行: '{target_username}' の初期パスワードをリセットしました。",
        )
        return {"status": "SUCCESS", "username": target_username}

    def unlock_user(
        self,
        target_username: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """[即時アンロック] Manually unlock a locked user account (Admin or Editor)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("アカウントのロック解除には管理者または編集長権限が必要です。")

        self.rbac.unlock_user(username=target_username, operator_role=session.role)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="USER_UNLOCK",
            resource=target_username,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"社員アカウント一時ロック即時解除: '{target_username}' のロックを解除しました。",
        )
        return {"status": "SUCCESS", "username": target_username, "message": f"ユーザー '{target_username}' のロックを解除しました。"}


    def delete_user(
        self,
        target_username: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """[退社時・完全抹消] Delete user account with strict safety guards (Requires USER_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.USER_MANAGE):
            raise PermissionError("ユーザーの削除には管理者または編集長権限が必要です。")

        req_user = session.username if session else None
        success = self.rbac.delete_user(target_username, requesting_username=req_user, operator_role=session.role)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="USER_DELETE",
            resource=target_username,
            status="SUCCESS" if success else "NOT_FOUND",
            ip_address=ip_address,
            details=f"社員アカウント完全抹消: '{target_username}'",
        )
        return {"status": "SUCCESS" if success else "NOT_FOUND", "username": target_username}

    # ---------------------------------------------------------
    # Multi-Thread Chat History (ChatGPT-like & Strict User Isolation)
    # ---------------------------------------------------------
    def list_chat_threads(self, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """List chat threads strictly for the authenticated current user."""
        if token:
            session = self.rbac.get_session(token)
            if not session:
                raise PermissionError("認証が必要です。ログインしてください。")
            user_id = session.username
        else:
            user_id = "default_user"
        return self.history.list_threads(user_id=user_id)

    def create_chat_thread(self, token: Optional[str] = None, title: str = "新しいチャット") -> Dict[str, Any]:
        """Create new conversation thread strictly for the current user."""
        if token:
            session = self.rbac.get_session(token)
            if not session:
                raise PermissionError("認証が必要です。ログインしてください。")
            user_id = session.username
        else:
            user_id = "default_user"
        thread = self.history.create_thread(user_id=user_id, title=title)
        return thread

    def get_chat_thread(self, thread_id: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get thread details only if owned by the current user."""
        if token:
            session = self.rbac.get_session(token)
            if not session:
                raise PermissionError("認証が必要です。ログインしてください。")
            user_id = session.username
        else:
            user_id = "default_user"
        return self.history.get_thread(thread_id=thread_id, user_id=user_id)

    def delete_chat_thread(self, thread_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        """Delete conversation thread owned by current user."""
        if token:
            session = self.rbac.get_session(token)
            if not session:
                raise PermissionError("認証が必要です。ログインしてください。")
            user_id = session.username
        else:
            user_id = "default_user"
        deleted = self.history.delete_thread(thread_id=thread_id, user_id=user_id)
        return {"status": "SUCCESS" if deleted else "NOT_FOUND", "thread_id": thread_id}

    def clear_chat_threads(self, token: Optional[str] = None, all_users: bool = False, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        """Clear all chat threads for current user, or for all users if admin requested."""
        if token:
            session = self.rbac.get_session(token)
            if not session:
                raise PermissionError("認証が必要です。ログインしてください。")
            if all_users:
                if not self.rbac.has_permission(session.role, Permission.SETTINGS_MANAGE):
                    raise PermissionError("全ユーザーのチャット履歴一括削除には管理者（Admin）権限が必要です。")
                deleted = self.history.clear_all_threads(user_id=None)
                target_desc = "システム全体の全チャット履歴"
            else:
                deleted = self.history.clear_all_threads(user_id=session.username)
                target_desc = f"ユーザー '{session.username}' の全チャット履歴"

            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="CHAT_CLEAR_ALL",
                status="SUCCESS",
                ip_address=ip_address,
                details=f"{target_desc}を完全消去しました（削除件数: {deleted}件）。",
            )
        else:
            deleted = self.history.clear_all_threads(user_id="default_user")

        return {"status": "SUCCESS", "deleted_count": deleted}

    def chat(
        self,
        question: str,
        thread_id: Optional[str] = None,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Ask chat assistant with RAG grounding and strictly isolated user thread."""
        if token:
            session = self.rbac.get_session(token)
            if not session or not self.rbac.check_access(token, Permission.CHAT):
                self.audit.record_audit(
                    username=session.username if session else "anonymous",
                    role=session.role if session else "none",
                    action="CHAT_QUERY",
                    status="FORBIDDEN",
                    ip_address=ip_address,
                    details=f"未許可のチャット要求: {question[:50]}",
                )
                raise PermissionError("チャット対話の権限がありません。ログインしてください。")
            user_id = session.username
            user_role = session.role
        else:
            session = None
            user_id = "default_user"
            user_role = "viewer"

        # Validate thread ownership: if specified thread is not owned by this user, isolate and create fresh thread
        if thread_id:
            existing = self.history.get_thread(thread_id=thread_id, user_id=user_id)
            if not existing:
                logger.warning(f"Thread '{thread_id}' is not owned by user '{user_id}'. Creating isolated thread.")
                thread_id = None

        if not thread_id:
            new_t = self.history.create_thread(user_id=user_id)
            thread_id = new_t["thread_id"]

        # Record user message in history
        self.history.add_message(thread_id=thread_id, user_id=user_id, role="user", content=question)


        # Execute RAG query
        try:
            res = self.pipeline.query(question=question, top_k=3, user_role=user_role)
            # Record assistant message in history
            self.history.add_message(
                thread_id=thread_id,
                user_id=user_id,
                role="assistant",
                content=res["answer"],
                citation_links=res.get("citation_links", []),
            )
            res["thread_id"] = thread_id

            # Record audit
            self.audit.record_audit(
                username=user_id,
                role=session.role if session else "anonymous",
                action="CHAT_QUERY",
                resource=thread_id,
                status="SUCCESS",
                ip_address=ip_address,
                details=f"質問: {question[:60]}... (回答文字数: {len(res['answer'])})",
            )
            return res

        except Exception as e:
            st = traceback.format_exc()
            self.audit.record_diagnostics(
                component="RAGPipeline",
                level="ERROR",
                message=f"Chat execution failed: {e}",
                stack_trace=st,
                context={"question": question, "thread_id": thread_id},
            )
            raise

    # ---------------------------------------------------------
    # Audit Trail & Diagnostics & Retention
    # ---------------------------------------------------------
    def query_audit_logs(
        self,
        token: Optional[str],
        username: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query user operation audit trail (Requires AUDIT_READ permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.AUDIT_READ):
            raise PermissionError("監査ログの閲覧には管理者（Admin）または監査役権限が必要です。")
        return self.audit.query_audit_logs(username=username, action=action, limit=limit)

    def query_diagnostics_logs(self, token: Optional[str], limit: int = 100) -> List[Dict[str, Any]]:
        """Query system diagnostics logs (Requires SETTINGS_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.SETTINGS_MANAGE):
            raise PermissionError("システム診断ログの閲覧には管理者（Admin）権限が必要です。")
        return self.audit.query_diagnostics_logs(limit=limit)

    def get_retention_days(self) -> int:
        """Get current log retention days."""
        return self.audit.get_retention_days()

    def set_retention_days(self, days: int, token: Optional[str] = None, ip_address: str = "127.0.0.1") -> int:
        """Set log retention days (Requires SETTINGS_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.SETTINGS_MANAGE):
            raise PermissionError("ログ保存期間の変更には管理者（Admin）権限が必要です。")

        saved = self.audit.set_retention_days(days)
        self.settings_manager.save_settings(retention_days=saved)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="RETENTION_UPDATE",
            status="SUCCESS",
            ip_address=ip_address,
            details=f"ログ保存期間を {saved} 日に変更しました（最大365日）。",
        )
        return saved

    # ---------------------------------------------------------
    # Settings & Model Management (Admin Only)
    # ---------------------------------------------------------
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Return available Gemini models (recommended + dynamic discovered)."""
        return self.settings_manager.get_available_models(api_key=self.gemini_api_key)

    def discover_gemini_models(self, api_key: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        """Query Google GenAI API directly to discover currently available models."""
        session = self.rbac.get_session(token)
        if token and not self.rbac.check_access(token, Permission.SETTINGS_MANAGE):
            raise PermissionError("モデル一覧の探索・更新には管理者（Admin）権限が必要です。")

        effective_key = api_key.strip() if api_key and api_key.strip() else self.gemini_api_key
        result = self.settings_manager.discover_live_models(api_key=effective_key)
        return result

    def get_settings(self, token: Optional[str]) -> Dict[str, Any]:
        """Get current settings with zero-trust key masking, model choices, rate limits, and retention info."""
        session = self.rbac.get_session(token)
        is_admin = session and self.rbac.has_permission(session.role, Permission.SETTINGS_MANAGE)
        persisted = self.settings_manager.load_settings()

        return {
            "active_provider": self.current_provider.value,
            "gemini_model": self.current_gemini_model,
            "has_gemini_key": bool(self.gemini_api_key),
            "masked_gemini_key": mask_api_key(self.gemini_api_key) if is_admin else "********",
            "can_manage_settings": bool(is_admin),
            "retention_days": self.get_retention_days(),
            "rate_limit_login": persisted.get("rate_limit_login", 20),
            "rate_limit_chat": persisted.get("rate_limit_chat", 60),
            "available_models": self.get_available_models(),
        }

    def set_provider(
        self,
        provider: str,
        gemini_api_key: Optional[str] = None,
        gemini_model: str = "gemini-3.5-flash-lite",
        rate_limit_login: Optional[int] = None,
        rate_limit_chat: Optional[int] = None,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Switch active inference provider and persist settings (Requires SETTINGS_MANAGE permission)."""
        session = self.rbac.get_session(token)
        if token and not self.rbac.check_access(token, Permission.SETTINGS_MANAGE):
            raise PermissionError("推論設定およびAPIキーの変更には管理者（Admin）権限が必要です。")

        self.current_provider = ProviderType(provider)
        if gemini_api_key and gemini_api_key.strip():
            self.gemini_api_key = gemini_api_key.strip()
        if gemini_model and gemini_model.strip():
            self.current_gemini_model = gemini_model.strip()

        # Persist settings across server restarts
        saved = self.settings_manager.save_settings(
            active_provider=self.current_provider.value,
            gemini_model=self.current_gemini_model,
            gemini_api_key=self.gemini_api_key,
            rate_limit_login=rate_limit_login,
            rate_limit_chat=rate_limit_chat,
        )

        self.engine.close()
        self.engine = InferenceEngine(
            provider=self.current_provider,
            backend=BackendType.GPU,
            mock_mode=True,
            gemini_api_key=self.gemini_api_key,
            gemini_model=self.current_gemini_model,
        )
        self.pipeline.engine = self.engine

        if session:
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="SETTINGS_UPDATE",
                status="SUCCESS",
                ip_address=ip_address,
                details=f"プロバイダ切替: {self.current_provider.value}, モデル: {self.current_gemini_model}",
            )

        return {
            "status": "SUCCESS",
            "active_provider": self.current_provider.value,
            "gemini_model": self.current_gemini_model,
            "has_gemini_key": bool(self.gemini_api_key),
            "masked_key": mask_api_key(self.gemini_api_key),
            "available_models": self.get_available_models(),
        }

    # ---------------------------------------------------------
    # Knowledge & Search Management
    # ---------------------------------------------------------
    def search_simulator(self, query: str, limit: int = 5, token: Optional[str] = None) -> Dict[str, Any]:
        """Search simulator without LLM generation."""
        if token and not self.rbac.check_access(token, Permission.KNOWLEDGE_READ):
            raise PermissionError("ナレッジ検索の権限がありません。")
        return self.cms.search_fast(query=query, limit=limit)

    def list_blocks(self, query: Optional[str] = None, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """List knowledge blocks."""
        if token and not self.rbac.check_access(token, Permission.KNOWLEDGE_READ):
            raise PermissionError("ナレッジ一覧閲覧の権限がありません。")
        return self.cms.list_blocks(query=query)

    def create_block(
        self,
        title: str,
        text: str,
        locator: str = "",
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Create new knowledge block (Requires KNOWLEDGE_WRITE permission)."""
        session = self.rbac.get_session(token)
        if token and not self.rbac.check_access(token, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("ナレッジ文面の追加には編集者（Editor/部門長）以上の権限が必要です。")

        block = self.cms.add_single_block(document_title=title, text=text, locator=locator)
        if session:
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="BLOCK_CREATE",
                resource=block["block_id"],
                status="SUCCESS",
                ip_address=ip_address,
                details=f"新規ナレッジ作成: 資料『{title}』 ({locator})",
            )
        return block

    def update_block(
        self,
        block_id: str,
        text: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Update existing knowledge block text (Requires KNOWLEDGE_WRITE permission)."""
        session = self.rbac.get_session(token)
        if token and not self.rbac.check_access(token, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("ナレッジ文面の更新には編集者（Editor/部門長）以上の権限が必要です。")

        updated = self.cms.update_block_text(block_id=block_id, new_text=text)
        if session:
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="BLOCK_UPDATE",
                resource=block_id,
                status="SUCCESS",
                ip_address=ip_address,
                details=f"ナレッジ文面更新: {block_id} (新文字数: {len(text)})",
            )
        return updated

    def delete_block(
        self,
        block_id: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Delete block (Requires KNOWLEDGE_WRITE permission)."""
        session = self.rbac.get_session(token)
        if token and not self.rbac.check_access(token, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("ナレッジ文面の削除には編集者（Editor/部門長）以上の権限が必要です。")

        deleted = self.cms.delete_block(block_id=block_id)
        if session:
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="BLOCK_DELETE",
                resource=block_id,
                status="SUCCESS" if deleted else "NOT_FOUND",
                ip_address=ip_address,
                details=f"ナレッジ文面削除: {block_id}",
            )
        return {"status": "SUCCESS" if deleted else "NOT_FOUND", "block_id": block_id}

    def upload_document(
        self,
        title: str,
        content: str,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Ingest document (Requires KNOWLEDGE_WRITE permission)."""
        session = self.rbac.get_session(token)
        if token and not self.rbac.check_access(token, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("ドキュメントの一括登録には編集者（Editor/部門長）以上の権限が必要です。")

        blocks = self.cms.ingest_document(title=title, text_content=content)
        if session:
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="DOCUMENT_UPLOAD",
                resource=title,
                status="SUCCESS",
                ip_address=ip_address,
                details=f"資料一括登録: 『{title}』 ({len(blocks)} ブロック生成)",
            )
        return {"status": "SUCCESS", "title": title, "blocks_created": len(blocks)}

    def upload_document_file(
        self,
        filename: str,
        file_bytes: bytes,
        token: Optional[str] = None,
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Ingest any binary/text file (PDF, Word, Excel, PPTX, TXT) into knowledge base."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("ファイルの一括登録には編集者（Editor）以上の権限が必要です。")

        result = self.cms.ingest_file(filename=filename, file_bytes=file_bytes)

        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="FILE_INGEST",
            resource=filename,
            status="SUCCESS",
            ip_address=ip_address,
            details=f"マルチ形式取込: '{filename}' ({result['file_type']}, {result['total_characters']}文字, {result['indexed_blocks']}ブロック生成)",
        )
        return result

    def logout(self, token: Optional[str] = None, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        """Destroy user session upon logout."""
        session = self.rbac.get_session(token)
        if session:
            self.rbac._sessions.pop(token, None)
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="LOGOUT",
                status="SUCCESS",
                ip_address=ip_address,
                details="ユーザーがログアウトしました。",
            )
        return {"status": "SUCCESS", "message": "正常にログアウトしました。"}

    def handle_mcp(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP JSON-RPC."""
        return self.mcp.handle_request(request_data)

    # ---------------------------------------------------------
    # Google Workspace SSO & Google Drive Synchronization
    # ---------------------------------------------------------
    def handle_google_login(self, id_token: str, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        """Process Google Workspace OpenID Connect login and JIT provisioning."""
        try:
            res = self.google_auth.authenticate_or_provision(id_token)
            user_info = res["user"]
            self.audit.record_audit(
                username=user_info["username"],
                role=user_info["role"],
                action="GOOGLE_SSO_LOGIN",
                status="SUCCESS",
                ip_address=ip_address,
                details=f"Google SSOログイン成功 (新規登録: {res['is_new_user']}, Email: {user_info['email']})",
            )
            return res
        except (DomainRestrictionError, InvalidTokenError, UserSuspendedError) as e:
            self.audit.record_audit(
                username="google_user",
                role="none",
                action="GOOGLE_SSO_LOGIN",
                status="FAILED",
                ip_address=ip_address,
                details=f"Google SSOログイン拒絶: {e}",
            )
            raise

    def handle_get_drive_status(self, token: str) -> Dict[str, Any]:
        """Retrieve Google Drive synchronization status, timestamps, and catalog count."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.check_access(token, Permission.CHAT):
            raise PermissionError("認証が必要です。ログインしてください。")
        return self.drive_sync.get_sync_status()

    def handle_drive_sync(
        self,
        token: str,
        ip_address: str = "127.0.0.1",
        simulated_changes: Optional[List[Dict[str, Any]]] = None,
        new_page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute incremental differential sync using Drive Changes API."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("Google Driveの同期実行には編集者（Editor）以上の権限が必要です。")

        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="DRIVE_SYNC_START",
            status="SUCCESS",
            ip_address=ip_address,
            details="Google Drive増分同期（Changes API）を開始しました。",
        )

        try:
            result = self.drive_sync.sync_changes(
                simulated_changes=simulated_changes,
                new_page_token=new_page_token,
            )
            self.audit.record_audit(
                username=session.username,
                role=session.role,
                action="DRIVE_SYNC_COMPLETE",
                status="SUCCESS",
                ip_address=ip_address,
                details=f"Drive同期完了: 追加={result['added']}, 更新={result['updated']}, 削除={result['purged']}, スキップ={result['skipped_etag']}, エラー={len(result['errors'])}",
            )
            return result
        except Exception as e:
            self.audit.record_diagnostics(
                category="DRIVE_SYNC",
                severity="ERROR",
                message=f"Drive増分同期中にエラーが発生しました: {e}",
                stacktrace=traceback.format_exc(),
                context={"user": session.username, "ip": ip_address},
            )
            raise

    def handle_get_drive_folders(self, token: str) -> List[Dict[str, Any]]:
        """List configured Google Drive target folders."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("同期フォルダの照会にはナレッジ編集者（Editor）以上の権限が必要です。")
        return self.drive_sync.get_target_folders()

    def handle_set_drive_folders(
        self,
        token: str,
        folders: List[Dict[str, Any]],
        ip_address: str = "127.0.0.1",
    ) -> Dict[str, Any]:
        """Configure whitelisted Google Drive target folders and required roles."""
        session = self.rbac.get_session(token)
        if not session or not self.rbac.has_permission(session.role, Permission.KNOWLEDGE_WRITE):
            raise PermissionError("同期フォルダの設定にはナレッジ編集者（Editor）以上の権限が必要です。")

        self.drive_sync.set_target_folders(folders)
        self.audit.record_audit(
            username=session.username,
            role=session.role,
            action="DRIVE_FOLDER_CONFIG",
            status="SUCCESS",
            ip_address=ip_address,
            details=f"同期対象フォルダを設定しました（{len(folders)}件）。",
        )
        return {"status": "SUCCESS", "configured_count": len(folders)}

