from __future__ import annotations

import ctypes
import os
import time
from dataclasses import asdict, dataclass

import win32api
import win32con
import win32gui
import win32process

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

BROWSER_PROCESS_NAMES = {
    "brave.exe",
    "chrome.exe",
    "firefox.exe",
    "msedge.exe",
    "opera.exe",
    "vivaldi.exe",
}


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    rect: tuple[int, int, int, int]
    visible: bool
    enabled: bool
    foreground: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _window_text(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd).strip()


def _window_process_details(hwnd: int) -> dict[str, object]:
    _, process_id = win32process.GetWindowThreadProcessId(hwnd)
    process_handle = None
    process_path = None
    process_name = None

    try:
        process_handle = win32api.OpenProcess(
            win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
            False,
            process_id,
        )
        process_path = win32process.GetModuleFileNameEx(process_handle, 0) or None
        if process_path:
            process_name = os.path.basename(process_path).casefold()
    except Exception:
        process_path = None
        process_name = None
    finally:
        if process_handle is not None:
            win32api.CloseHandle(process_handle)

    return {
        "process_id": int(process_id),
        "process_path": process_path,
        "process_name": process_name,
    }


def _window_info_from_hwnd(hwnd: int, *, foreground: int | None = None) -> WindowInfo:
    active_hwnd = win32gui.GetForegroundWindow() if foreground is None else foreground
    return WindowInfo(
        hwnd=hwnd,
        title=_window_text(hwnd),
        rect=win32gui.GetWindowRect(hwnd),
        visible=bool(win32gui.IsWindowVisible(hwnd)),
        enabled=bool(win32gui.IsWindowEnabled(hwnd)),
        foreground=hwnd == active_hwnd,
    )


def _window_state_payload(hwnd: int) -> dict[str, object]:
    info = _window_info_from_hwnd(hwnd)
    return {
        **info.to_dict(),
        "is_minimized": bool(win32gui.IsIconic(hwnd)),
        "is_maximized": bool(user32.IsZoomed(hwnd)),
    }


def _activate_window(hwnd: int, *, show_cmd: int | None = None) -> None:
    current_foreground = user32.GetForegroundWindow()
    current_thread = user32.GetWindowThreadProcessId(current_foreground, None)
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    this_thread = kernel32.GetCurrentThreadId()

    attached_current = False
    attached_target = False

    try:
        if current_thread and current_thread != this_thread:
            user32.AttachThreadInput(current_thread, this_thread, True)
            attached_current = True
        if target_thread and target_thread != this_thread:
            user32.AttachThreadInput(target_thread, this_thread, True)
            attached_target = True

        if win32gui.IsIconic(hwnd) and show_cmd != win32con.SW_RESTORE:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        if show_cmd is not None:
            win32gui.ShowWindow(hwnd, show_cmd)
        elif win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
        win32gui.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached_target:
            user32.AttachThreadInput(target_thread, this_thread, False)
        if attached_current:
            user32.AttachThreadInput(current_thread, this_thread, False)


def list_windows() -> list[WindowInfo]:
    windows: list[WindowInfo] = []
    foreground = win32gui.GetForegroundWindow()

    def callback(hwnd: int, _: int) -> bool:
        title = _window_text(hwnd)
        if not title:
            return True
        if not win32gui.IsWindowVisible(hwnd):
            return True
        rect = win32gui.GetWindowRect(hwnd)
        if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
            return True

        windows.append(_window_info_from_hwnd(hwnd, foreground=foreground))
        return True

    win32gui.EnumWindows(callback, 0)
    return windows


def find_window(title_query: str, exact: bool = False) -> WindowInfo:
    query = title_query.casefold()
    candidates = list_windows()
    exact_matches = [window for window in candidates if window.title.casefold() == query]
    matches = exact_matches if exact or exact_matches else [
        window for window in candidates if query in window.title.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = "; ".join(f"hwnd={window.hwnd} title={window.title!r}" for window in matches[:8])
        raise RuntimeError(
            f"Ambiguous visible window match for {title_query!r}: {choices}. "
            "Use a unique exact title or a UIA nodeRef bound to the intended window handle."
        )

    raise RuntimeError(f"No visible window matched: {title_query}")


def focus_window(title_query: str, exact: bool = False) -> WindowInfo:
    match = find_window(title_query, exact=exact)
    hwnd = match.hwnd
    _activate_window(hwnd)
    return _window_info_from_hwnd(hwnd)


def maximize_window(title_query: str, exact: bool = False, *, timeout_sec: float = 1.0) -> dict[str, object]:
    match = find_window(title_query, exact=exact)
    hwnd = match.hwnd

    _activate_window(hwnd, show_cmd=win32con.SW_MAXIMIZE)

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if user32.IsZoomed(hwnd):
            payload = _window_state_payload(hwnd)
            payload["operation"] = "maximize"
            return payload
        time.sleep(0.05)

    payload = _window_state_payload(hwnd)
    payload["operation"] = "maximize"
    raise RuntimeError(f"Window did not enter maximized state: {payload['title']}")


def foreground_window_details() -> dict[str, object]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("No foreground window is active.")

    info = _window_info_from_hwnd(hwnd)
    return {
        **info.to_dict(),
        **_window_process_details(hwnd),
    }


def require_foreground_browser_window() -> dict[str, object]:
    payload = foreground_window_details()
    process_name = str(payload.get("process_name") or "").casefold()
    if process_name not in BROWSER_PROCESS_NAMES:
        title = str(payload.get("title") or "").strip() or "<untitled>"
        raise RuntimeError(
            f"Foreground window is not a supported browser: title={title!r}, process={process_name or 'unknown'}"
        )
    return payload
