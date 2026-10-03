"""Unit and Integration Tests for User Chat Isolation, Model Selector, and Settings Persistence.

Validates:
- TEST-026: Multi-Tenant Chat Isolation (Each user sees and touches only their own threads/messages).
- TEST-027: Gemini Model Selector & Discovery (List choices and model switching).
- TEST-028: Settings Persistence Across Restarts (SettingsManager saves and reloads provider, API key, model, and retention).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from src.core.engine import ProviderType
from src.core.settings import SettingsManager, RECOMMENDED_GEMINI_MODELS
from src.web.app import KnowledgeWebApp


class TestUserChatIsolationAndSettings(unittest.TestCase):
    """Test suite for User Isolation and Settings Persistence."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chat_db = os.path.join(self.temp_dir.name, "test_chat.db")
        self.audit_db = os.path.join(self.temp_dir.name, "test_audit.db")
        self.settings_file = os.path.join(self.temp_dir.name, "test_settings.json")

        self.app = KnowledgeWebApp(
            store_path=":memory:",
            default_provider=ProviderType.LITERT,
            chat_db_path=self.chat_db,
            audit_db_path=self.audit_db,
            settings_path=self.settings_file,
        )

        self.admin_session = self.app.login("admin_user", "password123")["session_id"]

        # Create two distinct test users with admin token
        self.app.create_user(
            username="sato_user",
            display_name="Kenichi Sato",
            role="viewer",
            department="Sales Department",
            password="pass_sato_123",
            token=self.admin_session,
        )
        self.user1_session = self.app.login("sato_user", "pass_sato_123")["session_id"]

        self.app.create_user(
            username="tanaka_user",
            display_name="Taro Tanaka",
            role="viewer",
            department="開発部",
            password="pass_tanaka_123",
            token=self.admin_session,
        )
        self.user2_session = self.app.login("tanaka_user", "pass_tanaka_123")["session_id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_test_026_multi_tenant_user_chat_isolation(self) -> None:
        """TEST-026: Strict Chat Thread & Message Isolation Between Users."""
        # 1. User 1 (Sato) creates a chat thread and asks a question
        res1 = self.app.chat("Sato question: 交通費精算について教えてください。", token=self.user1_session)
        sato_thread_id = res1["thread_id"]
        self.assertTrue(sato_thread_id.startswith("th_"))

        # 2. User 2 (Tanaka) creates a separate chat thread
        res2 = self.app.chat("Tanaka question: リモートワークの上限日数は何日ですか？", token=self.user2_session)
        tanaka_thread_id = res2["thread_id"]
        self.assertNotEqual(sato_thread_id, tanaka_thread_id)

        # 3. List threads for Sato: must contain ONLY Sato's thread
        sato_threads = self.app.list_chat_threads(token=self.user1_session)
        self.assertEqual(len(sato_threads), 1)
        self.assertEqual(sato_threads[0]["thread_id"], sato_thread_id)
        self.assertEqual(sato_threads[0]["user_id"], "sato_user")

        # 4. List threads for Tanaka: must contain ONLY Tanaka's thread
        tanaka_threads = self.app.list_chat_threads(token=self.user2_session)
        self.assertEqual(len(tanaka_threads), 1)
        self.assertEqual(tanaka_threads[0]["thread_id"], tanaka_thread_id)
        self.assertEqual(tanaka_threads[0]["user_id"], "tanaka_user")

        # 5. Tanaka tries to read Sato's thread -> MUST return None (Strict Isolation)
        forbidden_detail = self.app.get_chat_thread(thread_id=sato_thread_id, token=self.user2_session)
        self.assertIsNone(forbidden_detail)

        # 6. Tanaka tries to post into Sato's thread -> MUST be quarantined into a new thread
        hijack_attempt = self.app.chat(
            "不正アクセステスト: 他人のスレッドに割り込み",
            thread_id=sato_thread_id,
            token=self.user2_session,
        )
        # Should not be sato's thread
        self.assertNotEqual(hijack_attempt["thread_id"], sato_thread_id)
        # Sato's thread should still have only 2 messages (1 user, 1 assistant)
        sato_detail = self.app.get_chat_thread(thread_id=sato_thread_id, token=self.user1_session)
        self.assertEqual(len(sato_detail["messages"]), 2)

        # 7. Tanaka tries to delete Sato's thread -> MUST fail (NOT_FOUND)
        del_attempt = self.app.delete_chat_thread(thread_id=sato_thread_id, token=self.user2_session)
        self.assertEqual(del_attempt["status"], "NOT_FOUND")
        # Sato's thread still exists
        self.assertIsNotNone(self.app.get_chat_thread(thread_id=sato_thread_id, token=self.user1_session))

    def test_test_027_gemini_model_selector_and_discovery(self) -> None:
        """TEST-027: Gemini Model Selection and Dynamic Model Listing."""
        # 1. Models list contains recommended models
        models = self.app.get_available_models()
        self.assertGreaterEqual(len(models), 4)
        model_ids = [m["id"] for m in models]
        self.assertIn("gemini-3.5-flash-lite", model_ids)
        self.assertIn("gemini-2.5-flash", model_ids)
        self.assertIn("gemini-2.5-pro", model_ids)
        self.assertIn("gemini-2.0-flash", model_ids)

        # 2. Admin switches provider to Gemini and selects Gemini 2.5 Pro
        res = self.app.set_provider(
            provider="gemini",
            gemini_api_key="AIzaSyDummyTestKeyForModelSelector123",
            gemini_model="gemini-2.5-pro",
            token=self.admin_session,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["active_provider"], "gemini")
        self.assertEqual(res["gemini_model"], "gemini-2.5-pro")

        # 3. get_settings returns updated model and available_models
        settings = self.app.get_settings(token=self.admin_session)
        self.assertEqual(settings["active_provider"], "gemini")
        self.assertEqual(settings["gemini_model"], "gemini-2.5-pro")
        self.assertIn("available_models", settings)
        self.assertEqual(len(settings["available_models"]), len(models))

    def test_test_028_persistent_settings_storage_and_restoration(self) -> None:
        """TEST-028: Persistence of Provider, Model, API Key, and Retention Days across restarts."""
        # 1. Update settings as Admin
        self.app.set_provider(
            provider="gemini",
            gemini_api_key="AIzaSySecretPersistedKey9999",
            gemini_model="gemini-2.5-flash",
            token=self.admin_session,
        )
        self.app.set_retention_days(days=180, token=self.admin_session)

        # 2. Verify file content on disk
        self.assertTrue(os.path.exists(self.settings_file))
        with open(self.settings_file, "r", encoding="utf-8") as f:
            persisted_data = json.load(f)
        self.assertEqual(persisted_data["active_provider"], "gemini")
        self.assertEqual(persisted_data["gemini_model"], "gemini-2.5-flash")
        self.assertEqual(persisted_data["gemini_api_key"], "AIzaSySecretPersistedKey9999")
        self.assertEqual(persisted_data["retention_days"], 180)

        # 3. Simulate Server Restart: Instantiate new KnowledgeWebApp pointing to the same settings_file
        restarted_app = KnowledgeWebApp(
            store_path=":memory:",
            chat_db_path=self.chat_db,
            audit_db_path=self.audit_db,
            settings_path=self.settings_file,
        )

        # 4. Verify all configurations are automatically restored
        self.assertEqual(restarted_app.current_provider, ProviderType.GEMINI)
        self.assertEqual(restarted_app.current_gemini_model, "gemini-2.5-flash")
        self.assertEqual(restarted_app.gemini_api_key, "AIzaSySecretPersistedKey9999")
        self.assertEqual(restarted_app.get_retention_days(), 180)

        admin_sess2 = restarted_app.login("admin_user", "password123")["session_id"]
        restored_settings = restarted_app.get_settings(token=admin_sess2)
        self.assertEqual(restored_settings["active_provider"], "gemini")
        self.assertEqual(restored_settings["gemini_model"], "gemini-2.5-flash")
        self.assertEqual(restored_settings["retention_days"], 180)

    def test_test_029_clear_all_chat_threads(self) -> None:
        """TEST-029: Bulk Clearing of Chat History (Per-User and System-Wide)."""
        # 1. Create chats for both users
        self.app.chat("Sato question1", token=self.user1_session)
        self.app.chat("Sato question2", token=self.user1_session)
        self.app.chat("Tanaka question1", token=self.user2_session)

        self.assertEqual(len(self.app.list_chat_threads(token=self.user1_session)), 2)
        self.assertEqual(len(self.app.list_chat_threads(token=self.user2_session)), 1)

        # 2. Sato clears their own history
        res1 = self.app.clear_chat_threads(token=self.user1_session, all_users=False)
        self.assertEqual(res1["status"], "SUCCESS")
        self.assertEqual(res1["deleted_count"], 2)

        # Sato's threads are gone, Tanaka's thread remains intact
        self.assertEqual(len(self.app.list_chat_threads(token=self.user1_session)), 0)
        self.assertEqual(len(self.app.list_chat_threads(token=self.user2_session)), 1)

        # 3. Non-admin trying to clear all_users -> MUST raise PermissionError
        with self.assertRaises(PermissionError):
            self.app.clear_chat_threads(token=self.user2_session, all_users=True)

        # 4. Admin clears system-wide history
        res2 = self.app.clear_chat_threads(token=self.admin_session, all_users=True)
        self.assertEqual(res2["status"], "SUCCESS")
        self.assertEqual(res2["deleted_count"], 1)
        self.assertEqual(len(self.app.list_chat_threads(token=self.user2_session)), 0)

    def test_test_030_discover_live_gemini_models(self) -> None:
        """TEST-030: Real-Time Gemini Model Discovery & Description Generation."""
        # 1. Non-admin cannot discover models
        with self.assertRaises(PermissionError):
            self.app.discover_gemini_models(token=self.user1_session)

        # 2. Admin discovers models (without API key -> returns fallback recommendations)
        res = self.app.discover_gemini_models(token=self.admin_session)
        self.assertIn("models", res)
        self.assertGreaterEqual(len(res["models"]), 4)
        for m in res["models"]:
            self.assertIn("id", m)
            self.assertIn("name", m)
            self.assertIn("description", m)

        # 3. Admin discovers with dummy API key -> graceful handling
        res_key = self.app.discover_gemini_models(api_key="AIzaSyDummyKeyForTestDiscovery", token=self.admin_session)
        self.assertIn("models", res_key)
        self.assertTrue(len(res_key["models"]) > 0)


if __name__ == "__main__":
    unittest.main()
