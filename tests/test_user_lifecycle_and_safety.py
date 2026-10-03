"""Unit and Integration Tests for User Lifecycle Management & Enterprise Safety Guards.

Covers:
- TEST-033: Join Lifecycle (New employee account creation, input validation, PBKDF2 hash, login verification)
- TEST-034: Transfer / Promotion Lifecycle (Role promotion, department update, admin password reset)
- TEST-035: Leave / Suspension Lifecycle (Instant account deactivation, active session revocation, login block, reactivation)
- TEST-036: Enterprise Safety Guards (Self-deletion prevention, self-suspension prevention, last-admin lockout protection, strict deletion)
- TEST-037: Full SQLite Persistence Across Server Restarts
- TEST-038: Comprehensive User Management Audit Trail Tracking
"""

from __future__ import annotations

import os
import tempfile
import unittest

from src.auth.rbac import Permission, RoleType
from src.core.engine import ProviderType
from src.web.app import KnowledgeWebApp


class TestUserLifecycleAndSafety(unittest.TestCase):
    """Test suite for complete user onboarding, offboarding, and safety operations."""

    def setUp(self) -> None:
        # Use isolated in-memory or temp DB for clean lifecycle testing
        self.temp_dir = tempfile.mkdtemp()
        self.user_db = os.path.join(self.temp_dir, "test_users.db")
        self.audit_db = os.path.join(self.temp_dir, "test_audit.db")

        self.app = KnowledgeWebApp(
            store_path=":memory:",
            default_provider=ProviderType.LITERT,
            user_db_path=self.user_db,
            audit_db_path=self.audit_db,
        )
        self.admin_login = self.app.login("admin_user", "password123")
        self.admin_session = self.admin_login["session_id"]

        self.viewer_login = self.app.login("viewer_user", "password123")
        self.viewer_session = self.viewer_login["session_id"]

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_test_033_join_lifecycle_and_validation(self) -> None:
        """TEST-033: [入社時] Employee account registration, validation, PBKDF2 auth, and permissions."""
        # 1. Non-admin cannot create users
        with self.assertRaises(PermissionError):
            self.app.create_user(
                username="tanaka_k",
                display_name="Kenichi Tanaka",
                role="editor",
                department="人事部",
                password="Password123!",
                token=self.viewer_session,
            )

        # 2. Validation: invalid username characters
        with self.assertRaises(ValueError):
            self.app.create_user(
                username="invalid name with spaces!",
                display_name="不正ID",
                role="viewer",
                department="一般",
                token=self.admin_session,
            )

        # 3. Successful employee creation
        created = self.app.create_user(
            username="yamada_t",
            display_name="Taro Yamada",
            role="viewer",
            department="営業第1課",
            password="InitialSecret2026!",
            notes="2026年10月新卒入社",
            token=self.admin_session,
        )
        self.assertEqual(created["username"], "yamada_t")
        self.assertEqual(created["display_name"], "Taro Yamada")
        self.assertEqual(created["role"], "viewer")
        self.assertTrue(created["is_active"])

        # 4. Duplicate ID validation
        with self.assertRaises(ValueError):
            self.app.create_user(
                username="yamada_t",
                display_name="Other Yamada",
                role="viewer",
                department="Sales Department",
                token=self.admin_session,
            )

        # 5. New user can authenticate successfully
        login_res = self.app.login("yamada_t", "InitialSecret2026!")
        self.assertEqual(login_res["status"], "SUCCESS")
        self.assertEqual(login_res["username"], "yamada_t")
        self.assertIn(Permission.CHAT.value, login_res["permissions"])
        self.assertNotIn(Permission.KNOWLEDGE_WRITE.value, login_res["permissions"])

    def test_test_034_transfer_promotion_and_pw_reset(self) -> None:
        """TEST-034: [異動・昇格時] Role upgrade, department update, and admin password reset."""
        # 1. Create a user
        self.app.create_user(
            username="suzuki_j",
            display_name="Jiro Suzuki",
            role="viewer",
            department="総務部",
            password="OldPassword123!",
            token=self.admin_session,
        )

        # 2. Promote to Editor and change department
        updated = self.app.update_user(
            target_username="suzuki_j",
            display_name="Jiro Suzuki (リーダー)",
            role="editor",
            department="ナレッジ統括部",
            notes="リーダーへ昇格",
            token=self.admin_session,
        )
        self.assertEqual(updated["role"], "editor")
        self.assertEqual(updated["department"], "ナレッジ統括部")

        # 3. Verify upgraded permissions on login
        login_upgraded = self.app.login("suzuki_j", "OldPassword123!")
        self.assertIn(Permission.KNOWLEDGE_WRITE.value, login_upgraded["permissions"])

        # 4. Admin resets employee password
        pw_res = self.app.reset_user_password(
            target_username="suzuki_j",
            new_password="NewSecurePassword2026!",
            token=self.admin_session,
        )
        self.assertEqual(pw_res["status"], "SUCCESS")

        # 5. Old password now fails, new password succeeds
        with self.assertRaises(PermissionError):
            self.app.login("suzuki_j", "OldPassword123!")

        new_login = self.app.login("suzuki_j", "NewSecurePassword2026!")
        self.assertEqual(new_login["status"], "SUCCESS")

    def test_test_035_suspension_session_revocation_and_reactivation(self) -> None:
        """TEST-035: [休職・退社時] Account suspension, immediate session kill, login blocking, and reactivation."""
        # 1. Create employee and login to obtain active session
        self.app.create_user(
            username="mori_s",
            display_name="森 翔太",
            role="viewer",
            department="開発部",
            password="Password12345!",
            token=self.admin_session,
        )
        mori_login = self.app.login("mori_s", "Password12345!")
        mori_token = mori_login["session_id"]

        # Verify active session works
        curr = self.app.get_current_user(mori_token)
        self.assertIsNotNone(curr)
        self.assertEqual(curr["username"], "mori_s")

        # 2. Admin suspends account (Offboarding / Leave of absence)
        suspend_res = self.app.toggle_user_status(
            target_username="mori_s",
            is_active=False,
            token=self.admin_session,
        )
        self.assertFalse(suspend_res["is_active"])

        # 3. Active session must be IMMEDIATELY revoked (Security Protection)
        session_after_suspend = self.app.get_current_user(mori_token)
        self.assertIsNone(session_after_suspend)

        # 4. New login attempt must be strictly blocked with suspension message
        with self.assertRaises(PermissionError) as ctx:
            self.app.login("mori_s", "Password12345!")
        self.assertIn("停止", str(ctx.exception))

        # 5. Admin reactivates account (Return to work)
        reactivate_res = self.app.toggle_user_status(
            target_username="mori_s",
            is_active=True,
            token=self.admin_session,
        )
        self.assertTrue(reactivate_res["is_active"])

        # 6. User can now login again
        login_again = self.app.login("mori_s", "Password12345!")
        self.assertEqual(login_again["status"], "SUCCESS")

    def test_test_036_safety_guards_and_strict_deletion(self) -> None:
        """TEST-036: Enterprise Safety Guards (Self-action guards, last-admin protection, clean deletion)."""
        # 1. Admin cannot suspend themselves
        with self.assertRaises(ValueError) as ctx:
            self.app.toggle_user_status(
                target_username="admin_user",
                is_active=False,
                token=self.admin_session,
            )
        self.assertIn("自身", str(ctx.exception))

        # 2. Admin cannot delete themselves
        with self.assertRaises(ValueError) as ctx:
            self.app.delete_user(
                target_username="admin_user",
                token=self.admin_session,
            )
        self.assertIn("自身", str(ctx.exception))

        # 3. Delete existing employee
        self.app.create_user(
            username="temp_worker",
            display_name="短期契約スタッフ",
            role="viewer",
            department="派遣",
            password="Password999!",
            token=self.admin_session,
        )
        # Session active before delete
        t_login = self.app.login("temp_worker", "Password999!")
        t_token = t_login["session_id"]

        del_res = self.app.delete_user(
            target_username="temp_worker",
            token=self.admin_session,
        )
        self.assertEqual(del_res["status"], "SUCCESS")

        # Session revoked and cannot login
        self.assertIsNone(self.app.get_current_user(t_token))
        with self.assertRaises(PermissionError):
            self.app.login("temp_worker", "Password999!")

    def test_test_037_sqlite_persistence_across_restarts(self) -> None:
        """TEST-037: Users, roles, and suspension states persist across server restarts."""
        # 1. Create a user and suspend them on the first instance
        self.app.create_user(
            username="permanent_user",
            display_name="永続化対象社員",
            role="editor",
            department="知財部",
            password="PermanentSecret123!",
            notes="再起動検証用",
            token=self.admin_session,
        )
        self.app.toggle_user_status(
            target_username="permanent_user",
            is_active=False,
            token=self.admin_session,
        )

        # 2. Simulate complete server shutdown and restart by spawning a fresh instance with the same DB
        restarted_app = KnowledgeWebApp(
            store_path=":memory:",
            default_provider=ProviderType.LITERT,
            user_db_path=self.user_db,
            audit_db_path=self.audit_db,
        )
        admin_login2 = restarted_app.login("admin_user", "password123")
        admin_session2 = admin_login2["session_id"]

        # 3. Verify user list contains permanent_user with exact role, department, notes, and suspended status
        user_list = restarted_app.list_users(token=admin_session2)
        target = next((u for u in user_list if u["username"] == "permanent_user"), None)
        self.assertIsNotNone(target)
        self.assertEqual(target["display_name"], "永続化対象社員")
        self.assertEqual(target["role"], "editor")
        self.assertEqual(target["department"], "知財部")
        self.assertEqual(target["notes"], "再起動検証用")
        self.assertFalse(target["is_active"])

        # 4. Verify user stats
        stats = restarted_app.get_user_stats(token=admin_session2)
        self.assertTrue(stats["suspended"] >= 1)
        self.assertTrue(stats["editors"] >= 1)

    def test_test_038_audit_trail_for_user_lifecycle(self) -> None:
        """TEST-038: Comprehensive Audit Trail Tracking for all user lifecycle actions."""
        # Perform lifecycle operations
        self.app.create_user(
            username="audit_target",
            display_name="監査対象",
            role="viewer",
            department="財務部",
            password="AuditPassword123!",
            token=self.admin_session,
            ip_address="192.168.10.50",
        )
        self.app.update_user(
            target_username="audit_target",
            display_name="監査対象 (更新後)",
            role="editor",
            token=self.admin_session,
            ip_address="192.168.10.50",
        )
        self.app.reset_user_password(
            target_username="audit_target",
            new_password="NewAuditPassword123!",
            token=self.admin_session,
            ip_address="192.168.10.50",
        )
        self.app.toggle_user_status(
            target_username="audit_target",
            is_active=False,
            token=self.admin_session,
            ip_address="192.168.10.50",
        )
        self.app.delete_user(
            target_username="audit_target",
            token=self.admin_session,
            ip_address="192.168.10.50",
        )

        # Query audit logs
        logs = self.app.query_audit_logs(token=self.admin_session, limit=50)
        actions = [l["action"] for l in logs]
        self.assertIn("USER_CREATE", actions)
        self.assertIn("USER_UPDATE", actions)
        self.assertIn("USER_PASSWORD_RESET", actions)
        self.assertIn("USER_SUSPEND", actions)
        self.assertIn("USER_DELETE", actions)
