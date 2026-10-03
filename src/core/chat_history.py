"""Multi-Session Chat History Management Module.

Provides ChatGPT-like persistent thread management:
- Create, list, retrieve, update title, and delete conversation threads.
- Message history preservation with timestamps and citation links.
- Automatic thread naming from the first user prompt.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Individual message in a conversation thread."""
    message_id: str
    role: str  # "user" or "assistant"
    content: str
    citation_links: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "citation_links": self.citation_links,
            "timestamp": self.timestamp,
        }


@dataclass
class ChatThread:
    """Conversation thread session."""
    thread_id: str
    user_id: str
    title: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: List[ChatMessage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
        }


class ChatHistoryManager:
    """Manages multi-thread chat sessions backed by SQLite for robust local persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._mem_conn: Optional[sqlite3.Connection] = None
        if db_path is None:
            # Default to local data directory
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scratch"))
            os.makedirs(base_dir, exist_ok=True)
            self.db_path = os.path.join(base_dir, "chat_history.db")
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
        """Create tables for threads and messages if not existing."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                    thread_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citation_links TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES chat_threads(thread_id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

    def create_thread(self, user_id: str, title: str = "新しいチャット") -> Dict[str, Any]:
        """Create a new conversation thread."""
        thread_id = f"th_{uuid.uuid4().hex[:12]}"
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO chat_threads (thread_id, user_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (thread_id, user_id, title, now, now),
            )
            conn.commit()

        logger.info(f"Created chat thread {thread_id} for user {user_id}")
        return {
            "thread_id": thread_id,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }

    def list_threads(self, user_id: str) -> List[Dict[str, Any]]:
        """List all threads belonging to the user sorted by latest update."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT t.thread_id, t.user_id, t.title, t.created_at, t.updated_at,
                       COUNT(m.message_id) AS message_count
                FROM chat_threads t
                LEFT JOIN chat_messages m ON t.thread_id = m.thread_id
                WHERE t.user_id = ?
                GROUP BY t.thread_id
                ORDER BY t.updated_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_thread(self, thread_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve thread with all messages."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT thread_id, user_id, title, created_at, updated_at FROM chat_threads WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id),
            )
            thread_row = cursor.fetchone()
            if not thread_row:
                return None

            msg_cursor = conn.execute(
                "SELECT message_id, role, content, citation_links, timestamp FROM chat_messages WHERE thread_id = ? ORDER BY timestamp ASC",
                (thread_id,),
            )
            messages = []
            for m in msg_cursor.fetchall():
                messages.append({
                    "message_id": m["message_id"],
                    "role": m["role"],
                    "content": m["content"],
                    "citation_links": json.loads(m["citation_links"]),
                    "timestamp": m["timestamp"],
                })

            thread_dict = dict(thread_row)
            thread_dict["messages"] = messages
            return thread_dict

    def add_message(
        self,
        thread_id: str,
        user_id: str,
        role: str,
        content: str,
        citation_links: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Append a message to thread and auto-generate title if it's the first user message."""
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = time.time()
        links_json = json.dumps(citation_links or [], ensure_ascii=False)

        with self._get_connection() as conn:
            # Check thread ownership
            t_row = conn.execute(
                "SELECT title FROM chat_threads WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id),
            ).fetchone()
            if not t_row:
                raise KeyError(f"Thread '{thread_id}' not found for user '{user_id}'")

            # Check if this is the first message to update title
            count = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE thread_id = ?", (thread_id,)).fetchone()[0]
            if count == 0 and role == "user":
                # Auto title from first prompt
                auto_title = content.strip().replace("\n", " ")
                if len(auto_title) > 24:
                    auto_title = auto_title[:24] + "..."
                conn.execute(
                    "UPDATE chat_threads SET title = ?, updated_at = ? WHERE thread_id = ?",
                    (auto_title, now, thread_id),
                )
            else:
                conn.execute("UPDATE chat_threads SET updated_at = ? WHERE thread_id = ?", (now, thread_id))

            conn.execute(
                "INSERT INTO chat_messages (message_id, thread_id, role, content, citation_links, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, thread_id, role, content, links_json, now),
            )
            conn.commit()

        return {
            "message_id": msg_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "citation_links": citation_links or [],
            "timestamp": now,
        }

    def update_thread_title(self, thread_id: str, user_id: str, new_title: str) -> bool:
        """Rename thread title."""
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE chat_threads SET title = ?, updated_at = ? WHERE thread_id = ? AND user_id = ?",
                (new_title, now, thread_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_thread(self, thread_id: str, user_id: str) -> bool:
        """Delete thread and all associated messages."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM chat_messages WHERE thread_id = ?", (thread_id,))
            cur = conn.execute(
                "DELETE FROM chat_threads WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def clear_all_threads(self, user_id: Optional[str] = None) -> int:
        """Clear chat threads and messages for a specific user, or for all users if user_id is None."""
        with self._get_connection() as conn:
            if user_id is not None:
                t_rows = conn.execute("SELECT thread_id FROM chat_threads WHERE user_id = ?", (user_id,)).fetchall()
                thread_ids = [r["thread_id"] for r in t_rows]
                if thread_ids:
                    placeholders = ",".join("?" for _ in thread_ids)
                    conn.execute(f"DELETE FROM chat_messages WHERE thread_id IN ({placeholders})", thread_ids)
                    cur = conn.execute("DELETE FROM chat_threads WHERE user_id = ?", (user_id,))
                    count = cur.rowcount
                else:
                    count = 0
            else:
                conn.execute("DELETE FROM chat_messages")
                cur = conn.execute("DELETE FROM chat_threads")
                count = cur.rowcount
            conn.commit()
            logger.info(f"Cleared {count} chat threads (user_id={user_id})")
            return count
