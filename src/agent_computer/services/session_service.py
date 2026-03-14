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
        self._observation_frames: dict[str, dict[str, Any]] = {}
        self._observation_token: str | None = None
        self._last_observation_cleanup_at: str | None = None
        self._browser_assist_token: str | None = None
        self._browser_assist_connected: bool = False
        self._browser_assist_last_keepalive_at: str | None = None
        self._browser_assist_last_page_url: str | None = None
        self._browser_assist_last_page_title: str | None = None
        self._browser_assist_last_error: str | None = None
        self._live_output: dict[str, Any] | None = None

    def set_last_capture(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_capture = payload

    def set_last_window(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._last_window = payload

    def set_observation_token(self, token: str) -> None:
        with self._lock:
            self._observation_token = token

    def set_latest_frame(self, mode: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._observation_frames[mode] = payload

    def get_latest_frame(self, mode: str) -> dict[str, Any] | None:
        with self._lock:
            frame = self._observation_frames.get(mode)
            return None if frame is None else dict(frame)

    def set_last_observation_cleanup_at(self, value: str) -> None:
        with self._lock:
            self._last_observation_cleanup_at = value

    def set_browser_assist_token(self, token: str) -> None:
        with self._lock:
            self._browser_assist_token = token

    def set_browser_assist_connected(self, connected: bool) -> None:
        with self._lock:
            self._browser_assist_connected = connected

    def set_browser_assist_last_keepalive_at(self, value: str) -> None:
        with self._lock:
            self._browser_assist_last_keepalive_at = value

    def set_browser_assist_last_page_url(self, url: str | None) -> None:
        with self._lock:
            self._browser_assist_last_page_url = url

    def set_browser_assist_last_page_title(self, title: str | None) -> None:
        with self._lock:
            self._browser_assist_last_page_title = title

    def set_browser_assist_last_error(self, value: str | None) -> None:
        with self._lock:
            self._browser_assist_last_error = value

    def set_live_output(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._live_output = dict(payload)

    def get_live_output(self) -> dict[str, Any] | None:
        with self._lock:
            payload = self._live_output
            return None if payload is None else dict(payload)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            preview = self._observation_frames.get("preview")
            grid = self._observation_frames.get("grid")
            live_output = self._live_output
            return {
                "pid": os.getpid(),
                "started_at": self._started_at,
                "uptime_seconds": round(max(0.0, time.time() - self._started_at), 3),
                "last_capture_path": None if not self._last_capture else self._last_capture.get("image_path"),
                "last_window_title": None if not self._last_window else self._last_window.get("title"),
                "observation_token_present": self._observation_token is not None,
                "observation_preview_updated_at": None if preview is None else preview.get("updated_at"),
                "observation_grid_updated_at": None if grid is None else grid.get("updated_at"),
                "last_observation_cleanup_at": self._last_observation_cleanup_at,
                "browser_assist_token_present": self._browser_assist_token is not None,
                "browser_assist_connected": self._browser_assist_connected,
                "browser_assist_last_keepalive_at": self._browser_assist_last_keepalive_at,
                "browser_assist_last_page_url": self._browser_assist_last_page_url,
                "browser_assist_last_page_title": self._browser_assist_last_page_title,
                "browser_assist_last_error": self._browser_assist_last_error,
                "live_output_status": None if live_output is None else live_output.get("status"),
                "live_output_updated_at": None if live_output is None else live_output.get("updated_at"),
                "live_output_heartbeat_at": None if live_output is None else live_output.get("heartbeat_at"),
                "live_output_seq": 0 if live_output is None else int(live_output.get("seq", 0)),
                "live_output_session_id": None if live_output is None else live_output.get("session_id"),
                "live_output_source_rollout_path": None if live_output is None else live_output.get("source_rollout_path"),
            }
