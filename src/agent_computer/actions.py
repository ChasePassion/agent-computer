from __future__ import annotations

import os
import time
from urllib.parse import urlparse

import pyautogui
import win32clipboard

pyautogui.FAILSAFE = True


def _input_pause_seconds() -> float:
    raw = os.getenv("AGENT_COMPUTER_INPUT_PAUSE_SEC", "0.03")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.03


pyautogui.PAUSE = _input_pause_seconds()


def mouse_position() -> tuple[int, int]:
    point = pyautogui.position()
    return int(point.x), int(point.y)


def move_to(x: int, y: int, duration: float = 0.0) -> None:
    pyautogui.moveTo(x=x, y=y, duration=duration)


def click(x: int, y: int, button: str = "left") -> None:
    pyautogui.click(x=x, y=y, button=button)


def double_click(x: int, y: int, button: str = "left") -> None:
    pyautogui.doubleClick(x=x, y=y, button=button)


def scroll(amount: int) -> None:
    pyautogui.scroll(amount)


def type_text(text: str, interval: float = 0.0) -> None:
    pyautogui.write(text, interval=interval)


def _with_clipboard_retry(callback, *, attempts: int = 10, delay: float = 0.05):
    last_error = None
    for _ in range(attempts):
        try:
            win32clipboard.OpenClipboard()
            try:
                return callback()
            finally:
                win32clipboard.CloseClipboard()
        except win32clipboard.error as exc:
            last_error = exc
            time.sleep(delay)
    raise RuntimeError("Unable to access the Windows clipboard.") from last_error


def _get_clipboard_text() -> str | None:
    def _reader() -> str | None:
        if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            return None
        return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)

    return _with_clipboard_retry(_reader)


def _set_clipboard_text(text: str) -> None:
    def _writer() -> None:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)

    _with_clipboard_retry(_writer)


def paste_text(text: str, restore_clipboard: bool = False) -> None:
    previous_text = _get_clipboard_text() if restore_clipboard else None
    _set_clipboard_text(text)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    if restore_clipboard and previous_text is not None:
        time.sleep(0.05)
        _set_clipboard_text(previous_text)


def browser_open_url(url: str, restore_clipboard: bool = False) -> None:
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.05)
    paste_text(url, restore_clipboard=restore_clipboard)
    # Give the address bar a bit more time to settle before confirming navigation.
    time.sleep(0.1)
    pyautogui.press("enter")


def browser_current_url(*, restore_clipboard: bool = True) -> str:
    previous_text = _get_clipboard_text() if restore_clipboard else None
    sentinel = f"agent-computer-browser-url-{time.time_ns()}"

    _set_clipboard_text(sentinel)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.05)
    copied_text = (_get_clipboard_text() or "").strip()
    pyautogui.press("esc")

    if restore_clipboard and previous_text is not None:
        time.sleep(0.05)
        _set_clipboard_text(previous_text)

    if not copied_text or copied_text == sentinel:
        raise RuntimeError("Unable to read the current browser URL from the address bar.")

    parsed = urlparse(copied_text)
    if not parsed.scheme:
        raise RuntimeError(f"Clipboard did not contain a valid browser URL: {copied_text!r}")

    return copied_text


def browser_back() -> None:
    pyautogui.hotkey("alt", "left")


def browser_forward() -> None:
    pyautogui.hotkey("alt", "right")


def browser_refresh() -> None:
    pyautogui.hotkey("ctrl", "r")


def press_key(key: str) -> None:
    pyautogui.press(key)


def hotkey(*keys: str) -> None:
    pyautogui.hotkey(*keys)
