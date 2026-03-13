from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import CaptureGridRequest, CaptureOcrRequest, CapturePreviewRequest, CaptureRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/capture", tags=["capture"])


@router.post("")
def capture(request: CaptureRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.capture.capture(
            output=request.output,
            target=request.target,
            window_title=request.window_title,
            window_exact=request.window_exact,
            grid=request.grid,
            grid_size=request.grid_size,
            image_format=request.format,
            jpeg_quality=request.jpeg_quality,
        )


@router.post("/preview")
def capture_preview(
    request: CapturePreviewRequest,
    registry: ServiceRegistry = Depends(get_registry),
) -> dict:
    with registry.execution_lock:
        return registry.capture.capture_preview(
            output=request.output,
            jpeg_quality=request.jpeg_quality,
        )


@router.post("/grid")
def capture_grid(request: CaptureGridRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.capture.capture_grid(
            output=request.output,
            grid_size=request.grid_size,
            jpeg_quality=request.jpeg_quality,
        )


@router.post("/ocr")
def capture_ocr(request: CaptureOcrRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        capture_options = {
            "output": request.output,
            "target": request.target,
            "window_title": request.window_title,
            "window_exact": request.window_exact,
            "grid": request.grid,
            "grid_size": request.grid_size,
            "image_format": request.format,
            "jpeg_quality": request.jpeg_quality,
        }
        analysis_options = {
            "model": request.model,
            "prompt": request.prompt,
            "prompt_file": request.prompt_file,
            "target_description": request.target_description,
            "json_output": request.json_output,
            "prompt_output": request.prompt_output,
        }
        return registry.gemini.capture_and_analyze(
            capture_service=registry.capture,
            capture_options=capture_options,
            analysis_options=analysis_options,
        )
