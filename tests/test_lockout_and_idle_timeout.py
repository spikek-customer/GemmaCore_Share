"""Test Suite for Account Lockout (Brute-Force Protection) and Session Idle Timeout.

Validates:
- TEST-049: 5 consecutive failed login attempts trigger 5-minute temporary account lockout
- TEST-050: Automatic unlock after 5-minute timeout expiration and counter reset on success
- TEST-051: Manual immediate unlock by Admin and Editor with delegated RBAC enforcement
- TEST-052: 30-minute session idle timeout and activity touch refreshing
"""

import time
import unittest
from unittest.mock import patch

from src.auth.rbac import (
    AccountLockedError,
    RBACManager,
    RoleType,
    UserSession,
)
from src.web.app import KnowledgeWebApp


class TestLockoutAndIdleTimeout(unittest.TestCase):
    """Test suite for brute-force protection (Account Lockout) and idle timeout."""

    def setUp(self) -> None:
        """Initialize in-memory RBAC and WebApp instances for clean isolation."""
        self.rbac = RBACManager(db_path=":memory:")
        self.app = KnowledgeWebApp()
        self.app.rbac = self.rbac

        # Create operator sessions
        self.admin_session = self.rbac.authenticate_or_switch("admin").session_id
        self.editor_session = self.rbac.authenticate_or_switch("editor_user").session_id

        # Create a dedicated target user for lockout testing
        self.rbac.create_user(
            username="target_victim",
            display_name="検証 対象社員",
            role=RoleType.VIEWER.value,
            department="総務部",
            password="CorrectPassword123!",
        )

    def test_test_049_account_lockout_after_five_failed_attempts(self) -> None:
        """TEST-049: 5 consecutive failed login attempts lock account for 5 minutes and block logins."""
        # Attempts 1 to 4: Failures, but not yet locked
        for i in range(1, 5):
            res = self.rbac.authenticate("target_victim", "WrongPassword!")
            self.assertIsNone(res, f"Attempt {i} should return None on bad credentials")
            user_info = self.rbac.get_user("target_victim")
            self.assertFalse(user_info["is_locked"], f"Account should not be locked at attempt {i}")
            self.assertEqual(user_info["failed_attempts"], i)

        # Attempt 5: 5th failure must trigger AccountLockedError and set 5-minute lockout
        with self.assertRaises(AccountLockedError) as ctx:
            self.rbac.authenticate("target_victim", "WrongPassword!")
        self.assertIn("一時ロック", str(ctx.exception))

        # Verify user state in DB
        locked_user = self.rbac.get_user("target_victim")
        self.assertTrue(locked_user["is_locked"])
        self.assertEqual(locked_user["failed_attempts"], 5)
        self.assertGreater(locked_user["locked_until"], time.time())

        # Attempt during lockout: Even with the CORRECT password, login must be blocked immediately
        with self.assertRaises(AccountLockedError) as ctx_locked:
            self.rbac.authenticate("target_victim", "CorrectPassword123!")
        self.assertIn("アカウントは一時的にロックされています", str(ctx_locked.exception))

        # Test WebApp controller layer (login endpoint raises PermissionError with audit trail)
        with self.assertRaises(PermissionError) as app_ctx:
            self.app.login("target_victim", "CorrectPassword123!")
        self.assertIn("一時的にロックされています", str(app_ctx.exception))

        # Audit trail must record LOGIN_LOCKED
        audit_logs = self.app.audit.query_audit_logs(limit=10)
        locked_events = [l for l in audit_logs if l["action"] == "LOGIN_LOCKED" and l["username"] == "target_victim"]
        self.assertGreaterEqual(len(locked_events), 1)
        self.assertEqual(locked_events[0]["status"], "BLOCKED")

    def test_test_050_automatic_unlock_after_timeout_expiration(self) -> None:
        """TEST-050: After 5 minutes, account automatically unlocks and resets failure counters upon correct login."""
        # 1. Trigger lockout (5 failures)
        for _ in range(5):
            try:
                self.rbac.authenticate("target_victim", "WrongPassword!")
            except AccountLockedError:
                pass

        user = self.rbac.get_user("target_victim")
        self.assertTrue(user["is_locked"])

        # 2. Simulate time advance past 5 minutes (301 seconds into the future)
        future_time = time.time() + 301.0
        with patch("time.time", return_value=future_time):
            # Check user status in future time
            fut_user = self.rbac.get_user("target_victim")
            self.assertFalse(fut_user["is_locked"])

            # 3. Login with correct password must now succeed
            session = self.rbac.authenticate("target_victim", "CorrectPassword123!")
            self.assertIsNotNone(session)
            self.assertEqual(session.username, "target_victim")

            # 4. Failure counter and lock deadline must be fully reset in DB
            reset_user = self.rbac.get_user("target_victim")
            self.assertEqual(reset_user["failed_attempts"], 0)
            self.assertEqual(reset_user["locked_until"], 0)
            self.assertFalse(reset_user["is_locked"])

    def test_test_051_manual_unlock_by_admin_and_editor(self) -> None:
        """TEST-051: Admin and Editor can manually unlock locked users; Editor cannot unlock Admin."""
        # 1. Lock the target user
        for _ in range(5):
            try:
                self.rbac.authenticate("target_victim", "WrongPassword!")
            except AccountLockedError:
                pass
        self.assertTrue(self.rbac.get_user("target_victim")["is_locked"])

        # 2. Admin unlocks the user via WebApp API
        admin_unlock_res = self.app.unlock_user("target_victim", token=self.admin_session)
        self.assertEqual(admin_unlock_res["status"], "SUCCESS")
        self.assertFalse(self.rbac.get_user("target_victim")["is_locked"])

        # Verify immediate login succeeds
        s1 = self.rbac.authenticate("target_victim", "CorrectPassword123!")
        self.assertIsNotNone(s1)

        # 3. Lock the target user again
        for _ in range(5):
            try:
                self.rbac.authenticate("target_victim", "WrongPassword!")
            except AccountLockedError:
                pass
        self.assertTrue(self.rbac.get_user("target_victim")["is_locked"])

        # 4. Editor unlocks the user (Department member) via WebApp API
        editor_unlock_res = self.app.unlock_user("target_victim", token=self.editor_session)
        self.assertEqual(editor_unlock_res["status"], "SUCCESS")
        self.assertFalse(self.rbac.get_user("target_victim")["is_locked"])

        # 5. Upper-tier Immunity Test: Lock the Admin account
        for _ in range(5):
            try:
                self.rbac.authenticate("admin", "WrongPass123!")
            except AccountLockedError:
                pass
        self.assertTrue(self.rbac.get_user("admin")["is_locked"])

        # Editor attempts to unlock Admin account -> Must be rejected with PermissionError (403)
        with self.assertRaises(PermissionError) as guard_ctx:
            self.app.unlock_user("admin", token=self.editor_session)
        self.assertIn("管理者（Admin）アカウントを操作することはできません", str(guard_ctx.exception))

        # Admin itself/system admin can unlock Admin account
        self.rbac.unlock_user("admin", operator_role=RoleType.ADMIN.value)
        self.assertFalse(self.rbac.get_user("admin")["is_locked"])

    def test_test_052_session_idle_timeout_and_activity_touch(self) -> None:
        """TEST-052: Session expires after 30 minutes of inactivity; activity touches refresh the idle timer."""
        # 1. Create a fresh session
        session = self.rbac.authenticate("target_victim", "CorrectPassword123!")
        self.assertIsNotNone(session)
        token = session.session_id

        # Initially active
        self.assertFalse(session.is_expired())

        # 2. Activity touch at 10 minutes (600s) keeps session alive
        now = time.time()
        session.last_activity_at = now - 600
        # Call get_session which triggers touch()
        active_session = self.rbac.get_session(token)
        self.assertIsNotNone(active_session)
        self.assertGreaterEqual(active_session.last_activity_at, now - 5)
        self.assertFalse(active_session.is_expired())

        # 3. Simulate 31 minutes of inactivity (1860s since last touch)
        session.last_activity_at = time.time() - 1860
        self.assertTrue(session.is_expired())

        # get_session must evict expired session and return None
        expired_res = self.rbac.get_session(token)
        self.assertIsNone(expired_res, "Session must be None and purged after 30 minutes idle timeout")

        # 4. Absolute 24h lifetime: Even if touched recently, created_at + 86400 expires session
        session_long = self.rbac.authenticate("target_victim", "CorrectPassword123!")
        session_long.expires_at = time.time() - 10  # 24h passed
        session_long.touch()  # Just touched
        self.assertTrue(session_long.is_expired(), "Session must expire after 24h absolute limit regardless of touch")


if __name__ == "__main__":
    unittest.main()
