from __future__ import annotations

from datetime import datetime
from pathlib import Path
import threading
from typing import Any, Callable

from agent_computer.services.codex_app_server_transport import CodexAppServerResponseError
from agent_computer.runtime import PROJECT_ROOT
from agent_computer.services.codex_app_server_transport import CodexAppServerTransport
from agent_computer.services.codex_session_watcher import CodexSessionWatcher
from agent_computer.services.live_output_service import LiveOutputService


class CodexManagedSessionService:
    def __init__(
        self,
        live_output: LiveOutputService,
        session_watcher: CodexSessionWatcher,
        *,
        target_cwd: str | Path = PROJECT_ROOT,
        codex_bin: str = "codex",
        config_overrides: tuple[str, ...] = (),
        transport_factory: Callable[[Callable[[str, dict[str, Any]], None]], Any] | None = None,
    ) -> None:
        self.live_output = live_output
        self.session_watcher = session_watcher
        self.target_cwd = str(Path(target_cwd).resolve())
        self.codex_bin = codex_bin
        self.config_overrides = tuple(config_overrides)
        self.transport_factory = transport_factory or self._default_transport_factory
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._transport: Any | None = None
        self._thread_id: str | None = None
        self._active_turn_id: str | None = None
        self._thread_status_type: str | None = None
        self._thread_active_flags: list[str] = []
        self._last_error: str | None = None
        self._watcher_stopped = False

    def close(self) -> None:
        with self._lock:
            transport = self._transport
            self._transport = None
            self._active_turn_id = None
        if transport is not None:
            transport.close()

    def send_message(self, message: str) -> dict[str, Any]:
        normalized_message = str(message or "").strip()
        if not normalized_message:
            raise ValueError("Message must not be empty.")
        with self._operation_lock:
            transport = self._ensure_transport()
            resume_snapshot = self.session_watcher.current_session_snapshot()
            dispatched_as = ""

            with self._lock:
                current_thread_id = self._thread_id

            if current_thread_id is None:
                resumed = False
                resume_thread_id = self._normalize_optional_text(resume_snapshot.get("thread_id"))
                resume_turn_id = self._normalize_optional_text(resume_snapshot.get("turn_id"))
                if resume_thread_id:
                    try:
                        response = transport.request("thread/resume", {"threadId": resume_thread_id})
                    except Exception as exc:  # noqa: BLE001
                        with self._lock:
                            self._last_error = f"Failed to resume thread {resume_thread_id}: {exc}"
                    else:
                        with self._lock:
                            self._adopt_thread_response_locked(response, fallback_thread_id=resume_thread_id)
                            self._active_turn_id = resume_turn_id
                            self._stop_watcher_locked()
                            current_thread_id = self._thread_id
                        resumed = True
                if not resumed:
                    response = transport.request(
                        "thread/start",
                        {
                            "cwd": self.target_cwd,
                        },
                    )
                    with self._lock:
                        self._adopt_thread_response_locked(response)
                        self._stop_watcher_locked()
                        current_thread_id = self._thread_id

            with self._lock:
                current_thread_id = self._thread_id
                current_turn_id = self._active_turn_id

            if current_thread_id is None:
                raise RuntimeError("Unable to initialize a managed Codex thread.")

            if current_turn_id:
                try:
                    response = transport.request(
                        "turn/steer",
                        {
                            "threadId": current_thread_id,
                            "expectedTurnId": current_turn_id,
                            "input": [{"type": "text", "text": normalized_message}],
                        },
                    )
                except CodexAppServerResponseError as exc:
                    if "no active turn to steer" not in exc.message.lower():
                        raise
                    response = transport.request(
                        "turn/start",
                        {
                            "threadId": current_thread_id,
                            "cwd": self.target_cwd,
                            "approvalPolicy": "never",
                            "input": [{"type": "text", "text": normalized_message}],
                        },
                    )
                    dispatched_as = "turn_start"
                    turn = response.get("turn")
                    next_turn_id = self._normalize_optional_text(turn.get("id")) if isinstance(turn, dict) else None
                else:
                    dispatched_as = "turn_steer"
                    next_turn_id = self._normalize_optional_text(response.get("turnId")) or current_turn_id
            else:
                response = transport.request(
                    "turn/start",
                    {
                        "threadId": current_thread_id,
                        "cwd": self.target_cwd,
                        "approvalPolicy": "never",
                        "input": [{"type": "text", "text": normalized_message}],
                    },
                )
                dispatched_as = "turn_start"
                turn = response.get("turn")
                next_turn_id = self._normalize_optional_text(turn.get("id")) if isinstance(turn, dict) else None

            with self._lock:
                self._thread_id = current_thread_id
                self._active_turn_id = next_turn_id or self._active_turn_id
                self._thread_status_type = "active"
                self._thread_active_flags = []
                self._last_error = None
                self.live_output.set_status(
                    "running",
                    updated_at=self._now_iso(),
                    heartbeat_at=self._now_iso(),
                    session_id=self._thread_id,
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type=self._thread_status_type,
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=None,
                )
                return {
                    "ok": True,
                    "mode": "managed",
                    "thread_id": self._thread_id,
                    "turn_id": self._active_turn_id,
                    "dispatched_as": dispatched_as,
                }

    def interrupt(self) -> dict[str, Any]:
        with self._operation_lock:
            with self._lock:
                transport = self._transport
                thread_id = self._thread_id
                turn_id = self._active_turn_id
                thread_status_type = self._thread_status_type
                thread_active_flags = list(self._thread_active_flags)
                last_error = self._last_error
            if transport is None or thread_id is None or turn_id is None:
                return {
                    "ok": True,
                    "submitted": False,
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                }
            transport.request(
                "turn/interrupt",
                {
                    "threadId": thread_id,
                    "turnId": turn_id,
                },
            )
            with self._lock:
                self.live_output.set_session_state(
                    session_mode="managed",
                    thread_id=thread_id,
                    turn_id=turn_id,
                    thread_status_type=thread_status_type,
                    thread_active_flags=thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=False,
                    last_error=last_error,
                    updated_at=self._now_iso(),
                    heartbeat_at=self._now_iso(),
                )
                return {
                    "ok": True,
                    "submitted": True,
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "thread_id": self._thread_id,
                "turn_id": self._active_turn_id,
                "thread_status_type": self._thread_status_type,
                "thread_active_flags": list(self._thread_active_flags),
                "last_error": self._last_error,
                "can_send": self._can_send_locked(),
                "can_interrupt": self._can_interrupt_locked(),
            }

    def on_notification(self, method: str, params: dict[str, Any]) -> None:
        timestamp = self._now_iso()
        with self._lock:
            if method == "__transport_error__":
                self._last_error = self._normalize_optional_text(params.get("message")) or "Codex transport closed."
                self._transport = None
                self._active_turn_id = None
                self._thread_status_type = "systemError"
                self._thread_active_flags = []
                self.live_output.set_session_state(
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type="systemError",
                    thread_active_flags=[],
                    can_send=False,
                    can_interrupt=False,
                    last_error=self._last_error,
                    updated_at=timestamp,
                    heartbeat_at=timestamp,
                )
                return

            if method == "__server_request__":
                request_method = self._normalize_optional_text(params.get("method")) or "unknown"
                title, detail, kind = self._describe_server_request(request_method, params.get("params"))
                self.live_output.upsert_activity(
                    activity_id=f"server-request:{request_method}",
                    kind=kind,
                    title=title,
                    status="waiting",
                    updated_at=timestamp,
                    detail=detail,
                )
                return

            notification_thread_id = self._normalize_optional_text(params.get("threadId"))
            if notification_thread_id and self._thread_id and notification_thread_id != self._thread_id:
                return

            if method == "thread/started":
                thread = params.get("thread")
                if isinstance(thread, dict):
                    self._adopt_thread_response_locked({"thread": thread})
                    self._last_error = None
                    self.live_output.set_session_state(
                        session_mode="managed",
                        thread_id=self._thread_id,
                        turn_id=self._active_turn_id,
                        thread_status_type=self._thread_status_type,
                        thread_active_flags=self._thread_active_flags,
                        can_send=self._can_send_locked(),
                        can_interrupt=self._can_interrupt_locked(),
                        last_error=self._last_error,
                        updated_at=timestamp,
                        heartbeat_at=timestamp,
                    )
                return

            if method == "thread/status/changed":
                self._adopt_thread_status_locked(params.get("status"))
                if self._thread_status_type != "systemError":
                    self._last_error = None
                self.live_output.set_session_state(
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type=self._thread_status_type,
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=self._last_error,
                    updated_at=timestamp,
                    heartbeat_at=timestamp,
                )
                return

            if method == "turn/started":
                turn = params.get("turn")
                if isinstance(turn, dict):
                    self._active_turn_id = self._normalize_optional_text(turn.get("id")) or self._active_turn_id
                self._thread_status_type = "active"
                self._thread_active_flags = []
                self._last_error = None
                self.live_output.set_status(
                    "running",
                    updated_at=timestamp,
                    heartbeat_at=timestamp,
                    session_id=self._thread_id,
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type=self._thread_status_type,
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=self._last_error,
                )
                return

            if method == "turn/plan/updated":
                self.live_output.set_plan(
                    explanation=self._normalize_optional_text(params.get("explanation")),
                    steps=self._extract_turn_plan_steps(params.get("plan")),
                    updated_at=timestamp,
                )
                return

            if method == "item/started":
                self._handle_item_started(params, timestamp)
                return

            if method == "item/agentMessage/delta":
                turn_id = self._normalize_optional_text(params.get("turnId")) or self._active_turn_id
                if turn_id:
                    self._active_turn_id = turn_id
                self._thread_status_type = "active"
                self._thread_active_flags = []
                self.live_output.append_delta(
                    text=str(params.get("delta") or ""),
                    created_at=timestamp,
                    session_id=self._thread_id,
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type=self._thread_status_type,
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=self._last_error,
                )
                return

            if method == "item/plan/delta":
                self.live_output.append_plan_delta(
                    text=str(params.get("delta") or ""),
                    updated_at=timestamp,
                )
                self.live_output.upsert_activity(
                    activity_id=self._normalize_optional_text(params.get("itemId")) or "plan",
                    kind="plan",
                    title="Updating plan",
                    status="running",
                    updated_at=timestamp,
                    preview=str(params.get("delta") or ""),
                    append_preview=True,
                )
                return

            if method == "item/reasoning/summaryTextDelta":
                self.live_output.append_reasoning_delta(
                    text=str(params.get("delta") or ""),
                    kind="summary",
                    updated_at=timestamp,
                )
                return

            if method == "item/reasoning/textDelta":
                self.live_output.append_reasoning_delta(
                    text=str(params.get("delta") or ""),
                    kind="raw",
                    updated_at=timestamp,
                )
                return

            if method == "item/commandExecution/terminalInteraction":
                activity_id = self._normalize_optional_text(params.get("itemId"))
                stdin_text = self._normalize_optional_text(params.get("stdin"))
                if activity_id and stdin_text:
                    self.live_output.upsert_activity(
                        activity_id=activity_id,
                        kind="command",
                        title=self._activity_title_for_known_item(activity_id) or "Running command",
                        status="running",
                        updated_at=timestamp,
                        preview=f"$ {stdin_text}",
                        append_preview=True,
                    )
                return

            if method in {"item/commandExecution/outputDelta", "item/fileChange/outputDelta"}:
                turn_id = self._normalize_optional_text(params.get("turnId")) or self._active_turn_id
                if turn_id:
                    self._active_turn_id = turn_id
                activity_id = self._normalize_optional_text(params.get("itemId"))
                if activity_id:
                    self.live_output.upsert_activity(
                        activity_id=activity_id,
                        kind="command" if method == "item/commandExecution/outputDelta" else "patch",
                        title=self._activity_title_for_known_item(activity_id) or ("Running command" if method == "item/commandExecution/outputDelta" else "Applying patch"),
                        status="running",
                        updated_at=timestamp,
                        preview=str(params.get("delta") or ""),
                        append_preview=True,
                    )
                self.live_output.heartbeat(
                    at=timestamp,
                    status="running",
                    session_id=self._thread_id,
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type="active",
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=self._last_error,
                )
                return

            if method == "item/mcpToolCall/progress":
                activity_id = self._normalize_optional_text(params.get("itemId"))
                if activity_id:
                    self.live_output.upsert_activity(
                        activity_id=activity_id,
                        kind="mcp",
                        title=self._activity_title_for_known_item(activity_id) or "Calling MCP tool",
                        status="running",
                        updated_at=timestamp,
                        detail=self._normalize_optional_text(params.get("message")) or "MCP tool progress",
                    )
                return

            if method == "item/completed":
                self._handle_item_completed(params, timestamp)
                return

            if method == "turn/completed":
                turn = params.get("turn")
                if not isinstance(turn, dict):
                    return
                completed_turn_id = self._normalize_optional_text(turn.get("id")) or self._active_turn_id
                turn_status = self._normalize_optional_text(turn.get("status")) or "completed"
                error = turn.get("error")
                error_message = None
                if isinstance(error, dict):
                    error_message = self._normalize_optional_text(error.get("message"))
                self._active_turn_id = None
                self._thread_status_type = "idle"
                self._thread_active_flags = []
                self._last_error = error_message
                committed_status = "idle"
                committed_kind = "final" if turn_status == "completed" else "commentary"
                self.live_output.commit_active_text(
                    kind=committed_kind,
                    created_at=timestamp,
                    status=committed_status,
                    session_id=self._thread_id,
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=completed_turn_id,
                    thread_status_type=self._thread_status_type,
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=self._last_error,
                )
                return

            if method == "error":
                self._last_error = self._extract_error_message(params) or "Codex error"
                self.live_output.upsert_activity(
                    activity_id=f"error:{timestamp}",
                    kind="error",
                    title="Error",
                    status="failed",
                    updated_at=timestamp,
                    detail=self._last_error,
                )
                self.live_output.set_session_state(
                    session_mode="managed",
                    thread_id=self._thread_id,
                    turn_id=self._active_turn_id,
                    thread_status_type=self._thread_status_type,
                    thread_active_flags=self._thread_active_flags,
                    can_send=self._can_send_locked(),
                    can_interrupt=self._can_interrupt_locked(),
                    last_error=self._last_error,
                    updated_at=timestamp,
                    heartbeat_at=timestamp,
                )

    def _handle_item_started(self, params: dict[str, Any], timestamp: str) -> None:
        item = params.get("item")
        if not isinstance(item, dict):
            return
        item_type = self._normalize_optional_text(item.get("type"))
        item_id = self._normalize_optional_text(item.get("id"))
        if not item_type or not item_id:
            return
        if item_type == "commandExecution":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="command",
                title="Running command",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("command")),
                meta=self._command_meta(item),
            )
            return
        if item_type == "fileChange":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="patch",
                title="Applying patch",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._summarize_file_changes(item.get("changes")),
            )
            return
        if item_type == "mcpToolCall":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="mcp",
                title="Calling MCP tool",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._mcp_detail(item),
            )
            return
        if item_type == "webSearch":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="web_search",
                title="Searching the web",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("query")),
            )
            return
        if item_type == "plan":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="plan",
                title="Updating plan",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("text")),
            )
            return
        if item_type == "reasoning":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="reasoning",
                title="Reasoning",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
            )
            return
        if item_type == "imageView":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="image",
                title="Viewed image",
                status="completed",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("path")),
            )
            return
        if item_type == "imageGeneration":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="image",
                title="Generating image",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("revisedPrompt")) or self._normalize_optional_text(item.get("result")),
            )
            return
        if item_type == "dynamicToolCall":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="tool",
                title="Calling tool",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("tool")),
            )
            return
        if item_type == "collabAgentToolCall":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="collab",
                title="Collaborating with agent",
                status="running",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("tool")) or self._normalize_optional_text(item.get("prompt")),
            )
            return
        if item_type == "enteredReviewMode":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="review",
                title="Entered review mode",
                status="info",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("review")),
            )
            return
        if item_type == "exitedReviewMode":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="review",
                title="Exited review mode",
                status="info",
                created_at=timestamp,
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("review")),
            )
            return
        if item_type == "contextCompaction":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="info",
                title="Context compacted",
                status="info",
                created_at=timestamp,
                updated_at=timestamp,
            )

    def _handle_item_completed(self, params: dict[str, Any], timestamp: str) -> None:
        item = params.get("item")
        if not isinstance(item, dict):
            return
        item_type = self._normalize_optional_text(item.get("type"))
        item_id = self._normalize_optional_text(item.get("id"))
        if not item_type or not item_id:
            return
        if item_type == "commandExecution":
            status = self._activity_status_from_value(item.get("status"))
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="command",
                title="Command finished",
                status=status,
                updated_at=timestamp,
                detail=self._command_completion_detail(item),
                preview=self._normalize_optional_text(item.get("aggregatedOutput")),
                append_preview=True,
                meta=self._command_meta(item),
            )
            return
        if item_type == "fileChange":
            status = self._activity_status_from_value(item.get("status"))
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="patch",
                title="Patch applied" if status == "completed" else "Patch result",
                status=status,
                updated_at=timestamp,
                detail=self._summarize_file_changes(item.get("changes")),
            )
            return
        if item_type == "mcpToolCall":
            status = self._activity_status_from_value(item.get("status"))
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="mcp",
                title="MCP tool finished",
                status=status,
                updated_at=timestamp,
                detail=self._mcp_detail(item),
                preview=self._mcp_result_preview(item),
            )
            return
        if item_type == "webSearch":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="web_search",
                title="Web search finished",
                status="completed",
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("query")),
                preview=self._normalize_optional_text(item.get("action")),
            )
            return
        if item_type == "plan":
            text = self._normalize_optional_text(item.get("text"))
            self.live_output.set_plan(text=text, updated_at=timestamp)
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="plan",
                title="Plan ready",
                status="completed",
                updated_at=timestamp,
                detail=text,
            )
            return
        if item_type == "reasoning":
            summary_text = self._extract_reasoning_text(item)
            if summary_text:
                self.live_output.set_reasoning(text=summary_text, kind="summary", updated_at=timestamp)
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="reasoning",
                title="Reasoning ready",
                status="completed",
                updated_at=timestamp,
                detail=summary_text,
            )
            return
        if item_type == "imageGeneration":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="image",
                title="Generated image",
                status=self._activity_status_from_value(item.get("status")),
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("revisedPrompt")) or self._normalize_optional_text(item.get("result")),
            )
            return
        if item_type == "dynamicToolCall":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="tool",
                title="Tool finished",
                status=self._activity_status_from_value(item.get("status")),
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("tool")),
            )
            return
        if item_type == "collabAgentToolCall":
            self.live_output.upsert_activity(
                activity_id=item_id,
                kind="collab",
                title="Agent collaboration finished",
                status=self._activity_status_from_value(item.get("status")),
                updated_at=timestamp,
                detail=self._normalize_optional_text(item.get("tool")) or self._normalize_optional_text(item.get("prompt")),
            )

    @staticmethod
    def _activity_status_from_value(value: Any) -> str:
        text = "" if value is None else str(value)
        lowered = text.lower()
        if lowered in {"completed", "success"}:
            return "completed"
        if lowered in {"failed", "error", "declined"}:
            return "failed"
        if lowered in {"inprogress", "running"}:
            return "running"
        if lowered in {"waiting", "pending"}:
            return "waiting"
        return "info"

    def _describe_server_request(self, method: str, params: Any) -> tuple[str, str | None, str]:
        payload = params if isinstance(params, dict) else {}
        if method == "item/commandExecution/requestApproval":
            return "Command approval requested", self._normalize_optional_text(payload.get("command")) or "Approval required for command execution", "approval"
        if method == "item/fileChange/requestApproval":
            return "Patch approval requested", self._summarize_file_changes(payload.get("changes")) or "Approval required for file changes", "approval"
        if method == "tool/requestUserInput":
            return "Waiting for user input", self._normalize_optional_text(payload.get("header")) or "Tool requested user input", "input"
        if method == "item/requestPermissions":
            return "Permissions requested", self._normalize_optional_text(payload.get("reason")) or "Additional permissions requested", "approval"
        return "Server request", method, "info"

    @staticmethod
    def _extract_turn_plan_steps(plan: Any) -> list[dict[str, str]]:
        steps: list[dict[str, str]] = []
        if not isinstance(plan, list):
            return steps
        for item in plan:
            if not isinstance(item, dict):
                continue
            step = str(item.get("step") or "").strip()
            status = str(item.get("status") or "pending").strip() or "pending"
            if step:
                steps.append({"step": step, "status": status})
        return steps

    def _command_meta(self, item: dict[str, Any]) -> list[str]:
        meta: list[str] = []
        cwd = self._normalize_optional_text(item.get("cwd"))
        if cwd:
            meta.append(cwd)
        exit_code = item.get("exitCode")
        if exit_code is not None:
            meta.append(f"exit {exit_code}")
        return meta

    def _command_completion_detail(self, item: dict[str, Any]) -> str | None:
        command = self._normalize_optional_text(item.get("command"))
        status = self._normalize_optional_text(item.get("status"))
        exit_code = item.get("exitCode")
        parts = [part for part in [command, status] if part]
        if exit_code is not None:
            parts.append(f"exit {exit_code}")
        return " | ".join(parts) if parts else None

    def _mcp_detail(self, item: dict[str, Any]) -> str | None:
        server = self._normalize_optional_text(item.get("server"))
        tool = self._normalize_optional_text(item.get("tool"))
        if server and tool:
            return f"{server} / {tool}"
        return server or tool

    def _mcp_result_preview(self, item: dict[str, Any]) -> str | None:
        result = item.get("result")
        if isinstance(result, dict):
            return self._normalize_optional_text(result.get("structuredContent")) or self._normalize_optional_text(result.get("content"))
        return self._normalize_optional_text(result)

    def _summarize_file_changes(self, changes: Any) -> str | None:
        if not isinstance(changes, list):
            return None
        parts: list[str] = []
        for change in changes[:5]:
            if not isinstance(change, dict):
                continue
            path = self._normalize_optional_text(change.get("path"))
            change_type = self._normalize_optional_text(change.get("type"))
            if path and change_type:
                parts.append(f"{change_type}: {path}")
            elif path:
                parts.append(path)
        return ", ".join(parts) if parts else None

    def _extract_reasoning_text(self, item: dict[str, Any]) -> str | None:
        summary = item.get("summary")
        if isinstance(summary, list):
            parts = []
            for entry in summary:
                if isinstance(entry, dict):
                    text = self._normalize_optional_text(entry.get("text"))
                    if text:
                        parts.append(text)
            if parts:
                return "\n".join(parts)
        content = item.get("content")
        if isinstance(content, list):
            parts = []
            for entry in content:
                text = self._normalize_optional_text(entry)
                if text:
                    parts.append(text)
            if parts:
                return "\n".join(parts)
        return None

    def _activity_title_for_known_item(self, activity_id: str) -> str | None:
        activity = self.live_output.snapshot().get("recent_activity", [])
        for item in activity:
            if item.get("id") == activity_id:
                title = self._normalize_optional_text(item.get("title"))
                if title:
                    return title
        return None

    def _ensure_transport(self) -> Any:
        with self._lock:
            existing = self._transport
        if existing is not None:
            is_running = getattr(existing, "is_running", None)
            if not callable(is_running) or is_running():
                return existing
            with self._lock:
                if self._transport is existing:
                    self._transport = None
            try:
                existing.close()
            except Exception:  # noqa: BLE001
                pass
        transport = self.transport_factory(self.on_notification)
        transport.start()
        with self._lock:
            if self._transport is None:
                self._transport = transport
                return transport
            existing = self._transport
        transport.close()
        return existing

    def _default_transport_factory(self, notification_handler: Callable[[str, dict[str, Any]], None]) -> CodexAppServerTransport:
        return CodexAppServerTransport(
            codex_bin=self.codex_bin,
            cwd=self.target_cwd,
            config_overrides=self.config_overrides,
            client_name="agent_computer",
            client_title="Agent Computer",
            client_version="0.1.0",
            experimental_api=False,
            notification_handler=notification_handler,
        )

    def _stop_watcher_locked(self) -> None:
        if self._watcher_stopped:
            return
        self.session_watcher.stop()
        self._watcher_stopped = True

    def _adopt_thread_response_locked(
        self,
        response: dict[str, Any] | Any,
        *,
        fallback_thread_id: str | None = None,
    ) -> None:
        thread = response.get("thread") if isinstance(response, dict) else None
        if isinstance(thread, dict):
            self._thread_id = self._normalize_optional_text(thread.get("id")) or fallback_thread_id or self._thread_id
            self._adopt_thread_status_locked(thread.get("status"))
        elif fallback_thread_id:
            self._thread_id = fallback_thread_id

    def _adopt_thread_status_locked(self, status_payload: Any) -> None:
        if isinstance(status_payload, dict):
            self._thread_status_type = self._normalize_optional_text(status_payload.get("type"))
            flags = status_payload.get("activeFlags", [])
            self._thread_active_flags = [str(item).strip() for item in flags if str(item).strip()] if isinstance(flags, list) else []
            return
        self._thread_status_type = self._normalize_optional_text(status_payload)
        self._thread_active_flags = []

    def _can_send_locked(self) -> bool:
        if self._thread_status_type == "notLoaded":
            return False
        if "waitingOnApproval" in self._thread_active_flags:
            return False
        return True

    def _can_interrupt_locked(self) -> bool:
        return self._active_turn_id is not None and self._thread_status_type == "active"

    @staticmethod
    def _normalize_optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _extract_error_message(self, payload: Any) -> str | None:
        if isinstance(payload, dict):
            nested = payload.get("error")
            if isinstance(nested, dict):
                message = self._normalize_optional_text(nested.get("message"))
                codex_error = nested.get("codexErrorInfo")
                detail = self._summarize_codex_error_info(codex_error)
                additional = self._normalize_optional_text(nested.get("additionalDetails"))
                parts = [part for part in [message, detail, additional] if part]
                if parts:
                    return " | ".join(parts)
            message = self._normalize_optional_text(payload.get("message"))
            if message:
                return message
        return self._normalize_optional_text(payload)

    def _summarize_codex_error_info(self, value: Any) -> str | None:
        if isinstance(value, dict):
            kind = self._normalize_optional_text(value.get("type")) or self._normalize_optional_text(value.get("code"))
            http_status = value.get("httpStatusCode")
            parts = [part for part in [kind] if part]
            if http_status is not None:
                parts.append(f"http {http_status}")
            return " ".join(parts) if parts else self._normalize_optional_text(value)
        return self._normalize_optional_text(value)
