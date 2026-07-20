from __future__ import annotations

import ctypes
import hashlib
import json
import os
from ctypes import wintypes
from typing import Any, Mapping, Protocol, Sequence


PER_MONITOR_AWARE_V2 = -4
ERROR_ACCESS_DENIED = 5
DISPLAY_LAYOUT_SCHEMA_VERSION = "display-layout-v1"


class DisplayError(RuntimeError):
    """Base error for display metadata and validation failures."""


class DisplayUnavailableError(DisplayError):
    """Raised when the required Windows display APIs are unavailable."""


class DisplayPreconditionError(DisplayError):
    """Raised when display or foreground-window state is unsafe to use."""


class _DisplayApi(Protocol):
    def set_process_dpi_awareness_context(self, context: int) -> bool: ...

    def get_last_error(self) -> int: ...

    def get_thread_dpi_awareness_context(self) -> int: ...

    def dpi_awareness_contexts_equal(self, first: int, second: int) -> bool: ...

    def get_virtual_bounds(self) -> tuple[int, int, int, int]: ...

    def enumerate_monitors(self) -> list[dict[str, object]]: ...

    def get_foreground_window(self) -> int: ...

    def is_window(self, hwnd: int) -> bool: ...

    def is_window_visible(self, hwnd: int) -> bool: ...

    def is_window_enabled(self, hwnd: int) -> bool: ...

    def is_window_minimized(self, hwnd: int) -> bool: ...

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int]: ...


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MonitorInfoExW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _Rect),
        ("rcWork", _Rect),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


def _handle_value(handle: object) -> int:
    value = getattr(handle, "value", handle)
    return int(value or 0)


