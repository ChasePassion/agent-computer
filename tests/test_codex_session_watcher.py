from __future__ import annotations

import json
from pathlib import Path

from agent_computer.services import codex_session_watcher as watcher_module
from agent_computer.services import live_output_service as live_output_module
from agent_computer.services.codex_session_watcher import CodexSessionWatcher
from agent_computer.services.live_output_service import LiveOutputService


def test_codex_session_watcher_replays_latest_rollout(tmp_path, monkeypatch) -> None:
    live_output_path = tmp_path / "live-output.json"
    monkeypatch.setattr(live_output_module, "live_output_latest_path", lambda: live_output_path)
    monkeypatch.setattr(watcher_module, "list_windows", lambda: [])

    codex_home = tmp_path / ".codex"
    rollout_dir = codex_home / "sessions" / "2026" / "03" / "17"
    rollout_dir.mkdir(parents=True)
    rollout_path = rollout_dir / "rollout-2026-03-17T12-00-00-abc.jsonl"
    target_cwd = (tmp_path / "workspace").resolve()
    target_cwd.mkdir()

    lines = [
        {
            "type": "session_meta",
            "payload": {
                "id": "thread-123",
                "cwd": str(target_cwd),
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-03-17T12:00:01+08:00",
            "payload": {
                "type": "task_started",
                "turn_id": "turn-456",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-03-17T12:00:02+08:00",
            "payload": {
                "type": "agent_message",
                "message": "first commentary",
            },
        },
        {
            "type": "event_msg",
            "timestamp": "2026-03-17T12:00:03+08:00",
            "payload": {
                "type": "task_complete",
                "turn_id": "turn-456",
                "last_agent_message": "final answer",
            },
        },
    ]
    rollout_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n", encoding="utf-8")

    live_output = LiveOutputService()
    watcher = CodexSessionWatcher(
        live_output,
        codex_home=codex_home,
        target_cwd=target_cwd,
        poll_interval_sec=0.25,
    )

    watcher.poll_once()
    snapshot = live_output.snapshot()

    assert snapshot["session_mode"] == "attach_readonly"
    assert snapshot["thread_id"] == "thread-123"
    assert snapshot["turn_id"] == "turn-456"
    assert snapshot["status"] == "idle"
    assert [item["text"] for item in snapshot["recent"]] == ["first commentary", "final answer"]
    assert live_output_path.exists()


def test_codex_session_watcher_lists_and_selects_sessions(tmp_path, monkeypatch) -> None:
    live_output_path = tmp_path / "live-output.json"
    monkeypatch.setattr(live_output_module, "live_output_latest_path", lambda: live_output_path)
    monkeypatch.setattr(watcher_module, "list_windows", lambda: [])

    codex_home = tmp_path / ".codex"
    target_cwd = (tmp_path / "workspace").resolve()
    target_cwd.mkdir()
    rollout_dir = codex_home / "sessions" / "2026" / "03" / "17"
    rollout_dir.mkdir(parents=True)
    session_index_path = codex_home / "session_index.jsonl"
    session_index_path.parent.mkdir(parents=True, exist_ok=True)
    session_index_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "thread-111", "thread_name": "alpha", "updated_at": "2026-03-17T12:00:00Z"}),
                json.dumps({"id": "thread-222", "thread_name": "beta", "updated_at": "2026-03-17T12:01:00Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def write_rollout(path: Path, session_id: str, message: str) -> None:
        lines = [
            {"type": "session_meta", "payload": {"id": session_id, "cwd": str(target_cwd)}},
            {"type": "event_msg", "timestamp": "2026-03-17T12:00:01+08:00", "payload": {"type": "task_started", "turn_id": f"{session_id}-turn"}},
            {"type": "event_msg", "timestamp": "2026-03-17T12:00:02+08:00", "payload": {"type": "task_complete", "turn_id": f"{session_id}-turn", "last_agent_message": message}},
        ]
        path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in lines) + "\n", encoding="utf-8")

    rollout_a = rollout_dir / "rollout-2026-03-17T12-00-00-thread-111.jsonl"
    rollout_b = rollout_dir / "rollout-2026-03-17T12-01-00-thread-222.jsonl"
    write_rollout(rollout_a, "thread-111", "alpha final")
    write_rollout(rollout_b, "thread-222", "beta final")

    live_output = LiveOutputService()
    watcher = CodexSessionWatcher(live_output, codex_home=codex_home, target_cwd=target_cwd, poll_interval_sec=0.25)

    watcher.poll_once()
    sessions = watcher.sessions_snapshot()
    assert [item["session_id"] for item in sessions["items"]] == ["thread-222", "thread-111"]
    assert sessions["items"][0]["thread_name"] == "beta"
    assert live_output.snapshot()["thread_id"] == "thread-222"

    watcher.select_session("thread-111")
    selected = watcher.sessions_snapshot()
    assert selected["selection_mode"] == "manual"
    assert selected["selected_session_id"] == "thread-111"
    assert live_output.snapshot()["thread_id"] == "thread-111"
    assert live_output.snapshot()["recent"][-1]["text"] == "alpha final"
