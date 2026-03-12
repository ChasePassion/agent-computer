from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_computer.actions import (
    click,
    double_click,
    hotkey as send_hotkey,
    move_to,
    open_url,
    paste_text,
    press_key,
    scroll,
    type_text,
)
from agent_computer.capture import capture
from agent_computer.gemini_client import GeminiDesktopOCR
from agent_computer.prompts import DEFAULT_OCR_PROMPT, build_locate_prompt
from agent_computer.windowing import focus_window, list_windows

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _default_capture_path(prefix: str = "capture", suffix: str = ".png") -> Path:
    return ARTIFACTS_DIR / f"{prefix}_{_timestamp()}{suffix}"


def _load_prompt(args: argparse.Namespace) -> str:
    if getattr(args, "prompt_file", None):
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if getattr(args, "prompt", None):
        return args.prompt
    if getattr(args, "target_description", None):
        return build_locate_prompt(args.target_description)
    return DEFAULT_OCR_PROMPT


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _metadata_sidecar_path(image_path: str | Path) -> Path:
    return Path(str(image_path) + ".meta.json")


def _write_capture_sidecar(capture_payload: dict[str, Any]) -> None:
    image_path = capture_payload.get("image_path")
    if not image_path:
        return
    _write_json(_metadata_sidecar_path(image_path), capture_payload)


def _print_result(result: dict[str, Any]) -> None:
    if result.get("parsed_json") is not None:
        print(json.dumps(result["parsed_json"], ensure_ascii=False, indent=2))
    else:
        print(result.get("raw_text", ""))


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _enrich_analysis(result: dict[str, Any], capture_meta: dict[str, Any] | None) -> dict[str, Any]:
    parsed = result.get("parsed_json")
    if not isinstance(parsed, dict) or not capture_meta:
        return result

    bounds = capture_meta.get("bounds")
    if not bounds or len(bounds) != 4:
        return result

    offset_x, offset_y = bounds[0], bounds[1]
    for element in parsed.get("elements", []):
        bbox = element.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            abs_bbox = None
        else:
            x1, y1, x2, y2 = bbox
            abs_bbox = [x1 + offset_x, y1 + offset_y, x2 + offset_x, y2 + offset_y]
            element["absolute_bbox"] = abs_bbox

        click_point = element.get("click_point")
        if isinstance(click_point, list) and len(click_point) == 2:
            element["click_point"] = [click_point[0] + offset_x, click_point[1] + offset_y]
        elif abs_bbox is not None:
            element["click_point"] = [
                int((abs_bbox[0] + abs_bbox[2]) / 2),
                int((abs_bbox[1] + abs_bbox[3]) / 2),
            ]

    result["parsed_json"] = parsed
    return result


