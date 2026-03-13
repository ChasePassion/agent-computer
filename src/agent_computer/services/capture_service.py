from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_computer.capture import capture
from agent_computer.runtime import default_capture_path, write_capture_sidecar
from agent_computer.services.session_service import SessionService


class CaptureService:
    def __init__(self, session: SessionService) -> None:
        self.session = session

    def capture(
        self,
        *,
        output: str | None = None,
        target: str = "active-window",
        window_title: str | None = None,
        window_exact: bool = False,
        grid: bool = False,
        grid_size: int = 100,
        image_format: str = "png",
        jpeg_quality: int = 75,
    ) -> dict[str, Any]:
        suffix = ".jpg" if image_format == "jpeg" else ".png"
        output_path = Path(output) if output else default_capture_path("capture", suffix)
        result = capture(
            output_path=output_path,
            target=target,
            draw_grid=grid,
            grid_size=grid_size,
            window_title_query=window_title,
            window_exact=window_exact,
            image_format=image_format,
            jpeg_quality=jpeg_quality,
        )
        payload = result.to_dict()
        write_capture_sidecar(payload)
        self.session.set_last_capture(payload)
        return payload

    def capture_preview(self, *, output: str | None = None, jpeg_quality: int = 75) -> dict[str, Any]:
        output_path = Path(output) if output else default_capture_path("preview", ".jpg")
        return self.capture(
            output=str(output_path),
            target="primary-screen",
            grid=False,
            image_format="jpeg",
            jpeg_quality=jpeg_quality,
        )

    def capture_grid(
        self,
        *,
        output: str | None = None,
        grid_size: int = 100,
        jpeg_quality: int = 75,
    ) -> dict[str, Any]:
        output_path = Path(output) if output else default_capture_path("grid", ".jpg")
        return self.capture(
            output=str(output_path),
            target="primary-screen",
            grid=True,
            grid_size=grid_size,
            image_format="jpeg",
            jpeg_quality=jpeg_quality,
        )
