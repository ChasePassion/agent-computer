from __future__ import annotations

import ctypes
from dataclasses import asdict, dataclass

import win32con
import win32gui

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


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

        windows.append(
            WindowInfo(
                hwnd=hwnd,
                title=title,
                rect=rect,
                visible=bool(win32gui.IsWindowVisible(hwnd)),
                enabled=bool(win32gui.IsWindowEnabled(hwnd)),
                foreground=hwnd == foreground,
            )
        )
        return True

    win32gui.EnumWindows(callback, 0)
    return windows


def find_window(title_query: str, exact: bool = False) -> WindowInfo:
    query = title_query.casefold()
    candidates = list_windows()
    for window in candidates:
        title = window.title.casefold()
        if exact and title == query:
            return window
        if not exact and query in title:
            return window

    raise RuntimeError(f"No visible window matched: {title_query}")


def focus_window(title_query: str, exact: bool = False) -> WindowInfo:
    match = find_window(title_query, exact=exact)
    hwnd = match.hwnd

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

        if win32gui.IsIconic(hwnd):
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

    foreground = win32gui.GetForegroundWindow()
    match.foreground = hwnd == foreground
    return match
