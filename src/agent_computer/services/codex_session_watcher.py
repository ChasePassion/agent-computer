from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any

from agent_computer.runtime import DEFAULT_CODEX_HOME, DEFAULT_CODEX_SESSION_POLL_INTERVAL_SEC, PROJECT_ROOT
from agent_computer.services.live_output_service import LiveOutputService
from agent_computer.windowing import list_windows


class CodexSessionWatcher:
    def __init__(
        self,
        live_output: LiveOutputService,
        *,
        codex_home: Path = DEFAULT_CODEX_HOME,
        target_cwd: Path = PROJECT_ROOT,
        poll_interval_sec: float = DEFAULT_CODEX_SESSION_POLL_INTERVAL_SEC,
        max_candidates: int = 64,
    ) -> None:
        self.live_output = live_output
        self.codex_home = Path(codex_home)
        self.target_cwd = self._normalize_path(target_cwd)
        self.poll_interval_sec = max(0.25, poll_interval_sec)
        self.max_candidates = max(8, max_candidates)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_rollout_path: Path | None = None
        self._current_offset = 0
        self._current_session_id: str | None = None
        self._current_turn_id: str | None = None
        self._selected_session_id: str | None = None
        self._session_meta_cache: dict[str, tuple[float, int, str | None, str | None]] = {}
        self._session_index_cache: tuple[float, int, dict[str, dict[str, str | None]]] | None = None
        self._candidate_sessions: list[dict[str, Any]] = []
        self._recent_signatures: list[str] = []

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self.poll_once()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="agent-computer-codex-session-watcher",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            if not thread:
                return
            self._stop_event.set()
        thread.join(timeout=5.0)
        with self._lock:
            self._thread = None

    def poll_once(self) -> None:
        candidates = self.discover_candidate_sessions()
        with self._lock:
            self._candidate_sessions = candidates
        candidate = self._choose_candidate_rollout(candidates)
        if candidate is None:
            with self._lock:
                self._current_rollout_path = None
                self._current_offset = 0
                self._current_session_id = None
                self._current_turn_id = None
                self._recent_signatures.clear()
            snapshot = self.live_output.snapshot()
            if snapshot.get("status") != "no_output" or snapshot.get("recent") or snapshot.get("active_text"):
                self.live_output.reset(
                    status="no_output",
                    session_id="active",
                    session_mode="none",
                    thread_id=None,
                    turn_id=None,
                    thread_status_type=None,
                    thread_active_flags=[],
                    can_send=False,
                    can_interrupt=False,
                    last_error=None,
                    source_rollout_path=None,
                )
            return

        if self._current_rollout_path != candidate:
            self.switch_rollout_file(candidate)
        self._consume_current_rollout()

    def discover_candidate_sessions(self) -> list[dict[str, Any]]:
        sessions_dir = self.codex_home / "sessions"
        if not sessions_dir.exists():
            return []

        file_entries = []
        for candidate in sessions_dir.glob("*/*/*/rollout-*.jsonl"):
            try:
                stat = candidate.stat()
            except OSError:
                continue
            session_id, candidate_cwd = self._read_session_meta(candidate)
            if candidate_cwd is None or self._normalize_path(candidate_cwd) != self.target_cwd:
                continue
            effective_session_id = session_id or candidate.stem
            file_entries.append((stat.st_mtime, candidate, effective_session_id))

        session_index = self._read_session_index()
        file_entries.sort(
            key=lambda item: (
                self._timestamp_from_iso(
                    self._normalize_optional_text(
                        session_index.get(item[2], {}).get("updated_at")
                    ),
                    fallback=item[0],
                ),
                item[0],
                str(item[1]),
            ),
            reverse=True,
        )
        codex_windows = self._discover_codex_window_titles()
        seen_session_ids: set[str] = set()
        sessions: list[dict[str, Any]] = []
        for updated_ts, rollout_path, session_id in file_entries[: self.max_candidates]:
            if session_id in seen_session_ids:
                continue
            seen_session_ids.add(session_id)
            index_meta = session_index.get(session_id, {})
            thread_name = self._normalize_optional_text(index_meta.get("thread_name"))
            window_matches = [
                title for title in codex_windows
                if thread_name and thread_name.casefold() in title.casefold()
            ]
            sessions.append(
                {
                    "session_id": session_id,
                    "thread_name": thread_name,
                    "updated_at": self._normalize_optional_text(index_meta.get("updated_at")) or self._iso_from_timestamp(updated_ts),
                    "rollout_path": str(rollout_path),
                    "window_matches": window_matches,
                }
            )
        return sessions

    def select_session(self, session_id: str | None) -> dict[str, Any]:
        normalized = self._normalize_optional_text(session_id)
        candidates = self.discover_candidate_sessions()
        session_ids = {str(item.get("session_id")) for item in candidates}
        if normalized is not None and normalized not in session_ids:
            raise KeyError(normalized)
        with self._lock:
            self._selected_session_id = normalized
            self._candidate_sessions = candidates
        self.poll_once()
        return self.sessions_snapshot()

    def sessions_snapshot(self) -> dict[str, Any]:
        candidates = self.discover_candidate_sessions()
        with self._lock:
            self._candidate_sessions = candidates
            selected_session_id = self._selected_session_id
            current_session_id = self._current_session_id
            current_turn_id = self._current_turn_id
        items = []
        for item in candidates:
            session_id = str(item.get("session_id"))
            enriched = dict(item)
            enriched["selected"] = selected_session_id == session_id
            enriched["current"] = current_session_id == session_id
            items.append(enriched)
        return {
            "selection_mode": "manual" if selected_session_id else "auto",
            "selected_session_id": selected_session_id,
            "current_session_id": current_session_id,
            "current_turn_id": current_turn_id,
            "items": items,
        }

    def switch_rollout_file(self, rollout_path: Path) -> None:
        session_id, _ = self._read_session_meta(rollout_path)
        with self._lock:
            self._current_rollout_path = rollout_path
            self._current_offset = 0
            self._current_session_id = session_id
            self._current_turn_id = None
            self._recent_signatures.clear()
        self.live_output.reset(
            session_id=session_id or rollout_path.stem,
            source_rollout_path=str(rollout_path),
            status="no_output",
            session_mode="attach_readonly",
            thread_id=session_id,
            turn_id=None,
            thread_status_type=None,
            thread_active_flags=[],
            can_send=False,
            can_interrupt=False,
            last_error=None,
        )

    def _choose_candidate_rollout(self, candidates: list[dict[str, Any]]) -> Path | None:
        if not candidates:
            return None
        with self._lock:
            selected_session_id = self._selected_session_id
        if selected_session_id:
            for item in candidates:
                if item.get("session_id") == selected_session_id:
                    rollout_path = self._normalize_optional_text(item.get("rollout_path"))
                    return None if rollout_path is None else Path(rollout_path)
        rollout_path = self._normalize_optional_text(candidates[0].get("rollout_path"))
        return None if rollout_path is None else Path(rollout_path)

    def update_heartbeat(self, *, timestamp: str | None = None) -> None:
        session_id = self._current_turn_id or self._current_session_id
        source_rollout_path = None if self._current_rollout_path is None else str(self._current_rollout_path)
        self.live_output.heartbeat(
            at=timestamp,
            session_id=session_id,
            source_rollout_path=source_rollout_path,
            session_mode="attach_readonly",
            thread_id=self._current_session_id,
            turn_id=self._current_turn_id,
            thread_status_type=None,
            thread_active_flags=[],
            can_send=False,
            can_interrupt=False,
            last_error=None,
        )

    def parse_line(self, line: str) -> None:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return

        root_type = payload.get("type")
        timestamp = self._normalize_optional_text(payload.get("timestamp"))
        source_rollout_path = None if self._current_rollout_path is None else str(self._current_rollout_path)
        session_id = self._current_turn_id or self._current_session_id or "active"

        if root_type == "session_meta":
            meta_payload = payload.get("payload")
            if isinstance(meta_payload, dict):
                session_meta_id = self._normalize_optional_text(meta_payload.get("id"))
                if session_meta_id:
                    self._current_session_id = session_meta_id
                    self.live_output.set_session_state(
                        session_mode="attach_readonly",
                        thread_id=session_meta_id,
                        turn_id=self._current_turn_id,
                        thread_status_type=None,
                        thread_active_flags=[],
                        can_send=False,
                        can_interrupt=False,
                        source_rollout_path=source_rollout_path,
                        last_error=None,
                    )
            return

        if root_type == "event_msg":
            event_payload = payload.get("payload")
            if not isinstance(event_payload, dict):
                return
            event_type = self._normalize_optional_text(event_payload.get("type"))
            if event_type == "task_started":
                self._current_turn_id = self._normalize_optional_text(event_payload.get("turn_id")) or self._current_session_id
                self.live_output.reset(
                    session_id=self._current_turn_id or session_id,
                    source_rollout_path=source_rollout_path,
                    status="running",
                    timestamp=timestamp,
                    session_mode="attach_readonly",
                    thread_id=self._current_session_id,
                    turn_id=self._current_turn_id,
                    thread_status_type=None,
                    thread_active_flags=[],
                    can_send=False,
                    can_interrupt=False,
                    last_error=None,
                )
                return
            if event_type == "agent_message":
                message = self._normalize_optional_text(event_payload.get("message"))
                if message and self._remember_signature("commentary", message):
                    self.live_output.append_event(
                        kind="commentary",
                        text=message,
                        created_at=timestamp,
                        session_id=self._current_turn_id or session_id,
                        source_rollout_path=source_rollout_path,
                        session_mode="attach_readonly",
                        thread_id=self._current_session_id,
                        turn_id=self._current_turn_id,
                        thread_status_type=None,
                        thread_active_flags=[],
                        can_send=False,
                        can_interrupt=False,
                        last_error=None,
                    )
                return
            if event_type == "task_complete":
                final_message = self._normalize_optional_text(event_payload.get("last_agent_message"))
                current_turn_id = self._normalize_optional_text(event_payload.get("turn_id")) or self._current_turn_id or session_id
                if final_message and self._remember_signature("final", final_message):
                    self.live_output.append_event(
                        kind="final",
                        text=final_message,
                        created_at=timestamp,
                        status="idle",
                        session_id=current_turn_id,
                        source_rollout_path=source_rollout_path,
                        session_mode="attach_readonly",
                        thread_id=self._current_session_id,
                        turn_id=current_turn_id,
                        thread_status_type=None,
                        thread_active_flags=[],
                        can_send=False,
                        can_interrupt=False,
                        last_error=None,
                    )
                else:
                    self.live_output.set_status(
                        "idle",
                        updated_at=timestamp,
                        heartbeat_at=timestamp,
                        session_id=current_turn_id,
                        source_rollout_path=source_rollout_path,
                        session_mode="attach_readonly",
                        thread_id=self._current_session_id,
                        turn_id=current_turn_id,
                        thread_status_type=None,
                        thread_active_flags=[],
                        can_send=False,
                        can_interrupt=False,
                        last_error=None,
                    )
                return
            if event_type == "token_count":
                self.update_heartbeat(timestamp=timestamp)
                return
            return

        if root_type != "response_item":
            return

        item_payload = payload.get("payload")
        if not isinstance(item_payload, dict):
            return
        item_type = self._normalize_optional_text(item_payload.get("type"))
        if item_type in {"function_call", "function_call_output", "reasoning"}:
            self.update_heartbeat(timestamp=timestamp)
            return

        if item_type != "message":
            return

        role = self._normalize_optional_text(item_payload.get("role"))
        if role != "assistant":
            return

        content = item_payload.get("content")
        if not isinstance(content, list):
            return
        text_fragments = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "output_text":
                fragment = self._normalize_optional_text(item.get("text"))
                if fragment:
                    text_fragments.append(fragment)
        message = "\n".join(text_fragments).strip()
        if not message:
            return

        phase = self._normalize_optional_text(item_payload.get("phase")) or "commentary"
        if phase == "final":
            if self._remember_signature("final", message):
                self.live_output.append_event(
                    kind="final",
                    text=message,
                    created_at=timestamp,
                    status="idle",
                    session_id=session_id,
                    source_rollout_path=source_rollout_path,
                    session_mode="attach_readonly",
                    thread_id=self._current_session_id,
                    turn_id=session_id,
                    thread_status_type=None,
                    thread_active_flags=[],
                    can_send=False,
                    can_interrupt=False,
                    last_error=None,
                )
            return

        if self._remember_signature("commentary", message):
            self.live_output.append_event(
                kind="commentary",
                text=message,
                created_at=timestamp,
                session_id=session_id,
                source_rollout_path=source_rollout_path,
                session_mode="attach_readonly",
                thread_id=self._current_session_id,
                turn_id=self._current_turn_id or session_id,
                thread_status_type=None,
                thread_active_flags=[],
                can_send=False,
                can_interrupt=False,
                last_error=None,
            )

    def _consume_current_rollout(self) -> None:
        rollout_path = self._current_rollout_path
        if rollout_path is None or not rollout_path.exists():
            return

        with rollout_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._current_offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                self._current_offset = handle.tell()
                self.parse_line(line)

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self.poll_interval_sec):
            try:
                self.poll_once()
            except Exception:
                continue

    def _read_session_meta(self, rollout_path: Path) -> tuple[str | None, str | None]:
        stat = rollout_path.stat()
        cache_key = str(rollout_path)
        cached = self._session_meta_cache.get(cache_key)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            return cached[2], cached[3]

        session_id: str | None = None
        cwd: str | None = None
        try:
            with rollout_path.open("r", encoding="utf-8", errors="replace") as handle:
                for _ in range(40):
                    line = handle.readline()
                    if not line:
                        break
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("type") != "session_meta":
                        continue
                    meta_payload = payload.get("payload")
                    if not isinstance(meta_payload, dict):
                        continue
                    session_id = self._normalize_optional_text(meta_payload.get("id"))
                    cwd = self._normalize_optional_text(meta_payload.get("cwd"))
                    break
        except OSError:
            return None, None

        self._session_meta_cache[cache_key] = (stat.st_mtime, stat.st_size, session_id, cwd)
        return session_id, cwd

    def _read_session_index(self) -> dict[str, dict[str, str | None]]:
        index_path = self.codex_home / "session_index.jsonl"
        if not index_path.exists():
            return {}
        try:
            stat = index_path.stat()
        except OSError:
            return {}
        with self._lock:
            cached = self._session_index_cache
            if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
                return dict(cached[2])

        session_index: dict[str, dict[str, str | None]] = {}
        try:
            with index_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    session_id = self._normalize_optional_text(payload.get("id"))
                    if not session_id:
                        continue
                    session_index[session_id] = {
                        "thread_name": self._normalize_optional_text(payload.get("thread_name")),
                        "updated_at": self._normalize_optional_text(payload.get("updated_at")),
                    }
        except OSError:
            return {}

        with self._lock:
            self._session_index_cache = (stat.st_mtime, stat.st_size, dict(session_index))
        return session_index

    def _discover_codex_window_titles(self) -> list[str]:
        titles: list[str] = []
        for window in list_windows():
            title = self._normalize_optional_text(window.title)
            if title is None:
                continue
            lowered = title.casefold()
            if "codex.js" in lowered or "\\npm\\\\node_modules\\@openai\\codex" in lowered or " codex " in lowered:
                titles.append(title)
        return titles

    def _remember_signature(self, kind: str, text: str) -> bool:
        signature = f"{kind}:{text.strip()}"
        if not signature:
            return False
        if signature in self._recent_signatures:
            return False
        self._recent_signatures.append(signature)
        if len(self._recent_signatures) > 16:
            self._recent_signatures = self._recent_signatures[-16:]
        return True

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_path(value: str | Path) -> Path:
        return Path(value).expanduser().resolve()

    @staticmethod
    def _iso_from_timestamp(value: float) -> str:
        return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")

    @staticmethod
    def _timestamp_from_iso(value: str | None, *, fallback: float) -> float:
        if not value:
            return fallback
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return fallback
