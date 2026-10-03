"""Structured Audit Trail, Diagnostics Logging, and Configurable Retention Module.

Key Features:
- Comprehensive Audit Trail: who, when, what IP, what action, on which resource, success/failure.
- Detailed System Diagnostics: component-level error tracking, sanitized stack traces, latency.
- Configurable Retention Period: 7, 30, 90, 180, up to 365 days (1 year max).
- Automatic Expired Log Purging: keeps storage clean while satisfying enterprise compliance.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from src.auth.rbac import sanitize_text

logger = logging.getLogger(__name__)


class AuditLogger:
    """Manages audit trails, diagnostics logs, and retention policies."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scratch"))
            os.makedirs(base_dir, exist_ok=True)
            self.db_path = os.path.join(base_dir, "system_audit.db")
        elif db_path == ":memory:":
            self.db_path = ":memory:"
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
        else:
            self.db_path = db_path

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create audit, diagnostics, and config tables."""
        with self._get_connection() as conn:
            # Audit trail table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    iso_time TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    status TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    details TEXT NOT NULL
                )
                """
            )
            # Diagnostics log table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS diagnostics_logs (
                    diag_id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    iso_time TEXT NOT NULL,
                    component TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    stack_trace TEXT NOT NULL,
                    context_json TEXT NOT NULL
                )
                """
            )
            # Retention settings table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            # Default retention: 365 days (1 year)
            conn.execute(
                "INSERT OR IGNORE INTO system_config (key, value) VALUES ('retention_days', '365')"
            )
            conn.commit()

    # ---------------------------------------------------------
    # Retention Management
    # ---------------------------------------------------------
    def get_retention_days(self) -> int:
        """Get current log retention period in days."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM system_config WHERE key = 'retention_days'").fetchone()
            return int(row["value"]) if row else 365

    def set_retention_days(self, days: int) -> int:
        """Set log retention period in days (7, 30, 90, 180, 365)."""
        if days not in [7, 30, 90, 180, 365]:
            days = min(max(days, 7), 365)  # Clamp between 7 and 365

        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_config (key, value) VALUES ('retention_days', ?)",
                (str(days),),
            )
            conn.commit()

        logger.info(f"Log retention period updated to {days} days.")
        # Trigger purge upon policy change
        self.purge_expired_logs()
        return days

    def purge_expired_logs(self) -> Dict[str, int]:
        """Purge logs older than retention period."""
        days = self.get_retention_days()
        cutoff = time.time() - (days * 86400)

        with self._get_connection() as conn:
            cur1 = conn.execute("DELETE FROM audit_logs WHERE timestamp < ?", (cutoff,))
            audit_purged = cur1.rowcount

            cur2 = conn.execute("DELETE FROM diagnostics_logs WHERE timestamp < ?", (cutoff,))
            diag_purged = cur2.rowcount

            conn.commit()

        if audit_purged > 0 or diag_purged > 0:
            logger.info(f"Purged {audit_purged} audit logs and {diag_purged} diagnostics logs older than {days} days.")

        return {"audit_purged": audit_purged, "diagnostics_purged": diag_purged, "retention_days": days}

    # ---------------------------------------------------------
    # Audit Trail Recording & Query
    # ---------------------------------------------------------
    def record_audit(
        self,
        username: str,
        role: str,
        action: str,
        resource: str = "",
        status: str = "SUCCESS",
        ip_address: str = "127.0.0.1",
        details: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record structured user action audit log."""
        log_id = f"aud_{uuid.uuid4().hex[:12]}"
        now = time.time()
        iso_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        clean_details = sanitize_text(details)
        uid = user_id or username

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (log_id, timestamp, iso_time, user_id, username, role, action, resource, status, ip_address, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, now, iso_time, uid, username, role, action, resource, status, ip_address, clean_details),
            )
            conn.commit()

        return {
            "log_id": log_id,
            "timestamp": now,
            "iso_time": iso_time,
            "username": username,
            "role": role,
            "action": action,
            "resource": resource,
            "status": status,
            "ip_address": ip_address,
            "details": clean_details,
        }

    def query_audit_logs(
        self,
        username: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit logs with optional filters."""
        query = "SELECT * FROM audit_logs"
        params: List[Any] = []
        conditions: List[str] = []

        if username:
            conditions.append("username = ?")
            params.append(username)
        if action:
            conditions.append("action = ?")
            params.append(action)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    # ---------------------------------------------------------
    # Diagnostics Recording & Query
    # ---------------------------------------------------------
    def record_diagnostics(
        self,
        component: str,
        level: str,
        message: str,
        stack_trace: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record system diagnostic or fault trace."""
        diag_id = f"diag_{uuid.uuid4().hex[:12]}"
        now = time.time()
        iso_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        clean_msg = sanitize_text(message)
        clean_stack = sanitize_text(stack_trace)
        clean_ctx = sanitize_text(json.dumps(context or {}, ensure_ascii=False))

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO diagnostics_logs (diag_id, timestamp, iso_time, component, level, message, stack_trace, context_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (diag_id, now, iso_time, component, level, clean_msg, clean_stack, clean_ctx),
            )
            conn.commit()

        return {
            "diag_id": diag_id,
            "timestamp": now,
            "iso_time": iso_time,
            "component": component,
            "level": level,
            "message": clean_msg,
            "stack_trace": clean_stack,
        }

    def query_diagnostics_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Query system diagnostics logs."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM diagnostics_logs ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
