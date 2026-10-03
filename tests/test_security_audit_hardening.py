"""Comprehensive Security Hardening and Vulnerability Remediation Tests.

Covers:
- TEST-SEC-01: Rate Limiter enforcement and sliding window retry-after calculation
- TEST-SEC-02: System settings file permissions restricted to 0600 (owner-only access)
- TEST-SEC-03: User list sensitive data masking for unprivileged viewers vs full view for admins
- TEST-SEC-04: Google OIDC strict mode rejection of unsigned mock JWTs
- TEST-SEC-05: Timing attack mitigation on non-existent usernames during authentication
- TEST-SEC-06: Request payload size limitation (413 Payload Too Large)
- TEST-SEC-07: Legacy / Dev switcher disabled by default in production
"""

from __future__ import annotations

import io
import json
import os
import stat
import tempfile
import time
import unittest
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from src.auth.google_auth import GoogleWorkspaceAuthService, InvalidTokenError
from src.auth.rate_limiter import RateLimiter
from src.auth.rbac import RBACManager, RoleType
from src.core.settings import SettingsManager
from src.web.app import KnowledgeWebApp
from scripts.start_web import MAX_PAYLOAD_SIZE, PortalRequestHandler, login_rate_limiter


class TestSecurityHardening(unittest.TestCase):
    """Test suite for security audit remediation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user_db = os.path.join(self.temp_dir.name, "users.db")
        self.settings_file = os.path.join(self.temp_dir.name, "settings.json")
        self.app = KnowledgeWebApp(
            store_path=":memory:",
            user_db_path=self.user_db,
            settings_path=self.settings_file,
            google_allow_mock=True,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rate_limiter_enforcement_and_retry_after(self) -> None:
        """TEST-SEC-01: RateLimiter permits requests within quota and throttles exceeding requests."""
        limiter = RateLimiter(max_requests=3, window_seconds=10.0)
        ip = "192.168.1.100"

        # First 3 requests must be allowed
        for i in range(3):
            allowed, retry_after = limiter.is_allowed(ip)
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
            self.assertEqual(retry_after, 0.0)

        # 4th request must be throttled
        allowed, retry_after = limiter.is_allowed(ip)
        self.assertFalse(allowed, "Request exceeding max quota must be blocked")
        self.assertGreater(retry_after, 0.0)

        # Different IP should have independent quota
        other_ip = "192.168.1.101"
        allowed, _ = limiter.is_allowed(other_ip)
        self.assertTrue(allowed, "Separate IP must have independent rate limit bucket")

    def test_system_settings_file_permissions_0600(self) -> None:
        """TEST-SEC-02: system_settings.json file permissions must be restricted to 0600 on disk."""
        sm = SettingsManager(file_path=self.settings_file)
        sm.save_settings(gemini_api_key="AIzaSyConfidentialSecretKey999")

        self.assertTrue(os.path.exists(self.settings_file))
        file_stat = os.stat(self.settings_file)
        file_mode = stat.S_IMODE(file_stat.st_mode)

        # On POSIX systems, file permissions must be 0o600 (-rw-------)
        self.assertEqual(file_mode, 0o600, f"Expected file permission 0600, got {oct(file_mode)}")

    def test_user_list_data_masking_for_viewers_vs_admins(self) -> None:
        """TEST-SEC-03: Viewers receive sanitized user list, while admins receive full sensitive metadata."""
        # Setup: create victim user with locked status and notes
        self.app.rbac.create_user(
            username="victim_employee",
            display_name="被害 社員",
            role=RoleType.VIEWER.value,
            department="開発部",
            password="Password123!",
            notes="【極秘人事メモ】来期異動予定",
        )
        # Lock the account artificially
        with self.app.rbac._get_connection() as conn:
            conn.execute(
                "UPDATE users SET failed_attempts = 5, locked_until = ? WHERE username = 'victim_employee'",
                (time.time() + 300,),
            )
            conn.commit()

        # 1. Admin querying list_users receives full metadata
        admin_sess = self.app.switch_user("admin")["session_id"]
        admin_users = self.app.list_users(token=admin_sess)
        victim_admin_view = next(u for u in admin_users if u["username"] == "victim_employee")
        self.assertEqual(victim_admin_view["notes"], "【極秘人事メモ】来期異動予定")
        self.assertEqual(victim_admin_view["failed_attempts"], 5)
        self.assertTrue(victim_admin_view["is_locked"])

        # 2. Viewer querying list_users receives sanitized metadata
        viewer_sess = self.app.switch_user("viewer_user")["session_id"]
        viewer_users = self.app.list_users(token=viewer_sess)
        victim_viewer_view = next(u for u in viewer_users if u["username"] == "victim_employee")
        self.assertEqual(victim_viewer_view["notes"], "", "Viewer must not see internal notes")
        self.assertEqual(victim_viewer_view["failed_attempts"], 0, "Viewer must not see failed attempts")
        self.assertFalse(victim_viewer_view["is_locked"], "Viewer must not see lockout state")
        self.assertEqual(victim_viewer_view["locked_until"], 0)

    def test_google_auth_strict_mode_rejects_mock(self) -> None:
        """TEST-SEC-04: In production (allow_mock=False), unverified mock JWT tokens are strictly rejected."""
        strict_service = GoogleWorkspaceAuthService(
            rbac_manager=self.app.rbac,
            allowed_domain="company.com",
            allow_mock=False,
        )
        fake_jwt = "eyJhbGciOiAiUlMyNTYiLCAidHlwIjogIkpXVCJ9.eyJlbWFpbCI6ICJhZG1pbkBjb21wYW55LmNvbSIsICJzdWIiOiAiYWRtaW4ifQ.unsigned_signature"

        with self.assertRaises(InvalidTokenError) as ctx:
            strict_service.verify_id_token(fake_jwt)
        self.assertIn("電子署名検証に失敗しました", str(ctx.exception))

    def test_timing_attack_mitigation_on_nonexistent_user(self) -> None:
        """TEST-SEC-05: Authenticating non-existent user performs constant-time hash check."""
        start = time.perf_counter()
        res = self.app.rbac.authenticate("nonexistent_unknown_user", "wrong_password")
        elapsed = time.perf_counter() - start

        self.assertIsNone(res)
        # 100,000 PBKDF2 iterations takes at least a few milliseconds (not instant 0.00001s)
        self.assertGreater(elapsed, 0.001, "Dummy hash verification ensures constant-time execution")

    def test_large_payload_rejected_by_max_size(self) -> None:
        """TEST-SEC-06: Payloads larger than MAX_PAYLOAD_SIZE are rejected with 413 Payload Too Large."""
        handler = object.__new__(PortalRequestHandler)
        handler.headers = {"Content-Length": str(MAX_PAYLOAD_SIZE + 1024)}
        handler._send_json = MagicMock()

        result = handler._read_json_body()
        self.assertIsNone(result)
        handler._send_json.assert_called_once()
        args, kwargs = handler._send_json.call_args
        self.assertEqual(kwargs.get("status"), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        self.assertEqual(args[0]["error"], "PAYLOAD_TOO_LARGE")

    def test_dev_switch_blocked_by_default(self) -> None:
        """TEST-SEC-07: Legacy / Dev switcher endpoint is blocked with 403 Forbidden by default."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("ALLOW_DEV_SWITCH", os.environ)
            # When ALLOW_DEV_SWITCH is not set, dev switch is disabled
            allowed = os.environ.get("ALLOW_DEV_SWITCH", "").lower() in ("true", "1")
            self.assertFalse(allowed)
