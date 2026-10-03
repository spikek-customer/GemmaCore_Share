"""Test Suite for Enterprise Delegated Role-Based Access Control (Delegated RBAC).

Validates:
- TEST-045: Editor can manage Viewer and Editor lifecycle (Create, Update, Reset PW, Suspend, Delete)
- TEST-046: Editor cannot modify, reset PW, suspend, or delete Admin accounts (Upper-tier immunity)
- TEST-047: Editor cannot assign Admin role (Privilege escalation prevention)
- TEST-048: Admin retains full system management authority with safety guards
"""

import unittest
from src.auth.rbac import RBACManager, RoleType
from src.web.app import KnowledgeWebApp


class TestDelegatedRBAC(unittest.TestCase):
    """Test suite for hierarchical delegated user management in large enterprises."""

    def setUp(self) -> None:
        """Initialize in-memory RBAC and WebApp instances for clean isolation."""
        self.rbac = RBACManager(db_path=":memory:")
        self.app = KnowledgeWebApp()
        self.app.rbac = self.rbac

        # Create operator sessions
        # 1. Admin Operator
        self.admin_session = self.rbac.authenticate_or_switch("admin").session_id
        # 2. Editor Operator (Department Manager)
        self.editor_session = self.rbac.authenticate_or_switch("editor_user").session_id
        # 3. Viewer Operator (Regular Employee)
        self.viewer_session = self.rbac.authenticate_or_switch("viewer_user").session_id

    def test_test_045_editor_can_manage_viewer_and_editor_lifecycle(self) -> None:
        """TEST-045: Editor can create, update, reset password, suspend, and delete Viewer & Editor."""
        # 1. Editor creates a new Viewer (New employee onboarding in department)
        created_viewer = self.app.create_user(
            username="sales_newbie",
            display_name="Taro Shinnyu",
            role="viewer",
            department="営業第1課",
            password="InitialPass123",
            token=self.editor_session,
        )
        self.assertEqual(created_viewer["username"], "sales_newbie")
        self.assertEqual(created_viewer["role"], "viewer")

        # 2. Editor updates employee details (Department transfer)
        upd_user = self.app.update_user(
            target_username="sales_newbie",
            display_name="Taro Shinnyu (昇格)",
            department="営業第2課",
            token=self.editor_session,
        )
        self.assertEqual(upd_user["display_name"], "Taro Shinnyu (昇格)")
        self.assertEqual(upd_user["department"], "営業第2課")

        # 3. Editor promotes Viewer to Editor (Leader assignment in department)
        promoted = self.app.update_user(
            target_username="sales_newbie",
            role="editor",
            token=self.editor_session,
        )
        self.assertEqual(promoted["role"], "editor")

        # 4. Editor resets password for the employee
        res_pw = self.app.reset_user_password(
            target_username="sales_newbie",
            new_password="NewSecurePass456",
            token=self.editor_session,
        )
        self.assertEqual(res_pw["status"], "SUCCESS")

        # Verify login succeeds with the newly reset password
        auth_check = self.rbac.authenticate("sales_newbie", "NewSecurePass456")
        self.assertIsNotNone(auth_check)

        # 5. Editor suspends and reactivates employee account (Leave / Sabbatical)
        suspend_res = self.app.toggle_user_status(
            target_username="sales_newbie",
            is_active=False,
            token=self.editor_session,
        )
        self.assertFalse(suspend_res["is_active"])

        # Reactivate
        reactivate_res = self.app.toggle_user_status(
            target_username="sales_newbie",
            is_active=True,
            token=self.editor_session,
        )
        self.assertTrue(reactivate_res["is_active"])

        # 6. Editor deletes the employee account (Offboarding / Exit)
        del_res = self.app.delete_user(
            target_username="sales_newbie",
            token=self.editor_session,
        )
        self.assertEqual(del_res["status"], "SUCCESS")
        self.assertIsNone(self.rbac.get_user("sales_newbie"))

    def test_test_046_editor_cannot_touch_admin_accounts(self) -> None:
        """TEST-046: Editor cannot modify, reset PW, suspend, or delete Admin accounts (Upper-tier immunity)."""
        # Ensure 'admin' exists and is an active Admin
        admin_user = self.rbac.get_user("admin")
        self.assertIsNotNone(admin_user)
        self.assertEqual(admin_user["role"], "admin")

        # 1. Editor attempts to update Admin account -> Must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            self.app.update_user(
                target_username="admin",
                display_name="改ざん管理者",
                token=self.editor_session,
            )
        self.assertIn("管理者", str(ctx.exception))

        # 2. Editor attempts to reset Admin password -> Must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            self.app.reset_user_password(
                target_username="admin",
                new_password="HackedAdminPass123",
                token=self.editor_session,
            )
        self.assertIn("管理者", str(ctx.exception))

        # 3. Editor attempts to suspend Admin account -> Must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            self.app.toggle_user_status(
                target_username="admin",
                is_active=False,
                token=self.editor_session,
            )
        self.assertIn("管理者", str(ctx.exception))

        # 4. Editor attempts to delete Admin account -> Must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            self.app.delete_user(
                target_username="admin",
                token=self.editor_session,
            )
        self.assertIn("管理者", str(ctx.exception))

        # Verify Admin remains intact and active
        intact_admin = self.rbac.get_user("admin")
        self.assertEqual(intact_admin["display_name"], "最高システム管理者")
        self.assertTrue(intact_admin["is_active"])

    def test_test_047_editor_cannot_assign_admin_role_privilege_escalation(self) -> None:
        """TEST-047: Editor cannot create or promote anyone to Admin role (Privilege escalation prevention)."""
        # 1. Editor attempts to create a new user with role='admin' -> Must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            self.app.create_user(
                username="fake_admin",
                display_name="不正昇格者",
                role="admin",
                department="総務部",
                password="password123",
                token=self.editor_session,
            )
        self.assertIn("権限昇格禁止", str(ctx.exception))

        # 2. Editor attempts to promote existing Viewer to 'admin' -> Must raise PermissionError
        with self.assertRaises(PermissionError) as ctx:
            self.app.update_user(
                target_username="viewer_user",
                role="admin",
                token=self.editor_session,
            )
        self.assertIn("権限昇格禁止", str(ctx.exception))

        # Verify target user was NOT promoted
        viewer_check = self.rbac.get_user("viewer_user")
        self.assertEqual(viewer_check["role"], "viewer")

    def test_test_048_admin_retains_full_control_and_safety_guards(self) -> None:
        """TEST-048: System Administrator can manage all roles, but is still subject to self/last-admin guards."""
        # 1. Admin can create, promote, and manage Admin users
        second_admin = self.app.create_user(
            username="admin_sub",
            display_name="副管理者",
            role="admin",
            department="IT Department",
            password="adminPass123",
            token=self.admin_session,
        )
        self.assertEqual(second_admin["role"], "admin")

        # 2. Admin can update second admin
        upd = self.app.update_user(
            target_username="admin_sub",
            display_name="副管理者 (昇格)",
            token=self.admin_session,
        )
        self.assertEqual(upd["display_name"], "副管理者 (昇格)")

        # 3. Admin cannot delete self
        with self.assertRaises(ValueError):
            self.app.delete_user(
                target_username="admin",
                token=self.admin_session,
            )

        # 4. Admin cannot suspend self
        with self.assertRaises(ValueError):
            self.app.toggle_user_status(
                target_username="admin",
                is_active=False,
                token=self.admin_session,
            )

        # 5. Viewer has NO user management permissions at all
        with self.assertRaises(PermissionError):
            self.app.create_user(
                username="viewer_illegal",
                display_name="不正作成",
                role="viewer",
                department="Sales Department",
                token=self.viewer_session,
            )


if __name__ == "__main__":
    unittest.main()
