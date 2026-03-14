from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["browser-assist"])


@router.websocket("/ws/browser-assist")
async def browser_assist_websocket(websocket: WebSocket) -> None:
    registry = websocket.app.state.registry
    token = str(websocket.query_params.get("token") or "").strip()
    expected = registry.browser_assist.token()
    if token != expected:
        await websocket.close(code=1008, reason="Invalid Browser Assist token.")
        return

    manager = registry.browser_assist.connection_manager
    await manager.accept(websocket)

    try:
        while True:
            message = await websocket.receive_json()
            if isinstance(message, dict):
                await manager.handle_message(message)
    except WebSocketDisconnect as exc:
        await manager.disconnect(websocket, reason=f"Browser Assist websocket disconnected ({exc.code}).")
    except Exception as exc:
        await manager.disconnect(websocket, reason=str(exc))
        raise
