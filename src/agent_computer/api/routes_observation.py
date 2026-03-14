from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from agent_computer.actions import mouse_position
from agent_computer.api.deps import get_registry
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(tags=["observation"])


def _normalize_mode(value: str | None, *, default: Literal["preview", "grid"]) -> Literal["preview", "grid"]:
    if value in {"preview", "grid"}:
        return value
    if value is None:
        return default
    raise HTTPException(status_code=400, detail=f"Unsupported observation mode: {value}")


def _normalize_grid_only_mode(value: str | None) -> Literal["grid"]:
    if value in {None, "grid"}:
        return "grid"
    raise HTTPException(status_code=400, detail="AI-facing observation endpoints only support mode=grid.")


def _require_token(
    token: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> str:
    expected = registry.observation.token()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid observation token.")
    return token


@router.get("/live", response_class=HTMLResponse)
def live_page(
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
) -> HTMLResponse:
    initial_mode = _normalize_mode(mode, default="preview")
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Computer Live</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0f1115;
      --panel: #171a21;
      --muted: #a6adbb;
      --text: #eef2f7;
      --accent: #4dd4ac;
      --border: #272d38;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.4 Consolas, "Courier New", monospace;
    }}
    .bar {{
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: rgba(15, 17, 21, 0.92);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(12px);
    }}
    .status {{
      display: flex;
      gap: 14px;
      color: var(--muted);
      flex-wrap: wrap;
    }}
    .controls {{
      display: flex;
      gap: 8px;
    }}
    button {{
      border: 1px solid var(--border);
      background: var(--panel);
      color: var(--text);
      padding: 8px 12px;
      cursor: pointer;
      border-radius: 8px;
    }}
    button.active {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .frame-wrap {{
      padding: 16px;
    }}
    img {{
      display: block;
      width: 100%;
      height: auto;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #0b0d11;
    }}
  </style>
</head>
<body>
  <div class="bar">
    <div class="status">
      <span>Mode: <strong id="mode-label">{initial_mode}</strong></span>
      <span>Updated: <strong id="updated-label">warming up</strong></span>
      <span>Resolution: <strong id="resolution-label">-</strong></span>
      <span>Cursor: <strong id="cursor-label">-</strong></span>
    </div>
    <div class="controls">
      <button id="preview-btn">Preview</button>
      <button id="grid-btn">Grid</button>
    </div>
  </div>
  <div class="frame-wrap">
    <img id="frame" alt="live observation frame">
  </div>
  <script>
    const token = {token!r};
    let mode = {initial_mode!r};
    let lastFrameSeq = -1;
    const frame = document.getElementById("frame");
    const modeLabel = document.getElementById("mode-label");
    const updatedLabel = document.getElementById("updated-label");
    const resolutionLabel = document.getElementById("resolution-label");
    const cursorLabel = document.getElementById("cursor-label");
    const previewBtn = document.getElementById("preview-btn");
    const gridBtn = document.getElementById("grid-btn");

    function updateButtons() {{
      previewBtn.classList.toggle("active", mode === "preview");
      gridBtn.classList.toggle("active", mode === "grid");
      modeLabel.textContent = mode;
    }}

    function latestJsonUrl() {{
      return `/live/frame.json?token=${{encodeURIComponent(token)}}&mode=${{encodeURIComponent(mode)}}`;
    }}

    async function poll() {{
      try {{
        const response = await fetch(latestJsonUrl(), {{ cache: "no-store" }});
        if (!response.ok) {{
          throw new Error(`HTTP ${{response.status}}`);
        }}
        const payload = await response.json();
        updatedLabel.textContent = payload.updated_at || "-";
        resolutionLabel.textContent = `${{payload.desktop_width || payload.width}}x${{payload.desktop_height || payload.height}}`;
        const cursor = payload.mouse_position;
        cursorLabel.textContent = cursor ? `(${{cursor.x}}, ${{cursor.y}})` : "-";
        if (payload.frame_seq !== lastFrameSeq) {{
          frame.src = `${{payload.image_url}}&ts=${{Date.now()}}`;
          lastFrameSeq = payload.frame_seq;
        }}
      }} catch (error) {{
        updatedLabel.textContent = "waiting";
        cursorLabel.textContent = "-";
      }}
    }}

    previewBtn.addEventListener("click", () => {{
      mode = "preview";
      lastFrameSeq = -1;
      updateButtons();
      poll();
    }});

    gridBtn.addEventListener("click", () => {{
      mode = "grid";
      lastFrameSeq = -1;
      updateButtons();
      poll();
    }});

    updateButtons();
    poll();
    setInterval(poll, 1000);
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@router.get("/live/frame.jpg", name="live_observation_image")
def live_image(
    request: Request,
    _: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> FileResponse:
    normalized_mode = _normalize_mode(mode, default="grid")
    try:
        image_path = registry.observation.latest_image_path(normalized_mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/live/frame.json")
def live_json(
    request: Request,
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    normalized_mode = _normalize_mode(mode, default="grid")
    payload = registry.observation.latest(normalized_mode)
    if payload is None:
        raise HTTPException(status_code=503, detail=f"No latest observation frame available for mode: {normalized_mode}")
    image_url = str(
        request.url_for("live_observation_image").include_query_params(
            token=token,
            mode=normalized_mode,
        )
    )
    response_payload = dict(payload)
    response_payload["image_url"] = image_url
    return JSONResponse(content=response_payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("/observation/latest.jpg", name="observation_latest_image")
def latest_image(
    request: Request,
    _: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> FileResponse:
    normalized_mode = _normalize_grid_only_mode(mode)
    try:
        image_path = registry.observation.latest_image_path(normalized_mode)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(
        image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.get("/observation/latest.json")
def latest_json(
    request: Request,
    token: str = Depends(_require_token),
    mode: str | None = Query(default=None),
    registry: ServiceRegistry = Depends(get_registry),
) -> JSONResponse:
    normalized_mode = _normalize_grid_only_mode(mode)
    payload = registry.observation.latest(normalized_mode)
    if payload is None:
        raise HTTPException(status_code=503, detail=f"No latest observation frame available for mode: {normalized_mode}")
    image_url = str(
        request.url_for("observation_latest_image").include_query_params(
            token=token,
            mode=normalized_mode,
        )
    )
    response_payload = dict(payload)
    response_payload["image_url"] = image_url
    return JSONResponse(content=response_payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@router.get("/observation/mouse.json")
def mouse_json(
    _: str = Depends(_require_token),
) -> JSONResponse:
    x, y = mouse_position()
    payload = {
        "x": x,
        "y": y,
        "coordinate_system": "screen-absolute-grid",
        "origin": [0, 0],
    }
    return JSONResponse(content=payload, headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
