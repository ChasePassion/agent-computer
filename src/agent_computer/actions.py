from __future__ import annotations

import time

import pyautogui
import win32clipboard

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.15


def move_to(x: int, y: int, duration: float = 0.0) -> None:
    pyautogui.moveTo(x=x, y=y, duration=duration)


def click(x: int, y: int, button: str = "left") -> None:
    pyautogui.click(x=x, y=y, button=button)


def double_click(x: int, y: int, button: str = "left") -> None:
    pyautogui.doubleClick(x=x, y=y, button=button)


def scroll(amount: int) -> None:
    pyautogui.scroll(amount)


def type_text(text: str, interval: float = 0.02) -> None:
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


def open_url(url: str, restore_clipboard: bool = False) -> None:
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.05)
    paste_text(url, restore_clipboard=restore_clipboard)
    time.sleep(0.05)
    pyautogui.press("enter")


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
