from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenElement(BaseModel):
    label: str = Field(description="Visible label or concise description of the element.")
    kind: str = Field(
        description="Element kind such as button, input, tab, menu, link, checkbox, dialog, text, or other."
    )
    bbox: list[int] = Field(
        default_factory=list,
        description="Bounding box in the same pixel coordinate system as the screenshot as [x1, y1, x2, y2].",
    )
    click_point: list[int] = Field(
        default_factory=list,
        description="Preferred click point in the same pixel coordinate system as the screenshot as [x, y].",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence from 0.0 to 1.0.",
    )
    reason: str = Field(
        default="",
        description="Short reason for why the element or text matters.",
    )


class ScreenAnalysis(BaseModel):
    summary: str = Field(description="Short summary of the current screen.")
    screen_text: list[str] = Field(
        default_factory=list,
        description="Visible text snippets that are relevant.",
    )
    elements: list[ScreenElement] = Field(
        default_factory=list,
        description="Important visible GUI elements.",
    )
    next_actions: list[str] = Field(
        default_factory=list,
        description="Plausible next actions a desktop agent could take.",
    )
