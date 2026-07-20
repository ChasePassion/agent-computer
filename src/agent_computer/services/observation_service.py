from __future__ import annotations

import secrets
import os
import shutil
import string
import threading
import time
from datetime import datetime
from collections import deque
from pathlib import Path
from typing import Any, Callable, Literal, cast

from agent_computer.actions import mouse_position
from agent_computer.capture import capture_observation_pair
from agent_computer.display import get_display_layout
from agent_computer.runtime import (
    DEFAULT_OBSERVATION_GRID_SIZE,
    DEFAULT_OBSERVATION_INTERVAL_SEC,
    DEFAULT_OBSERVATION_JPEG_QUALITY,
    DEFAULT_OBSERVATION_RETENTION_DAYS,
    DEFAULT_OBSERVATION_RETENTION_MAX_FILES,
    DEFAULT_OBSERVATION_TARGET,
    DEFAULT_LIVE_IMAGE_JPEG_QUALITY,
    DEFAULT_LIVE_IMAGE_MAX_DIMENSION,
    OBSERVATION_DIR,
    ARTIFACTS_DIR,
    ensure_runtime_dirs,
    grid_latest_path,
    live_grid_latest_path,
    live_preview_latest_path,
    metadata_sidecar_path,
    observation_token_path,
    preview_latest_path,
    read_json,
    write_observation_urls_manifest,
    write_json,
)
from agent_computer.services.artifact_retention import cleanup_observation_artifacts, cleanup_snapshot_artifacts
from agent_computer.services.session_service import SessionService
from agent_computer.structured_logging import get_event_logger, log_event

ObservationMode = Literal["preview", "grid"]
TOKEN_ALPHABET = string.ascii_uppercase + string.digits
TOKEN_LENGTH = 12
LOGGER = get_event_logger("observation")


