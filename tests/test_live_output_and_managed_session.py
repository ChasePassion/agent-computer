from __future__ import annotations

from pathlib import Path

from agent_computer.services.codex_app_server_transport import CodexAppServerResponseError
from agent_computer.services.codex_app_server_transport import CodexAppServerTransport
from agent_computer.services.codex_managed_session_service import CodexManagedSessionService
from agent_computer.services.live_output_service import LiveOutputService
from agent_computer.services.session_service import SessionService
import agent_computer.services.live_output_service as live_output_module


class StubWatcher:
    def __init__(self, *, thread_id: str | None = None, turn_id: str | None = None) -> None:
        self.thread_id = thread_id
        self.turn_id = turn_id
        self.stop_calls = 0

    def current_session_snapshot(self) -> dict[str, str | None]:
        return {
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "rollout_path": None,
        }

    def stop(self) -> None:
        self.stop_calls += 1


class StubTransport:
    def __init__(
        self,
        responses: dict[str, list[dict[str, object]]],
        *,
        notification_handler=None,
        before_return: dict[str, list[tuple[str, dict[str, object]]]] | None = None,
    ) -> None:
        self.responses = {key: list(value) for key, value in responses.items()}
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.started = False
        self.closed = False
        self.notification_handler = notification_handler
        self.before_return = {key: list(value) for key, value in (before_return or {}).items()}

    def start(self) -> None:
        self.started = True

    def close(self) -> None:
        self.closed = True

    def is_running(self) -> bool:
        return self.started and not self.closed

    def request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.requests.append((method, dict(params or {})))
        for notification_method, notification_params in self.before_return.get(method, []):
            if self.notification_handler is not None:
                self.notification_handler(notification_method, dict(notification_params))
        queue = self.responses.get(method)
        if not queue:
            raise AssertionError(f"Unexpected request: {method}")
        return queue.pop(0)


def build_live_output(monkeypatch, tmp_path: Path) -> LiveOutputService:
    path = tmp_path / "latest.json"
    monkeypatch.setattr(live_output_module, "live_output_latest_path", lambda: path)
    return LiveOutputService(SessionService())


def test_live_output_commits_active_text(monkeypatch, tmp_path: Path) -> None:
    service = build_live_output(monkeypatch, tmp_path)

    snapshot = service.append_delta(
        text="Hel",
        session_mode="managed",
        thread_id="thr-1",
        turn_id="turn-1",
    )
    assert snapshot["active_text"] == "Hel"
    assert snapshot["latest_text"] == "Hel"
    assert snapshot["recent"] == []

    snapshot = service.append_delta(text="lo", thread_id="thr-1", turn_id="turn-1")
    assert snapshot["active_text"] == "Hello"

    snapshot = service.commit_active_text(
        kind="final",
        session_mode="managed",
        thread_id="thr-1",
        turn_id="turn-1",
    )
    assert snapshot["active_text"] is None
    assert snapshot["latest_text"] == "Hello"
    assert snapshot["recent"][-1]["kind"] == "final"
    assert snapshot["recent"][-1]["text"] == "Hello"
    assert snapshot["session_mode"] == "managed"


def test_live_output_tracks_activity_plan_and_reasoning(monkeypatch, tmp_path: Path) -> None:
    service = build_live_output(monkeypatch, tmp_path)

    snapshot = service.upsert_activity(
        activity_id="cmd-1",
        kind="command",
        title="Running command",
        status="running",
        detail="git status",
        preview="line 1",
    )
    assert snapshot["recent_activity"][0]["id"] == "cmd-1"
    assert snapshot["recent_activity"][0]["detail"] == "git status"

    snapshot = service.upsert_activity(
        activity_id="cmd-1",
        kind="command",
        title="Running command",
        status="completed",
        preview="\nline 2",
        append_preview=True,
    )
    assert "line 1" in snapshot["recent_activity"][0]["preview"]
    assert "line 2" in snapshot["recent_activity"][0]["preview"]

    snapshot = service.set_plan(
        explanation="Plan note",
        steps=[{"step": "Do the thing", "status": "in_progress"}],
    )
    assert snapshot["plan"]["explanation"] == "Plan note"
    assert snapshot["plan"]["steps"][0]["step"] == "Do the thing"

    snapshot = service.append_reasoning_delta(text="Reasoning summary", kind="summary")
    assert snapshot["reasoning"]["text"] == "Reasoning summary"
    assert snapshot["reasoning"]["kind"] == "summary"


