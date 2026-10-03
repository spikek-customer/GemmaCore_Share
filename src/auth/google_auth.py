"""Google Workspace OpenID Connect (OIDC) Single Sign-On and JIT Provisioning Module.

Supports:
- Secure Google ID Token verification (JWT signature, aud, iss, exp, hd)
- Strict Corporate Domain Restriction (Hosted Domain / hd parameter enforcement)
- Just-In-Time (JIT) User Provisioning with default Viewer (Standard Employee) role
- Hybrid integration with existing SQLite-backed RBACManager
- Graceful handling of suspended accounts and active session creation
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional

from src.auth.rbac import RBACManager, RoleType, UserSuspendedError

logger = logging.getLogger(__name__)


class DomainRestrictionError(PermissionError):
    """Raised when authentication fails due to non-whitelisted domain."""
    pass


class InvalidTokenError(ValueError):
    """Raised when the ID token is malformed, expired, or invalid."""
    pass


class GoogleWorkspaceAuthService:
    """Enterprise Single Sign-On handler for Google Workspace accounts."""

    def __init__(
        self,
        rbac_manager: RBACManager,
        allowed_domain: Optional[str] = None,
        client_id: Optional[str] = None,
        allow_mock: bool = False,
    ) -> None:
        self.rbac_manager = rbac_manager
        self.allowed_domain = allowed_domain.strip().lower() if allowed_domain else None
        self.client_id = client_id.strip() if client_id else None
        self.allow_mock = allow_mock or os.environ.get("GOOGLE_AUTH_MOCK", "").lower() in ("true", "1")

    def verify_id_token(self, id_token_str: str) -> Dict[str, Any]:
        """Verify and decode a Google ID token.

        Enforces cryptographic RSA signature verification against Google's public JWKS.
        Fallback to mock decoding is strictly disabled in production unless allow_mock is explicitly enabled.
        """
        if not id_token_str or not isinstance(id_token_str, str):
            raise InvalidTokenError("IDトークンが空または無効です。")

        if not self.allow_mock:
            try:
                from google.auth.transport import requests as google_requests
                from google.oauth2 import id_token as google_id_token
                req = google_requests.Request()
                payload = google_id_token.verify_oauth2_token(id_token_str, req, audience=self.client_id)
            except Exception as e:
                logger.warning(f"Google ID token signature verification failed: {e}")
                raise InvalidTokenError(f"Google IDトークンの電子署名検証に失敗しました: {e}")
        else:
            payload = self._parse_jwt_payload(id_token_str)

        # 1. Expiration check
        exp = payload.get("exp")
        if exp is not None:
            now = time.time()
            if now > exp:
                raise InvalidTokenError("IDトークンの有効期限が切れています。再度ログインしてください。")

        # 2. Audience check (if client_id is set)
        aud = payload.get("aud")
        if self.client_id and aud and aud != self.client_id:
            raise InvalidTokenError(f"トークンのクライアントID ({aud}) が一致しません。")

        # 3. Corporate domain check
        email = payload.get("email", "").strip().lower()
        hd = payload.get("hd", "").strip().lower()

        if self.allowed_domain:
            email_domain = email.split("@")[-1] if "@" in email else ""
            if hd != self.allowed_domain and email_domain != self.allowed_domain:
                logger.warning(
                    f"Blocked login attempt from non-corporate account: email='{email}', hd='{hd}', allowed='{self.allowed_domain}'"
                )
                raise DomainRestrictionError(
                    f"社外アカウント（@{email_domain or 'unknown'}）からのアクセスは拒絶されました。社内Workspaceドメイン（@{self.allowed_domain}）のアカウントをご利用ください。"
                )

        return payload

    def authenticate_or_provision(self, id_token_str: str) -> Dict[str, Any]:
        """Authenticate existing employee or JIT provision a new standard corporate user.

        Initial role is strictly VIEWER (Standard employee with read/ask permissions only),
        preventing unauthorized privilege escalation upon initial login.
        """
        payload = self.verify_id_token(id_token_str)

        email = payload.get("email", "").strip().lower()
        sub = payload.get("sub", "").strip()
        display_name = payload.get("name", "").strip() or email.split("@")[0]

        if not email and not sub:
            raise InvalidTokenError("トークンにメールアドレスまたはSubject IDが含まれていません。")

        # Determine target username
        # Prefer the local part of email (e.g. 'sato' for 'sato@company.com')
        base_username = email.split("@")[0] if "@" in email else f"user_{sub[:8]}"
        candidate_username = base_username

        # Check if user already exists
        existing_user = self.rbac_manager.get_user(candidate_username)
        is_new_user = False

        if not existing_user:
            # Check by full email as username
            existing_user = self.rbac_manager.get_user(email)
            if existing_user:
                candidate_username = email

        if existing_user:
            # Existing corporate account: verify active status
            if not existing_user.get("is_active", True):
                logger.warning(f"Google SSO attempt for suspended account: {candidate_username}")
                raise UserSuspendedError(
                    "このアカウントは現在利用停止（休職・退職）されています。システム管理者にお問い合わせください。"
                )

            # Issue session
            session = self.rbac_manager.create_session_for_user(candidate_username)
            logger.info(f"Google SSO login successful for existing user: {candidate_username} (role: {session.role})")
        else:
            # JIT (Just-In-Time) Provisioning for new corporate user
            is_new_user = True
            initial_role = RoleType.VIEWER.value  # 一般ユーザー権限（閲覧・質問のみ）
            initial_dept = "一般部門"
            initial_notes = f"Google Workspace SSO初回ログイン自動作成 (Email: {email}, Sub: {sub})"
            random_pw = secrets.token_urlsafe(32)

            # If base_username is taken by someone else with different email, fallback to full email
            if self.rbac_manager.get_user(candidate_username):
                candidate_username = email

            self.rbac_manager.create_user(
                username=candidate_username,
                display_name=display_name,
                role=initial_role,
                department=initial_dept,
                password=random_pw,
                notes=initial_notes,
            )

            session = self.rbac_manager.create_session_for_user(candidate_username)
            logger.info(
                f"JIT Provisioned new employee via Google SSO: '{candidate_username}', display_name='{display_name}', role='{initial_role}'"
            )

        return {
            "token": session.session_id,
            "user": {
                "username": session.username,
                "display_name": session.display_name,
                "role": session.role,
                "department": session.department,
                "email": email,
            },
            "is_new_user": is_new_user,
        }

    def _parse_jwt_payload(self, jwt_str: str) -> Dict[str, Any]:
        """Parse JWT token payload safely with Base64 URL decoding."""
        parts = jwt_str.split(".")
        if len(parts) < 2:
            raise InvalidTokenError("JWT形式が不正です（セグメント不足）。")

        payload_b64 = parts[1]
        # Pad base64 if needed
        padding = len(payload_b64) % 4
        if padding > 0:
            payload_b64 += "=" * (4 - padding)

        try:
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded_bytes.decode("utf-8"))
        except Exception as e:
            raise InvalidTokenError(f"トークンのデコードに失敗しました: {e}")
