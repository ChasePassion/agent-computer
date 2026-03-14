from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from agent_computer.actions import mouse_position
from agent_computer.client import DaemonClient
from agent_computer.daemon import main as daemon_main
from agent_computer.models.browser_assist import BrowserAssistLocateRequest
from agent_computer.models.requests import (
    BrowserOpenUrlRequest,
    CaptureGridRequest,
    CapturePreviewRequest,
    CaptureRequest,
    ClickRequest,
    FocusRequest,
    HotkeyRequest,
    LiveOutputEventRequest,
    LiveOutputStatusRequest,
    MaximizeRequest,
    MoveRequest,
    PasteRequest,
    PressRequest,
    ScrollRequest,
    TypeRequest,
)
from agent_computer.runtime import observation_token_path, read_json, write_observation_urls_manifest


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _call(
    client: DaemonClient,
    *,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    return client.request(method, path, payload)


def _print_observation_urls(payload: dict[str, Any]) -> None:
    print("Defaults:")
    print(f"  Human Live: {payload['human_default_url']}")
    print(f"  Model Image: {payload['model_default_image_url']}")
    print(f"  Model Meta: {payload['model_default_meta_url']}")
    print(f"  Model Mouse: {payload['model_mouse_url']}")
    print("")
    print("Local:")
    print(f"  Live: {payload['human_live_url']}")
    print(f"  Preview Image: {payload['human_preview_url']}")
    print(f"  Grid Image: {payload['human_grid_url']}")
    print(f"  Grid Meta: {payload['model_default_meta_url']}")
    print(f"  Mouse: {payload['model_mouse_url']}")

    public_bundle = payload.get("public")
    if isinstance(public_bundle, dict):
        print("")
        print("Public:")
        print(f"  Live: {payload['public_human_live_url']}")
        print(f"  Preview Image: {payload['public_human_preview_url']}")
        print(f"  Grid Image: {payload['public_human_grid_url']}")
        print(f"  Grid Meta: {payload['public_model_default_meta_url']}")
        print(f"  Mouse: {payload['public_model_mouse_url']}")


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
        _print_json(_call(client, method="POST", path="/capture", payload=payload))
        return

    if command == "capture-preview":
        payload = CapturePreviewRequest(output=args.output, jpeg_quality=args.jpeg_quality).model_dump()
        _print_json(_call(client, method="POST", path="/capture/preview", payload=payload))
        return

    if command == "capture-grid":
        payload = CaptureGridRequest(
            output=args.output,
            grid_size=args.grid_size,
            jpeg_quality=args.jpeg_quality,
        ).model_dump()
        _print_json(_call(client, method="POST", path="/capture/grid", payload=payload))
        return

    if command == "windows":
        _print_json(_call(client, method="GET", path="/navigation/windows"))
        return

    if command == "focus":
        payload = FocusRequest(title=args.title, exact=args.exact).model_dump()
        _print_json(_call(client, method="POST", path="/navigation/focus", payload=payload))
        return

    if command == "maximize":
        payload = MaximizeRequest(title=args.title, exact=args.exact).model_dump()
        _print_json(_call(client, method="POST", path="/navigation/maximize", payload=payload))
        return

    if command == "move":
        payload = MoveRequest(x=args.x, y=args.y, duration=args.duration).model_dump()
        _print_json(_call(client, method="POST", path="/actions/move", payload=payload))
        return

    if command == "click":
        payload = ClickRequest(x=args.x, y=args.y, button=args.button, double=args.double).model_dump()
        _print_json(_call(client, method="POST", path="/actions/click", payload=payload))
        return

    if command == "scroll":
        payload = ScrollRequest(amount=args.amount).model_dump()
        _print_json(_call(client, method="POST", path="/actions/scroll", payload=payload))
        return

    if command == "type":
        payload = TypeRequest(text=args.text, interval=args.interval).model_dump()
        _print_json(_call(client, method="POST", path="/actions/type", payload=payload))
        return

    if command == "paste":
        payload = PasteRequest(text=args.text, restore_clipboard=args.restore_clipboard).model_dump()
        _print_json(_call(client, method="POST", path="/actions/paste", payload=payload))
        return

    if command == "browser-open-url":
        payload = BrowserOpenUrlRequest(url=args.url, restore_clipboard=args.restore_clipboard).model_dump()
        _print_json(_call(client, method="POST", path="/navigation/browser-open-url", payload=payload))
        return

    if command == "browser-current-url":
        _print_json(_call(client, method="POST", path="/navigation/browser-current-url"))
        return

    if command == "browser-back":
        _print_json(_call(client, method="POST", path="/navigation/browser-back"))
        return

    if command == "browser-forward":
        _print_json(_call(client, method="POST", path="/navigation/browser-forward"))
        return

    if command == "browser-refresh":
        _print_json(_call(client, method="POST", path="/navigation/browser-refresh"))
        return

    if command == "browser-assist-status":
        _print_json(_call(client, method="GET", path="/browser-assist/status"))
        return

    if command == "browser-assist-locate":
        raw_input = args.input_json
        if args.input_file:
            raw_input = Path(args.input_file).read_text(encoding="utf-8")
        payload = BrowserAssistLocateRequest.model_validate(json.loads(raw_input)).model_dump(mode="json")
        _print_json(_call(client, method="POST", path="/browser-assist/locate", payload=payload))
        return

    if command == "press":
        payload = PressRequest(key=args.key).model_dump()
        _print_json(_call(client, method="POST", path="/actions/press", payload=payload))
        return

    if command == "hotkey":
        payload = HotkeyRequest(keys=args.keys).model_dump()
        _print_json(_call(client, method="POST", path="/actions/hotkey", payload=payload))
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
        _print_json(client.wait_until_ready())
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

    raise RuntimeError(f"Unsupported command: {args.daemon_command}")


def _handle_observation(args: argparse.Namespace) -> None:
    if args.observation_command == "urls":
        client = DaemonClient(host=args.host, port=args.port)
        client.ensure_running()
        token_payload = read_json(observation_token_path())
        token = str(token_payload.get("token", "")).strip() if isinstance(token_payload, dict) else ""
        if not token:
            raise RuntimeError("Observation token is missing. Start the daemon and try again.")
        payload = write_observation_urls_manifest(token=token, host=args.host, port=args.port)
        if args.json:
            _print_json(payload)
        else:
            _print_observation_urls(payload)
        return

    if args.observation_command == "mouse":
        x, y = mouse_position()
        payload = {
            "x": x,
            "y": y,
            "coordinate_system": "screen-absolute-grid",
            "origin": [0, 0],
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"Mouse: ({x}, {y}) [screen-absolute-grid]")
        return

    raise RuntimeError(f"Unsupported command: {args.observation_command}")


def _handle_live_output(args: argparse.Namespace) -> None:
    client = DaemonClient(host=args.host, port=args.port)

    if args.live_output_command == "append":
        payload = LiveOutputEventRequest(
            kind=args.kind,
            text=args.text,
            session_id=args.session_id,
            status=args.status,
            created_at=args.created_at,
            source_rollout_path=args.source_rollout_path,
        ).model_dump(exclude_none=True)
        _print_json(_call(client, method="POST", path="/internal/live-output/events", payload=payload))
        return

    if args.live_output_command == "status":
        payload = LiveOutputStatusRequest(
            value=args.value,
            session_id=args.session_id,
            updated_at=args.updated_at,
            source_rollout_path=args.source_rollout_path,
        ).model_dump(exclude_none=True)
        _print_json(_call(client, method="POST", path="/internal/live-output/status", payload=payload))
        return

    if args.live_output_command == "reset":
        _print_json(_call(client, method="POST", path="/internal/live-output/reset"))
        return

    if args.live_output_command == "show":
        _print_json(_call(client, method="GET", path="/internal/live-output"))
        return

    raise RuntimeError(f"Unsupported command: {args.live_output_command}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-computer",
        description="Capture Windows desktop screenshots and drive desktop actions.",
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
        help="Capture a lightweight full-screen JPEG preview for direct inspection.",
    )
    preview_parser.add_argument("--output", help="Path to save the preview image.")
    preview_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])

    grid_parser = subparsers.add_parser(
        "capture-grid",
        help="Capture a full-screen high-quality JPEG with absolute coordinate grid.",
    )
    grid_parser.add_argument("--output", help="Path to save the grid image.")
    grid_parser.add_argument("--grid-size", **common_capture["grid_size"])
    grid_parser.add_argument("--jpeg-quality", **common_capture["jpeg_quality"])

    subparsers.add_parser("windows", help="List visible desktop windows.")

    focus_parser = subparsers.add_parser("focus", help="Focus a visible window by title match.")
    focus_parser.add_argument("--title", required=True, help="Substring to match against visible window titles.")
    focus_parser.add_argument("--exact", action="store_true", help="Require exact title match.")

    maximize_parser = subparsers.add_parser("maximize", help="Maximize a visible window by title match.")
    maximize_parser.add_argument("--title", required=True, help="Substring to match against visible window titles.")
    maximize_parser.add_argument("--exact", action="store_true", help="Require exact title match.")

    move_parser = subparsers.add_parser("move", help="Move the mouse cursor.")
    move_parser.add_argument("--x", required=True, type=int, help="Screen X coordinate.")
    move_parser.add_argument("--y", required=True, type=int, help="Screen Y coordinate.")
    move_parser.add_argument("--duration", default=0.0, type=float, help="Movement duration in seconds.")

    click_parser = subparsers.add_parser("click", help="Click at screen coordinates.")
    click_parser.add_argument("--x", required=True, type=int, help="Screen X coordinate.")
    click_parser.add_argument("--y", required=True, type=int, help="Screen Y coordinate.")
    click_parser.add_argument("--button", default="left", choices=["left", "right", "middle"], help="Mouse button.")
    click_parser.add_argument("--double", action="store_true", help="Double click instead of single click.")

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

    browser_open_url_parser = subparsers.add_parser(
        "browser-open-url",
        help="Focus the browser address bar, paste a URL, and press Enter.",
    )
    browser_open_url_parser.add_argument("--url", required=True, help="URL to open in the active browser window.")
    browser_open_url_parser.add_argument(
        "--restore-clipboard",
        action="store_true",
        help="Restore the previous clipboard text after navigation when possible.",
    )

    subparsers.add_parser("browser-current-url", help="Read the current URL from the active browser tab.")
    subparsers.add_parser("browser-back", help="Navigate the active browser back.")
    subparsers.add_parser("browser-forward", help="Navigate the active browser forward.")
    subparsers.add_parser("browser-refresh", help="Refresh the active browser page.")
    subparsers.add_parser("browser-assist-status", help="Show Browser Assist extension connection status.")

    browser_assist_locate_parser = subparsers.add_parser(
        "browser-assist-locate",
        help="Send a structured Browser Assist locate request.",
    )
    browser_assist_locate_input_group = browser_assist_locate_parser.add_mutually_exclusive_group(required=True)
    browser_assist_locate_input_group.add_argument("--input-json", help="Inline JSON request payload.")
    browser_assist_locate_input_group.add_argument("--input-file", help="Path to a JSON request payload.")

    press_parser = subparsers.add_parser("press", help="Press a single key.")
    press_parser.add_argument("--key", required=True, help="Key name, for example enter or tab.")

    hotkey_parser = subparsers.add_parser("hotkey", help="Press a hotkey chord.")
    hotkey_parser.add_argument("keys", nargs="+", help="Keys to press together, for example ctrl shift s.")

    observation_parser = subparsers.add_parser("observation", help="Observation helpers.")
    observation_subparsers = observation_parser.add_subparsers(dest="observation_command", required=True)
    observation_urls_parser = observation_subparsers.add_parser("urls", help="Print default observation URLs.")
    observation_urls_parser.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
    observation_urls_parser.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")
    observation_urls_parser.add_argument("--json", action="store_true", help="Print URLs as JSON.")
    observation_mouse_parser = observation_subparsers.add_parser(
        "mouse",
        help="Print the current mouse position in the grid coordinate system.",
    )
    observation_mouse_parser.add_argument("--json", action="store_true", help="Print the mouse position as JSON.")

    live_output_parser = subparsers.add_parser("live-output", help="Live output helpers.")
    live_output_subparsers = live_output_parser.add_subparsers(dest="live_output_command", required=True)

    live_output_append_parser = live_output_subparsers.add_parser("append", help="Append a live output event.")
    live_output_append_parser.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
    live_output_append_parser.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")
    live_output_append_parser.add_argument("--kind", default="commentary", choices=["commentary", "final", "tool"])
    live_output_append_parser.add_argument("--text", required=True, help="Text to append.")
    live_output_append_parser.add_argument("--status", choices=["running", "idle", "no_output"], default=None)
    live_output_append_parser.add_argument("--session-id", default=None, help="Optional session identifier.")
    live_output_append_parser.add_argument("--created-at", default=None, help="Optional ISO timestamp.")
    live_output_append_parser.add_argument("--source-rollout-path", default=None, help="Optional source rollout path.")

    live_output_status_parser = live_output_subparsers.add_parser("status", help="Set live output status.")
    live_output_status_parser.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
    live_output_status_parser.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")
    live_output_status_parser.add_argument("--value", required=True, choices=["running", "idle", "no_output"])
    live_output_status_parser.add_argument("--session-id", default=None, help="Optional session identifier.")
    live_output_status_parser.add_argument("--updated-at", default=None, help="Optional ISO timestamp.")
    live_output_status_parser.add_argument("--source-rollout-path", default=None, help="Optional source rollout path.")

    live_output_reset_parser = live_output_subparsers.add_parser("reset", help="Reset live output state.")
    live_output_reset_parser.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
    live_output_reset_parser.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")

    live_output_show_parser = live_output_subparsers.add_parser("show", help="Show current live output state.")
    live_output_show_parser.add_argument("--host", default=DaemonClient().host, help="Daemon host.")
    live_output_show_parser.add_argument("--port", default=DaemonClient().port, type=int, help="Daemon port.")

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

    if args.command == "observation":
        _handle_observation(args)
        return

    if args.command == "live-output":
        _handle_live_output(args)
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
