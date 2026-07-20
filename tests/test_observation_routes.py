from __future__ import annotations
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_computer.api.routes_observation import router as observation_router


class StubObservationService:
    def __init__(self) -> None:
        self.live_calls: list[str] = []
        self.model_calls: list[str] = []
        self.wait_calls: list[tuple[str, int, float]] = []
        self.frame_path_calls: list[tuple[str, int]] = []

    def token(self) -> str:
        return "TOKEN123"

    def latest_live_image_path(self, mode: str):
        self.live_calls.append(mode)
        return __file__

    def latest_image_path(self, mode: str):
        self.model_calls.append(mode)
        return __file__

    def image_path_for_frame(self, mode: str, frame_seq: int):
        self.frame_path_calls.append((mode, frame_seq))
        return __file__

    def latest(self, mode: str):
        return {
            "image_path": __file__,
            "live_image_path": __file__,
            "width": 100,
            "height": 100,
            "desktop_width": 100,
            "desktop_height": 100,
            "bounds": [0, 0, 100, 100],
            "updated_at": "2026-03-17T12:00:00+08:00",
            "frame_seq": 1,
            "mouse_position": {"x": 1, "y": 2},
            "mode": mode,
        }

    def wait_for_frame(self, mode: str, *, after_seq: int, timeout_sec: float):
        self.wait_calls.append((mode, after_seq, timeout_sec))
        payload = self.latest(mode)
        payload["frame_seq"] = after_seq + 1
        return payload


class StubLiveOutputService:
    def snapshot(self) -> dict[str, object]:
        return {
            "session_id": "sess-1",
            "session_mode": "attach_readonly",
            "status": "running",
            "updated_at": "2026-03-17T12:01:00+08:00",
            "recent": [
                {
                    "seq": 7,
                    "kind": "commentary",
                    "text": "hello from codex",
                    "created_at": "2026-03-17T12:01:00+08:00",
                }
            ],
        }


class StubCodexSessionWatcher:
    def __init__(self) -> None:
        self.selected_session_id: str | None = None

    def sessions_snapshot(self) -> dict[str, object]:
        items = [
            {
                "session_id": "sess-1",
                "thread_name": "alpha",
                "updated_at": "2026-03-17T12:01:00+08:00",
                "rollout_path": "C:/rollouts/sess-1.jsonl",
                "window_matches": [],
                "selected": self.selected_session_id == "sess-1",
                "current": (self.selected_session_id or "sess-1") == "sess-1",
            },
            {
                "session_id": "sess-2",
                "thread_name": "beta",
                "updated_at": "2026-03-17T12:02:00+08:00",
                "rollout_path": "C:/rollouts/sess-2.jsonl",
                "window_matches": ["Codex beta"],
                "selected": self.selected_session_id == "sess-2",
                "current": self.selected_session_id == "sess-2",
            },
        ]
        return {
            "selection_mode": "manual" if self.selected_session_id else "auto",
            "selected_session_id": self.selected_session_id,
            "current_session_id": self.selected_session_id or "sess-1",
            "current_turn_id": "turn-1",
            "items": items,
        }

    def select_session(self, session_id: str | None) -> dict[str, object]:
        if session_id not in {None, "sess-1", "sess-2"}:
            raise KeyError(session_id)
        self.selected_session_id = session_id
        return self.sessions_snapshot()


def test_live_frame_uses_live_image_path() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live/frame.jpg", params={"token": "TOKEN123", "mode": "preview"})

    assert response.status_code == 200
    assert observation.live_calls == ["preview"]
    assert observation.model_calls == []


def test_live_page_exposes_remote_control_surface() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live", params={"token": "TOKEN123"})

    assert response.status_code == 200
    assert "Remote Control" in response.text
    assert "Codex Live" in response.text
    assert "Transcript" in response.text
    assert "Follow Latest" in response.text
    assert "Selected Point" not in response.text
    assert "Paste + Enter" in response.text
    assert ">Move<" not in response.text
    assert "Ctrl+C" in response.text
    assert "Backspace" in response.text
    assert "Ctrl+V" not in response.text
    assert "Tab" not in response.text
    assert "Interrupt" not in response.text
    assert "Send a message to the current Codex session" not in response.text


