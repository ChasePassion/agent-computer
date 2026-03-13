from __future__ import annotations

import os
import threading
import time
from typing import Any


class SessionService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started_at = time.time()
        self._last_capture: dict[str, Any] | None = None
        self._last_window: dict[str, Any] | None = None

    def set_last_capture(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_capture = payload

    def set_last_window(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_window = payload

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "pid": os.getpid(),
                "started_at": self._started_at,
                "uptime_seconds": round(max(0.0, time.time() - self._started_at), 3),
                "last_capture_path": None if not self._last_capture else self._last_capture.get("image_path"),
                "last_window_title": None if not self._last_window else self._last_window.get("title"),
            }
