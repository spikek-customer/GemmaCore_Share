"""Google Drive Incremental Synchronizer and Native Export Pipeline.

Supports:
- Google Drive API v3 Changes API (Incremental Differential Sync)
- Google Native Export: Docs -> text/plain, Sheets -> text/csv, Slides -> text/plain
- Universal Document Parser Integration (PDF, Word, Excel, PowerPoint, TXT)
- Real-time Knowledge Block & Qdrant Vector purging on file deletion or trash
- ETag / MD5 checksum caching to skip redundant vector embeddings
- Error Quarantine: Resilient sync pipeline that isolates corrupted files without crashing
- Whitelist Target Folders / Shared Drives configuration with Role-based ACL mapping
- SQLite State Persistence across server restarts
"""

from __future__ import annotations

import datetime
import io
import json
import logging
import os
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.rag.chunking import chunk_text_sentence_aware
from src.rag.parser import UniversalDocumentParser
from src.rag.service import KnowledgeCMSService

logger = logging.getLogger(__name__)


GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
GOOGLE_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
GOOGLE_SLIDE_MIME = "application/vnd.google-apps.presentation"


class GoogleDriveSyncEngine:
    """Enterprise Google Drive differential synchronizer and knowledge ingestion engine."""

    def __init__(
        self,
        cms_service: KnowledgeCMSService,
        db_path: Optional[str] = None,
        drive_client: Optional[Any] = None,
    ) -> None:
        self.cms = cms_service
        self.drive_client = drive_client

        if db_path:
            self.db_path = db_path
        else:
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scratch")
            os.makedirs(base_dir, exist_ok=True)
            self.db_path = os.path.join(base_dir, "drive_sync.db")

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize sync tables for checkpointing, file tracking, and target folders."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS synced_files (
                    file_id TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    etag TEXT,
                    folder_id TEXT,
                    required_role TEXT DEFAULT 'viewer',
                    block_count INTEGER DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS target_folders (
                    folder_id TEXT PRIMARY KEY,
                    folder_name TEXT NOT NULL,
                    required_role TEXT DEFAULT 'viewer',
                    is_active INTEGER DEFAULT 1,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()

    # ---------------------------------------------------------
    # Target Folders & Whitelist Management
    # ---------------------------------------------------------
    def set_target_folders(self, folders: List[Dict[str, Any]]) -> None:
        """Configure whitelisted target folders with ACL access roles."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("DELETE FROM target_folders")
            for f in folders:
                folder_id = str(f.get("folder_id", "")).strip()
                if not folder_id:
                    continue
                name = str(f.get("folder_name", folder_id)).strip()
                role = str(f.get("required_role", "viewer")).strip().lower()
                conn.execute(
                    """
                    INSERT INTO target_folders (folder_id, folder_name, required_role, is_active, created_at)
                    VALUES (?, ?, ?, 1, ?)
                    """,
                    (folder_id, name, role, now),
                )
            conn.commit()
        logger.info(f"Configured {len(folders)} Drive target folders.")

    def get_target_folders(self) -> List[Dict[str, Any]]:
        """Retrieve configured target folders."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM target_folders WHERE is_active = 1").fetchall()
            return [
                {
                    "folder_id": r["folder_id"],
                    "folder_name": r["folder_name"],
                    "required_role": r["required_role"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    # ---------------------------------------------------------
    # State & Checkpoint Accessors
    # ---------------------------------------------------------
    def get_start_page_token(self) -> Optional[str]:
        """Fetch current saved changes token."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM sync_state WHERE key = 'start_page_token'").fetchone()
            return row["value"] if row else None

    def save_start_page_token(self, token: str) -> None:
        """Persist latest changes token."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('start_page_token', ?, ?)",
                (token, now),
            )
            conn.commit()

    def get_sync_status(self) -> Dict[str, Any]:
        """Retrieve current sync status, timestamps, and statistics."""
        with self._get_connection() as conn:
            st_row = conn.execute("SELECT value, updated_at FROM sync_state WHERE key = 'status'").fetchone()
            status = st_row["value"] if st_row else "IDLE"

            time_row = conn.execute("SELECT value FROM sync_state WHERE key = 'last_sync_time'").fetchone()
            last_sync_time = time_row["value"] if time_row else "未実行"

            err_row = conn.execute("SELECT value FROM sync_state WHERE key = 'last_error'").fetchone()
            last_error = err_row["value"] if err_row else None

            count_row = conn.execute("SELECT COUNT(*) AS total, SUM(block_count) AS total_blocks FROM synced_files").fetchone()
            total_files = count_row["total"] if count_row else 0
            total_blocks = count_row["total_blocks"] or 0

        target_folders = self.get_target_folders()

        return {
            "status": status,
            "last_sync_time": last_sync_time,
            "last_error": last_error,
            "synced_file_count": total_files,
            "indexed_block_count": total_blocks,
            "target_folder_count": len(target_folders),
            "target_folders": target_folders,
        }

    # ---------------------------------------------------------
    # Native Format Exporters
    # ---------------------------------------------------------
    def export_google_file(
        self,
        file_id: str,
        mime_type: str,
        file_name: str,
        content_override: Optional[bytes] = None,
    ) -> Tuple[str, str]:
        """Export Google native docs into plain text or CSV.

        Returns (extracted_text, format_name).
        """
        # If raw mock bytes or simulated content is passed
        if content_override is not None:
            raw_text = content_override.decode("utf-8", errors="replace")
            if mime_type == GOOGLE_SHEET_MIME:
                return raw_text, "CSV"
            return raw_text, "TXT"

        if not self.drive_client:
            # Standalone fallback: generate informational template if client not wired
            return f"【{file_name}】(Google Docs 内容同期)", "TXT"

        try:
            if mime_type == GOOGLE_DOC_MIME:
                # Export Docs to text/plain
                res = self.drive_client.files().export(fileId=file_id, mimeType="text/plain").execute()
                text = res.decode("utf-8", errors="replace") if isinstance(res, bytes) else str(res)
                return text, "TXT"
            elif mime_type == GOOGLE_SHEET_MIME:
                # Export Sheets to text/csv
                res = self.drive_client.files().export(fileId=file_id, mimeType="text/csv").execute()
                text = res.decode("utf-8", errors="replace") if isinstance(res, bytes) else str(res)
                return text, "CSV"
            elif mime_type == GOOGLE_SLIDE_MIME:
                # Export Slides to text/plain
                res = self.drive_client.files().export(fileId=file_id, mimeType="text/plain").execute()
                text = res.decode("utf-8", errors="replace") if isinstance(res, bytes) else str(res)
                return text, "TXT"
            else:
                # Standard binary download (PDF, docx, etc.)
                req = self.drive_client.files().get_media(fileId=file_id)
                fh = io.BytesIO()
                downloader = self.drive_client.http.MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                fh.seek(0)
                parsed = UniversalDocumentParser.parse_file(file_name, fh.read())
                combined_text = "\n\n".join(s.text for s in parsed.sections if s.text.strip())
                return combined_text, parsed.file_type
        except Exception as e:
            logger.error(f"Failed to export Google Drive file '{file_id}' ({file_name}): {e}")
            raise

    # ---------------------------------------------------------
    # File Purge (On Delete or Trash)
    # ---------------------------------------------------------
    def purge_file(self, file_id: str) -> int:
        """Purge all knowledge blocks and vector points when a file is deleted or trashed in Drive."""
        purged_blocks = self.cms.delete_document(file_id)
        with self._get_connection() as conn:
            conn.execute("DELETE FROM synced_files WHERE file_id = ?", (file_id,))
            conn.commit()
        logger.info(f"Drive Purge: File '{file_id}' was deleted/trashed. Removed {purged_blocks} blocks from Qdrant.")
        return purged_blocks

    # ---------------------------------------------------------
    # Core Incremental Differential Sync Pipeline
    # ---------------------------------------------------------
    def sync_changes(
        self,
        simulated_changes: Optional[List[Dict[str, Any]]] = None,
        new_page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform differential sync using Drive Changes API.

        Processes only changed, added, or deleted files since last checkpoint.
        Uses ETag to avoid re-embedding unmodified files.
        Isolates corrupted files without interrupting remaining items.
        """
        now = time.time()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('status', 'SYNCING', ?)",
                (now,),
            )
            conn.commit()

        target_folders = {tf["folder_id"]: tf for tf in self.get_target_folders()}

        # Result metrics
        stats = {
            "processed": 0,
            "added": 0,
            "updated": 0,
            "purged": 0,
            "skipped_etag": 0,
            "skipped_scope": 0,
            "errors": [],
        }

        changes_to_process = simulated_changes or []

        # If live client is available and no simulated changes passed
        if self.drive_client and not simulated_changes:
            try:
                saved_token = self.get_start_page_token()
                if not saved_token:
                    # Get fresh token
                    resp = self.drive_client.changes().getStartPageToken().execute()
                    saved_token = resp.get("startPageToken")
                    self.save_start_page_token(saved_token)

                page_token = saved_token
                while page_token:
                    response = self.drive_client.changes().list(
                        pageToken=page_token,
                        fields="nextPageToken, newStartPageToken, changes(fileId, removed, file(id, name, mimeType, trashed, parents, md5Checksum, version))",
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                    ).execute()

                    for change in response.get("changes", []):
                        changes_to_process.append(change)

                    if "newStartPageToken" in response:
                        new_page_token = response["newStartPageToken"]
                    page_token = response.get("nextPageToken")
            except Exception as e:
                err_msg = f"Drive Changes API query failed: {e}"
                logger.error(err_msg)
                with self._get_connection() as conn:
                    conn.execute("INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('status', 'ERROR', ?)", (now,))
                    conn.execute("INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('last_error', ?, ?)", (err_msg, now))
                    conn.commit()
                raise

        # Process the changes feed
        for item in changes_to_process:
            stats["processed"] += 1
            file_id = item.get("fileId") or item.get("id")
            if not file_id:
                continue

            is_removed = bool(item.get("removed"))
            file_data = item.get("file", {}) or item
            is_trashed = bool(file_data.get("trashed"))
            file_name = file_data.get("name", file_id)
            mime_type = file_data.get("mimeType", "")
            parents = file_data.get("parents", [])
            etag = str(file_data.get("etag") or file_data.get("md5Checksum") or file_data.get("version") or "")

            # 1. Deletion or Trash Check -> Immediate Complete Purge
            if is_removed or is_trashed:
                purged_count = self.purge_file(file_id)
                stats["purged"] += 1
                continue

            # 2. Scope / Target Folder Whitelist Check
            matched_folder = None
            if target_folders:
                for p in parents:
                    if p in target_folders:
                        matched_folder = target_folders[p]
                        break
                if not matched_folder:
                    # Outside whitelisted folders -> Skip and purge if previously synced
                    if self._is_previously_synced(file_id):
                        self.purge_file(file_id)
                        stats["purged"] += 1
                    stats["skipped_scope"] += 1
                    continue

            required_role = matched_folder["required_role"] if matched_folder else "viewer"
            folder_id = matched_folder["folder_id"] if matched_folder else (parents[0] if parents else "")

            # 3. ETag Check -> Skip redundant embedding if content has not changed
            if etag and self._has_matching_etag(file_id, etag):
                stats["skipped_etag"] += 1
                logger.debug(f"ETag match for '{file_name}' ({file_id}). Skipped re-embedding.")
                continue

            # 4. Extract and Ingest with Error Quarantine
            try:
                content_override = item.get("content_override")
                text_content, format_type = self.export_google_file(
                    file_id=file_id,
                    mime_type=mime_type,
                    file_name=file_name,
                    content_override=content_override,
                )

                if not text_content.strip():
                    logger.warning(f"File '{file_name}' ({file_id}) produced empty text. Skipped.")
                    continue

                # Remove previous blocks if updating
                is_existing = self._is_previously_synced(file_id)
                if is_existing:
                    self.cms.delete_document(file_id)
                    stats["updated"] += 1
                else:
                    stats["added"] += 1

                # Ingest into vector store with sentence boundary preservation
                chunks = chunk_text_sentence_aware(
                    text=text_content,
                    chunk_size=500,
                    overlap=80,
                    locator=f"{file_name} (Drive同期)",
                    heading=file_name,
                )

                for draft in chunks:
                    block_id = f"gdrive_{file_id[:8]}_{draft.ordinal}"
                    self.cms.store.add_or_update_block(
                        block_id=block_id,
                        text=draft.text,
                        document_id=file_id,
                        document_title=file_name,
                        locator=f"{file_name} (ブロック #{draft.ordinal + 1})",
                        metadata={
                            "source": "google_drive",
                            "file_id": file_id,
                            "folder_id": folder_id,
                            "required_role": required_role,
                            "mime_type": mime_type,
                            "format_type": format_type,
                            "synced_at": now_str,
                        },
                    )

                # Update SQLite synced_files catalog
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO synced_files
                        (file_id, file_name, mime_type, etag, folder_id, required_role, block_count, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (file_id, file_name, mime_type, etag, folder_id, required_role, len(chunks), now),
                    )
                    conn.commit()

                logger.info(f"Drive Sync Ingested: '{file_name}' ({file_id}) -> {len(chunks)} blocks (role: {required_role}).")
            except Exception as e:
                # Error Quarantine: Record error and isolate without failing the entire batch
                logger.error(f"Error quarantined for file '{file_name}' ({file_id}): {e}")
                stats["errors"].append({"file_id": file_id, "file_name": file_name, "error": str(e)})

        # Save checkpoint page token if provided
        if new_page_token:
            self.save_start_page_token(new_page_token)

        # Update final status
        final_status = "SUCCESS" if not stats["errors"] else "COMPLETED_WITH_WARNINGS"
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('status', ?, ?)",
                (final_status, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('last_sync_time', ?, ?)",
                (now_str, now),
            )
            if stats["errors"]:
                conn.execute(
                    "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES ('last_error', ?, ?)",
                    (f"{len(stats['errors'])} 件のエラーが隔離されました。", now),
                )
            else:
                conn.execute("DELETE FROM sync_state WHERE key = 'last_error'")
            conn.commit()

        logger.info(
            f"Drive Incremental Sync completed: {stats['processed']} processed, "
            f"{stats['added']} added, {stats['updated']} updated, {stats['purged']} purged, "
            f"{stats['skipped_etag']} etag skipped, {len(stats['errors'])} errors."
        )
        return stats

    def _is_previously_synced(self, file_id: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT 1 FROM synced_files WHERE file_id = ?", (file_id,)).fetchone()
            return row is not None

    def _has_matching_etag(self, file_id: str, current_etag: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT etag FROM synced_files WHERE file_id = ?", (file_id,)).fetchone()
            if row and row["etag"] and row["etag"] == current_etag:
                return True
            return False