def test_live_page_polling_is_single_flight_and_visibility_aware() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live", params={"token": "TOKEN123"})

    assert response.status_code == 200
    assert "let pollInFlight = false" in response.text
    assert "let pollPending = false" in response.text
    assert 'document.addEventListener("visibilitychange"' in response.text
    assert "Math.min(30000" in response.text
    assert "framePayload.mode" in response.text
    assert "framePayload.frame_seq" in response.text
    assert "Date.now()" not in response.text.split("function applyFrame", 1)[1].split("function parseFramePoint", 1)[0]


def test_live_page_paste_and_enter_uses_one_batch_request() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live", params={"token": "TOKEN123"})

    script = response.text.split('document.getElementById("paste-enter-btn").addEventListener', 1)[1]
    script = script.split('document.getElementById("ctrl-c-btn")', 1)[0]
    assert 'runControl("Paste + Enter", "batch"' in script
    assert 'await runControl("Paste", "paste"' not in script


def test_live_state_returns_frame_and_output_payload() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/live/state.json", params={"token": "TOKEN123", "mode": "preview"})

    assert response.status_code == 200
    payload = response.json()
    assert list(payload.keys()) == ["frame", "output", "sessions"]
    assert payload["frame"]["mode"] == "preview"
    assert payload["frame"]["bounds"] == [0, 0, 100, 100]
    assert payload["frame"]["image_url"] == "/live/frame.jpg?token=TOKEN123&mode=preview"
    assert payload["output"]["session_id"] == "sess-1"
    assert payload["output"]["status"] == "running"
    assert payload["output"]["recent"][0]["text"] == "hello from codex"
    assert payload["sessions"]["selection_mode"] == "auto"
    assert len(payload["sessions"]["items"]) == 2


def test_live_session_select_switches_viewed_session() -> None:
    observation = StubObservationService()
    watcher = StubCodexSessionWatcher()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=watcher,
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.post("/live/session/select", params={"token": "TOKEN123"}, json={"session_id": "sess-2"})

    assert response.status_code == 200
    payload = response.json()
    assert watcher.selected_session_id == "sess-2"
    assert payload["selection_mode"] == "manual"
    assert payload["selected_session_id"] == "sess-2"


def test_model_latest_json_uses_relative_image_url() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get("/observation/latest.json", params={"token": "TOKEN123", "mode": "grid"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "grid"
    assert payload["image_url"] == "/observation/latest.jpg?token=TOKEN123&mode=grid&frame_seq=1"


def test_model_image_can_be_fenced_to_metadata_frame_sequence() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get(
            "/observation/latest.jpg",
            params={"token": "TOKEN123", "mode": "grid", "frame_seq": 7},
        )

    assert response.status_code == 200
    assert observation.frame_path_calls == [("grid", 7)]


def test_model_latest_json_can_wait_for_a_newer_frame() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get(
            "/observation/latest.json",
            params={"token": "TOKEN123", "mode": "grid", "after_seq": 7, "timeout_ms": 1250},
        )

    assert response.status_code == 200
    assert response.json()["frame_seq"] == 8
    assert observation.wait_calls == [("grid", 7, 1.25)]


def test_model_observation_accepts_token_header_for_stdio_clients() -> None:
    observation = StubObservationService()
    app = FastAPI()
    app.state.registry = SimpleNamespace(
        observation=observation,
        live_output=StubLiveOutputService(),
        codex_session_watcher=StubCodexSessionWatcher(),
    )
    app.include_router(observation_router)

    with TestClient(app) as client:
        response = client.get(
            "/observation/latest.json",
            params={"mode": "grid"},
            headers={"X-Agent-Computer-Token": "TOKEN123"},
        )

    assert response.status_code == 200
