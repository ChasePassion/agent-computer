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
    last_window_title: str | None = None
    observation_token_present: bool = False
    observation_preview_updated_at: str | None = None
    observation_grid_updated_at: str | None = None
    last_observation_cleanup_at: str | None = None
