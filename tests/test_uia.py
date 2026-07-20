from __future__ import annotations

import json
from typing import Any

import pytest

import agent_computer.uia as uia
from agent_computer.uia import (
    UIAClient,
    UIAutomationError,
    UIAutomationUnavailableError,
    UnsupportedUIAActionError,
)


class FakeUIABackend:
    name = "uia"

    def __init__(self) -> None:
        self.locate_calls: list[dict[str, Any]] = []
        self.observe_calls: list[dict[str, Any]] = []
        self.act_calls: list[dict[str, Any]] = []
        self.observed_value = "before"

    def locate(
        self,
        *,
        window_handle: int,
        locator: dict[str, object],
        scope: str,
        max_results: int,
    ) -> list[dict[str, object]]:
        self.locate_calls.append(
            {
                "window_handle": window_handle,
                "locator": locator,
                "scope": scope,
                "max_results": max_results,
            }
        )
        return [
            {
                "nodeRef": {
                    "backend": "uia",
                    "runtime_id": [42, 7],
                    "window_handle": window_handle,
                },
                "name": "Save",
                "automation_id": "save-button",
                "control_type": 50000,
                "localized_control_type": "button",
                "class_name": "Button",
                "bounds": {
                    "left": 20,
                    "top": 30,
                    "right": 120,
                    "bottom": 70,
                    "width": 100,
                    "height": 40,
                },
                "enabled": True,
                "offscreen": False,
            }
        ]

    def observe(self, node_ref: dict[str, object]) -> dict[str, object]:
        self.observe_calls.append(node_ref)
        return {
            "nodeRef": node_ref,
            "name": "Save",
            "value": self.observed_value,
            "enabled": True,
        }

    def act(
        self,
        node_ref: dict[str, object],
        *,
        action: str,
        value: object | None,
    ) -> dict[str, object]:
        self.act_calls.append({"nodeRef": node_ref, "action": action, "value": value})
        if action == "set_value":
            self.observed_value = str(value)
        return {"performed": True, "pattern": action}


def _node_ref() -> dict[str, object]:
    return {"backend": "uia", "runtime_id": [42, 7], "window_handle": 101}


def _precondition_validator(**kwargs: object) -> dict[str, object]:
    return {"ok": True, "validated": kwargs}


def test_client_loads_default_backend_only_when_first_operation_runs(
    monkeypatch,
) -> None:
    loads: list[bool] = []
    backend = FakeUIABackend()

    def load_backend() -> FakeUIABackend:
        loads.append(True)
        return backend

    monkeypatch.setattr(uia, "_load_default_backend", load_backend)
    client = UIAClient(precondition_validator=_precondition_validator)
    assert loads == []

    client.locate(window_handle=101, locator={"name": "Save"})

    assert loads == [True]


def test_missing_uiautomation_dependency_has_a_clear_error(monkeypatch) -> None:
    def missing(_name: str):
        raise ModuleNotFoundError("No module named 'win32com'")

    monkeypatch.setattr(uia.importlib, "import_module", missing)
    monkeypatch.setattr(uia, "_DEFAULT_BACKEND", None)
    monkeypatch.setattr(uia.os, "name", "nt")

    with pytest.raises(UIAutomationUnavailableError, match="uiautomation"):
        uia._load_default_backend()


def test_locate_returns_json_friendly_node_refs_scoped_to_a_window() -> None:
    backend = FakeUIABackend()
    client = UIAClient(backend=backend, precondition_validator=_precondition_validator)

    result = client.locate(
        window_handle=101,
        locator={"automation_id": "save-button", "control_type": "button"},
        scope="descendants",
        max_results=5,
    )

    assert result["backend"] == "uia"
    assert result["count"] == 1
    assert result["matches"][0]["nodeRef"] == _node_ref()
    assert backend.locate_calls == [
        {
            "window_handle": 101,
            "locator": {"automation_id": "save-button", "control_type": "button"},
            "scope": "descendants",
            "max_results": 5,
        }
    ]
    json.dumps(result)


def test_observe_returns_current_element_properties() -> None:
    backend = FakeUIABackend()
    client = UIAClient(backend=backend, precondition_validator=_precondition_validator)

    result = client.observe(_node_ref())

    assert result == {
        "backend": "uia",
        "element": {
            "nodeRef": _node_ref(),
            "name": "Save",
            "value": "before",
            "enabled": True,
        },
    }
    json.dumps(result)


def test_act_uses_uia_pattern_without_requesting_verification() -> None:
    backend = FakeUIABackend()
    precondition_calls: list[dict[str, object]] = []

    def validate(**kwargs: object) -> dict[str, object]:
        precondition_calls.append(kwargs)
        return {"ok": True}

    client = UIAClient(backend=backend, precondition_validator=validate)

    result = client.act(
        _node_ref(),
        action="invoke",
        expected_bounds=(10, 20, 310, 220),
        layout_version="display-layout-v1:abc123",
    )

    assert backend.act_calls == [
        {"nodeRef": _node_ref(), "action": "invoke", "value": None}
    ]
    assert precondition_calls == [
        {
            "expected_hwnd": 101,
            "bounds": (10, 20, 310, 220),
            "layout_version": "display-layout-v1:abc123",
        }
    ]
    assert result["performed"] is True
    assert result["verificationStatus"] == "not_requested"
    assert result["verification"] is None


@pytest.mark.parametrize(
    ("expected", "status"),
    [("after", "passed"), ("different", "failed")],
)
def test_act_reports_three_state_verification(expected: str, status: str) -> None:
    backend = FakeUIABackend()
    client = UIAClient(backend=backend, precondition_validator=_precondition_validator)

    result = client.act(
        _node_ref(),
        action="set_value",
        value="after",
        verify={"property": "value", "equals": expected},
    )

    assert result["verificationStatus"] == status
    assert result["verification"] == {
        "property": "value",
        "expected": expected,
        "actual": "after",
    }


def test_act_rejects_unknown_actions_before_touching_backend() -> None:
    backend = FakeUIABackend()
    client = UIAClient(backend=backend, precondition_validator=_precondition_validator)

    with pytest.raises(UnsupportedUIAActionError, match="Unsupported UIA action"):
        client.act(_node_ref(), action="coordinate_click")

    assert backend.act_calls == []


def test_act_validates_verification_contract_before_touching_backend() -> None:
    backend = FakeUIABackend()
    client = UIAClient(backend=backend, precondition_validator=_precondition_validator)

    with pytest.raises(UIAutomationError, match="verify must contain exactly"):
        client.act(
            _node_ref(),
            action="set_value",
            value="after",
            verify={"property": "value"},
        )

    assert backend.act_calls == []