def handle_capture(args: argparse.Namespace) -> None:
    suffix = ".jpg" if args.format == "jpeg" else ".png"
    output = Path(args.output or _default_capture_path("capture", suffix))
    result = capture(
        output_path=output,
        target=args.target,
        draw_grid=args.grid,
        grid_size=args.grid_size,
        window_title_query=args.window_title,
        window_exact=args.window_exact,
        image_format=args.format,
        jpeg_quality=args.jpeg_quality,
    )
    payload = result.to_dict()
    _write_capture_sidecar(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_capture_preview(args: argparse.Namespace) -> None:
    output = Path(args.output or _default_capture_path("preview", ".jpg"))
    result = capture(
        output_path=output,
        target="primary-screen",
        draw_grid=False,
        image_format="jpeg",
        jpeg_quality=args.jpeg_quality,
    )
    payload = result.to_dict()
    _write_capture_sidecar(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_capture_grid(args: argparse.Namespace) -> None:
    output = Path(args.output or _default_capture_path("grid", ".jpg"))
    result = capture(
        output_path=output,
        target="primary-screen",
        draw_grid=True,
        grid_size=args.grid_size,
        image_format="jpeg",
        jpeg_quality=args.jpeg_quality,
    )
    payload = result.to_dict()
    _write_capture_sidecar(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def handle_ocr(args: argparse.Namespace) -> None:
    prompt = _load_prompt(args)
    client = GeminiDesktopOCR(model=args.model)
    result = client.analyze_image(image_path=args.image, prompt=prompt)

    if args.json_output:
        _write_json(args.json_output, result)
    if args.prompt_output:
        Path(args.prompt_output).write_text(result["effective_prompt"], encoding="utf-8")
    _print_result(result)


def handle_locate(args: argparse.Namespace) -> None:
    prompt = _load_prompt(args)
    client = GeminiDesktopOCR(model=args.model)
    result = client.analyze_image(image_path=args.image, prompt=prompt)

    if args.json_output:
        _write_json(args.json_output, result)
    if args.prompt_output:
        Path(args.prompt_output).write_text(result["effective_prompt"], encoding="utf-8")
    _print_result(result)


def handle_capture_ocr(args: argparse.Namespace) -> None:
    suffix = ".jpg" if args.format == "jpeg" else ".png"
    capture_path = Path(args.output or _default_capture_path("capture", suffix))
    shot = capture(
        output_path=capture_path,
        target=args.target,
        draw_grid=args.grid,
        grid_size=args.grid_size,
        window_title_query=args.window_title,
        window_exact=args.window_exact,
        image_format=args.format,
        jpeg_quality=args.jpeg_quality,
    )
    prompt = _load_prompt(args)
    client = GeminiDesktopOCR(model=args.model)
    result = client.analyze_image(image_path=shot.image_path, prompt=prompt)
    capture_payload = shot.to_dict()
    _write_capture_sidecar(capture_payload)
    result["capture"] = capture_payload
    result = _enrich_analysis(result, result["capture"])

    if args.json_output:
        _write_json(args.json_output, result)
    if args.prompt_output:
        Path(args.prompt_output).write_text(result["effective_prompt"], encoding="utf-8")
    _print_result(result)


def handle_windows(_: argparse.Namespace) -> None:
    windows = [window.to_dict() for window in list_windows()]
    print(json.dumps(windows, ensure_ascii=False, indent=2))


def handle_focus(args: argparse.Namespace) -> None:
    window = focus_window(args.title, exact=args.exact)
    print(json.dumps(window.to_dict(), ensure_ascii=False, indent=2))


def handle_move(args: argparse.Namespace) -> None:
    move_to(args.x, args.y, duration=args.duration)
    print(json.dumps({"moved_to": [args.x, args.y], "duration": args.duration}, ensure_ascii=False, indent=2))


def handle_click(args: argparse.Namespace) -> None:
    if args.double:
        double_click(args.x, args.y, button=args.button)
    else:
        click(args.x, args.y, button=args.button)
    print(
        json.dumps(
            {
                "clicked": [args.x, args.y],
                "button": args.button,
                "double": args.double,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_scroll(args: argparse.Namespace) -> None:
    scroll(args.amount)
    print(json.dumps({"scrolled": args.amount}, ensure_ascii=False, indent=2))


def handle_type(args: argparse.Namespace) -> None:
    type_text(args.text, interval=args.interval)
    print(json.dumps({"typed_length": len(args.text), "interval": args.interval}, ensure_ascii=False, indent=2))


def handle_paste(args: argparse.Namespace) -> None:
    paste_text(args.text, restore_clipboard=args.restore_clipboard)
    print(
        json.dumps(
            {
                "pasted_length": len(args.text),
                "restore_clipboard": args.restore_clipboard,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_open_url(args: argparse.Namespace) -> None:
    open_url(args.url, restore_clipboard=args.restore_clipboard)
    print(
        json.dumps(
            {
                "opened_url": args.url,
                "restore_clipboard": args.restore_clipboard,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def handle_press(args: argparse.Namespace) -> None:
    press_key(args.key)
    print(json.dumps({"pressed": args.key}, ensure_ascii=False, indent=2))


def handle_hotkey(args: argparse.Namespace) -> None:
    send_hotkey(*args.keys)
    print(json.dumps({"hotkey": args.keys}, ensure_ascii=False, indent=2))


def handle_click_element(args: argparse.Namespace) -> None:
    payload = _read_json(args.json_file)
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
    if not isinstance(elements, list) or args.index < 0 or args.index >= len(elements):
        raise RuntimeError(f"Element index out of range: {args.index}")

    element = elements[args.index]
    click_point = element.get("click_point")
    if not click_point:
        bbox = element.get("absolute_bbox") or element.get("bbox")
        if not bbox or len(bbox) != 4:
            raise RuntimeError("Selected element has no click_point or bbox.")
        click_point = [int((bbox[0] + bbox[2]) / 2), int((bbox[1] + bbox[3]) / 2)]

    x, y = click_point
    if args.double:
        double_click(x, y, button=args.button)
    else:
        click(x, y, button=args.button)

    print(
        json.dumps(
            {
                "element_index": args.index,
                "label": element.get("label"),
                "click_point": [x, y],
                "button": args.button,
                "double": args.double,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-computer",
        description="Capture Windows desktop screenshots, analyze them with Gemini, and drive desktop actions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common_capture = {
        "target": {
            "choices": ["active-window", "primary-screen"],
            "default": "active-window",
            "help": "What to capture.",
        },
        "grid_size": {
            "type": int,
            "default": 100,
            "help": "Coordinate grid spacing in pixels.",
        },
        "format": {
            "choices": ["png", "jpeg"],
            "default": "png",
            "help": "Image format for the saved screenshot.",
        },
        "jpeg_quality": {
            "type": int,
            "default": 75,
            "help": "JPEG quality when format is jpeg.",
        },
    }

    capture_parser = subparsers.add_parser("capture", help="Capture a screenshot only.")
    capture_parser.add_argument("--output", help="Path to save the screenshot.")
    capture_parser.add_argument("--target", **common_capture["target"])
    capture_parser.add_argument(
        "--window-title",
        default=None,
        help="Capture a visible window by title match instead of relying on the foreground window.",
    )
    capture_parser.add_argument("--window-exact", action="store_true", help="Require exact window title match.")
    capture_parser.add_argument("--grid", action="store_true", help="Overlay a coordinate grid.")
    capture_parser.add_argument("--grid-size", **common_capture["grid_size"])
    capture_parser.add_argument("--format", **common_capture["format"])
    capture_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])
    capture_parser.set_defaults(func=handle_capture)

    preview_parser = subparsers.add_parser(
        "capture-preview",
        help="Capture a lightweight full-screen JPEG preview for Codex to inspect directly.",
    )
    preview_parser.add_argument("--output", help="Path to save the preview image.")
    preview_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])
    preview_parser.set_defaults(func=handle_capture_preview)

    grid_parser = subparsers.add_parser(
        "capture-grid",
        help="Capture a full-screen high-quality JPEG with absolute coordinate grid for Gemini coordinate lookup.",
    )
    grid_parser.add_argument("--output", help="Path to save the grid image.")
    grid_parser.add_argument("--grid-size", **common_capture["grid_size"])
    grid_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])
    grid_parser.set_defaults(func=handle_capture_grid)

    ocr_parser = subparsers.add_parser("ocr", help="Run Gemini OCR/GUI understanding on an image.")
    ocr_parser.add_argument("--image", required=True, help="Path to the image file.")
    ocr_parser.add_argument("--model", default=None, help="Gemini model name.")
    ocr_parser.add_argument("--prompt", default=None, help="Inline prompt override.")
    ocr_parser.add_argument("--prompt-file", default=None, help="Path to a custom prompt file.")
    ocr_parser.add_argument("--json-output", default=None, help="Path to save raw result JSON.")
    ocr_parser.add_argument("--prompt-output", default=None, help="Path to save the final prompt sent to Gemini.")
    ocr_parser.set_defaults(func=handle_ocr)

    locate_parser = subparsers.add_parser(
        "locate",
        help="Use Gemini to locate a target on an image. Accepts either a custom prompt or a target description.",
    )
    locate_parser.add_argument("--image", required=True, help="Path to the image file.")
    locate_parser.add_argument("--model", default=None, help="Gemini model name.")
    locate_parser.add_argument("--target-description", default=None, help="Short target description used to build a locate prompt.")
    locate_parser.add_argument("--prompt", default=None, help="Inline custom prompt override.")
    locate_parser.add_argument("--prompt-file", default=None, help="Path to a custom prompt file.")
    locate_parser.add_argument("--json-output", default=None, help="Path to save raw result JSON.")
    locate_parser.add_argument("--prompt-output", default=None, help="Path to save the final prompt sent to Gemini.")
    locate_parser.set_defaults(func=handle_locate)

    capture_ocr_parser = subparsers.add_parser(
        "capture-ocr",
        help="Capture first, then run Gemini OCR/GUI understanding.",
    )
    capture_ocr_parser.add_argument("--output", help="Path to save the screenshot.")
    capture_ocr_parser.add_argument(
        "--target",
        choices=["active-window", "primary-screen"],
        default="primary-screen",
        help="What to capture. For clickable OCR results, keep this as primary-screen.",
    )
    capture_ocr_parser.add_argument(
        "--window-title",
        default=None,
        help="Capture a visible window by title match instead of relying on the foreground window.",
    )
    capture_ocr_parser.add_argument("--window-exact", action="store_true", help="Require exact window title match.")
    capture_ocr_parser.add_argument("--grid", action="store_true", help="Overlay a coordinate grid.")
    capture_ocr_parser.add_argument("--grid-size", **common_capture["grid_size"])
    capture_ocr_parser.add_argument("--format", **common_capture["format"])
    capture_ocr_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])
    capture_ocr_parser.add_argument("--model", default=None, help="Gemini model name.")
    capture_ocr_parser.add_argument("--prompt", default=None, help="Inline prompt override.")
    capture_ocr_parser.add_argument("--prompt-file", default=None, help="Path to a custom prompt file.")
    capture_ocr_parser.add_argument("--json-output", default=None, help="Path to save raw result JSON.")
    capture_ocr_parser.add_argument("--prompt-output", default=None, help="Path to save the final prompt sent to Gemini.")
    capture_ocr_parser.set_defaults(func=handle_capture_ocr)

    windows_parser = subparsers.add_parser("windows", help="List visible desktop windows.")
    windows_parser.set_defaults(func=handle_windows)

    focus_parser = subparsers.add_parser("focus", help="Focus a visible window by title match.")
    focus_parser.add_argument("--title", required=True, help="Substring to match against visible window titles.")
    focus_parser.add_argument("--exact", action="store_true", help="Require exact title match.")
    focus_parser.set_defaults(func=handle_focus)

    move_parser = subparsers.add_parser("move", help="Move the mouse cursor.")
    move_parser.add_argument("--x", required=True, type=int, help="Screen X coordinate.")
    move_parser.add_argument("--y", required=True, type=int, help="Screen Y coordinate.")
    move_parser.add_argument("--duration", default=0.0, type=float, help="Movement duration in seconds.")
    move_parser.set_defaults(func=handle_move)

    click_parser = subparsers.add_parser("click", help="Click at screen coordinates.")
    click_parser.add_argument("--x", required=True, type=int, help="Screen X coordinate.")
    click_parser.add_argument("--y", required=True, type=int, help="Screen Y coordinate.")
    click_parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")
    click_parser.add_argument("--double", action="store_true", help="Double click instead of single click.")
    click_parser.set_defaults(func=handle_click)

    click_element_parser = subparsers.add_parser(
        "click-element",
        help="Click an element from a prior OCR JSON result by index.",
    )
    click_element_parser.add_argument("--json-file", required=True, help="Path to a JSON result file.")
    click_element_parser.add_argument("--index", required=True, type=int, help="Zero-based element index.")
    click_element_parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")
    click_element_parser.add_argument("--double", action="store_true", help="Double click instead of single click.")
    click_element_parser.set_defaults(func=handle_click_element)

    scroll_parser = subparsers.add_parser("scroll", help="Scroll the mouse wheel.")
    scroll_parser.add_argument("--amount", required=True, type=int, help="Positive scrolls up, negative scrolls down.")
    scroll_parser.set_defaults(func=handle_scroll)

    type_parser = subparsers.add_parser("type", help="Type text into the active window.")
    type_parser.add_argument("--text", required=True, help="Text to type.")
    type_parser.add_argument("--interval", default=0.02, type=float, help="Delay between keystrokes.")
    type_parser.set_defaults(func=handle_type)

    paste_parser = subparsers.add_parser(
        "paste",
        help="Paste text into the active input using the Windows clipboard and Ctrl+V.",
    )
    paste_parser.add_argument("--text", required=True, help="Text to put on the clipboard and paste.")
    paste_parser.add_argument(
        "--restore-clipboard",
        action="store_true",
        help="Restore the previous clipboard text after pasting when possible.",
    )
    paste_parser.set_defaults(func=handle_paste)

    open_url_parser = subparsers.add_parser(
        "open-url",
        help="Focus the browser address bar, paste a URL, and press Enter.",
    )
    open_url_parser.add_argument("--url", required=True, help="URL to open in the active browser window.")
    open_url_parser.add_argument(
        "--restore-clipboard",
        action="store_true",
        help="Restore the previous clipboard text after navigation when possible.",
    )
    open_url_parser.set_defaults(func=handle_open_url)

    press_parser = subparsers.add_parser("press", help="Press a single key.")
    press_parser.add_argument("--key", required=True, help="Key name, for example enter or tab.")
    press_parser.set_defaults(func=handle_press)

    hotkey_parser = subparsers.add_parser("hotkey", help="Press a hotkey chord.")
    hotkey_parser.add_argument("keys", nargs="+", help="Keys to press together, for example ctrl shift s.")
    hotkey_parser.set_defaults(func=handle_hotkey)

    return parser


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
