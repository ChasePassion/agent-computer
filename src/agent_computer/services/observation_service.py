from __future__ import annotations

import secrets
import string
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from agent_computer.capture import capture_observation_pair
from agent_computer.runtime import (
    DEFAULT_OBSERVATION_GRID_SIZE,
    DEFAULT_OBSERVATION_INTERVAL_SEC,
    DEFAULT_OBSERVATION_JPEG_QUALITY,
    DEFAULT_OBSERVATION_RETENTION_DAYS,
    DEFAULT_OBSERVATION_RETENTION_MAX_FILES,
    OBSERVATION_DIR,
    ARTIFACTS_DIR,
    ensure_runtime_dirs,
    grid_latest_path,
    metadata_sidecar_path,
    observation_token_path,
    preview_latest_path,
    read_json,
    write_observation_urls_manifest,
    write_json,
)
from agent_computer.services.artifact_retention import cleanup_observation_artifacts, cleanup_snapshot_artifacts
from agent_computer.services.session_service import SessionService

ObservationMode = Literal["preview", "grid"]
TOKEN_ALPHABET = string.ascii_uppercase + string.digits
TOKEN_LENGTH = 12


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
        retention_days: int = DEFAULT_OBSERVATION_RETENTION_DAYS,
        retention_max_files: int = DEFAULT_OBSERVATION_RETENTION_MAX_FILES,
    ) -> None:
        self.session = session
        self.host = host
        self.port = port
        self.interval_sec = interval_sec
        self.grid_size = grid_size
        self.jpeg_quality = jpeg_quality
        self.retention_days = retention_days
        self.retention_max_files = retention_max_files
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._token: str | None = None
        self._frame_seq = 0
        self._last_cleanup_at_monotonic = 0.0

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

    def refresh_now(self) -> None:
        ensure_runtime_dirs()
        preview_target = preview_latest_path()
        grid_target = grid_latest_path()
        preview_temp = preview_target.with_name(preview_target.name + ".tmp")
        grid_temp = grid_target.with_name(grid_target.name + ".tmp")

        preview_result, grid_result = capture_observation_pair(
            preview_output_path=preview_temp,
            grid_output_path=grid_temp,
            grid_size=self.grid_size,
            jpeg_quality=self.jpeg_quality,
        )

        preview_temp.replace(preview_target)
        grid_temp.replace(grid_target)

        self._frame_seq += 1
        updated_at = self._now_iso()
        preview_payload = self._build_payload("preview", preview_result.to_dict(), preview_target, updated_at)
        grid_payload = self._build_payload("grid", grid_result.to_dict(), grid_target, updated_at)

        self._write_latest_meta(preview_payload)
        self._write_latest_meta(grid_payload)
        self.session.set_latest_frame("preview", preview_payload)
        self.session.set_latest_frame("grid", grid_payload)
        self.cleanup_if_needed()

    def cleanup_if_needed(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_cleanup_at_monotonic < 300:
            return
        cleanup_observation_artifacts(OBSERVATION_DIR)
        cleanup_snapshot_artifacts(
            ARTIFACTS_DIR,
            keep_days=self.retention_days,
            keep_count=self.retention_max_files,
        )
        self._last_cleanup_at_monotonic = now
        self.session.set_last_observation_cleanup_at(self._now_iso())

    def _run_loop(self) -> None:
        while not self._stop_event.wait(self.interval_sec):
            try:
                self.refresh_now()
            except Exception:
                continue

    def _build_payload(
        self,
        mode: ObservationMode,
        payload: dict[str, Any],
        image_path: Path,
        updated_at: str,
    ) -> dict[str, Any]:
        bounds = payload.get("bounds") or [0, 0, payload.get("width", 0), payload.get("height", 0)]
        desktop_width = max(0, int(bounds[2]) - int(bounds[0]))
        desktop_height = max(0, int(bounds[3]) - int(bounds[1]))
        payload["image_path"] = str(image_path)
        payload["mode"] = mode
        payload["updated_at"] = updated_at
        payload["frame_seq"] = self._frame_seq
        payload["content_type"] = "image/jpeg"
        payload["desktop_width"] = desktop_width
        payload["desktop_height"] = desktop_height
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

    @staticmethod
    def _generate_token() -> str:
        return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))

    @staticmethod
    def _is_valid_token(token: str) -> bool:
        return len(token) == TOKEN_LENGTH and all(ch in TOKEN_ALPHABET for ch in token)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
