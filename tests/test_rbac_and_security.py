"""Unit and Integration Tests for RBAC, Security Masking, Lite Model Defaults, and Dynamic Discovery.

Covers:
- TEST-014: Multi-Tier Role-Based Access Control (Viewer, Editor, Admin, Custom roles)
- TEST-015: Lite Model Defaults and Dynamic Model Discovery
- TEST-016: Zero-Trust API Key Masking & Log Sanitization
- TEST-017: Git Boundary & Confidential Ledger Exclusion
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from src.auth.rbac import (
    Permission,
    RBACManager,
    RoleType,
    mask_api_key,
    sanitize_text,
)
from src.core.engine import ProviderType
from src.core.gemini_provider import DEFAULT_LITE_MODEL, GeminiCloudProvider
from src.web.app import KnowledgeWebApp


class TestRBACAndSecurity(unittest.TestCase):
    """Test suite for v3.0 security, permissions, and dynamic model discovery."""

    def setUp(self) -> None:
        self.app = KnowledgeWebApp(
            store_path=":memory:",
            default_provider=ProviderType.LITERT,
            gemini_api_key="AIzaSyTestSecretKeyForVerification1234",
            gemini_model="gemini-3.5-flash-lite",
        )
        self.viewer_session = self.app.switch_user("viewer_user")["session_id"]
        self.editor_session = self.app.switch_user("editor_user")["session_id"]
        self.admin_session = self.app.switch_user("admin_user")["session_id"]

    def test_rbac_viewer_restrictions(self) -> None:
        """TEST-014: Viewer can chat and search, but cannot modify knowledge or change settings."""
        # 1. Chat & Search allowed
        chat_res = self.app.chat("通勤手当の規定を教えてください", token=self.viewer_session)
        self.assertIn("answer", chat_res)

        search_res = self.app.search_simulator("リモートワーク", token=self.viewer_session)
        self.assertIn("citations", search_res)

        blocks = self.app.list_blocks(token=self.viewer_session)
        self.assertTrue(len(blocks) > 0)

        # 2. Creating block is forbidden (PermissionError)
        with self.assertRaises(PermissionError):
            self.app.create_block(title="不正資料", text="本文", token=self.viewer_session)

        # 3. Updating block is forbidden
        block_id = blocks[0]["block_id"]
        with self.assertRaises(PermissionError):
            self.app.update_block(block_id=block_id, text="改ざん文面", token=self.viewer_session)

        # 4. Deleting block is forbidden
        with self.assertRaises(PermissionError):
            self.app.delete_block(block_id=block_id, token=self.viewer_session)

        # 5. Setting provider / API key is forbidden
        with self.assertRaises(PermissionError):
            self.app.set_provider(provider="gemini", token=self.viewer_session)

    def test_rbac_editor_capabilities_and_limits(self) -> None:
        """TEST-014: Editor can perform knowledge CRUD, but cannot change models or API keys."""
        # 1. Create block succeeds
        new_block = self.app.create_block(
            title="総務部規定",
            text="夏季休暇は有給とは別に3日付与する。",
            locator="第10条",
            token=self.editor_session,
        )
        self.assertIn("block_id", new_block)
        b_id = new_block["block_id"]

        # 2. Update block succeeds
        upd = self.app.update_block(block_id=b_id, text="夏季休暇は4日付与する。", token=self.editor_session)
        self.assertEqual(upd["text"], "夏季休暇は4日付与する。")

        # 3. Settings change is forbidden
        with self.assertRaises(PermissionError):
            self.app.set_provider(provider="gemini", token=self.editor_session)

        # 4. Delete block succeeds
        del_res = self.app.delete_block(block_id=b_id, token=self.editor_session)
        self.assertEqual(del_res["status"], "SUCCESS")

    def test_rbac_admin_full_access(self) -> None:
        """TEST-014: Admin has complete access including settings and provider configuration."""
        settings_res = self.app.set_provider(
            provider="gemini",
            gemini_api_key="AIzaSyUpdatedKeyForTestingAdmin5678",
            gemini_model="gemini-3.5-flash-lite",
            token=self.admin_session,
        )
        self.assertEqual(settings_res["status"], "SUCCESS")
        self.assertEqual(settings_res["active_provider"], "gemini")

    def test_custom_role_registration(self) -> None:
        """TEST-014: Extensible corporate roles can be registered with custom permission sets."""
        rbac = RBACManager()
        rbac.register_custom_role("compliance_officer", [Permission.CHAT, Permission.KNOWLEDGE_READ])
        self.assertTrue(rbac.has_permission("compliance_officer", Permission.CHAT))
        self.assertTrue(rbac.has_permission("compliance_officer", Permission.KNOWLEDGE_READ))
        self.assertFalse(rbac.has_permission("compliance_officer", Permission.KNOWLEDGE_WRITE))
        self.assertFalse(rbac.has_permission("compliance_officer", Permission.SETTINGS_MANAGE))

    def test_lite_model_default_and_discovery(self) -> None:
        """TEST-015: Default model is gemini-3.5-flash-lite, and list returns Gemini 3.5 Flash Lite."""
        self.assertEqual(DEFAULT_LITE_MODEL, "gemini-3.5-flash-lite")
        provider = GeminiCloudProvider()
        self.assertEqual(provider.model_name, "gemini-3.5-flash-lite")

        models = provider.list_available_models()
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "gemini-3.5-flash-lite")
        self.assertEqual(models[0]["display_name"], "Gemini 3.5 Flash Lite")

    def test_api_key_masking_and_sanitization(self) -> None:
        """TEST-016: API keys are masked for display and redacted from log strings."""
        raw_key = "AIzaSyABC1234567890XYZabcdefghijKLMN"
        masked = mask_api_key(raw_key)
        self.assertTrue(masked.startswith("AIzaSy"))
        self.assertTrue(masked.endswith("KLMN"))
        self.assertIn("...****", masked)
        self.assertNotIn("1234567890XYZ", masked)

        # Log sanitization
        dirty_log = f"Failed to connect to Google API with key {raw_key} at endpoint."
        clean_log = sanitize_text(dirty_log)
        self.assertNotIn(raw_key, clean_log)
        self.assertIn("[API_KEY_REDACTED]", clean_log)

        # Settings endpoint masks key for admin and hides for viewer
        admin_settings = self.app.get_settings(token=self.admin_session)
        self.assertTrue(admin_settings["can_manage_settings"])
        self.assertIn("...****", admin_settings["masked_gemini_key"])

        viewer_settings = self.app.get_settings(token=self.viewer_session)
        self.assertFalse(viewer_settings["can_manage_settings"])
        self.assertEqual(viewer_settings["masked_gemini_key"], "********")

    def test_git_boundary_exclusion(self) -> None:
        """TEST-017: Verify .gitignore explicitly excludes private docs, AI rules, and Venv."""
        gitignore_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", ".gitignore")
        )
        self.assertTrue(os.path.exists(gitignore_path), ".gitignore must exist")
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_patterns = [
            ".agents",
            "docs/AUTONOMY.md",
            "docs/TRACEABILITY.md",
            "docs/TEST_RESULTS.md",
            "docs/APPROVALS.md",
            "litert-env",
            "models/*.litertlm",
        ]
        for pat in required_patterns:
            self.assertIn(pat, content, f"Pattern '{pat}' must be present in .gitignore")


if __name__ == "__main__":
    unittest.main()