def test_managed_session_starts_thread_and_turn(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher()
    transport = StubTransport(
        {
            "thread/start": [{"thread": {"id": "thr-new", "status": {"type": "idle"}}}],
            "turn/start": [{"turn": {"id": "turn-1"}}],
        }
    )
    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=lambda _handler: transport,
    )

    payload = service.send_message("hello from live")

    assert payload["dispatched_as"] == "turn_start"
    assert watcher.stop_calls == 1
    assert transport.started is True
    assert transport.requests[0][0] == "thread/start"
    assert transport.requests[1][0] == "turn/start"
    assert transport.requests[1][1]["input"] == [{"type": "text", "text": "hello from live"}]
    snapshot = live_output.snapshot()
    assert snapshot["session_mode"] == "managed"
    assert snapshot["thread_id"] == "thr-new"
    assert snapshot["turn_id"] == "turn-1"
    assert snapshot["status"] == "running"


def test_managed_session_resumes_and_steers_active_turn(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher(thread_id="thr-existing", turn_id="turn-existing")
    transport = StubTransport(
        {
            "thread/resume": [{"thread": {"id": "thr-existing", "status": {"type": "active"}}}],
            "turn/steer": [{"turnId": "turn-existing"}],
        }
    )
    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=lambda _handler: transport,
    )

    payload = service.send_message("continue")

    assert payload["dispatched_as"] == "turn_steer"
    assert watcher.stop_calls == 1
    assert transport.requests[0][0] == "thread/resume"
    assert transport.requests[1][0] == "turn/steer"
    assert transport.requests[1][1]["expectedTurnId"] == "turn-existing"


def test_managed_notifications_commit_delta_to_recent(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher()
    transport = StubTransport({})
    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=lambda _handler: transport,
    )

    with service._lock:
        service._thread_id = "thr-1"
        service._active_turn_id = "turn-1"
        service._thread_status_type = "active"

    service.on_notification(
        "item/agentMessage/delta",
        {
            "threadId": "thr-1",
            "turnId": "turn-1",
            "delta": "Hello world",
        },
    )
    service.on_notification(
        "turn/completed",
        {
            "threadId": "thr-1",
            "turn": {
                "id": "turn-1",
                "status": "completed",
            },
        },
    )

    snapshot = live_output.snapshot()
    assert snapshot["active_text"] is None
    assert snapshot["recent"][-1]["text"] == "Hello world"
    assert snapshot["status"] == "idle"
    assert snapshot["turn_id"] == "turn-1"


def test_managed_notifications_render_command_activity(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher()
    transport = StubTransport({})
    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=lambda _handler: transport,
    )

    with service._lock:
        service._thread_id = "thr-1"

    service.on_notification(
        "item/started",
        {
            "threadId": "thr-1",
            "turnId": "turn-1",
            "item": {
                "type": "commandExecution",
                "id": "item-cmd",
                "command": "git status",
                "cwd": str(tmp_path),
                "status": "inProgress",
            },
        },
    )
    service.on_notification(
        "item/commandExecution/outputDelta",
        {
            "threadId": "thr-1",
            "turnId": "turn-1",
            "itemId": "item-cmd",
            "delta": "On branch main",
        },
    )
    service.on_notification(
        "item/completed",
        {
            "threadId": "thr-1",
            "turnId": "turn-1",
            "item": {
                "type": "commandExecution",
                "id": "item-cmd",
                "command": "git status",
                "cwd": str(tmp_path),
                "status": "completed",
                "exitCode": 0,
                "aggregatedOutput": "On branch main",
            },
        },
    )

    snapshot = live_output.snapshot()
    activity = next(item for item in snapshot["recent_activity"] if item["id"] == "item-cmd")
    assert activity["kind"] == "command"
    assert activity["status"] == "completed"
    assert "git status" in activity["detail"]
    assert "On branch main" in activity["preview"]


