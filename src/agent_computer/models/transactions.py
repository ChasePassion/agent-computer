from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class MoveActionCommand(BaseModel):
    kind: Literal["move"] = "move"
    x: int
    y: int
    duration: float = Field(default=0.0, ge=0.0)


class ClickActionCommand(BaseModel):
    kind: Literal["click"] = "click"
    x: int
    y: int
    button: Literal["left", "right", "middle"] = "left"
    double: bool = False


class ScrollActionCommand(BaseModel):
    kind: Literal["scroll"] = "scroll"
    amount: int


class TypeActionCommand(BaseModel):
    kind: Literal["type"] = "type"
    text: str
    interval: float = Field(default=0.0, ge=0.0)


class PasteActionCommand(BaseModel):
    kind: Literal["paste"] = "paste"
    text: str
    restore_clipboard: bool = False


class PressActionCommand(BaseModel):
    kind: Literal["press"] = "press"
    key: str


class HotkeyActionCommand(BaseModel):
    kind: Literal["hotkey"] = "hotkey"
    keys: list[str] = Field(min_length=1, max_length=8)


DesktopActionCommand = Annotated[
    MoveActionCommand
    | ClickActionCommand
    | ScrollActionCommand
    | TypeActionCommand
    | PasteActionCommand
    | PressActionCommand
    | HotkeyActionCommand,
    Field(discriminator="kind"),
]


class ActionPreconditions(BaseModel):
    expected_frame_seq: int | None = Field(default=None, ge=0)
    expected_screen_digest: str | None = None
    max_frame_age_ms: int | None = Field(default=None, ge=0, le=60_000)
    expected_window_handle: int | None = Field(default=None, ge=0)
    expected_window_bounds: tuple[int, int, int, int] | None = None
    expected_layout_version: str | None = None


class DesktopVerifySpec(BaseModel):
    kind: Literal["fresh_frame", "frame_changed"]


class ActAndObserveRequest(BaseModel):
    action: DesktopActionCommand
    preconditions: ActionPreconditions = Field(default_factory=ActionPreconditions)
    verify: DesktopVerifySpec | None = None


class BatchActAndObserveRequest(BaseModel):
    actions: list[DesktopActionCommand] = Field(min_length=1, max_length=50)
    preconditions: ActionPreconditions = Field(default_factory=ActionPreconditions)
    verify: DesktopVerifySpec | None = None

