"""Unit and Integration Tests for Google Workspace SSO & Drive Continuous Synchronizer.

Covers:
- TEST-039: Google Workspace OIDC SSO, Corporate Domain Restriction & JIT Provisioning (Viewer Role Default)
- TEST-040: Google Docs/Sheets/Slides Native Export & Universal Parsing & Sentence-Aware Chunking
- TEST-041: Google Drive Changes API Incremental Differential Sync & Update Detection
- TEST-042: Google Drive Deleted / Trashed File Immediate Complete Purge from Qdrant/CMS
- TEST-043: Target Folders Whitelist Scope Enforcement & Role-based ACL Access Control
- TEST-044: ETag Checksum Re-embedding Skip & Error Quarantine Fault Tolerance
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
import unittest
from typing import Any, Dict

from src.auth.google_auth import (
    DomainRestrictionError,
    GoogleWorkspaceAuthService,
    InvalidTokenError,
)
from src.auth.rbac import RoleType, UserSuspendedError
from src.core.engine import ProviderType
from src.sync.drive_sync import (
    GOOGLE_DOC_MIME,
    GOOGLE_SHEET_MIME,
    GOOGLE_SLIDE_MIME,
    GoogleDriveSyncEngine,
)
from src.web.app import KnowledgeWebApp


def create_mock_jwt(payload: Dict[str, Any]) -> str:
    """Generate a mock JWT token for testing Google OIDC parsing."""
    header = {"alg": "RS256", "typ": "JWT"}
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("utf-8").rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"{h_b64}.{p_b64}.mock_signature"


class TestGoogleWorkspaceAndDriveSync(unittest.TestCase):
    """Test suite for Google Workspace SSO, JIT Provisioning, and Drive Synchronization."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user_db = os.path.join(self.temp_dir.name, "test_user.db")
        self.chat_db = os.path.join(self.temp_dir.name, "test_chat.db")
        self.audit_db = os.path.join(self.temp_dir.name, "test_audit.db")
        self.drive_db = os.path.join(self.temp_dir.name, "test_drive.db")

        self.app = KnowledgeWebApp(
            store_path=":memory:",
            default_provider=ProviderType.LITERT,
            gemini_api_key="AIzaSyTestSecretEnterpriseKey1234",
            gemini_model="gemini-3.5-flash-lite",
            user_db_path=self.user_db,
            chat_db_path=self.chat_db,
            audit_db_path=self.audit_db,
            drive_db_path=self.drive_db,
            google_domain="company.com",
            google_client_id="company-apps.apps.googleusercontent.com",
            google_allow_mock=True,
        )

        # Authenticate admin session for setup
        self.admin_login = self.app.login("admin", "admin123")
        self.admin_token = self.admin_login["session_id"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # =========================================================
    # TEST-039: Google Workspace OIDC & JIT Provisioning
    # =========================================================
    def test_test_039_google_oidc_domain_restriction_and_jit_provisioning(self) -> None:
        """TEST-039: Verify Google SSO login, domain restriction, and JIT standard user provisioning."""
        # 1. Valid corporate employee login with @company.com
        now = time.time()
        corp_payload = {
            "sub": "google_sub_1001",
            "email": "yamada.taro@example.com",
            "name": "Taro Yamada",
            "hd": "company.com",
            "aud": "company-apps.apps.googleusercontent.com",
            "exp": now + 3600,
        }
        corp_token = create_mock_jwt(corp_payload)

        # First login -> JIT provisioning
        res = self.app.handle_google_login(corp_token)
        self.assertTrue(res["is_new_user"])
        self.assertIn("token", res)
        user_info = res["user"]
        self.assertEqual(user_info["username"], "yamada.taro")
        self.assertEqual(user_info["display_name"], "Taro Yamada")
        # Strict security: Initial role is VIEWER (Standard employee, read/ask only)
        self.assertEqual(user_info["role"], RoleType.VIEWER.value)
        self.assertEqual(user_info["email"], "yamada.taro@example.com")

        # Verify session is valid and can perform chat
        session = self.app.rbac.get_session(res["token"])
        self.assertIsNotNone(session)
        self.assertEqual(session.username, "yamada.taro")

        # 2. Subsequent login with same user -> Existing account reused
        res_second = self.app.handle_google_login(corp_token)
        self.assertFalse(res_second["is_new_user"])
        self.assertEqual(res_second["user"]["username"], "yamada.taro")

        # 3. Non-corporate domain account (e.g. personal Gmail) rejection
        personal_payload = {
            "sub": "google_sub_9999",
            "email": "attacker@gmail.com",
            "name": "外部 アカウント",
            "hd": "",
            "aud": "company-apps.apps.googleusercontent.com",
            "exp": now + 3600,
        }
        personal_token = create_mock_jwt(personal_payload)
        with self.assertRaises(DomainRestrictionError):
            self.app.handle_google_login(personal_token)

        # 4. Suspended corporate employee rejection
        # Suspend yamada.taro using admin session
        self.app.toggle_user_status(
            target_username="yamada.taro",
            is_active=False,
            token=self.admin_token,
        )

        with self.assertRaises(UserSuspendedError):
            self.app.handle_google_login(corp_token)

        # 5. Expired token rejection
        expired_payload = dict(corp_payload)
        expired_payload["sub"] = "google_sub_1002"
        expired_payload["email"] = "suzuki@example.com"
        expired_payload["exp"] = now - 100
        expired_token = create_mock_jwt(expired_payload)
        with self.assertRaises(InvalidTokenError):
            self.app.handle_google_login(expired_token)

    # =========================================================
    # TEST-040: Docs/Sheets/Slides Export & Universal Parsing
    # =========================================================
    def test_test_040_google_native_export_and_sentence_chunking(self) -> None:
        """TEST-040: Verify Google Docs, Sheets, and Slides export and chunk ingestion."""
        sync_engine = self.app.drive_sync

        # 1. Google Docs export (text/plain)
        docs_raw = "第1条 目的。本規程は当社の情報セキュリティ管理を定める。第2条 適用範囲。全役職員に適用される。".encode("utf-8")
        text_doc, fmt_doc = sync_engine.export_google_file(
            file_id="gdoc_001",
            mime_type=GOOGLE_DOC_MIME,
            file_name="セキュリティ規程.gdoc",
            content_override=docs_raw,
        )
        self.assertEqual(fmt_doc, "TXT")
        self.assertIn("情報セキュリティ管理", text_doc)

        # 2. Google Sheets export (text/csv)
        sheets_raw = "部署名,予算額,責任者\nSales Department,5000000,Sato\n技術部,8000000,Suzuki".encode("utf-8")
        text_sheet, fmt_sheet = sync_engine.export_google_file(
            file_id="gsheet_001",
            mime_type=GOOGLE_SHEET_MIME,
            file_name="2026年度予算表.gsheet",
            content_override=sheets_raw,
        )
        self.assertEqual(fmt_sheet, "CSV")
        self.assertIn("Sales Department", text_sheet)
        self.assertIn("技術部", text_sheet)

        # 3. Google Slides export (text/plain)
        slides_raw = "スライド1: 全社方針サマリー\nAI技術の積極的活用を進めます。\n\nスライド2: 今期の重点課題\nセキュリティとコンプライアンスの遵守。".encode("utf-8")
        text_slide, fmt_slide = sync_engine.export_google_file(
            file_id="gslide_001",
            mime_type=GOOGLE_SLIDE_MIME,
            file_name="全社キックオフ発表資料.gslide",
            content_override=slides_raw,
        )
        self.assertEqual(fmt_slide, "TXT")
        self.assertIn("全社方針サマリー", text_slide)

        # 4. Ingest via sync_changes and verify Qdrant blocks and locators
        changes = [
            {
                "fileId": "gdoc_001",
                "name": "セキュリティ規程.gdoc",
                "mimeType": GOOGLE_DOC_MIME,
                "etag": "doc_etag_v1",
                "content_override": docs_raw,
            },
            {
                "fileId": "gsheet_001",
                "name": "2026年度予算表.gsheet",
                "mimeType": GOOGLE_SHEET_MIME,
                "etag": "sheet_etag_v1",
                "content_override": sheets_raw,
            },
        ]

        result = self.app.handle_drive_sync(self.admin_token, simulated_changes=changes)
        self.assertEqual(result["added"], 2)
        self.assertEqual(len(result["errors"]), 0)

        # Verify indexed knowledge blocks
        blocks = self.app.cms.store.list_blocks("セキュリティ規程")
        self.assertGreaterEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["document_title"], "セキュリティ規程.gdoc")
        self.assertIn("ブロック #1", blocks[0]["locator"])

    # =========================================================
    # TEST-041: Changes API Incremental Differential Sync
    # =========================================================
    def test_test_041_changes_api_incremental_differential_sync(self) -> None:
        """TEST-041: Verify incremental differential detection and update processing."""
        # 1. Initial sync with 2 files
        initial_changes = [
            {
                "fileId": "file_alpha",
                "name": "プロジェクト計画書.txt",
                "mimeType": "text/plain",
                "etag": "alpha_v1",
                "content_override": "プロジェクトAlphaの目標は新基幹システムの構築です。".encode("utf-8"),
            },
            {
                "fileId": "file_beta",
                "name": "仕様書_Beta.txt",
                "mimeType": "text/plain",
                "etag": "beta_v1",
                "content_override": "仕様書Betaの要件定義。認証方式にOIDCを採用。".encode("utf-8"),
            },
        ]

        res1 = self.app.handle_drive_sync(
            self.admin_token,
            simulated_changes=initial_changes,
            new_page_token="token_checkpoint_100",
        )
        self.assertEqual(res1["added"], 2)
        self.assertEqual(self.app.drive_sync.get_start_page_token(), "token_checkpoint_100")

        # 2. Incremental sync: file_alpha was updated, file_beta has same etag
        incremental_changes = [
            {
                "fileId": "file_alpha",
                "name": "プロジェクト計画書.txt",
                "mimeType": "text/plain",
                "etag": "alpha_v2",  # Updated ETag
                "content_override": "プロジェクトAlphaの更新版。AIエージェント統合を追加。".encode("utf-8"),
            },
            {
                "fileId": "file_beta",
                "name": "仕様書_Beta.txt",
                "mimeType": "text/plain",
                "etag": "beta_v1",  # Same ETag -> should skip
                "content_override": "仕様書Betaの要件定義。認証方式にOIDCを採用。".encode("utf-8"),
            },
        ]

        res2 = self.app.handle_drive_sync(
            self.admin_token,
            simulated_changes=incremental_changes,
            new_page_token="token_checkpoint_101",
        )

        self.assertEqual(res2["updated"], 1)
        self.assertEqual(res2["skipped_etag"], 1)
        self.assertEqual(self.app.drive_sync.get_start_page_token(), "token_checkpoint_101")

        # Verify updated content is searchable
        search_res = self.app.cms.store.search("AIエージェント統合")
        self.assertGreaterEqual(len(search_res), 1)
        self.assertIn("AIエージェント統合", search_res[0]["text"])

    # =========================================================
    # TEST-042: Deleted / Trashed File Immediate Complete Purge
    # =========================================================
    def test_test_042_deleted_or_trashed_file_immediate_complete_purge(self) -> None:
        """TEST-042: Verify deleted or trashed files are completely wiped from knowledge store."""
        # 1. Ingest file to be deleted
        file_to_delete = {
            "fileId": "secret_doc_999",
            "name": "廃止規定.txt",
            "mimeType": "text/plain",
            "etag": "purge_etag_1",
            "content_override": "旧業務プロセスに関する極秘手順書。機密指定。".encode("utf-8"),
        }
        self.app.handle_drive_sync(self.admin_token, simulated_changes=[file_to_delete])

        # Confirm it exists
        blocks = self.app.cms.store.list_blocks("旧業務プロセス")
        self.assertEqual(len(blocks), 1)

        # 2. Simulate Drive Changes API event: removed=True
        delete_event = [
            {
                "fileId": "secret_doc_999",
                "removed": True,
            }
        ]
        res_del = self.app.handle_drive_sync(self.admin_token, simulated_changes=delete_event)
        self.assertEqual(res_del["purged"], 1)

        # Verify block is purged completely from blocks catalog
        blocks_after = self.app.cms.store.list_blocks("廃止規定")
        self.assertEqual(len(blocks_after), 0)

        # Verify purged document does not appear in search hits
        search_hits = self.app.cms.store.search("旧業務プロセスに関する極秘手順書")
        purged_titles = [h.get("document_title") for h in search_hits]
        self.assertNotIn("廃止規定.txt", purged_titles)

        # 3. Simulate Drive trashed=True
        trashed_file = {
            "fileId": "trashed_doc_888",
            "name": "一時メモ.txt",
            "mimeType": "text/plain",
            "etag": "trash_etag_1",
            "content_override": "一時的な下書きメモ内容。".encode("utf-8"),
        }
        self.app.handle_drive_sync(self.admin_token, simulated_changes=[trashed_file])
        self.assertEqual(len(self.app.cms.store.list_blocks("一時メモ")), 1)

        trash_event = [
            {
                "fileId": "trashed_doc_888",
                "file": {"trashed": True},
            }
        ]
        res_trash = self.app.handle_drive_sync(self.admin_token, simulated_changes=trash_event)
        self.assertEqual(res_trash["purged"], 1)
        self.assertEqual(len(self.app.cms.store.list_blocks("一時メモ")), 0)

        search_trash = self.app.cms.store.search("一時的な下書きメモ内容")
        trash_titles = [h.get("document_title") for h in search_trash]
        self.assertNotIn("一時メモ.txt", trash_titles)

    # =========================================================
    # TEST-043: Target Folders Whitelist & Role ACL Access Control
    # =========================================================
    def test_test_043_target_folders_scope_and_role_acl_enforcement(self) -> None:
        """TEST-043: Verify folder whitelist limits ingestion scope, and role ACL restricts search."""
        # 1. Configure target folders:
        # - folder_pub: Viewer allowed
        # - folder_admin: Admin only
        folders = [
            {"folder_id": "f_public", "folder_name": "全社共有フォルダ", "required_role": "viewer"},
            {"folder_id": "f_admin_only", "folder_name": "役員機密フォルダ", "required_role": "admin"},
        ]
        self.app.handle_set_drive_folders(self.admin_token, folders)

        # 2. Ingest 3 files:
        # File 1 in f_public (Viewer OK)
        # File 2 in f_admin_only (Admin only)
        # File 3 in f_unauthorized (Not in whitelist)
        changes = [
            {
                "fileId": "file_pub_01",
                "name": "全社周知事項.txt",
                "mimeType": "text/plain",
                "parents": ["f_public"],
                "etag": "tag1",
                "content_override": "全社方針：福利厚生制度が拡充されました。".encode("utf-8"),
            },
            {
                "fileId": "file_admin_01",
                "name": "役員会議事録.txt",
                "mimeType": "text/plain",
                "parents": ["f_admin_only"],
                "etag": "tag2",
                "content_override": "極秘役員会決議：新会社設立及びM&A投資計画。".encode("utf-8"),
            },
            {
                "fileId": "file_ignored_01",
                "name": "未許可私用ファイル.txt",
                "mimeType": "text/plain",
                "parents": ["f_unauthorized"],
                "etag": "tag3",
                "content_override": "これは対象外フォルダのファイルです。".encode("utf-8"),
            },
        ]

        res = self.app.handle_drive_sync(self.admin_token, simulated_changes=changes)
        self.assertEqual(res["added"], 2)
        self.assertEqual(res["skipped_scope"], 1)

        # File 3 should NOT exist in knowledge store
        self.assertEqual(len(self.app.cms.store.list_blocks("未許可私用ファイル")), 0)

        # 3. Role-based ACL verification on Search
        # Viewer user search:
        # - Should see "全社周知事項"
        # - Should NOT see "役員会議事録" (Admin only)
        viewer_hits = self.app.cms.store.search(
            query="福利厚生 及び M&A投資計画",
            user_role="viewer",
        )
        viewer_titles = [h.get("document_title") for h in viewer_hits]
        self.assertIn("全社周知事項.txt", viewer_titles)
        self.assertNotIn("役員会議事録.txt", viewer_titles)

        # Admin user search:
        # - Should see both "全社周知事項" and "役員会議事録"
        admin_hits = self.app.cms.store.search(
            query="M&A投資計画",
            user_role="admin",
        )
        admin_titles = [h.get("document_title") for h in admin_hits]
        self.assertIn("役員会議事録.txt", admin_titles)

    # =========================================================
    # TEST-044: ETag Caching Skip & Error Quarantine Fault Tolerance
    # =========================================================
    def test_test_044_etag_caching_and_error_quarantine_resilience(self) -> None:
        """TEST-044: Verify redundant embeddings are skipped via ETag and corrupted files are quarantined."""
        # 1. Initial ingestion
        file_valid = {
            "fileId": "valid_file_1",
            "name": "正常ファイル.txt",
            "mimeType": "text/plain",
            "etag": "etag_valid_123",
            "content_override": "正常な業務手順マニュアルです。".encode("utf-8"),
        }
        res1 = self.app.handle_drive_sync(self.admin_token, simulated_changes=[file_valid])
        self.assertEqual(res1["added"], 1)

        # 2. Re-sync with exact same ETag -> Skip
        res2 = self.app.handle_drive_sync(self.admin_token, simulated_changes=[file_valid])
        self.assertEqual(res2["skipped_etag"], 1)
        self.assertEqual(res2["added"], 0)

        # 3. Fault Tolerance: Mix a corrupted file into the sync batch
        # We simulate a corrupted item that raises an exception during processing
        class CorruptedChange(dict):
            def get(self, key, default=None):
                if key == "content_override":
                    raise RuntimeError("Simulated drive download network I/O corruption")
                return super().get(key, default)

        corrupted_item = CorruptedChange(
            {
                "fileId": "corrupted_file_2",
                "name": "破損ファイル.pdf",
                "mimeType": "application/pdf",
                "etag": "etag_bad_999",
            }
        )

        valid_item_2 = {
            "fileId": "valid_file_3",
            "name": "正常ファイル第2弾.txt",
            "mimeType": "text/plain",
            "etag": "etag_valid_456",
            "content_override": "2件目の正常なファイルです。".encode("utf-8"),
        }

        # Sync batch containing 1 corrupted item and 1 valid item
        res3 = self.app.handle_drive_sync(
            self.admin_token,
            simulated_changes=[corrupted_item, valid_item_2],
        )

        # Verify error quarantine: The sync job completes without crashing!
        self.assertEqual(res3["added"], 1)
        self.assertEqual(len(res3["errors"]), 1)
        self.assertEqual(res3["errors"][0]["file_id"], "corrupted_file_2")
        self.assertIn("Simulated drive download network I/O corruption", res3["errors"][0]["error"])

        # Check sync status reflects warning
        status = self.app.handle_get_drive_status(self.admin_token)
        self.assertEqual(status["status"], "COMPLETED_WITH_WARNINGS")
        self.assertIn("エラーが隔離されました", status["last_error"])


if __name__ == "__main__":
    unittest.main()