def test_send_message_does_not_deadlock_when_notification_arrives_before_response(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher(thread_id="thr-existing", turn_id="turn-existing")
    holder: dict[str, StubTransport] = {}

    def factory(handler):
        transport = StubTransport(
            {
                "thread/resume": [{"thread": {"id": "thr-existing", "status": {"type": "active", "activeFlags": []}}}],
                "turn/steer": [{"turnId": "turn-existing"}],
            },
            notification_handler=handler,
            before_return={
                "thread/resume": [
                    ("thread/status/changed", {"threadId": "thr-existing", "status": {"type": "active", "activeFlags": []}})
                ]
            },
        )
        holder["transport"] = transport
        return transport

    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=factory,
    )

    payload = service.send_message("continue")

    assert payload["dispatched_as"] == "turn_steer"
    assert holder["transport"].requests[0][0] == "thread/resume"
    assert holder["transport"].requests[1][0] == "turn/steer"


class SteerFallbackTransport(StubTransport):
    def request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        if method == "turn/steer":
            self.requests.append((method, dict(params or {})))
            raise CodexAppServerResponseError(code=-32600, message="no active turn to steer")
        return super().request(method, params)


def test_send_message_falls_back_to_turn_start_when_steer_has_no_active_turn(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher(thread_id="thr-existing", turn_id="turn-existing")
    transport = SteerFallbackTransport(
        {
            "thread/resume": [{"thread": {"id": "thr-existing", "status": {"type": "idle"}}}],
            "turn/start": [{"turn": {"id": "turn-new"}}],
        }
    )
    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=lambda _handler: transport,
    )

    payload = service.send_message("continue")

    assert payload["dispatched_as"] == "turn_start"
    assert transport.requests[0][0] == "thread/resume"
    assert transport.requests[1][0] == "turn/steer"
    assert transport.requests[2][0] == "turn/start"


def test_send_message_recreates_dead_transport(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher(thread_id="thr-existing")
    dead_transport = StubTransport({})
    dead_transport.started = True
    dead_transport.closed = True
    fresh_transport = StubTransport(
        {
            "thread/resume": [{"thread": {"id": "thr-existing", "status": {"type": "idle"}}}],
            "turn/start": [{"turn": {"id": "turn-new"}}],
        }
    )
    calls = {"count": 0}

    def factory(handler):
        calls["count"] += 1
        return fresh_transport

    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=factory,
    )
    with service._lock:
        service._transport = dead_transport
        service._thread_id = "thr-existing"
        service._thread_status_type = "systemError"

    payload = service.send_message("retry")

    assert payload["ok"] is True
    assert calls["count"] == 1
    assert fresh_transport.requests[0][0] == "turn/start"


def test_error_notification_uses_nested_error_message(monkeypatch, tmp_path: Path) -> None:
    live_output = build_live_output(monkeypatch, tmp_path)
    watcher = StubWatcher()
    service = CodexManagedSessionService(
        live_output,
        watcher,
        target_cwd=tmp_path,
        transport_factory=lambda _handler: StubTransport({}),
    )

    with service._lock:
        service._thread_id = "thr-1"
        service._thread_status_type = "active"

    service.on_notification(
        "error",
        {
            "threadId": "thr-1",
            "error": {
                "message": "Usage limit exceeded",
                "codexErrorInfo": {"type": "UsageLimitExceeded", "httpStatusCode": 429},
            },
        },
    )

    snapshot = live_output.snapshot()
    assert snapshot["last_error"] == "Usage limit exceeded | UsageLimitExceeded http 429"
    assert snapshot["recent_activity"][0]["detail"] == "Usage limit exceeded | UsageLimitExceeded http 429"


def test_transport_resolves_windows_npm_codex(monkeypatch, tmp_path: Path) -> None:
    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    codex_cmd = npm_dir / "codex.cmd"
    codex_cmd.write_text("@echo off\r\n", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("agent_computer.services.codex_app_server_transport.os.name", "nt")
    monkeypatch.setattr("agent_computer.services.codex_app_server_transport.shutil.which", lambda _name: None)
    transport = CodexAppServerTransport(codex_bin="codex")

    assert transport._resolve_codex_bin() == str(codex_cmd)
