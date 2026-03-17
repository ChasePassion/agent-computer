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
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=SimpleNamespace(snapshot=lambda: {"status": "no_output"}),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live/frame.jpg", params={"token": "TOKEN123", "mode": "preview"})

    assert response.status_code == 200
    assert observation.live_calls == ["preview"]
    assert observation.model_calls == []