class ObservationService:
    def __init__(
        self,
        session: SessionService,
        *,
        host: str,
        port: int,
        interval_sec: float = DEFAULT_OBSERVATION_INTERVAL_SEC,
        grid_size: int = DEFAULT_OBSERVATION_GRID_SIZE,
        jpeg_quality: int = DEFAULT_OBSERVATION_JPEG_QUALITY,
        live_image_max_dimension: int = DEFAULT_LIVE_IMAGE_MAX_DIMENSION,
        live_image_jpeg_quality: int = DEFAULT_LIVE_IMAGE_JPEG_QUALITY,
        retention_days: int = DEFAULT_OBSERVATION_RETENTION_DAYS,
        retention_max_files: int = DEFAULT_OBSERVATION_RETENTION_MAX_FILES,
        metrics: Any | None = None,
        capture_target: Literal["primary-screen", "virtual-screen"] = cast(
            Literal["primary-screen", "virtual-screen"], DEFAULT_OBSERVATION_TARGET
        ),
        display_layout_provider: Callable[[], dict[str, object]] | None = None,
    ) -> None:
        self.session = session
        self.host = host
        self.port = port
        self.interval_sec = interval_sec
        self.grid_size = grid_size
        self.jpeg_quality = jpeg_quality
        self.live_image_max_dimension = live_image_max_dimension
        self.live_image_jpeg_quality = live_image_jpeg_quality
        self.retention_days = retention_days
        self.retention_max_files = retention_max_files
        self.metrics = metrics
        self.capture_target = capture_target
        self.display_layout_provider = display_layout_provider or get_display_layout
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._frame_condition = threading.Condition()
        self._refresh_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._token: str | None = None
        self._frame_seq = 0
        self._last_cleanup_at_monotonic = 0.0
        self._grid_frame_paths: dict[int, Path] = {}
        self._grid_frame_order: deque[int] = deque()
        self._max_retained_grid_frames = 16

    def ensure_token(self) -> str:
        with self._lock:
            if self._token:
                return self._token

            config_path = observation_token_path()
            if config_path.exists():
                try:
                    payload = read_json(config_path)
                except (OSError, TypeError, ValueError):
                    payload = {}
                token = str(payload.get("token", "")).strip() if isinstance(payload, dict) else ""
                if self._is_valid_token(token):
                    self._token = token
                    self.session.set_observation_token(token)
                    return token

            token = self._generate_token()
            payload = {
                "token": token,
                "created_at": self._now_iso(),
            }
            write_json(config_path, payload)
            self._token = token
            self.session.set_observation_token(token)
            return token

    def token(self) -> str:
        return self.ensure_token()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            ensure_runtime_dirs()
            self._write_urls_manifest(self.ensure_token())
            self._stop_event.clear()
            self.cleanup_if_needed(force=True)
            try:
                self.refresh_now()
            except Exception:
                # Keep daemon boot resilient; background loop can retry.
                pass
            self._thread = threading.Thread(
                target=self._run_loop,
                name="agent-computer-observation",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            if not thread:
                return
            self._stop_event.set()
            self._refresh_event.set()
        thread.join(timeout=5.0)
        with self._lock:
            self._thread = None

    def latest(self, mode: ObservationMode) -> dict[str, Any] | None:
        return self.session.get_latest_frame(mode)

    def latest_image_path(self, mode: ObservationMode) -> Path:
        payload = self.latest(mode)
        if not payload:
            raise RuntimeError(f"No latest observation frame available for mode: {mode}")
        return Path(str(payload["image_path"]))

    def latest_live_image_path(self, mode: ObservationMode) -> Path:
        payload = self.latest(mode)
        if not payload:
            raise RuntimeError(f"No latest observation frame available for mode: {mode}")
        live_image_path = payload.get("live_image_path") or payload.get("image_path")
        return Path(str(live_image_path))

    def image_path_for_frame(self, mode: ObservationMode, frame_seq: int) -> Path:
        if mode != "grid":
            raise KeyError(frame_seq)
        with self._lock:
            path = self._grid_frame_paths.get(frame_seq)
        if path is None or not path.exists():
            raise KeyError(frame_seq)
        return path

    def request_refresh(self) -> None:
        self._refresh_event.set()

    def wait_for_frame(
        self,
        mode: ObservationMode,
        *,
        after_seq: int,
        timeout_sec: float,
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + max(0.0, timeout_sec)
        with self._frame_condition:
            while True:
                payload = self.latest(mode)
                if payload is not None and int(payload.get("frame_seq", -1)) > after_seq:
                    return payload
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._frame_condition.wait(remaining)

    def refresh_now(self, *, reason: str = "manual") -> dict[str, dict[str, Any]]:
        started_ns = time.monotonic_ns()
        try:
            with self._refresh_lock:
                result = self._refresh_impl(reason=reason)
        except Exception:
            duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000
            self._record_metric("observation.refresh", duration_ms, "failed")
            log_event(
                LOGGER,
                event="observation.refresh_failed",
                message="Observation refresh failed",
                outcome="failed",
                reason=reason,
                duration_ms=round(duration_ms, 3),
                exc_info=True,
            )
            raise
        duration_ms = (time.monotonic_ns() - started_ns) / 1_000_000
        self._record_metric("observation.refresh", duration_ms, "success")
        if duration_ms >= max(1000.0, self.interval_sec * 1000):
            log_event(
                LOGGER,
                event="observation.refresh_slow",
                message="Observation refresh exceeded its latency budget",
                outcome="degraded",
                reason=reason,
                duration_ms=round(duration_ms, 3),
            )
        return result

    def _refresh_impl(self, *, reason: str) -> dict[str, dict[str, Any]]:
        refresh_started_ns = time.monotonic_ns()
        ensure_runtime_dirs()
        preview_target = preview_latest_path()
        grid_target = grid_latest_path()
        live_preview_target = live_preview_latest_path()
        live_grid_target = live_grid_latest_path()
        preview_temp = preview_target.with_name(preview_target.name + ".tmp")
        grid_temp = grid_target.with_name(grid_target.name + ".tmp")
        live_preview_temp = live_preview_target.with_name(live_preview_target.name + ".tmp")
        live_grid_temp = live_grid_target.with_name(live_grid_target.name + ".tmp")
        display_layout = self.display_layout_provider()

        next_frame_seq = self._frame_seq + 1
        preview_result, grid_result = capture_observation_pair(
            preview_output_path=preview_temp,
            grid_output_path=grid_temp,
            grid_size=self.grid_size,
            jpeg_quality=self.jpeg_quality,
            live_preview_output_path=live_preview_temp,
            live_grid_output_path=live_grid_temp,
            live_max_dimension=self.live_image_max_dimension,
            live_jpeg_quality=self.live_image_jpeg_quality,
            target=self.capture_target,
        )
        if self.capture_target == "virtual-screen":
            virtual_bounds = display_layout.get("virtual_bounds")
            if not isinstance(virtual_bounds, dict):
                raise RuntimeError("Display layout did not include virtual desktop bounds.")
            expected_bounds = (
                int(virtual_bounds["left"]),
                int(virtual_bounds["top"]),
                int(virtual_bounds["right"]),
                int(virtual_bounds["bottom"]),
            )
            if tuple(preview_result.bounds or ()) != expected_bounds:
                raise RuntimeError(
                    "Display layout changed during capture; discard this frame and retry."
                )

        preview_temp.replace(preview_target)
        grid_snapshot = grid_target.with_name(f"grid_frame_{os.getpid()}_{next_frame_seq:08d}.jpg")
        grid_temp.replace(grid_snapshot)
        self._publish_latest_alias(grid_snapshot, grid_target)
        live_preview_temp.replace(live_preview_target)
        live_grid_temp.replace(live_grid_target)

        captured_monotonic_ns = preview_result.captured_monotonic_ns or time.monotonic_ns()
        self._frame_seq = next_frame_seq
        updated_at = self._now_iso()
        cursor_x, cursor_y = mouse_position()
        preview_payload = self._build_payload(
            "preview",
            preview_result.to_dict(),
            preview_target,
            live_preview_target,
            updated_at,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            captured_monotonic_ns=captured_monotonic_ns,
            reason=reason,
            display_layout=display_layout,
        )
        grid_payload = self._build_payload(
            "grid",
            grid_result.to_dict(),
            grid_snapshot,
            live_grid_target,
            updated_at,
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            captured_monotonic_ns=captured_monotonic_ns,
            reason=reason,
            display_layout=display_layout,
        )

        refresh_duration_ms = round((time.monotonic_ns() - refresh_started_ns) / 1_000_000, 3)
        preview_payload["refresh_duration_ms"] = refresh_duration_ms
        grid_payload["refresh_duration_ms"] = refresh_duration_ms

        self._write_latest_meta(preview_payload)
        self._write_latest_meta(grid_payload)
        self._register_grid_frame(self._frame_seq, grid_snapshot)
        self.session.set_latest_frame("preview", preview_payload)
        self.session.set_latest_frame("grid", grid_payload)
        with self._frame_condition:
            self._frame_condition.notify_all()
        self.cleanup_if_needed()
        return {"preview": preview_payload, "grid": grid_payload}

    @staticmethod
    def _publish_latest_alias(source: Path, target: Path) -> None:
        publish_temp = target.with_name(target.name + ".publish.tmp")
        publish_temp.unlink(missing_ok=True)
        try:
            os.link(source, publish_temp)
        except OSError:
            shutil.copyfile(source, publish_temp)
        publish_temp.replace(target)

    def _register_grid_frame(self, frame_seq: int, path: Path) -> None:
        with self._lock:
            self._grid_frame_paths[frame_seq] = path
            self._grid_frame_order.append(frame_seq)
            while len(self._grid_frame_order) > self._max_retained_grid_frames:
                expired_seq = self._grid_frame_order.popleft()
                expired_path = self._grid_frame_paths.pop(expired_seq, None)
                if expired_path is not None:
                    expired_path.unlink(missing_ok=True)
                    metadata_sidecar_path(expired_path).unlink(missing_ok=True)

    def cleanup_if_needed(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_cleanup_at_monotonic < 300:
            return
        if force:
            stale_before = time.time() - 3600
            for path in OBSERVATION_DIR.glob("grid_frame_*.jpg"):
                try:
                    is_stale = path.stat().st_mtime < stale_before
                except OSError:
                    is_stale = False
                if is_stale:
                    path.unlink(missing_ok=True)
                    metadata_sidecar_path(path).unlink(missing_ok=True)
            with self._lock:
                self._grid_frame_paths.clear()
                self._grid_frame_order.clear()
        cleanup_observation_artifacts(OBSERVATION_DIR)
        cleanup_snapshot_artifacts(
            ARTIFACTS_DIR,
            keep_days=self.retention_days,
            keep_count=self.retention_max_files,
        )
        self._last_cleanup_at_monotonic = now
        self.session.set_last_observation_cleanup_at(self._now_iso())

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            requested = self._refresh_event.wait(self.interval_sec)
            self._refresh_event.clear()
            if self._stop_event.is_set():
                break
            try:
                self.refresh_now(reason="requested" if requested else "scheduled")
            except Exception:
                continue

    def _build_payload(
        self,
        mode: ObservationMode,
        payload: dict[str, Any],
        image_path: Path,
        live_image_path: Path,
        updated_at: str,
        *,
        cursor_x: int,
        cursor_y: int,
        captured_monotonic_ns: int,
        reason: str,
        display_layout: dict[str, object],
    ) -> dict[str, Any]:
        bounds = payload.get("bounds") or [0, 0, payload.get("width", 0), payload.get("height", 0)]
        desktop_width = max(0, int(bounds[2]) - int(bounds[0]))
        desktop_height = max(0, int(bounds[3]) - int(bounds[1]))
        payload["image_path"] = str(image_path)
        payload["live_image_path"] = str(live_image_path)
        payload["mode"] = mode
        payload["updated_at"] = updated_at
        payload["frame_seq"] = self._frame_seq
        payload["captured_monotonic_ns"] = captured_monotonic_ns
        payload["refresh_reason"] = reason
        payload["content_type"] = "image/jpeg"
        payload["desktop_width"] = desktop_width
        payload["desktop_height"] = desktop_height
        payload["coordinate_system"] = "virtual-screen-physical-pixels"
        payload["layout_version"] = display_layout.get("layout_version")
        payload["display_layout"] = display_layout
        payload["origin"] = {"x": int(bounds[0]), "y": int(bounds[1])}
        payload["mouse_position"] = {
            "x": cursor_x,
            "y": cursor_y,
            "coordinate_system": "screen-absolute-grid",
        }
        return payload

    def _write_latest_meta(self, payload: dict[str, Any]) -> None:
        image_path = Path(str(payload["image_path"]))
        meta_path = metadata_sidecar_path(image_path)
        meta_temp = meta_path.with_name(meta_path.name + ".tmp")
        write_json(meta_temp, payload)
        meta_temp.replace(meta_path)

    def _write_urls_manifest(self, token: str) -> None:
        write_observation_urls_manifest(
            token=token,
            host=self.host,
            port=self.port,
        )

    def _record_metric(self, name: str, duration_ms: float, outcome: str) -> None:
        if self.metrics is not None and hasattr(self.metrics, "record"):
            self.metrics.record(name, duration_ms=duration_ms, outcome=outcome)

    @staticmethod
    def _generate_token() -> str:
        return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))

    @staticmethod
    def _is_valid_token(token: str) -> bool:
        return len(token) == TOKEN_LENGTH and all(ch in TOKEN_ALPHABET for ch in token)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="milliseconds")
