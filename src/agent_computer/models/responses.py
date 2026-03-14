from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LiveOutputEntry(BaseModel):
    seq: int
    kind: Literal["commentary", "final", "tool"]
    text: str
    created_at: str


class LiveOutputSnapshotResponse(BaseModel):
    session_id: str
    seq: int = 0
    status: Literal["running", "idle", "no_output"] = "no_output"
    updated_at: str | None = None
    heartbeat_at: str | None = None
    latest_text: str | None = None
    recent: list[LiveOutputEntry] = Field(default_factory=list)
    truncated: bool = False
    stale_after_seconds: int = 15
    source_rollout_path: str | None = None


class LiveStateResponse(BaseModel):
    frame: dict[str, Any]
    output: LiveOutputSnapshotResponse


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
    live_output_status: str | None = None
    live_output_updated_at: str | None = None
    live_output_heartbeat_at: str | None = None
    live_output_seq: int = 0
    live_output_session_id: str | None = None
    live_output_source_rollout_path: str | None = None
