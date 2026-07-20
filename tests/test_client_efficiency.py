from __future__ import annotations

from typing import Any

import httpx
import pytest

from agent_computer.client import DaemonClient


class StubResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class RecordingHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __enter__(self) -> "RecordingHttpClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def get(self, path: str) -> StubResponse:
        self.calls.append(("GET", path))
        return StubResponse({"status": "ok"})

    def request(
        self,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None,
        headers: dict[str, str] | None = None,
    ) -> StubResponse:
        self.calls.append((method, url))
        return StubResponse({"ok": True, "payload": json})


def test_request_does_not_probe_health_when_daemon_accepts_business_request(monkeypatch) -> None:
    client = DaemonClient()
    http = RecordingHttpClient()
    monkeypatch.setattr(client, "_http_client", lambda: http)

    result = client.request("POST", "/actions/press", {"key": "enter"})

    assert result == {"ok": True, "payload": {"key": "enter"}}
    assert http.calls == [("POST", "/actions/press")]


def test_request_does_not_replay_action_after_ambiguous_read_timeout(monkeypatch) -> None:
    client = DaemonClient()
    attempts: list[str] = []
    spawned: list[bool] = []

    def fail_after_send(_method: str, _path: str, _payload=None, **_kwargs):
        attempts.append("request")
        raise httpx.ReadTimeout("response was lost")

    monkeypatch.setattr(client, "_request_once", fail_after_send)
    monkeypatch.setattr(client, "_spawn_background", lambda: spawned.append(True))
    monkeypatch.setattr(client, "wait_until_ready", lambda: {"status": "ok"})

    with pytest.raises(httpx.ReadTimeout):
        client.request("POST", "/actions/press", {"key": "enter"})

    assert attempts == ["request"]
    assert spawned == []
