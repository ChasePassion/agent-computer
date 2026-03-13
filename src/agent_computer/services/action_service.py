from __future__ import annotations

from typing import Any

from agent_computer.actions import click, double_click, hotkey, move_to, paste_text, press_key, scroll, type_text


class ActionService:
    def move(self, *, x: int, y: int, duration: float = 0.0) -> dict[str, Any]:
        move_to(x, y, duration=duration)
        return {"moved_to": [x, y], "duration": duration}

    def click(self, *, x: int, y: int, button: str = "left", double: bool = False) -> dict[str, Any]:
        if double:
            double_click(x, y, button=button)
        else:
            click(x, y, button=button)
        return {"clicked": [x, y], "button": button, "double": double}

    def scroll(self, *, amount: int) -> dict[str, Any]:
        scroll(amount)
        return {"scrolled": amount}

    def type_text(self, *, text: str, interval: float = 0.02) -> dict[str, Any]:
        type_text(text, interval=interval)
        return {"typed_length": len(text), "interval": interval}

    def paste(self, *, text: str, restore_clipboard: bool = False) -> dict[str, Any]:
        paste_text(text, restore_clipboard=restore_clipboard)
        return {"pasted_length": len(text), "restore_clipboard": restore_clipboard}

    def press(self, *, key: str) -> dict[str, Any]:
        press_key(key)
        return {"pressed": key}

    def hotkey(self, *, keys: list[str]) -> dict[str, Any]:
        hotkey(*keys)
        return {"hotkey": keys}
