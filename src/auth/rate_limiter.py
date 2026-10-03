"""Thread-safe In-Memory Rate Limiter for GemmaCore Mac API Endpoints.

Provides sliding window rate limiting to protect against:
- Brute-force credential guessing on /api/v1/auth/login
- Account Lockout Denial-of-Service (Lockout DoS)
- Excessive resource consumption on /api/v1/chat
- General API abuse
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional, Tuple


class RateLimiter:
    """Sliding window rate limiter with automatic stale key eviction."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._history: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()

    def is_allowed(self, key: str) -> Tuple[bool, float]:
        """Check if an action from the given key (e.g. IP address or username) is allowed.

        Returns (allowed, retry_after_seconds).
        """
        now = time.time()
        with self._lock:
            # Periodic cleanup every 60 seconds
            if now - self._last_cleanup > 60.0:
                self._evict_stale_entries(now)
                self._last_cleanup = now

            timestamps = self._history.get(key, [])
            # Filter timestamps within the current sliding window
            cutoff = now - self.window_seconds
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= self.max_requests:
                oldest = timestamps[0]
                retry_after = max(1.0, (oldest + self.window_seconds) - now)
                self._history[key] = timestamps
                return False, retry_after

            timestamps.append(now)
            self._history[key] = timestamps
            return True, 0.0

    def reset(self, key: Optional[str] = None) -> None:
        """Reset history for a specific key, or all keys."""
        with self._lock:
            if key is not None:
                self._history.pop(key, None)
            else:
                self._history.clear()

    def _evict_stale_entries(self, now: float) -> None:
        cutoff = now - self.window_seconds
        keys_to_delete = []
        for k, ts in self._history.items():
            valid = [t for t in ts if t > cutoff]
            if not valid:
                keys_to_delete.append(k)
            else:
                self._history[k] = valid
        for k in keys_to_delete:
            del self._history[k]
