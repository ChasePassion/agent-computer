from __future__ import annotations

import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_computer.api.routes_live_control import router as live_control_router


class StubObservationService:
    def token(self) -> str:
        return "TOKEN123"


class StubActions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def click(self, *, x: int, y: int, button: str = "left", double: bool = False) -> dict:
        payload = {"x": x, "y": y, "button": button, "double": double}
        self.calls.append(("click", payload))
        return {"ok": True, "action": "click", **payload}

    def scroll(self, *, amount: int) -> dict:
        payload = {"amount": amount}
        self.calls.append(("scroll", payload))
        return {"ok": True, "action": "scroll", **payload}

    def paste(self, *, text: str, restore_clipboard: bool = False) -> dict:
        payload = {"text": text, "restore_clipboard": restore_clipboard}
        self.calls.append(("paste", payload))
        return {"ok": True, "action": "paste", **payload}

    def press(self, *, key: str) -> dict:
        payload = {"key": key}
        self.calls.append(("press", payload))
        return {"ok": True, "action": "press", **payload}

    def hotkey(self, *, keys: list[str]) -> dict:
        payload = {"keys": keys}
        self.calls.append(("hotkey", payload))
        return {"ok": True, "action": "hotkey", **payload}


class StubActionCoordinator:
    def __init__(self) -> None:
        self.requests = []

    def execute_batch(self, request):
        self.requests.append(request)
        return {"ok": True, "actions": [item.kind for item in request.actions]}


def build_client() -> tuple[TestClient, StubActions, StubActionCoordinator]:
    app = FastAPI()
    actions = StubActions()
    action_coordinator = StubActionCoordinator()
    app.state.registry = SimpleNamespace(
        observation=StubObservationService(),
        actions=actions,
        action_coordinator=action_coordinator,
        execution_lock=threading.RLock(),
    )
    app.include_router(live_control_router)
    return TestClient(app), actions, action_coordinator


def test_live_control_requires_token() -> None:
    client, _actions, _coordinator = build_client()

    with client:
        response = client.post("/live/control/press", json={"key": "enter"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid observation token."


def test_live_control_click_and_paste_forward_to_actions() -> None:
    client, actions, _coordinator = build_client()

    with client:
        click_response = client.post(
            "/live/control/click",
            params={"token": "TOKEN123"},
            json={"x": 100, "y": 200, "button": "right", "double": False},
        )
        paste_response = client.post(
            "/live/control/paste",
            params={"token": "TOKEN123"},
            json={"text": "hello codex", "restore_clipboard": False},
        )

    assert click_response.status_code == 200
    assert paste_response.status_code == 200
    assert actions.calls == [
        ("click", {"x": 100, "y": 200, "button": "right", "double": False}),
        ("paste", {"text": "hello codex", "restore_clipboard": False}),
    ]


def test_live_control_press_and_hotkey_forward_to_actions() -> None:
    client, actions, _coordinator = build_client()

    with client:
        press_response = client.post("/live/control/press", params={"token": "TOKEN123"}, json={"key": "enter"})
        hotkey_response = client.post("/live/control/hotkey", params={"token": "TOKEN123"}, json={"keys": ["ctrl", "v"]})
        scroll_response = client.post("/live/control/scroll", params={"token": "TOKEN123"}, json={"amount": -600})

    assert press_response.status_code == 200
    assert hotkey_response.status_code == 200
    assert scroll_response.status_code == 200
    assert actions.calls == [
        ("press", {"key": "enter"}),
        ("hotkey", {"keys": ["ctrl", "v"]}),
        ("scroll", {"amount": -600}),
    ]


def test_live_control_batch_uses_one_coordinated_transaction() -> None:
    client, _actions, coordinator = build_client()

    with client:
        response = client.post(
            "/live/control/batch",
            params={"token": "TOKEN123"},
            json={
                "actions": [
                    {"kind": "paste", "text": "hello", "restore_clipboard": False},
                    {"kind": "press", "key": "enter"},
                ],
                "verify": {"kind": "fresh_frame"},
            },
        )

    assert response.status_code == 200
    assert response.json()["actions"] == ["paste", "press"]
    assert len(coordinator.requests) == 1
