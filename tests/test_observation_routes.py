from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_computer.api.routes_observation import router as observation_router


class StubObservationService:
    def __init__(self) -> None:
        self.live_calls: list[str] = []
        self.model_calls: list[str] = []

    def token(self) -> str:
        return "TOKEN123"

    def latest_live_image_path(self, mode: str):
        self.live_calls.append(mode)
        return __file__

    def latest_image_path(self, mode: str):
        self.model_calls.append(mode)
        return __file__

    def latest(self, mode: str):
        return {
            "image_path": __file__,
            "live_image_path": __file__,
            "width": 100,
            "height": 100,
            "desktop_width": 100,
            "desktop_height": 100,
            "updated_at": "2026-03-17T12:00:00+08:00",
            "frame_seq": 1,
            "mouse_position": {"x": 1, "y": 2},
            "mode": mode,
        }


def test_live_frame_uses_live_image_path() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(observation=observation)
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live/frame.jpg", params={"token": "TOKEN123", "mode": "preview"})

    assert response.status_code == 200
    assert observation.live_calls == ["preview"]
    assert observation.model_calls == []


def test_live_page_exposes_remote_control_surface() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(observation=observation)
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live", params={"token": "TOKEN123"})

    assert response.status_code == 200
    assert "Remote Control" in response.text
    assert "Selected Point" not in response.text
    assert "Paste + Enter" in response.text
    assert ">Move<" not in response.text
    assert "Ctrl+C" in response.text
    assert "Backspace" in response.text
    assert "Ctrl+V" not in response.text
    assert "Tab" not in response.text
    assert "Interrupt" not in response.text
    assert "Send a message to the current Codex session" not in response.text


def test_live_state_only_returns_frame_payload() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(observation=observation)
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live/state.json", params={"token": "TOKEN123", "mode": "preview"})

    assert response.status_code == 200
    payload = response.json()
    assert list(payload.keys()) == ["frame"]
    assert payload["frame"]["mode"] == "preview"
    assert payload["frame"]["image_url"] == "/live/frame.jpg?token=TOKEN123&mode=preview"


def test_model_latest_json_uses_relative_image_url() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(observation=observation)
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/observation/latest.json", params={"token": "TOKEN123", "mode": "grid"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "grid"
    assert payload["image_url"] == "/observation/latest.jpg?token=TOKEN123&mode=grid"
