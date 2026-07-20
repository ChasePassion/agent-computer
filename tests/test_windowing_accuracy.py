from __future__ import annotations

import pytest

from agent_computer import windowing


def _window(hwnd: int, title: str, *, foreground: bool = False) -> windowing.WindowInfo:
    return windowing.WindowInfo(
        hwnd=hwnd,
        title=title,
        rect=(0, 0, 100, 100),
        visible=True,
        enabled=True,
        foreground=foreground,
    )


def test_find_window_prefers_exact_title_over_earlier_substring(monkeypatch) -> None:
    monkeypatch.setattr(
        windowing,
        "list_windows",
        lambda: [_window(1, "Project - Google Chrome"), _window(2, "Google Chrome")],
    )

    assert windowing.find_window("Google Chrome").hwnd == 2


def test_find_window_rejects_ambiguous_substring_instead_of_guessing(monkeypatch) -> None:
    monkeypatch.setattr(
        windowing,
        "list_windows",
        lambda: [_window(1, "Alpha - Chrome"), _window(2, "Beta - Chrome")],
    )

    with pytest.raises(RuntimeError, match="Ambiguous visible window match"):
        windowing.find_window("Chrome")
