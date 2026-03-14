from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
import threading
from typing import Any, Literal

from agent_computer.runtime import (
    DEFAULT_LIVE_OUTPUT_MAX_CHARS,
    DEFAULT_LIVE_OUTPUT_MAX_ITEMS,
    DEFAULT_LIVE_OUTPUT_STALE_AFTER_SEC,
    live_output_latest_path,
    read_json,
    write_json,
)
from agent_computer.services.session_service import SessionService

LiveOutputKind = Literal["commentary", "final", "tool"]
LiveOutputStatus = Literal["running", "idle", "no_output"]


class LiveOutputService:
    def __init__(
        self,
        session: SessionService,
        *,
        max_items: int = DEFAULT_LIVE_OUTPUT_MAX_ITEMS,
        max_chars: int = DEFAULT_LIVE_OUTPUT_MAX_CHARS,
        stale_after_sec: int = DEFAULT_LIVE_OUTPUT_STALE_AFTER_SEC,
    ) -> None:
        self.session = session
        self.max_items = max(1, max_items)
        self.max_chars = max(256, max_chars)
        self.stale_after_sec = max(1, stale_after_sec)
        self._lock = threading.RLock()
        self._recent: deque[dict[str, Any]] = deque()
        self._seq = 0
        self._status: LiveOutputStatus = "no_output"
        self._updated_at: str | None = None
        self._heartbeat_at: str | None = None
        self._latest_text: str | None = None
        self._truncated = False
        self._session_id = "active"
        self._source_rollout_path: str | None = None
        self.load_from_disk()

    def load_from_disk(self) -> dict[str, Any]:
        path = live_output_latest_path()
        if not path.exists():
            snapshot = self._snapshot_locked()
            self.session.set_live_output(snapshot)
            return snapshot

        try:
            payload = read_json(path)
        except (OSError, TypeError, ValueError):
            snapshot = self._snapshot_locked()
            self.session.set_live_output(snapshot)
            return snapshot

        with self._lock:
            self._seq = max(0, int(payload.get("seq", 0)))
            status = str(payload.get("status", "no_output"))
            self._status = status if status in {"running", "idle", "no_output"} else "no_output"
            self._updated_at = self._normalize_optional_text(payload.get("updated_at"))
            self._heartbeat_at = self._normalize_optional_text(payload.get("heartbeat_at"))
            self._latest_text = self._normalize_optional_text(payload.get("latest_text"))
            self._truncated = bool(payload.get("truncated", False))
            self._session_id = self._normalize_optional_text(payload.get("session_id")) or "active"
            self._source_rollout_path = self._normalize_optional_text(payload.get("source_rollout_path"))
            self._recent.clear()
            for item in payload.get("recent", []):
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind", "commentary"))
                text = self._normalize_event_text(item.get("text"))
                created_at = self._normalize_optional_text(item.get("created_at"))
                if kind not in {"commentary", "final", "tool"} or not text or not created_at:
                    continue
                self._recent.append(
                    {
                        "seq": max(0, int(item.get("seq", 0))),
                        "kind": kind,
                        "text": text,
                        "created_at": created_at,
                    }
                )
            self._trim_recent_locked()
            snapshot = self._snapshot_locked()
            self.session.set_live_output(snapshot)
            return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot_locked()
        self.session.set_live_output(snapshot)
        return snapshot

    def reset(
        self,
        *,
        session_id: str | None = None,
        source_rollout_path: str | None = None,
        status: LiveOutputStatus = "no_output",
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._recent.clear()
            self._latest_text = None
            self._updated_at = None
            self._heartbeat_at = self._normalize_optional_text(timestamp)
            self._truncated = False
            self._status = status
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._seq += 1
            return self._commit_locked()

    def append_event(
        self,
        *,
        kind: LiveOutputKind,
        text: str,
        created_at: str | None = None,
        status: LiveOutputStatus | None = None,
        session_id: str | None = None,
        source_rollout_path: str | None = None,
    ) -> dict[str, Any]:
        normalized_text = self._normalize_event_text(text)
        if not normalized_text:
            return self.snapshot()

        effective_created_at = self._normalize_optional_text(created_at) or self._now_iso()
        effective_status = status
        if effective_status is None:
            effective_status = "idle" if kind == "final" else "running"

        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._recent.append(
                {
                    "seq": self._seq + 1,
                    "kind": kind,
                    "text": normalized_text,
                    "created_at": effective_created_at,
                }
            )
            self._trim_recent_locked()
            self._latest_text = normalized_text
            self._updated_at = effective_created_at
            self._heartbeat_at = effective_created_at
            self._status = effective_status
            self._seq += 1
            return self._commit_locked()

    def heartbeat(
        self,
        *,
        at: str | None = None,
        status: LiveOutputStatus | None = None,
        session_id: str | None = None,
        source_rollout_path: str | None = None,
    ) -> dict[str, Any]:
        effective_at = self._normalize_optional_text(at) or self._now_iso()
        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._heartbeat_at = effective_at
            if status is not None:
                self._status = status
            return self._commit_locked()

    def set_status(
        self,
        status: LiveOutputStatus,
        *,
        updated_at: str | None = None,
        heartbeat_at: str | None = None,
        session_id: str | None = None,
        source_rollout_path: str | None = None,
    ) -> dict[str, Any]:
        normalized_updated_at = self._normalize_optional_text(updated_at)
        normalized_heartbeat_at = self._normalize_optional_text(heartbeat_at) or normalized_updated_at
        with self._lock:
            self._status = status
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            if normalized_updated_at is not None:
                self._updated_at = normalized_updated_at
            if normalized_heartbeat_at is not None:
                self._heartbeat_at = normalized_heartbeat_at
            return self._commit_locked()

    def _trim_recent_locked(self) -> None:
        self._truncated = False
        if not self._recent:
            return

        while len(self._recent) > self.max_items:
            self._recent.popleft()
            self._truncated = True

        while len(self._recent) > 1 and self._recent_chars_locked() > self.max_chars:
            self._recent.popleft()
            self._truncated = True

        while self._recent and self._recent_chars_locked() > self.max_chars * 2:
            self._recent.popleft()
            self._truncated = True

    def _recent_chars_locked(self) -> int:
        return sum(len(str(item.get("text", ""))) for item in self._recent)

    def _commit_locked(self) -> dict[str, Any]:
        snapshot = self._snapshot_locked()
        self._persist_snapshot_locked(snapshot)
        self.session.set_live_output(snapshot)
        return snapshot

    def _persist_snapshot_locked(self, snapshot: dict[str, Any]) -> None:
        path = live_output_latest_path()
        temp_path = Path(str(path) + ".tmp")
        write_json(temp_path, snapshot)
        try:
            temp_path.replace(path)
        except PermissionError:
            write_json(path, snapshot)
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "session_id": self._session_id,
            "seq": self._seq,
            "status": self._status,
            "updated_at": self._updated_at,
            "heartbeat_at": self._heartbeat_at,
            "latest_text": self._latest_text,
            "recent": [dict(item) for item in self._recent],
            "truncated": self._truncated,
            "stale_after_seconds": self.stale_after_sec,
            "source_rollout_path": self._source_rollout_path,
        }

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize_event_text(self, value: Any) -> str:
        text = self._normalize_optional_text(value)
        if text is None:
            return ""
        collapsed = "\n".join(part.rstrip() for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
        return collapsed[: self.max_chars]

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
