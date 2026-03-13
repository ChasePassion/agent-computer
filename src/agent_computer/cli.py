from __future__ import annotations

import argparse
import json
from typing import Any

import httpx

from agent_computer.client import DaemonClient
from agent_computer.daemon import main as daemon_main
from agent_computer.models.requests import (
    AnalyzeRequest,
    CaptureGridRequest,
    CaptureOcrRequest,
    CapturePreviewRequest,
    CaptureRequest,
    ClickElementRequest,
    ClickRequest,
    FocusRequest,
    HotkeyRequest,
    MoveRequest,
    OpenUrlRequest,
    PasteRequest,
    PressRequest,
    ScrollRequest,
    TypeRequest,
)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_analysis_result(payload: dict[str, Any]) -> None:
    if payload.get("parsed_json") is not None:
        _print_json(payload["parsed_json"])
    else:
        print(payload.get("raw_text", ""))


def _call(
    client: DaemonClient,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    return client.request(method, path, payload)


def _handle_remote(args: argparse.Namespace, client: DaemonClient) -> None:
    command = args.command

    if command == "capture":
        payload = CaptureRequest(
            output=args.output,
            target=args.target,
            window_title=args.window_title,
            window_exact=args.window_exact,
            grid=args.grid,
            grid_size=args.grid_size,
            format=args.format,
            jpeg_quality=args.jpeg_quality,
        ).model_dump()
        result = _call(client, method="POST", path="/capture", payload=payload)
        _print_json(result)
        return

    if command == "capture-preview":
        payload = CapturePreviewRequest(output=args.output, jpeg_quality=args.jpeg_quality).model_dump()
        result = _call(client, method="POST", path="/capture/preview", payload=payload)
        _print_json(result)
        return

    if command == "capture-grid":
        payload = CaptureGridRequest(
            output=args.output,
            grid_size=args.grid_size,
            jpeg_quality=args.jpeg_quality,
        ).model_dump()
        result = _call(client, method="POST", path="/capture/grid", payload=payload)
        _print_json(result)
        return

    if command == "ocr":
        payload = AnalyzeRequest(
            image=args.image,
            model=args.model,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            target_description=None,
            json_output=args.json_output,
            prompt_output=args.prompt_output,
        ).model_dump()
        result = _call(client, method="POST", path="/gemini/ocr", payload=payload)
        _print_analysis_result(result)
        return

    if command == "locate":
        payload = AnalyzeRequest(
            image=args.image,
            model=args.model,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            target_description=args.target_description,
            json_output=args.json_output,
            prompt_output=args.prompt_output,
        ).model_dump()
        result = _call(client, method="POST", path="/gemini/locate", payload=payload)
        _print_analysis_result(result)
        return

    if command == "capture-ocr":
        payload = CaptureOcrRequest(
            output=args.output,
            target=args.target,
            window_title=args.window_title,
            window_exact=args.window_exact,
            grid=args.grid,
            grid_size=args.grid_size,
            format=args.format,
            jpeg_quality=args.jpeg_quality,
            model=args.model,
            prompt=args.prompt,
            prompt_file=args.prompt_file,
            target_description=None,
            json_output=args.json_output,
            prompt_output=args.prompt_output,
        ).model_dump()
        result = _call(client, method="POST", path="/capture/ocr", payload=payload)
        _print_analysis_result(result)
        return

    if command == "windows":
        result = _call(client, method="GET", path="/navigation/windows")
        _print_json(result)
        return

    if command == "focus":
        payload = FocusRequest(title=args.title, exact=args.exact).model_dump()
        result = _call(client, method="POST", path="/navigation/focus", payload=payload)
        _print_json(result)
        return

    if command == "move":
        payload = MoveRequest(x=args.x, y=args.y, duration=args.duration).model_dump()
        result = _call(client, method="POST", path="/actions/move", payload=payload)
        _print_json(result)
        return

    if command == "click":
        payload = ClickRequest(x=args.x, y=args.y, button=args.button, double=args.double).model_dump()
        result = _call(client, method="POST", path="/actions/click", payload=payload)
        _print_json(result)
        return

    if command == "click-element":
        payload = ClickElementRequest(
            json_file=args.json_file,
            index=args.index,
            button=args.button,
            double=args.double,
        ).model_dump()
        result = _call(client, method="POST", path="/actions/click-element", payload=payload)
        _print_json(result)
        return

    if command == "scroll":
        payload = ScrollRequest(amount=args.amount).model_dump()
        result = _call(client, method="POST", path="/actions/scroll", payload=payload)
        _print_json(result)
        return

    if command == "type":
        payload = TypeRequest(text=args.text, interval=args.interval).model_dump()
        result = _call(client, method="POST", path="/actions/type", payload=payload)
        _print_json(result)
        return

    if command == "paste":
        payload = PasteRequest(text=args.text, restore_clipboard=args.restore_clipboard).model_dump()
        result = _call(client, method="POST", path="/actions/paste", payload=payload)
        _print_json(result)
        return

    if command == "open-url":
        payload = OpenUrlRequest(url=args.url, restore_clipboard=args.restore_clipboard).model_dump()
        result = _call(client, method="POST", path="/navigation/open-url", payload=payload)
        _print_json(result)
        return

    if command == "press":
        payload = PressRequest(key=args.key).model_dump()
        result = _call(client, method="POST", path="/actions/press", payload=payload)
        _print_json(result)
        return

    if command == "hotkey":
        payload = HotkeyRequest(keys=args.keys).model_dump()
        result = _call(client, method="POST", path="/actions/hotkey", payload=payload)
        _print_json(result)
        return

    raise RuntimeError(f"Unsupported command: {command}")


def _handle_daemon(args: argparse.Namespace) -> None:
    client = DaemonClient(host=args.host, port=args.port)

    if args.daemon_command == "run":
        daemon_argv = ["--host", args.host, "--port", str(args.port), "--log-level", args.log_level]
        daemon_main(daemon_argv)
        return

    if args.daemon_command == "start":
        client.start_background()
        result = client.wait_until_ready()
        _print_json(result)
        return

    if args.daemon_command == "status":
        if client.is_running():
            _print_json(client.health())
        else:
            _print_json({"status": "not_running", "host": args.host, "port": args.port})
        return

    if args.daemon_command == "stop":
        if client.is_running():
            _print_json(client.shutdown())
        else:
            _print_json({"status": "not_running", "host": args.host, "port": args.port})
        return

    raise RuntimeError(f"Unsupported daemon command: {args.daemon_command}")


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
            "default": 50,
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
    capture_parser.add_argument("--window-title", default=None, help="Capture a visible window by title match.")
    capture_parser.add_argument("--window-exact", action="store_true", help="Require exact window title match.")
    capture_parser.add_argument("--grid", action="store_true", help="Overlay a coordinate grid.")
    capture_parser.add_argument("--grid-size", **common_capture["grid_size"])
    capture_parser.add_argument("--format", **common_capture["format"])
    capture_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])

    preview_parser = subparsers.add_parser(
        "capture-preview",
        help="Capture a lightweight full-screen JPEG preview for Codex to inspect directly.",
    )
    preview_parser.add_argument("--output", help="Path to save the preview image.")
    preview_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])

    grid_parser = subparsers.add_parser(
        "capture-grid",
        help="Capture a full-screen high-quality JPEG with absolute coordinate grid for Gemini coordinate lookup.",
    )
    grid_parser.add_argument("--output", help="Path to save the grid image.")
    grid_parser.add_argument("--grid-size", **common_capture["grid_size"])
    grid_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])

    ocr_parser = subparsers.add_parser("ocr", help="Run Gemini OCR/GUI understanding on an image.")
    ocr_parser.add_argument("--image", required=True, help="Path to the image file.")
    ocr_parser.add_argument("--model", default=None, help="Gemini model name.")
    ocr_parser.add_argument("--prompt", default=None, help="Inline prompt override.")
    ocr_parser.add_argument("--prompt-file", default=None, help="Path to a custom prompt file.")
    ocr_parser.add_argument("--json-output", default=None, help="Path to save raw result JSON.")
    ocr_parser.add_argument("--prompt-output", default=None, help="Path to save the final prompt sent to Gemini.")

    locate_parser = subparsers.add_parser(
        "locate",
        help="Use Gemini to locate a target on an image. Accepts either a custom prompt or a target description.",
    )
    locate_parser.add_argument("--image", required=True, help="Path to the image file.")
    locate_parser.add_argument("--model", default=None, help="Gemini model name.")
    locate_parser.add_argument("--target-description", default=None, help="Short target description.")
    locate_parser.add_argument("--prompt", default=None, help="Inline custom prompt override.")
    locate_parser.add_argument("--prompt-file", default=None, help="Path to a custom prompt file.")
    locate_parser.add_argument("--json-output", default=None, help="Path to save raw result JSON.")
    locate_parser.add_argument("--prompt-output", default=None, help="Path to save the final prompt sent to Gemini.")

    capture_ocr_parser = subparsers.add_parser(
        "capture-ocr",
        help="Capture first, then run Gemini OCR/GUI understanding.",
    )
    capture_ocr_parser.add_argument("--output", help="Path to save the screenshot.")
    capture_ocr_parser.add_argument(
        "--target",
        choices=["active-window", "primary-screen"],
        default="primary-screen",
        help="What to capture.",
    )
    capture_ocr_parser.add_argument("--window-title", default=None, help="Capture a visible window by title match.")
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

    windows_parser = subparsers.add_parser("windows", help="List visible desktop windows.")

    focus_parser = subparsers.add_parser("focus", help="Focus a visible window by title match.")
    focus_parser.add_argument("--title", required=True, help="Substring to match against visible window titles.")
    focus_parser.add_argument("--exact", action="store_true", help="Require exact title match.")

    move_parser = subparsers.add_parser("move", help="Move the mouse cursor.")
    move_parser.add_argument("--x", required=True, type=int, help="Screen X coordinate.")
    move_parser.add_argument("--y", required=True, type=int, help="Screen Y coordinate.")
    move_parser.add_argument("--duration", default=0.0, type=float, help="Movement duration in seconds.")

    click_parser = subparsers.add_parser("click", help="Click at screen coordinates.")
    click_parser.add_argument("--x", required=True, type=int, help="Screen X coordinate.")
    click_parser.add_argument("--y", required=True, type=int, help="Screen Y coordinate.")
    click_parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")
    click_parser.add_argument("--double", action="store_true", help="Double click instead of single click.")

    click_element_parser = subparsers.add_parser(
        "click-element",
        help="Click an element from a prior OCR JSON result by index.",
    )
    click_element_parser.add_argument("--json-file", required=True, help="Path to a JSON result file.")
    click_element_parser.add_argument("--index", required=True, type=int, help="Zero-based element index.")
    click_element_parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")
    click_element_parser.add_argument("--double", action="store_true", help="Double click instead of single click.")

    scroll_parser = subparsers.add_parser("scroll", help="Scroll the mouse wheel.")
    scroll_parser.add_argument("--amount", required=True, type=int, help="Positive scrolls up, negative scrolls down.")

    type_parser = subparsers.add_parser("type", help="Type text into the active window.")
    type_parser.add_argument("--text", required=True, help="Text to type.")
    type_parser.add_argument("--interval", default=0.02, type=float, help="Delay between keystrokes.")

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

    press_parser = subparsers.add_parser("press", help="Press a single key.")
    press_parser.add_argument("--key", required=True, help="Key name, for example enter or tab.")

    hotkey_parser = subparsers.add_parser("hotkey", help="Press a hotkey chord.")
    hotkey_parser.add_argument("keys", nargs="+", help="Keys to press together, for example ctrl shift s.")

    daemon_parser = subparsers.add_parser("daemon", help="Manage the local agent-computer daemon.")
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_command", required=True)
    for subcommand in ("start", "status", "stop"):
        parser_item = daemon_subparsers.add_parser(subcommand)
        parser_item.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
        parser_item.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")
    daemon_run_parser = daemon_subparsers.add_parser("run")
    daemon_run_parser.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
    daemon_run_parser.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")
    daemon_run_parser.add_argument("--log-level", default="warning", help="Daemon log level.")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "daemon":
        _handle_daemon(args)
        return

    client = DaemonClient()
    try:
        _handle_remote(args, client)
    except httpx.HTTPStatusError as exc:
        try:
            payload = exc.response.json()
        except Exception:
            payload = {"error": {"type": "HTTPStatusError", "message": str(exc)}}
        _print_json(payload)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
