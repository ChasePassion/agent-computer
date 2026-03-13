from __future__ import annotations

from pydantic import BaseModel


class DaemonHealthResponse(BaseModel):
    status: str
    version: str
    host: str
    port: int
    pid: int
    started_at: float
    uptime_seconds: float
    last_capture_path: str | None = None
    last_analysis_image_path: str | None = None
    last_window_title: str | None = None
