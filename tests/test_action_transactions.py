from __future__ import annotations

import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_computer.api.routes_transactions import router as transaction_router
from agent_computer.models.transactions import ActAndObserveRequest, BatchActAndObserveRequest
from agent_computer.services.action_coordinator import (
    ActionCoordinator,
    ActionOutcomeUnknownError,
    ActionPreconditionError,
)


class RecordingActions:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def press(self, *, key: str) -> dict:
        self.calls.append(("press", key))
        return {"pressed": key}

    def paste(self, *, text: str, restore_clipboard: bool = False) -> dict:
        self.calls.append(("paste", text))
        return {"pasted_length": len(text), "restore_clipboard": restore_clipboard}

    def click(self, *, x: int, y: int, button: str, double: bool) -> dict:
        self.calls.append(("click", (x, y)))
        return {"clicked": [x, y], "button": button, "double": double}


class RecordingObservation:
    def __init__(self) -> None:
        self.refresh_reasons: list[str] = []

    def latest(self, mode: str) -> dict:
        assert mode == "grid"
        return {
            "mode": "grid",
            "frame_seq": 5,
            "screen_digest": "before",
            "captured_monotonic_ns": 10,
        }

    def refresh_now(self, *, reason: str = "scheduled") -> dict[str, dict]:
        self.refresh_reasons.append(reason)
        return {
            "preview": {"mode": "preview", "frame_seq": 6, "screen_digest": "after"},
            "grid": {
                "mode": "grid",
                "frame_seq": 6,
                "screen_digest": "after",
                "captured_monotonic_ns": 20,
            },
        }


def test_act_and_observe_returns_a_post_action_frame_and_verification() -> None:
    actions = RecordingActions()
    observation = RecordingObservation()
    coordinator = ActionCoordinator(actions, observation, execution_lock=threading.RLock())
    request = ActAndObserveRequest.model_validate(
        {
            "action": {"kind": "press", "key": "enter"},
            "verify": {"kind": "frame_changed"},
        }
    )

    result = coordinator.execute(request)

    assert result["action_result"] == {"pressed": "enter"}
    assert result["pre_frame_seq"] == 5
    assert result["post_frame"]["frame_seq"] == 6
    assert result["verification"]["status"] == "passed"
    assert actions.calls == [("press", "enter")]
    assert observation.refresh_reasons == ["post_action"]


def test_batch_executes_compound_actions_with_one_post_action_capture() -> None:
    actions = RecordingActions()
    observation = RecordingObservation()
    coordinator = ActionCoordinator(actions, observation, execution_lock=threading.RLock())
    request = BatchActAndObserveRequest.model_validate(
        {
            "actions": [
                {"kind": "paste", "text": "hello", "restore_clipboard": False},
                {"kind": "press", "key": "enter"},
            ]
        }
    )

    result = coordinator.execute_batch(request)

    assert actions.calls == [("paste", "hello"), ("press", "enter")]
    assert len(result["action_results"]) == 2
    assert result["verification"]["status"] == "not_requested"
    assert observation.refresh_reasons == ["post_action_batch"]


def test_coordinate_action_validates_window_layout_and_point_before_dispatch() -> None:
    actions = RecordingActions()
    observation = RecordingObservation()
    validation_calls: list[dict[str, object]] = []

    def validate(**kwargs: object) -> dict[str, object]:
        validation_calls.append(kwargs)
        return {"ok": True}

    coordinator = ActionCoordinator(
        actions,
        observation,
        execution_lock=threading.RLock(),
        display_precondition_validator=validate,
    )
    request = ActAndObserveRequest.model_validate(
        {
            "action": {"kind": "click", "x": -500, "y": 320},
            "preconditions": {
                "expected_window_handle": 101,
                "expected_window_bounds": [-1200, 80, -200, 880],
                "expected_layout_version": "display-layout-v1:abc",
            },
        }
    )

    coordinator.execute(request)

    assert validation_calls == [
        {
            "expected_hwnd": 101,
            "bounds": (-1200, 80, -200, 880),
            "layout_version": "display-layout-v1:abc",
            "point": (-500, 320),
        }
    ]
    assert actions.calls == [("click", (-500, 320))]


def test_post_action_capture_failure_is_not_safe_to_retry() -> None:
    class FailingObservation(RecordingObservation):
        def refresh_now(self, *, reason: str = "scheduled") -> dict[str, dict]:
            self.refresh_reasons.append(reason)
            raise RuntimeError("capture backend unavailable")

    actions = RecordingActions()
    observation = FailingObservation()
    coordinator = ActionCoordinator(actions, observation, execution_lock=threading.RLock())
    request = ActAndObserveRequest.model_validate(
        {"action": {"kind": "press", "key": "enter"}}
    )

    try:
        coordinator.execute(request)
    except ActionOutcomeUnknownError as exc:
        assert exc.details["outcome"] == "action_dispatched_observation_failed"
        assert exc.details["actionMayHaveExecuted"] is True
        assert exc.details["executedActionCount"] == 1
    else:
        raise AssertionError("Expected an ambiguous post-action observation failure.")

    assert actions.calls == [("press", "enter")]
    assert observation.refresh_reasons == ["post_action"]


def test_transaction_route_reports_stale_precondition_as_conflict() -> None:
    class RejectingCoordinator:
        def execute(self, _request):
            raise ActionPreconditionError("display layout changed")

    app = FastAPI()
    app.state.registry = SimpleNamespace(action_coordinator=RejectingCoordinator())
    app.include_router(transaction_router)

    with TestClient(app) as client:
        response = client.post(
            "/actions/act-and-observe",
            json={"action": {"kind": "press", "key": "enter"}},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["retryDisposition"] == "reacquire_target"


def test_transaction_route_marks_post_action_observation_failure_as_non_retryable() -> None:
    class AmbiguousCoordinator:
        def execute(self, _request):
            raise ActionOutcomeUnknownError(
                "action dispatched but observation failed",
                action_id="action-test",
                executed_action_count=1,
                action_count=1,
            )

    app = FastAPI()
    app.state.registry = SimpleNamespace(action_coordinator=AmbiguousCoordinator())
    app.include_router(transaction_router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/actions/act-and-observe",
            json={"action": {"kind": "press", "key": "enter"}},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == {
        "message": "action dispatched but observation failed",
        "retryDisposition": "fail_fast",
        "details": {
            "actionId": "action-test",
            "outcome": "action_dispatched_observation_failed",
            "actionMayHaveExecuted": True,
            "executedActionCount": 1,
            "actionCount": 1,
        },
    }
