from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any

from agent_computer.runtime import DEFAULT_CODEX_HOME, DEFAULT_CODEX_SESSION_POLL_INTERVAL_SEC, PROJECT_ROOT
from agent_computer.services.live_output_service import LiveOutputService


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
        self._session_meta_cache: dict[str, tuple[float, int, str | None, str | None]] = {}
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
        candidate = self.discover_latest_rollout_file()
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

    def discover_latest_rollout_file(self) -> Path | None:
        sessions_dir = self.codex_home / "sessions"
        if not sessions_dir.exists():
            return None

        files = []
        for candidate in sessions_dir.glob("*/*/*/rollout-*.jsonl"):
            try:
                files.append((candidate.stat().st_mtime, candidate))
            except OSError:
                continue
        files.sort(key=lambda item: item[0], reverse=True)
        for _, candidate in files[: self.max_candidates]:
            session_id, candidate_cwd = self._read_session_meta(candidate)
            if candidate_cwd is None or self._normalize_path(candidate_cwd) != self.target_cwd:
                continue
            if self._current_rollout_path is not None and candidate == self._current_rollout_path:
                if session_id:
                    self._current_session_id = session_id
                return candidate
            return candidate
        return None

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
