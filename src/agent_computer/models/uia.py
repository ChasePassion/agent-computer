from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class UIANodeRef(BaseModel):
    backend: Literal["uia"] = "uia"
    runtime_id: list[int] = Field(min_length=1)
    window_handle: int = Field(gt=0)


class UIALocateRequest(BaseModel):
    window_handle: int = Field(gt=0)
    locator: dict[str, Any]
    scope: Literal["element", "children", "descendants", "subtree"] = "descendants"
    max_results: int = Field(default=20, ge=1, le=100)


class UIAObserveRequest(BaseModel):
    nodeRef: UIANodeRef


class UIAVerifySpec(BaseModel):
    property: str = Field(min_length=1)
    equals: Any


class UIAActRequest(BaseModel):
    nodeRef: UIANodeRef
    action: Literal["invoke", "set_value", "toggle", "select", "expand", "collapse", "focus"]
    value: str | None = None
    verify: UIAVerifySpec | None = None
    expected_bounds: tuple[int, int, int, int] | None = None
    layout_version: str | None = None

    @model_validator(mode="after")
    def validate_value(self) -> "UIAActRequest":
        if self.action == "set_value" and self.value is None:
            raise ValueError("set_value requires value.")
        if self.action != "set_value" and self.value is not None:
            raise ValueError(f"{self.action} does not accept value.")
        return self
