from __future__ import annotations

import json

import pytest

from agent_computer.display import (
    DisplayPreconditionError,
    ensure_per_monitor_v2_dpi_awareness,
    get_display_layout,
    validate_screen_point,
    validate_window_preconditions,
)


class FakeDisplayApi:
    def __init__(self) -> None:
        self.dpi_set_result = True
        self.last_error = 0
        self.clear_error_on_context_read = False
        self.current_dpi_context = -4
        self.dpi_set_calls: list[int] = []
        self.foreground_hwnd = 101
        self.valid_windows = {101}
        self.visible_windows = {101}
        self.enabled_windows = {101}
        self.minimized_windows: set[int] = set()
        self.window_rects = {101: (-1200, 80, -200, 880)}
        self.virtual_bounds = (-1920, 0, 1920, 1080)
        self.monitors = [
            {
                "handle": 2,
                "device_name": r"\\.\DISPLAY2",
                "bounds": (-1920, 0, 0, 1080),
                "work_area": (-1920, 0, 0, 1040),
                "primary": False,
                "dpi_x": 144,
                "dpi_y": 144,
            },
            {
                "handle": 1,
                "device_name": r"\\.\DISPLAY1",
                "bounds": (0, 0, 1920, 1080),
                "work_area": (0, 0, 1920, 1040),
                "primary": True,
                "dpi_x": 96,
                "dpi_y": 96,
            },
        ]

    def set_process_dpi_awareness_context(self, context: int) -> bool:
        self.dpi_set_calls.append(context)
        return self.dpi_set_result

    def get_last_error(self) -> int:
        return self.last_error

    def get_thread_dpi_awareness_context(self) -> int:
        if self.clear_error_on_context_read:
            self.last_error = 0
        return self.current_dpi_context

    def dpi_awareness_contexts_equal(self, first: int, second: int) -> bool:
        return first == second

    def get_virtual_bounds(self) -> tuple[int, int, int, int]:
        return self.virtual_bounds

    def enumerate_monitors(self) -> list[dict[str, object]]:
        return list(self.monitors)

    def get_foreground_window(self) -> int:
        return self.foreground_hwnd

    def is_window(self, hwnd: int) -> bool:
        return hwnd in self.valid_windows

    def is_window_visible(self, hwnd: int) -> bool:
        return hwnd in self.visible_windows

    def is_window_enabled(self, hwnd: int) -> bool:
        return hwnd in self.enabled_windows

    def is_window_minimized(self, hwnd: int) -> bool:
        return hwnd in self.minimized_windows

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        return self.window_rects[hwnd]


def test_dpi_awareness_sets_per_monitor_v2() -> None:
    api = FakeDisplayApi()

    result = ensure_per_monitor_v2_dpi_awareness(_api=api)

    assert api.dpi_set_calls == [-4]
    assert result == {
        "mode": "per-monitor-v2",
        "context": -4,
        "changed": True,
        "already_configured": False,
    }


def test_dpi_awareness_treats_access_denied_as_idempotent_only_when_context_matches() -> (
    None
):
    api = FakeDisplayApi()
    api.dpi_set_result = False
    api.last_error = 5
    api.clear_error_on_context_read = True

    result = ensure_per_monitor_v2_dpi_awareness(_api=api)

    assert result["changed"] is False
    assert result["already_configured"] is True

    api.current_dpi_context = -2
    api.last_error = 5
    with pytest.raises(DisplayPreconditionError, match="different DPI awareness"):
        ensure_per_monitor_v2_dpi_awareness(_api=api)


def test_display_layout_is_stable_and_supports_negative_virtual_coordinates() -> None:
    api = FakeDisplayApi()

    first = get_display_layout(_api=api)
    api.monitors.reverse()
    api.monitors[0]["handle"] = 999
    api.monitors[1]["handle"] = 998
    second = get_display_layout(_api=api)

    assert first["layout_version"] == second["layout_version"]
    assert first["layout_hash"] == second["layout_hash"]
    assert first["virtual_bounds"] == {
        "left": -1920,
        "top": 0,
        "right": 1920,
        "bottom": 1080,
        "width": 3840,
        "height": 1080,
    }
    assert [monitor["device_name"] for monitor in first["monitors"]] == [
        r"\\.\DISPLAY1",
        r"\\.\DISPLAY2",
    ]
    assert first["monitors"][1]["scale_factor"] == 1.5
    json.dumps(first)


def test_validate_screen_point_requires_a_real_monitor_not_a_virtual_desktop_gap() -> (
    None
):
    api = FakeDisplayApi()
    api.virtual_bounds = (-100, 0, 300, 200)
    api.monitors[0]["bounds"] = (-100, 0, 0, 100)
    api.monitors[1]["bounds"] = (100, 0, 300, 200)

    valid = validate_screen_point(-50, 50, _api=api)

    assert valid["point"] == {"x": -50, "y": 50}
    assert valid["monitor"]["device_name"] == r"\\.\DISPLAY2"
    with pytest.raises(DisplayPreconditionError, match="not on an attached monitor"):
        validate_screen_point(50, 50, _api=api)


def test_validate_window_preconditions_returns_a_json_friendly_snapshot() -> None:
    api = FakeDisplayApi()
    layout = get_display_layout(_api=api)

    result = validate_window_preconditions(
        expected_hwnd=101,
        bounds=(-1200, 80, -200, 880),
        layout_version=layout["layout_version"],
        point=(-800, 300),
        _api=api,
    )

    assert result["ok"] is True
    assert result["foreground_window"] == {
        "hwnd": 101,
        "bounds": {
            "left": -1200,
            "top": 80,
            "right": -200,
            "bottom": 880,
            "width": 1000,
            "height": 800,
        },
        "visible": True,
        "enabled": True,
        "minimized": False,
    }
    assert result["point"]["inside_window"] is True
    json.dumps(result)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda api: setattr(api, "foreground_hwnd", 202), "foreground window changed"),
        (
            lambda api: api.window_rects.__setitem__(101, (-1200, 80, -199, 880)),
            "window bounds changed",
        ),
        (
            lambda api: api.monitors[0].__setitem__("dpi_x", 120),
            "display layout changed",
        ),
    ],
)
def test_validate_window_preconditions_rejects_stale_context(
    mutation, message: str
) -> None:
    api = FakeDisplayApi()
    layout = get_display_layout(_api=api)
    mutation(api)

    with pytest.raises(DisplayPreconditionError, match=message):
        validate_window_preconditions(
            expected_hwnd=101,
            bounds=(-1200, 80, -200, 880),
            layout_version=layout["layout_version"],
            _api=api,
        )
