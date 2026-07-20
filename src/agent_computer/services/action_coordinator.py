from __future__ import annotations

import threading
import time
from typing import Any, Callable
from uuid import uuid4

from agent_computer.models.transactions import (
    ActionPreconditions,
    ActAndObserveRequest,
    BatchActAndObserveRequest,
    DesktopActionCommand,
    DesktopVerifySpec,
)
from agent_computer.services.action_service import ActionService
from agent_computer.services.observation_service import ObservationService
from agent_computer.structured_logging import get_event_logger, log_event


LOGGER = get_event_logger("action-coordinator")


class ActionPreconditionError(RuntimeError):
    pass


class ActionOutcomeUnknownError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        action_id: str,
        executed_action_count: int,
        action_count: int,
    ) -> None:
        super().__init__(message)
        self.details = {
            "actionId": action_id,
            "outcome": "action_dispatched_observation_failed",
            "actionMayHaveExecuted": executed_action_count > 0,
            "executedActionCount": executed_action_count,
            "actionCount": action_count,
        }


class ActionCoordinator:
    def __init__(
        self,
        actions: ActionService,
        observation: ObservationService,
        *,
        execution_lock: threading.RLock,
        metrics: Any | None = None,
        display_precondition_validator: Callable[..., dict[str, object]] | None = None,
    ) -> None:
        self.actions = actions
        self.observation = observation
        self.execution_lock = execution_lock
        self.metrics = metrics
        self.display_precondition_validator = display_precondition_validator

    def execute(self, request: ActAndObserveRequest) -> dict[str, Any]:
        started_ns = time.monotonic_ns()
        action_id = f"action-{uuid4().hex}"
        try:
            with self.execution_lock:
                pre_frame = self.observation.latest("grid")
                self._validate_preconditions(request.preconditions, pre_frame)
                self._validate_display_preconditions(request.preconditions, request.action)
                dispatch_started_ns = time.monotonic_ns()
                action_result = self._dispatch(request.action)
                dispatch_completed_ns = time.monotonic_ns()
                try:
                    frames = self.observation.refresh_now(reason="post_action")
                except Exception as exc:
                    raise ActionOutcomeUnknownError(
                        "The desktop action was dispatched, but its post-action observation failed. "
                        "Do not retry the action automatically.",
                        action_id=action_id,
                        executed_action_count=1,
                        action_count=1,
                    ) from exc
                post_frame = frames["grid"]
        except Exception:
            duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000
            self._record_metric("desktop.act_and_observe", duration_ms, "failed")
            log_event(
                LOGGER,
                event="desktop.action_failed",
                message="Desktop action transaction failed",
                outcome="failed",
                action_id=action_id,
                action_kind=request.action.kind,
                duration_ms=round(duration_ms, 3),
                exc_info=True,
            )
            raise

        result = {
            "action_id": action_id,
            "action_result": action_result,
            "pre_frame_seq": None if pre_frame is None else pre_frame.get("frame_seq"),
            "post_frame": post_frame,
            "verification": self._verify(request.verify, pre_frame, post_frame),
            "timings_ms": {
                "dispatch": round((dispatch_completed_ns - dispatch_started_ns) / 1_000_000, 3),
                "observe": round((time.monotonic_ns() - dispatch_completed_ns) / 1_000_000, 3),
                "total": round((time.monotonic_ns() - started_ns) / 1_000_000, 3),
            },
        }
        self._record_metric("desktop.act_and_observe", result["timings_ms"]["total"], "success")
        log_event(
            LOGGER,
            event="desktop.action_completed",
            message="Desktop action transaction completed",
            outcome=result["verification"]["status"],
            action_id=action_id,
            action_kind=request.action.kind,
            pre_frame_seq=result["pre_frame_seq"],
            post_frame_seq=post_frame.get("frame_seq"),
            duration_ms=result["timings_ms"]["total"],
        )
        return result

    def execute_batch(self, request: BatchActAndObserveRequest) -> dict[str, Any]:
        started_ns = time.monotonic_ns()
        action_id = f"batch-{uuid4().hex}"
        try:
            with self.execution_lock:
                pre_frame = self.observation.latest("grid")
                self._validate_preconditions(request.preconditions, pre_frame)
                coordinate_actions = [action for action in request.actions if action.kind in {"move", "click"}]
                if coordinate_actions:
                    for action in coordinate_actions:
                        self._validate_display_preconditions(request.preconditions, action)
                else:
                    self._validate_display_preconditions(request.preconditions, None)
                dispatch_started_ns = time.monotonic_ns()
                action_results = [self._dispatch(action) for action in request.actions]
                dispatch_completed_ns = time.monotonic_ns()
                try:
                    frames = self.observation.refresh_now(reason="post_action_batch")
                except Exception as exc:
                    raise ActionOutcomeUnknownError(
                        "The desktop action batch was dispatched, but its post-action observation failed. "
                        "Do not retry the batch automatically.",
                        action_id=action_id,
                        executed_action_count=len(action_results),
                        action_count=len(request.actions),
                    ) from exc
                post_frame = frames["grid"]
        except Exception:
            duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000
            self._record_metric("desktop.batch_act_and_observe", duration_ms, "failed")
            log_event(
                LOGGER,
                event="desktop.batch_failed",
                message="Desktop batch transaction failed",
                outcome="failed",
                action_id=action_id,
                action_count=len(request.actions),
                duration_ms=round(duration_ms, 3),
                exc_info=True,
            )
            raise

        result = {
            "action_id": action_id,
            "action_results": action_results,
            "pre_frame_seq": None if pre_frame is None else pre_frame.get("frame_seq"),
            "post_frame": post_frame,
            "verification": self._verify(request.verify, pre_frame, post_frame),
            "timings_ms": {
                "dispatch": round((dispatch_completed_ns - dispatch_started_ns) / 1_000_000, 3),
                "observe": round((time.monotonic_ns() - dispatch_completed_ns) / 1_000_000, 3),
                "total": round((time.monotonic_ns() - started_ns) / 1_000_000, 3),
            },
        }
        self._record_metric("desktop.batch_act_and_observe", result["timings_ms"]["total"], "success")
        log_event(
            LOGGER,
            event="desktop.batch_completed",
            message="Desktop batch transaction completed",
            outcome=result["verification"]["status"],
            action_id=action_id,
            action_count=len(request.actions),
            pre_frame_seq=result["pre_frame_seq"],
            post_frame_seq=post_frame.get("frame_seq"),
            duration_ms=result["timings_ms"]["total"],
        )
        return result

    def _dispatch(self, action: DesktopActionCommand) -> dict[str, Any]:
        kind = action.kind
        if kind == "move":
            return self.actions.move(x=action.x, y=action.y, duration=action.duration)
        if kind == "click":
            return self.actions.click(x=action.x, y=action.y, button=action.button, double=action.double)
        if kind == "scroll":
            return self.actions.scroll(amount=action.amount)
        if kind == "type":
            return self.actions.type_text(text=action.text, interval=action.interval)
        if kind == "paste":
            return self.actions.paste(text=action.text, restore_clipboard=action.restore_clipboard)
        if kind == "press":
            return self.actions.press(key=action.key)
        if kind == "hotkey":
            return self.actions.hotkey(keys=action.keys)
        raise RuntimeError(f"Unsupported desktop action kind: {kind}")

    @staticmethod
    def _validate_preconditions(preconditions: ActionPreconditions, pre_frame: dict[str, Any] | None) -> None:
        if preconditions.expected_frame_seq is not None:
            actual_seq = None if pre_frame is None else pre_frame.get("frame_seq")
            if actual_seq is None or int(actual_seq) < preconditions.expected_frame_seq:
                raise ActionPreconditionError(
                    f"Latest frame sequence {actual_seq!r} is older than expected {preconditions.expected_frame_seq}."
                )

        if preconditions.expected_screen_digest is not None:
            actual_digest = None if pre_frame is None else pre_frame.get("screen_digest")
            if actual_digest != preconditions.expected_screen_digest:
                raise ActionPreconditionError("Screen content changed after the action target was acquired.")

        if preconditions.max_frame_age_ms is not None:
            captured_ns = None if pre_frame is None else pre_frame.get("captured_monotonic_ns")
            if captured_ns is None:
                raise ActionPreconditionError("Latest frame does not contain a monotonic capture timestamp.")
            age_ms = (time.monotonic_ns() - int(captured_ns)) / 1_000_000
            if age_ms > preconditions.max_frame_age_ms:
                raise ActionPreconditionError(
                    f"Latest frame is too old: {age_ms:.1f}ms > {preconditions.max_frame_age_ms}ms."
                )

    def _validate_display_preconditions(
        self,
        preconditions: ActionPreconditions,
        action: DesktopActionCommand | None,
    ) -> None:
        validator = self.display_precondition_validator
        if validator is None:
            return
        point = None
        if action is not None and action.kind in {"move", "click"}:
            point = (action.x, action.y)
        has_explicit_fence = any(
            value is not None
            for value in (
                preconditions.expected_window_handle,
                preconditions.expected_window_bounds,
                preconditions.expected_layout_version,
            )
        )
        if point is None and not has_explicit_fence:
            return
        try:
            validator(
                expected_hwnd=preconditions.expected_window_handle,
                bounds=preconditions.expected_window_bounds,
                layout_version=preconditions.expected_layout_version,
                point=point,
            )
        except Exception as exc:
            raise ActionPreconditionError(str(exc)) from exc

    @staticmethod
    def _verify(
        verify: DesktopVerifySpec | None,
        pre_frame: dict[str, Any] | None,
        post_frame: dict[str, Any],
    ) -> dict[str, Any]:
        if verify is None:
            return {"status": "not_requested", "kind": None, "failure_reason": None}

        pre_seq = None if pre_frame is None else pre_frame.get("frame_seq")
        post_seq = post_frame.get("frame_seq")
        if verify.kind == "fresh_frame":
            passed = pre_seq is None or (post_seq is not None and int(post_seq) > int(pre_seq))
        else:
            before = None if pre_frame is None else pre_frame.get("screen_digest")
            after = post_frame.get("screen_digest")
            passed = before is not None and after is not None and before != after

        return {
            "status": "passed" if passed else "failed",
            "kind": verify.kind,
            "failure_reason": None if passed else f"Postcondition {verify.kind} was not satisfied.",
        }

    def _record_metric(self, name: str, duration_ms: float, outcome: str) -> None:
        if self.metrics is not None and hasattr(self.metrics, "record"):
            self.metrics.record(name, duration_ms=duration_ms, outcome=outcome)