class _WindowsDisplayApi:
    _SM_XVIRTUALSCREEN = 76
    _SM_YVIRTUALSCREEN = 77
    _SM_CXVIRTUALSCREEN = 78
    _SM_CYVIRTUALSCREEN = 79
    _MONITORINFOF_PRIMARY = 1
    _MDT_EFFECTIVE_DPI = 0

    def __init__(self) -> None:
        try:
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        except (AttributeError, OSError) as exc:
            raise DisplayUnavailableError(
                "Windows display APIs are unavailable on this platform."
            ) from exc

        try:
            self._shcore = ctypes.WinDLL("shcore", use_last_error=True)
        except OSError:
            self._shcore = None

    @staticmethod
    def _dpi_context(context: int) -> ctypes.c_void_p:
        return ctypes.c_void_p(context)

    def set_process_dpi_awareness_context(self, context: int) -> bool:
        try:
            function = self._user32.SetProcessDpiAwarenessContext
        except AttributeError as exc:
            raise DisplayUnavailableError(
                "Per-Monitor DPI Awareness V2 requires Windows 10 version 1703 or later."
            ) from exc
        function.argtypes = [ctypes.c_void_p]
        function.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        return bool(function(self._dpi_context(context)))

    def get_last_error(self) -> int:
        return int(ctypes.get_last_error() or self._kernel32.GetLastError())

    def get_thread_dpi_awareness_context(self) -> int:
        function = self._user32.GetThreadDpiAwarenessContext
        function.argtypes = []
        function.restype = ctypes.c_void_p
        return _handle_value(function())

    def dpi_awareness_contexts_equal(self, first: int, second: int) -> bool:
        function = self._user32.AreDpiAwarenessContextsEqual
        function.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        function.restype = wintypes.BOOL
        return bool(function(self._dpi_context(first), self._dpi_context(second)))

    def get_virtual_bounds(self) -> tuple[int, int, int, int]:
        left = int(self._user32.GetSystemMetrics(self._SM_XVIRTUALSCREEN))
        top = int(self._user32.GetSystemMetrics(self._SM_YVIRTUALSCREEN))
        width = int(self._user32.GetSystemMetrics(self._SM_CXVIRTUALSCREEN))
        height = int(self._user32.GetSystemMetrics(self._SM_CYVIRTUALSCREEN))
        return left, top, left + width, top + height

    def _monitor_dpi(self, monitor_handle: int) -> tuple[int, int]:
        if self._shcore is None:
            return 96, 96
        try:
            function = self._shcore.GetDpiForMonitor
        except AttributeError:
            return 96, 96
        dpi_x = wintypes.UINT()
        dpi_y = wintypes.UINT()
        function.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
        ]
        function.restype = ctypes.c_long
        result = function(
            wintypes.HANDLE(monitor_handle),
            self._MDT_EFFECTIVE_DPI,
            ctypes.byref(dpi_x),
            ctypes.byref(dpi_y),
        )
        if result != 0 or dpi_x.value <= 0 or dpi_y.value <= 0:
            return 96, 96
        return int(dpi_x.value), int(dpi_y.value)

    def enumerate_monitors(self) -> list[dict[str, object]]:
        monitors: list[dict[str, object]] = []
        callback_type = ctypes.WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HANDLE,
            wintypes.HDC,
            ctypes.POINTER(_Rect),
            wintypes.LPARAM,
        )

        def callback(
            monitor: wintypes.HANDLE,
            _device_context: wintypes.HDC,
            _monitor_rect: ctypes.POINTER(_Rect),
            _data: wintypes.LPARAM,
        ) -> bool:
            handle = _handle_value(monitor)
            info = _MonitorInfoExW()
            info.cbSize = ctypes.sizeof(info)
            if not self._user32.GetMonitorInfoW(
                wintypes.HANDLE(handle), ctypes.byref(info)
            ):
                return True
            dpi_x, dpi_y = self._monitor_dpi(handle)
            monitors.append(
                {
                    "handle": handle,
                    "device_name": str(info.szDevice),
                    "bounds": (
                        int(info.rcMonitor.left),
                        int(info.rcMonitor.top),
                        int(info.rcMonitor.right),
                        int(info.rcMonitor.bottom),
                    ),
                    "work_area": (
                        int(info.rcWork.left),
                        int(info.rcWork.top),
                        int(info.rcWork.right),
                        int(info.rcWork.bottom),
                    ),
                    "primary": bool(info.dwFlags & self._MONITORINFOF_PRIMARY),
                    "dpi_x": dpi_x,
                    "dpi_y": dpi_y,
                }
            )
            return True

        callback_pointer = callback_type(callback)
        function = self._user32.EnumDisplayMonitors
        function.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(_Rect),
            callback_type,
            wintypes.LPARAM,
        ]
        function.restype = wintypes.BOOL
        if not function(None, None, callback_pointer, 0):
            raise DisplayUnavailableError(
                f"EnumDisplayMonitors failed with Windows error {self.get_last_error()}."
            )
        return monitors

    def get_foreground_window(self) -> int:
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        return _handle_value(self._user32.GetForegroundWindow())

    def is_window(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindow(wintypes.HWND(hwnd)))

    def is_window_visible(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindowVisible(wintypes.HWND(hwnd)))

    def is_window_enabled(self, hwnd: int) -> bool:
        return bool(self._user32.IsWindowEnabled(wintypes.HWND(hwnd)))

    def is_window_minimized(self, hwnd: int) -> bool:
        return bool(self._user32.IsIconic(wintypes.HWND(hwnd)))

    def get_window_rect(self, hwnd: int) -> tuple[int, int, int, int]:
        rect = _Rect()
        if not self._user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            raise DisplayPreconditionError(
                f"Unable to read bounds for window {hwnd}; Windows error {self.get_last_error()}."
            )
        return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _load_windows_display_api() -> _DisplayApi:
    if os.name != "nt":
        raise DisplayUnavailableError(
            "Display inspection requires Windows; the current platform is not Windows."
        )
    return _WindowsDisplayApi()


def _resolve_api(api: _DisplayApi | None) -> _DisplayApi:
    return api if api is not None else _load_windows_display_api()


def ensure_per_monitor_v2_dpi_awareness(
    *, _api: _DisplayApi | None = None
) -> dict[str, object]:
    """Set and verify process DPI awareness before any coordinate-dependent work."""

    api = _resolve_api(_api)
    changed = api.set_process_dpi_awareness_context(PER_MONITOR_AWARE_V2)
    error = 0 if changed else api.get_last_error()
    current_context = api.get_thread_dpi_awareness_context()
    matches = api.dpi_awareness_contexts_equal(current_context, PER_MONITOR_AWARE_V2)

    if changed:
        if not matches:
            raise DisplayPreconditionError(
                "Windows accepted Per-Monitor DPI Awareness V2 but the current thread did not inherit it."
            )
        return {
            "mode": "per-monitor-v2",
            "context": PER_MONITOR_AWARE_V2,
            "changed": True,
            "already_configured": False,
        }

    if error == ERROR_ACCESS_DENIED and matches:
        return {
            "mode": "per-monitor-v2",
            "context": PER_MONITOR_AWARE_V2,
            "changed": False,
            "already_configured": True,
        }
    if error == ERROR_ACCESS_DENIED:
        raise DisplayPreconditionError(
            "The process already uses a different DPI awareness context; "
            "Per-Monitor DPI Awareness V2 must be configured before UI initialization."
        )
    raise DisplayPreconditionError(
        f"Unable to enable Per-Monitor DPI Awareness V2; Windows error {error}."
    )


