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
LiveSessionMode = Literal["none", "attach_readonly", "managed"]
ActivityStatus = Literal["running", "completed", "failed", "waiting", "info"]

_UNSET = object()


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
        self.activity_max_items = max(16, self.max_items * 2)
        self.activity_preview_chars = max(400, min(1600, self.max_chars // 3))
        self.activity_detail_chars = 320
        self.stale_after_sec = max(1, stale_after_sec)
        self._lock = threading.RLock()
        self._recent: deque[dict[str, Any]] = deque()
        self._recent_activity: deque[dict[str, Any]] = deque()
        self._seq = 0
        self._status: LiveOutputStatus = "no_output"
        self._updated_at: str | None = None
        self._heartbeat_at: str | None = None
        self._latest_text: str | None = None
        self._active_text: str | None = None
        self._plan: dict[str, Any] | None = None
        self._reasoning: dict[str, Any] | None = None
        self._truncated = False
        self._session_id = "active"
        self._thread_id: str | None = None
        self._turn_id: str | None = None
        self._session_mode: LiveSessionMode = "none"
        self._thread_status_type: str | None = None
        self._thread_active_flags: list[str] = []
        self._can_send = True
        self._can_interrupt = False
        self._last_error: str | None = None
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
            raw_status = str(payload.get("status", "no_output"))
            self._status = raw_status if raw_status in {"running", "idle", "no_output"} else "no_output"
            self._updated_at = self._normalize_optional_text(payload.get("updated_at"))
            self._heartbeat_at = self._normalize_optional_text(payload.get("heartbeat_at"))
            self._latest_text = self._normalize_optional_text(payload.get("latest_text"))
            self._active_text = self._normalize_optional_text(payload.get("active_text"))
            self._truncated = bool(payload.get("truncated", False))
            self._session_id = self._normalize_optional_text(payload.get("session_id")) or "active"
            self._thread_id = self._normalize_optional_text(payload.get("thread_id"))
            self._turn_id = self._normalize_optional_text(payload.get("turn_id"))
            raw_mode = str(payload.get("session_mode", "none"))
            self._session_mode = raw_mode if raw_mode in {"none", "attach_readonly", "managed"} else "none"
            self._thread_status_type = self._normalize_optional_text(payload.get("thread_status_type"))
            flags = payload.get("thread_active_flags", [])
            self._thread_active_flags = [str(item).strip() for item in flags if str(item).strip()] if isinstance(flags, list) else []
            self._can_send = bool(payload.get("can_send", True))
            self._can_interrupt = bool(payload.get("can_interrupt", False))
            self._last_error = self._normalize_optional_text(payload.get("last_error"))
            self._source_rollout_path = self._normalize_optional_text(payload.get("source_rollout_path"))
            self._plan = self._normalize_plan(payload.get("plan"))
            self._reasoning = self._normalize_reasoning(payload.get("reasoning"))
            self._recent.clear()
            for item in payload.get("recent", []):
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind", "commentary"))
                text = self._normalize_event_text(item.get("text"))
                created_at = self._normalize_optional_text(item.get("created_at"))
                if kind in {"commentary", "final", "tool"} and text and created_at:
                    self._recent.append({"seq": max(0, int(item.get("seq", 0))), "kind": kind, "text": text, "created_at": created_at})
            self._trim_recent_locked()
            self._recent_activity.clear()
            for item in payload.get("recent_activity", []):
                normalized = self._normalize_activity(item)
                if normalized is not None:
                    self._recent_activity.append(normalized)
            self._trim_recent_activity_locked()
            snapshot = self._snapshot_locked()
            self.session.set_live_output(snapshot)
            return snapshot

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot_locked()
        self.session.set_live_output(snapshot)
        return snapshot

    def reset(self, *, session_id: str | None = None, source_rollout_path: str | None = None, status: LiveOutputStatus = "no_output", timestamp: str | None = None, **ctx: object) -> dict[str, Any]:
        with self._lock:
            self._recent.clear()
            self._recent_activity.clear()
            self._latest_text = None
            self._active_text = None
            self._plan = None
            self._reasoning = None
            self._updated_at = None
            self._heartbeat_at = self._normalize_optional_text(timestamp)
            self._truncated = False
            self._status = status
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            self._seq += 1
            return self._commit_locked()

    def append_event(self, *, kind: LiveOutputKind, text: str, created_at: str | None = None, status: LiveOutputStatus | None = None, session_id: str | None = None, source_rollout_path: str | None = None, **ctx: object) -> dict[str, Any]:
        normalized_text = self._normalize_event_text(text)
        if not normalized_text:
            return self.snapshot()
        effective_at = self._normalize_optional_text(created_at) or self._now_iso()
        effective_status = status if status is not None else ("idle" if kind == "final" else "running")
        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            self._recent.append({"seq": self._seq + 1, "kind": kind, "text": normalized_text, "created_at": effective_at})
            self._trim_recent_locked()
            self._active_text = None
            self._latest_text = normalized_text
            self._updated_at = effective_at
            self._heartbeat_at = effective_at
            self._status = effective_status
            self._seq += 1
            return self._commit_locked()

    def append_delta(self, *, text: str, created_at: str | None = None, session_id: str | None = None, source_rollout_path: str | None = None, **ctx: object) -> dict[str, Any]:
        normalized_text = self._normalize_delta_text(text)
        if not normalized_text:
            return self.snapshot()
        effective_at = self._normalize_optional_text(created_at) or self._now_iso()
        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            self._active_text = ((self._active_text or "") + normalized_text)[: self.max_chars]
            self._latest_text = self._active_text
            self._updated_at = effective_at
            self._heartbeat_at = effective_at
            self._status = "running"
            return self._commit_locked()

    def commit_active_text(self, *, kind: LiveOutputKind = "final", created_at: str | None = None, status: LiveOutputStatus = "idle", session_id: str | None = None, source_rollout_path: str | None = None, **ctx: object) -> dict[str, Any]:
        effective_at = self._normalize_optional_text(created_at) or self._now_iso()
        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            committed_text = self._normalize_event_text(self._active_text)
            self._active_text = None
            self._status = status
            self._updated_at = effective_at
            self._heartbeat_at = effective_at
            if committed_text:
                self._recent.append({"seq": self._seq + 1, "kind": kind, "text": committed_text, "created_at": effective_at})
                self._trim_recent_locked()
                self._latest_text = committed_text
                self._seq += 1
            return self._commit_locked()

    def heartbeat(self, *, at: str | None = None, status: LiveOutputStatus | None = None, session_id: str | None = None, source_rollout_path: str | None = None, **ctx: object) -> dict[str, Any]:
        effective_at = self._normalize_optional_text(at) or self._now_iso()
        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            self._heartbeat_at = effective_at
            if status is not None:
                self._status = status
            return self._commit_locked()

    def set_status(self, status: LiveOutputStatus, *, updated_at: str | None = None, heartbeat_at: str | None = None, session_id: str | None = None, source_rollout_path: str | None = None, **ctx: object) -> dict[str, Any]:
        with self._lock:
            self._status = status
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            if updated_at is not None:
                self._updated_at = self._normalize_optional_text(updated_at)
            hb = self._normalize_optional_text(heartbeat_at) or self._normalize_optional_text(updated_at)
            if hb is not None:
                self._heartbeat_at = hb
            return self._commit_locked()

    def set_session_state(self, *, session_id: str | None = None, source_rollout_path: str | None = None, updated_at: str | None = None, heartbeat_at: str | None = None, **ctx: object) -> dict[str, Any]:
        with self._lock:
            if session_id:
                self._session_id = session_id
            if source_rollout_path is not None:
                self._source_rollout_path = source_rollout_path
            self._apply_session_fields_locked(**ctx)
            if updated_at is not None:
                self._updated_at = self._normalize_optional_text(updated_at)
            if heartbeat_at is not None:
                self._heartbeat_at = self._normalize_optional_text(heartbeat_at)
            return self._commit_locked()

    def upsert_activity(
        self,
        *,
        activity_id: str,
        kind: str,
        title: str,
        status: ActivityStatus,
        created_at: str | None = None,
        updated_at: str | None = None,
        detail: str | None = None,
        preview: str | None = None,
        append_preview: bool = False,
        meta: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_id = self._normalize_optional_text(activity_id)
        normalized_title = self._normalize_optional_text(title)
        if not normalized_id or not normalized_title:
            return self.snapshot()
        created_value = self._normalize_optional_text(created_at) or self._now_iso()
        updated_value = self._normalize_optional_text(updated_at) or created_value
        with self._lock:
            activity = self._find_activity_locked(normalized_id)
            if activity is None:
                activity = {
                    "id": normalized_id,
                    "kind": self._normalize_optional_text(kind) or "tool",
                    "title": normalized_title,
                    "status": status,
                    "created_at": created_value,
                    "updated_at": updated_value,
                    "detail": None,
                    "preview": None,
                    "meta": [],
                }
                self._recent_activity.append(activity)
            else:
                activity["kind"] = self._normalize_optional_text(kind) or activity.get("kind") or "tool"
                activity["title"] = normalized_title
                activity["status"] = status
                activity["updated_at"] = updated_value
            if detail is not None:
                activity["detail"] = self._normalize_detail_text(detail)
            if preview is not None:
                normalized_preview = self._normalize_preview_text(preview)
                if append_preview and normalized_preview:
                    combined = ((activity.get("preview") or "") + normalized_preview)[-self.activity_preview_chars :]
                    activity["preview"] = self._normalize_preview_text(combined)
                else:
                    activity["preview"] = normalized_preview
            if meta is not None:
                activity["meta"] = self._normalize_meta(meta)
            self._trim_recent_activity_locked()
            self._updated_at = updated_value
            self._heartbeat_at = updated_value
            return self._commit_locked()

    def set_plan(
        self,
        *,
        text: str | None = None,
        explanation: str | None = None,
        steps: list[dict[str, str]] | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        updated_value = self._normalize_optional_text(updated_at) or self._now_iso()
        with self._lock:
            existing = self._plan or {}
            merged_text = self._normalize_event_text(text) or existing.get("text")
            merged_explanation = self._normalize_detail_text(explanation) or existing.get("explanation")
            merged_steps = self._normalize_plan_steps(steps or []) or existing.get("steps") or []
            self._plan = None if not (merged_text or merged_explanation or merged_steps) else {
                "text": merged_text or None,
                "explanation": merged_explanation,
                "steps": merged_steps,
                "updated_at": updated_value,
            }
            self._updated_at = updated_value
            self._heartbeat_at = updated_value
            return self._commit_locked()

    def append_plan_delta(self, *, text: str, updated_at: str | None = None) -> dict[str, Any]:
        updated_value = self._normalize_optional_text(updated_at) or self._now_iso()
        normalized = self._normalize_delta_text(text)
        if not normalized:
            return self.snapshot()
        with self._lock:
            base = ""
            if self._plan and self._plan.get("text"):
                base = str(self._plan.get("text"))
            self._plan = {
                "text": self._normalize_event_text((base + normalized)[-self.max_chars :]) or None,
                "explanation": None if self._plan is None else self._plan.get("explanation"),
                "steps": [] if self._plan is None else list(self._plan.get("steps") or []),
                "updated_at": updated_value,
            }
            self._updated_at = updated_value
            self._heartbeat_at = updated_value
            return self._commit_locked()

    def set_reasoning(self, *, text: str | None = None, kind: str = "summary", updated_at: str | None = None) -> dict[str, Any]:
        updated_value = self._normalize_optional_text(updated_at) or self._now_iso()
        normalized = self._normalize_event_text(text)
        with self._lock:
            self._reasoning = None if not normalized else {
                "text": normalized,
                "kind": self._normalize_optional_text(kind) or "summary",
                "updated_at": updated_value,
            }
            self._updated_at = updated_value
            self._heartbeat_at = updated_value
            return self._commit_locked()

    def append_reasoning_delta(self, *, text: str, kind: str = "summary", updated_at: str | None = None) -> dict[str, Any]:
        updated_value = self._normalize_optional_text(updated_at) or self._now_iso()
        normalized = self._normalize_delta_text(text)
        if not normalized:
            return self.snapshot()
        with self._lock:
            base = ""
            if self._reasoning and self._reasoning.get("text"):
                base = str(self._reasoning.get("text"))
            self._reasoning = {
                "text": self._normalize_event_text((base + normalized)[-self.max_chars :]) or None,
                "kind": self._normalize_optional_text(kind) or "summary",
                "updated_at": updated_value,
            }
            self._updated_at = updated_value
            self._heartbeat_at = updated_value
            return self._commit_locked()

    def _trim_recent_locked(self) -> None:
        self._truncated = False
        while len(self._recent) > self.max_items:
            self._recent.popleft()
            self._truncated = True
        while len(self._recent) > 1 and sum(len(str(item.get("text", ""))) for item in self._recent) > self.max_chars:
            self._recent.popleft()
            self._truncated = True

    def _trim_recent_activity_locked(self) -> None:
        while len(self._recent_activity) > self.activity_max_items:
            self._recent_activity.popleft()

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
            "thread_id": self._thread_id,
            "turn_id": self._turn_id,
            "session_mode": self._session_mode,
            "thread_status_type": self._thread_status_type,
            "thread_active_flags": list(self._thread_active_flags),
            "can_send": self._can_send,
            "can_interrupt": self._can_interrupt,
            "last_error": self._last_error,
            "seq": self._seq,
            "status": self._status,
            "updated_at": self._updated_at,
            "heartbeat_at": self._heartbeat_at,
            "latest_text": self._latest_text,
            "active_text": self._active_text,
            "plan": None if self._plan is None else dict(self._plan),
            "reasoning": None if self._reasoning is None else dict(self._reasoning),
            "recent": [dict(item) for item in self._recent],
            "recent_activity": sorted(
                [dict(item) for item in self._recent_activity],
                key=lambda item: item.get("updated_at") or item.get("created_at") or "",
                reverse=True,
            ),
            "truncated": self._truncated,
            "stale_after_seconds": self.stale_after_sec,
            "source_rollout_path": self._source_rollout_path,
        }

    def _apply_session_fields_locked(self, **ctx: object) -> None:
        session_mode = ctx.get("session_mode", _UNSET)
        if session_mode is not _UNSET:
            self._session_mode = session_mode  # type: ignore[assignment]
        thread_id = ctx.get("thread_id", _UNSET)
        if thread_id is not _UNSET:
            self._thread_id = self._normalize_optional_text(thread_id)
        turn_id = ctx.get("turn_id", _UNSET)
        if turn_id is not _UNSET:
            self._turn_id = self._normalize_optional_text(turn_id)
        status_type = ctx.get("thread_status_type", _UNSET)
        if status_type is not _UNSET:
            self._thread_status_type = self._normalize_optional_text(status_type)
        flags = ctx.get("thread_active_flags", _UNSET)
        if flags is not _UNSET and isinstance(flags, list):
            self._thread_active_flags = [str(item).strip() for item in flags if str(item).strip()]
        can_send = ctx.get("can_send", _UNSET)
        if can_send is not _UNSET:
            self._can_send = bool(can_send)
        can_interrupt = ctx.get("can_interrupt", _UNSET)
        if can_interrupt is not _UNSET:
            self._can_interrupt = bool(can_interrupt)
        last_error = ctx.get("last_error", _UNSET)
        if last_error is not _UNSET:
            self._last_error = self._normalize_optional_text(last_error)

    def _find_activity_locked(self, activity_id: str) -> dict[str, Any] | None:
        for item in self._recent_activity:
            if item.get("id") == activity_id:
                return item
        return None

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
        return "\n".join(part.rstrip() for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))[: self.max_chars]

    @staticmethod
    def _normalize_delta_text(value: Any) -> str:
        return "" if value is None else str(value).replace("\r\n", "\n").replace("\r", "\n")

    def _normalize_detail_text(self, value: Any) -> str | None:
        text = self._normalize_optional_text(value)
        if text is None:
            return None
        return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())[: self.activity_detail_chars] or None

    def _normalize_preview_text(self, value: Any) -> str | None:
        if value is None:
            return None
        compact = "\n".join(line.rstrip() for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
        return compact[-self.activity_preview_chars :] if compact else None

    @staticmethod
    def _normalize_meta(values: Any) -> list[str]:
        return [str(item).strip() for item in values if str(item).strip()] if isinstance(values, list) else []

    def _normalize_plan_steps(self, steps: list[dict[str, str]]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in steps:
            if not isinstance(item, dict):
                continue
            step = self._normalize_optional_text(item.get("step"))
            status = self._normalize_optional_text(item.get("status")) or "pending"
            if step:
                normalized.append({"step": step, "status": status})
        return normalized

    def _normalize_plan(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        text = self._normalize_event_text(value.get("text"))
        explanation = self._normalize_detail_text(value.get("explanation"))
        steps = self._normalize_plan_steps(value.get("steps", []))
        updated_at = self._normalize_optional_text(value.get("updated_at"))
        if not text and not explanation and not steps:
            return None
        return {"text": text or None, "explanation": explanation, "steps": steps, "updated_at": updated_at}

    def _normalize_reasoning(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        text = self._normalize_event_text(value.get("text"))
        if not text:
            return None
        return {
            "text": text,
            "kind": self._normalize_optional_text(value.get("kind")) or "summary",
            "updated_at": self._normalize_optional_text(value.get("updated_at")),
        }

    def _normalize_activity(self, value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        activity_id = self._normalize_optional_text(value.get("id"))
        title = self._normalize_optional_text(value.get("title"))
        created_at = self._normalize_optional_text(value.get("created_at"))
        if not activity_id or not title or not created_at:
            return None
        return {
            "id": activity_id,
            "kind": self._normalize_optional_text(value.get("kind")) or "tool",
            "title": title,
            "status": self._normalize_optional_text(value.get("status")) or "info",
            "created_at": created_at,
            "updated_at": self._normalize_optional_text(value.get("updated_at")) or created_at,
            "detail": self._normalize_detail_text(value.get("detail")),
            "preview": self._normalize_preview_text(value.get("preview")),
            "meta": self._normalize_meta(value.get("meta", [])),
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
