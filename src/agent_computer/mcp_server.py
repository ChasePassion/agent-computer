from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from mcp.server.fastmcp import FastMCP

from agent_computer.client import DaemonClient
from agent_computer.runtime import observation_token_path, read_json


def build_mcp_server(client: DaemonClient | None = None) -> FastMCP:
    daemon = client or DaemonClient()
    server = FastMCP(
        "agent-computer",
        instructions=(
            "Operate the local Windows computer through verified, session-aware primitives. "
            "Prefer browser_assist_* for web pages, uia_* for native controls, and coordinate actions only as fallback."
        ),
    )

    def observation_token() -> str:
        path = observation_token_path()
        if not path.exists():
            daemon.request("GET", "/system/health")
        payload = read_json(path)
        token = str(payload.get("token") or "").strip()
        if not token:
            raise RuntimeError("Observation token is unavailable after daemon startup.")
        return token

    @server.tool()
    def system_status() -> dict[str, Any]:
        """Return daemon health, current observation state, and Browser Assist state."""
        return {
            "health": daemon.request("GET", "/system/health"),
            "browser_assist": daemon.request("GET", "/browser-assist/status"),
        }

    @server.tool()
    def observe(after_seq: int | None = None, timeout_ms: int = 2000) -> dict[str, Any]:
        """Return the latest coordinate grid metadata, optionally waiting for a newer frame."""
        token = observation_token()
        query: dict[str, Any] = {"mode": "grid"}
        if after_seq is not None:
            query.update({"after_seq": after_seq, "timeout_ms": timeout_ms})
        result = daemon.request(
            "GET",
            f"/observation/latest.json?{urlencode(query)}",
            headers={"X-Agent-Computer-Token": token},
        )
        if isinstance(result, dict):
            result = dict(result)
            result.pop("image_url", None)
        return result

    @server.tool()
    def desktop_act_and_observe(
        action: dict[str, Any],
        preconditions: dict[str, Any] | None = None,
        verify: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute one desktop action and return a guaranteed post-action observation frame."""
        payload: dict[str, Any] = {"action": action}
        if preconditions is not None:
            payload["preconditions"] = preconditions
        if verify is not None:
            payload["verify"] = verify
        return daemon.request("POST", "/actions/act-and-observe", payload)

    @server.tool()
    def desktop_batch_act_and_observe(
        actions: list[dict[str, Any]],
        preconditions: dict[str, Any] | None = None,
        verify: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a short compound desktop action sequence with one post-action capture."""
        payload: dict[str, Any] = {"actions": actions}
        if preconditions is not None:
            payload["preconditions"] = preconditions
        if verify is not None:
            payload["verify"] = verify
        return daemon.request("POST", "/actions/batch-act-and-observe", payload)

    @server.tool()
    def browser_assist_locate(request: dict[str, Any]) -> dict[str, Any]:
        """Locate browser elements through the Browser Assist DOM/CDP layer."""
        return daemon.request("POST", "/browser-assist/locate", request)

    @server.tool()
    def browser_assist_observe(request: dict[str, Any]) -> dict[str, Any]:
        """Observe a previously located browser node reference."""
        return daemon.request("POST", "/browser-assist/observe", request)

    @server.tool()
    def browser_assist_act(request: dict[str, Any]) -> dict[str, Any]:
        """Act on a browser node reference and report explicit verification status."""
        return daemon.request("POST", "/browser-assist/act", request)

    @server.tool()
    def display_layout() -> dict[str, Any]:
        """Return physical-pixel monitor bounds and the current stable layout version."""
        return daemon.request("GET", "/system/display-layout")

    @server.tool()
    def uia_locate(
        window_handle: int,
        locator: dict[str, Any],
        scope: str = "descendants",
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Locate native Windows controls by UI Automation properties inside one window."""
        return daemon.request(
            "POST",
            "/uia/locate",
            {
                "window_handle": window_handle,
                "locator": locator,
                "scope": scope,
                "max_results": max_results,
            },
        )

    @server.tool()
    def uia_observe(node_ref: dict[str, Any]) -> dict[str, Any]:
        """Read current properties for a previously located native UIA element."""
        return daemon.request("POST", "/uia/observe", {"nodeRef": node_ref})

    @server.tool()
    def uia_act(
        node_ref: dict[str, Any],
        action: str,
        value: str | None = None,
        verify: dict[str, Any] | None = None,
        expected_bounds: list[int] | None = None,
        layout_version: str | None = None,
    ) -> dict[str, Any]:
        """Act through a native UIA pattern with optional property verification and layout fencing."""
        payload: dict[str, Any] = {"nodeRef": node_ref, "action": action}
        if value is not None:
            payload["value"] = value
        if verify is not None:
            payload["verify"] = verify
        if expected_bounds is not None:
            payload["expected_bounds"] = expected_bounds
        if layout_version is not None:
            payload["layout_version"] = layout_version
        return daemon.request("POST", "/uia/act", payload)

    return server


def main() -> None:
    build_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