def _coerce_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DisplayPreconditionError(f"{name} must be an integer.")
    return value


def _rect_values(
    value: Sequence[object] | Mapping[str, object], *, name: str
) -> tuple[int, int, int, int]:
    if isinstance(value, Mapping):
        try:
            raw = (value["left"], value["top"], value["right"], value["bottom"])
        except KeyError as exc:
            raise DisplayPreconditionError(
                f"{name} must include left, top, right, and bottom."
            ) from exc
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) != 4:
            raise DisplayPreconditionError(f"{name} must contain four coordinates.")
        raw = tuple(value)
    else:
        raise DisplayPreconditionError(
            f"{name} must be a four-item sequence or rectangle mapping."
        )
    left, top, right, bottom = (
        _coerce_int(item, name=f"{name} coordinate") for item in raw
    )
    if right <= left or bottom <= top:
        raise DisplayPreconditionError(f"{name} must have positive width and height.")
    return left, top, right, bottom


def _rect_payload(rect: tuple[int, int, int, int]) -> dict[str, int]:
    left, top, right, bottom = rect
    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def _monitor_payload(raw: Mapping[str, object]) -> dict[str, object]:
    bounds = _rect_values(raw.get("bounds", ()), name="monitor bounds")
    work_area = _rect_values(raw.get("work_area", bounds), name="monitor work area")
    dpi_x = _coerce_int(raw.get("dpi_x", 96), name="monitor dpi_x")
    dpi_y = _coerce_int(raw.get("dpi_y", 96), name="monitor dpi_y")
    if dpi_x <= 0 or dpi_y <= 0:
        raise DisplayPreconditionError("Monitor DPI values must be greater than zero.")
    device_name = str(raw.get("device_name") or "").strip()
    monitor_id = device_name or (
        f"monitor:{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
    )
    return {
        "id": monitor_id,
        "handle": _coerce_int(raw.get("handle", 0), name="monitor handle"),
        "device_name": device_name,
        "bounds": _rect_payload(bounds),
        "work_area": _rect_payload(work_area),
        "primary": bool(raw.get("primary", False)),
        "dpi_x": dpi_x,
        "dpi_y": dpi_y,
        "scale_factor": round(dpi_x / 96.0, 4),
    }


def _stable_layout_payload(
    virtual_bounds: dict[str, int], monitors: list[dict[str, object]]
) -> dict[str, object]:
    stable_monitors: list[dict[str, object]] = []
    for monitor in monitors:
        stable_monitors.append(
            {key: value for key, value in monitor.items() if key != "handle"}
        )
    return {
        "schema_version": DISPLAY_LAYOUT_SCHEMA_VERSION,
        "coordinate_system": "virtual-screen-physical-pixels",
        "virtual_bounds": virtual_bounds,
        "monitors": stable_monitors,
    }


