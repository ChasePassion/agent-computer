from __future__ import annotations

import inspect

import pyautogui

from agent_computer import actions


def test_default_input_pause_is_fast_but_not_zero() -> None:
    assert 0.0 < pyautogui.PAUSE <= 0.05


def test_typing_default_does_not_add_per_character_delay() -> None:
    assert inspect.signature(actions.type_text).parameters["interval"].default == 0.0
