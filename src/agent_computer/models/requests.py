from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CaptureRequest(BaseModel):
    output: str | None = None
    target: Literal["active-window", "primary-screen"] = "active-window"
    window_title: str | None = None
    window_exact: bool = False
    grid: bool = False
    grid_size: int = Field(default=50, ge=1)
    format: Literal["png", "jpeg"] = "png"
    jpeg_quality: int = Field(default=75, ge=1, le=100)


class CapturePreviewRequest(BaseModel):
    output: str | None = None
    jpeg_quality: int = Field(default=75, ge=1, le=100)


class CaptureGridRequest(BaseModel):
    output: str | None = None
    grid_size: int = Field(default=50, ge=1)
    jpeg_quality: int = Field(default=75, ge=1, le=100)

class FocusRequest(BaseModel):
    title: str
    exact: bool = False


class MaximizeRequest(BaseModel):
    title: str
    exact: bool = False


class MoveRequest(BaseModel):
    x: int
    y: int
    duration: float = Field(default=0.0, ge=0.0)


class ClickRequest(BaseModel):
    x: int
    y: int
    button: Literal["left", "right", "middle"] = "left"
    double: bool = False


class ScrollRequest(BaseModel):
    amount: int


class TypeRequest(BaseModel):
    text: str
    interval: float = Field(default=0.02, ge=0.0)


class PasteRequest(BaseModel):
    text: str
    restore_clipboard: bool = False


class BrowserOpenUrlRequest(BaseModel):
    url: str
    restore_clipboard: bool = False


class PressRequest(BaseModel):
    key: str


class HotkeyRequest(BaseModel):
    keys: list[str]
