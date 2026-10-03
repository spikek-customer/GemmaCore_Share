"""Unit and Integration Tests for Enterprise Features (v3.1).

Covers:
- TEST-018: Multi-Thread Chat History Persistence & Auto-Naming (ChatGPT-like)
- TEST-019: Dynamic User Management, Role Assignment & PBKDF2 Password Authentication
- TEST-020: Comprehensive Audit Trail (Who/What/When/IP) & Filtering
- TEST-021: System Diagnostics Logging with Stack Trace Capture
- TEST-022: Configurable Log Retention (7-365 days) & Automatic Purge
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from src.auth.audit_log import AuditLogger
from src.auth.rbac import Permission, RBACManager
from src.core.chat_history import ChatHistoryManager
from src.core.engine import ProviderType
from src.web.app import KnowledgeWebApp


class TestEnterpriseFeatures(unittest.TestCase):
    """Test suite for Chat History, Dynamic RBAC, Audit Logging, and Retention Policies."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.chat_db = os.path.join(self.temp_dir.name, "test_chat.db")
        self.audit_db = os.path.join(self.temp_dir.name, "test_audit.db")

        self.app = KnowledgeWebApp(
            store_path=":memory:",
            default_provider=ProviderType.LITERT,
            gemini_api_key="AIzaSyTestSecretEnterpriseKey1234",
            gemini_model="gemini-3.5-flash-lite",
            chat_db_path=self.chat_db,
            audit_db_path=self.audit_db,
        )
        self.admin_session = self.app.switch_user("admin_user")["session_id"]
        self.viewer_session = self.app.switch_user("viewer_user")["session_id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_test_018_chat_history_persistence_and_naming(self) -> None:
        """TEST-018: Multi-Thread Chat History Persistence & Auto-Naming."""
        # 1. Ask question without specifying thread_id -> automatically creates thread
        res1 = self.app.chat("リモートワークの利用条件を教えてください。", token=self.admin_session)
        self.assertIn("thread_id", res1)
        thread_id = res1["thread_id"]

        # 2. Verify thread list has the new thread with auto-generated title
        threads = self.app.list_chat_threads(token=self.admin_session)
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]["thread_id"], thread_id)
        self.assertTrue(threads[0]["title"].startswith("リモートワーク"))
        self.assertEqual(threads[0]["message_count"], 2)  # User + Assistant

        # 3. Follow up question in the same thread
        res2 = self.app.chat("通勤手当の上限も教えてください。", thread_id=thread_id, token=self.admin_session)
        self.assertEqual(res2["thread_id"], thread_id)

        # 4. Fetch thread details
        thread_detail = self.app.get_chat_thread(thread_id=thread_id, token=self.admin_session)
        self.assertIsNotNone(thread_detail)
        self.assertEqual(len(thread_detail["messages"]), 4)
        self.assertEqual(thread_detail["messages"][0]["role"], "user")
        self.assertEqual(thread_detail["messages"][1]["role"], "assistant")

        # 5. Delete thread
        del_res = self.app.delete_chat_thread(thread_id=thread_id, token=self.admin_session)
        self.assertEqual(del_res["status"], "SUCCESS")

        # Verify thread list is now empty
        threads_after = self.app.list_chat_threads(token=self.admin_session)
        self.assertEqual(len(threads_after), 0)

    def test_test_019_dynamic_user_management_and_pbkdf2_auth(self) -> None:
        """TEST-019: Dynamic User Management, Role Assignment & PBKDF2 Password Authentication."""
        # 1. Non-admin cannot create users
        with self.assertRaises(PermissionError):
            self.app.create_user(
                username="hacker",
                display_name="悪意あるユーザー",
                role="admin",
                department="不明",
                password="secret_password",
                token=self.viewer_session,
            )

        # 2. Admin creates a new viewer user
        new_user = self.app.create_user(
            username="sato_k",
            display_name="Kenta Sato",
            role="viewer",
            department="営業第1課",
            password="SecurePassword999!",
            token=self.admin_session,
        )
        self.assertEqual(new_user["username"], "sato_k")
        self.assertEqual(new_user["role"], "viewer")

        # 3. Authenticate with password (PBKDF2)
        login_res = self.app.login(username="sato_k", password="SecurePassword999!")
        self.assertEqual(login_res["status"], "SUCCESS")
        self.assertIn("chat:interact", login_res["permissions"])
        self.assertNotIn("knowledge:write", login_res["permissions"])

        # 4. Failed authentication with wrong password
        with self.assertRaises(PermissionError):
            self.app.login(username="sato_k", password="WrongPassword!")

        # 5. Admin promotes sato_k to editor
        update_res = self.app.update_user_role(
            target_username="sato_k",
            new_role="editor",
            token=self.admin_session,
        )
        self.assertEqual(update_res["role"], "editor")

        # 6. Verify upgraded permissions on next login
        login_after_upgrade = self.app.login(username="sato_k", password="SecurePassword999!")
        self.assertIn("knowledge:write", login_after_upgrade["permissions"])

        # 7. Admin deletes user
        del_user = self.app.delete_user(target_username="sato_k", token=self.admin_session)
        self.assertEqual(del_user["status"], "SUCCESS")

    def test_test_020_audit_trail_and_filtering(self) -> None:
        """TEST-020: Comprehensive Audit Trail (Who/What/When/IP) & Filtering."""
        # 1. Perform operations
        self.app.chat("AIツールの利用基準は？", token=self.admin_session, ip_address="192.168.1.100")
        self.app.create_block(
            title="テスト規定",
            text="新しいテスト条文です。",
            locator="第100条",
            token=self.admin_session,
            ip_address="192.168.1.101",
        )

        # 2. Viewer cannot query audit logs
        with self.assertRaises(PermissionError):
            self.app.query_audit_logs(token=self.viewer_session)

        # 3. Admin queries all audit logs
        logs = self.app.query_audit_logs(token=self.admin_session)
        self.assertTrue(len(logs) >= 2)

        # 4. Check contents of the audit records
        actions = [l["action"] for l in logs]
        self.assertIn("CHAT_QUERY", actions)
        self.assertIn("BLOCK_CREATE", actions)

        # Verify IP address tracking
        chat_log = next(l for l in logs if l["action"] == "CHAT_QUERY")
        self.assertEqual(chat_log["ip_address"], "192.168.1.100")
        self.assertEqual(chat_log["username"], "admin_user")
        self.assertEqual(chat_log["status"], "SUCCESS")

        # 5. Test filtering by action
        filtered_logs = self.app.query_audit_logs(token=self.admin_session, action="BLOCK_CREATE")
        self.assertTrue(all(l["action"] == "BLOCK_CREATE" for l in filtered_logs))

    def test_test_021_diagnostics_logging_and_stacktrace(self) -> None:
        """TEST-021: System Diagnostics Logging with Stack Trace Capture."""
        # 1. Record synthetic system diagnostics error
        self.app.audit.record_diagnostics(
            component="VectorIndexWorker",
            level="ERROR",
            message="FAISS indexing allocation failed (synthetic test)",
            stack_trace="Traceback (most recent call last):\n  File 'test.py', line 1, in <module>\nMemoryError",
            context={"doc_id": "doc_999"},
        )

        # 2. Viewer cannot access diagnostics
        with self.assertRaises(PermissionError):
            self.app.query_diagnostics_logs(token=self.viewer_session)

        # 3. Admin queries diagnostics logs
        diag_logs = self.app.query_diagnostics_logs(token=self.admin_session)
        self.assertEqual(len(diag_logs), 1)
        self.assertEqual(diag_logs[0]["component"], "VectorIndexWorker")
        self.assertEqual(diag_logs[0]["level"], "ERROR")
        self.assertIn("MemoryError", diag_logs[0]["stack_trace"])
        self.assertIn("doc_999", diag_logs[0]["context_json"])

    def test_test_022_retention_period_and_auto_purge(self) -> None:
        """TEST-022: Configurable Log Retention (7-365 days) & Automatic Purge."""
        # 1. Get and update retention days
        initial_days = self.app.get_retention_days()
        self.assertEqual(initial_days, 365)

        # 2. Change retention days to 30 days
        new_days = self.app.set_retention_days(30, token=self.admin_session)
        self.assertEqual(new_days, 30)
        self.assertEqual(self.app.get_retention_days(), 30)

        # 3. Insert mock expired logs (> 30 days old) and fresh logs (< 30 days old)
        conn = sqlite3.connect(self.audit_db)
        cur = conn.cursor()

        now_ts = time.time()
        old_ts = now_ts - (45 * 86400)
        fresh_ts = now_ts - (10 * 86400)

        old_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(old_ts))
        fresh_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(fresh_ts))

        cur.execute(
            """INSERT INTO audit_logs (log_id, timestamp, iso_time, user_id, username, role, action, resource, status, ip_address, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"log_{uuid.uuid4().hex[:12]}", old_ts, old_iso, "old_u", "old_user", "viewer", "EXPIRED_ACTION", "res", "SUCCESS", "127.0.0.1", "45日前ログ"),
        )
        cur.execute(
            """INSERT INTO audit_logs (log_id, timestamp, iso_time, user_id, username, role, action, resource, status, ip_address, details)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f"log_{uuid.uuid4().hex[:12]}", fresh_ts, fresh_iso, "fresh_u", "fresh_user", "viewer", "FRESH_ACTION", "res", "SUCCESS", "127.0.0.1", "10日前ログ"),
        )
        conn.commit()
        conn.close()

        # 4. Trigger auto-purge
        purged = self.app.audit.purge_expired_logs()
        self.assertEqual(purged["audit_purged"], 1)

        # 5. Verify that old log was purged and fresh log remains
        remaining_logs = self.app.query_audit_logs(token=self.admin_session)
        usernames = [l["username"] for l in remaining_logs]
        self.assertIn("fresh_user", usernames)
        self.assertNotIn("old_user", usernames)


if __name__ == "__main__":
    unittest.main()
