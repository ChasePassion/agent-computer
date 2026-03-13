from __future__ import annotations

from typing import Any

from agent_computer.actions import click, double_click, hotkey, move_to, paste_text, press_key, scroll, type_text
from agent_computer.runtime import read_json


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

    def click_element(
        self,
        *,
        json_file: str,
        index: int,
        button: str = "left",
        double: bool = False,
    ) -> dict[str, Any]:
        payload = read_json(json_file)
        parsed = payload.get("parsed_json", payload)
        if not isinstance(parsed, dict):
            raise RuntimeError("JSON file does not contain parsed_json or a direct analysis payload.")

        capture_meta = payload.get("capture")
        if isinstance(capture_meta, dict):
            bounds = capture_meta.get("bounds")
            if isinstance(bounds, list) and len(bounds) == 4 and (bounds[0] != 0 or bounds[1] != 0):
                raise RuntimeError(
                    "click-element now only supports full-screen OCR results with screen-origin coordinates. "
                    "Use capture-ocr --target primary-screen --grid."
                )

        elements = parsed.get("elements", [])
        if not isinstance(elements, list) or index < 0 or index >= len(elements):
            raise RuntimeError(f"Element index out of range: {index}")

        element = elements[index]
        click_point = element.get("click_point")
        if not click_point:
            bbox = element.get("absolute_bbox") or element.get("bbox")
            if not bbox or len(bbox) != 4:
                raise RuntimeError("Selected element has no click_point or bbox.")
            click_point = [int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)]

        x, y = click_point
        result = self.click(x=x, y=y, button=button, double=double)
        result["element_index"] = index
        result["label"] = element.get("label")
        result["click_point"] = [x, y]
        return result