def get_display_layout(*, _api: _DisplayApi | None = None) -> dict[str, object]:
    """Return a deterministic snapshot of the Windows virtual desktop layout."""

    api = _resolve_api(_api)
    dpi_awareness = ensure_per_monitor_v2_dpi_awareness(_api=api)
    virtual_bounds = _rect_payload(
        _rect_values(api.get_virtual_bounds(), name="virtual desktop bounds")
    )
    monitors = [_monitor_payload(raw) for raw in api.enumerate_monitors()]
    if not monitors:
        raise DisplayUnavailableError("Windows reported no attached display monitors.")
    monitors.sort(
        key=lambda monitor: (
            str(monitor["device_name"]).casefold(),
            int(_as_mapping(monitor["bounds"])["left"]),
            int(_as_mapping(monitor["bounds"])["top"]),
        )
    )
    stable = _stable_layout_payload(virtual_bounds, monitors)
    serialized = json.dumps(
        stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    layout_hash = hashlib.sha256(serialized).hexdigest()
    return {
        **stable,
        "layout_version": f"{DISPLAY_LAYOUT_SCHEMA_VERSION}:{layout_hash[:16]}",
        "layout_hash": layout_hash,
        "dpi_awareness": dpi_awareness,
        "monitor_count": len(monitors),
        "monitors": monitors,
    }


def _as_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DisplayPreconditionError("Expected rectangle metadata to be a mapping.")
    return value


def _point_in_rect(x: int, y: int, rect: Mapping[str, object]) -> bool:
    return int(rect["left"]) <= x < int(rect["right"]) and int(rect["top"]) <= y < int(
        rect["bottom"]
    )


def _validated_point(
    x: object, y: object, layout: Mapping[str, object]
) -> tuple[int, int, dict[str, object]]:
    point_x = _coerce_int(x, name="x")
    point_y = _coerce_int(y, name="y")
    virtual_bounds = _as_mapping(layout["virtual_bounds"])
    if not _point_in_rect(point_x, point_y, virtual_bounds):
        raise DisplayPreconditionError(
            f"Screen point ({point_x}, {point_y}) is outside the virtual desktop bounds."
        )
    monitors = layout.get("monitors")
    if not isinstance(monitors, list):
        raise DisplayPreconditionError(
            "Display layout contains invalid monitor metadata."
        )
    for monitor in monitors:
        if isinstance(monitor, dict) and _point_in_rect(
            point_x, point_y, _as_mapping(monitor["bounds"])
        ):
            return point_x, point_y, monitor
    raise DisplayPreconditionError(
        f"Screen point ({point_x}, {point_y}) is not on an attached monitor."
    )


def validate_screen_point(
    x: object, y: object, *, _api: _DisplayApi | None = None
) -> dict[str, object]:
    """Validate an absolute physical-pixel point against attached monitors."""

    layout = get_display_layout(_api=_api)
    point_x, point_y, monitor = _validated_point(x, y, layout)
    return {
        "ok": True,
        "coordinate_system": layout["coordinate_system"],
        "layout_version": layout["layout_version"],
        "point": {"x": point_x, "y": point_y},
        "monitor": monitor,
    }


def validate_window_preconditions(
    *,
    expected_hwnd: int | None = None,
    bounds: Sequence[object] | Mapping[str, object] | None = None,
    layout_version: str | None = None,
    point: Sequence[object] | Mapping[str, object] | None = None,
    _api: _DisplayApi | None = None,
) -> dict[str, object]:
    """Fence an action against foreground-window, geometry, and layout drift."""

    api = _resolve_api(_api)
    layout = get_display_layout(_api=api)
    if layout_version is not None and layout["layout_version"] != layout_version:
        raise DisplayPreconditionError(
            "The display layout changed after observation; refresh coordinates before acting."
        )

    hwnd = api.get_foreground_window()
    if expected_hwnd is not None:
        expected = _coerce_int(expected_hwnd, name="expected_hwnd")
        if hwnd != expected:
            raise DisplayPreconditionError(
                f"The foreground window changed: expected {expected}, found {hwnd}."
            )
    if hwnd <= 0 or not api.is_window(hwnd):
        raise DisplayPreconditionError("No valid foreground window is available.")

    visible = api.is_window_visible(hwnd)
    enabled = api.is_window_enabled(hwnd)
    minimized = api.is_window_minimized(hwnd)
    if not visible:
        raise DisplayPreconditionError(f"Foreground window {hwnd} is not visible.")
    if not enabled:
        raise DisplayPreconditionError(f"Foreground window {hwnd} is not enabled.")
    if minimized:
        raise DisplayPreconditionError(f"Foreground window {hwnd} is minimized.")

    actual_rect = _rect_values(api.get_window_rect(hwnd), name="window bounds")
    if bounds is not None:
        expected_rect = _rect_values(bounds, name="expected window bounds")
        if actual_rect != expected_rect:
            raise DisplayPreconditionError(
                "The foreground window bounds changed after observation: "
                f"expected {expected_rect}, found {actual_rect}."
            )

    point_payload: dict[str, object] | None = None
    if point is not None:
        if isinstance(point, Mapping):
            try:
                point_values = (point["x"], point["y"])
            except KeyError as exc:
                raise DisplayPreconditionError("point must include x and y.") from exc
        elif isinstance(point, Sequence) and not isinstance(point, (str, bytes)):
            if len(point) != 2:
                raise DisplayPreconditionError("point must contain two coordinates.")
            point_values = (point[0], point[1])
        else:
            raise DisplayPreconditionError(
                "point must be a two-item sequence or x/y mapping."
            )
        point_x, point_y, monitor = _validated_point(*point_values, layout)
        if not _point_in_rect(point_x, point_y, _rect_payload(actual_rect)):
            raise DisplayPreconditionError(
                f"Screen point ({point_x}, {point_y}) is outside foreground window {hwnd}."
            )
        point_payload = {
            "x": point_x,
            "y": point_y,
            "inside_window": True,
            "monitor": monitor,
        }

    return {
        "ok": True,
        "coordinate_system": layout["coordinate_system"],
        "layout_version": layout["layout_version"],
        "layout_hash": layout["layout_hash"],
        "foreground_window": {
            "hwnd": hwnd,
            "bounds": _rect_payload(actual_rect),
            "visible": visible,
            "enabled": enabled,
            "minimized": minimized,
        },
        "point": point_payload,
    }
