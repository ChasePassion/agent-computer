from __future__ import annotations

import io
import json

from agent_computer.stdio_server import run_stdio


class StubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, payload: dict | None = None):
        self.calls.append((method, path, payload))
        return {"path": path, "sequence": len(self.calls)}


def test_stdio_server_reuses_one_client_for_multiple_requests() -> None:
    source = io.StringIO(
        "\n".join(
            [
                json.dumps({"id": "one", "method": "POST", "path": "/actions/press", "payload": {"key": "enter"}}),
                json.dumps({"id": "two", "method": "GET", "path": "/system/health"}),
            ]
        )
        + "\n"
    )
    destination = io.StringIO()
    client = StubClient()

    run_stdio(source, destination, client=client)

    responses = [json.loads(line) for line in destination.getvalue().splitlines()]
    assert responses == [
        {"id": "one", "ok": True, "result": {"path": "/actions/press", "sequence": 1}},
        {"id": "two", "ok": True, "result": {"path": "/system/health", "sequence": 2}},
    ]
    assert client.calls == [
        ("POST", "/actions/press", {"key": "enter"}),
        ("GET", "/system/health", None),
    ]
