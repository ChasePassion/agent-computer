from __future__ import annotations

import asyncio

from agent_computer.mcp_server import build_mcp_server


def test_mcp_server_exposes_persistent_agent_primitives() -> None:
    async def list_names() -> set[str]:
        return {tool.name for tool in await build_mcp_server().list_tools()}

    names = asyncio.run(list_names())

    assert {
        "observe",
        "desktop_act_and_observe",
        "desktop_batch_act_and_observe",
        "browser_assist_locate",
        "browser_assist_observe",
        "browser_assist_act",
        "display_layout",
        "uia_locate",
        "uia_observe",
        "uia_act",
    } <= names
