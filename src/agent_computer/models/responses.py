from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LiveStateResponse(BaseModel):
    frame: dict[str, Any]
    output: dict[str, Any]


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
    browser_assist_token_present: bool = False
    browser_assist_connected: bool = False
    browser_assist_last_keepalive_at: str | None = None
    browser_assist_last_page_url: str | None = None
    browser_assist_last_page_title: str | None = None
    browser_assist_last_error: str | None = None
