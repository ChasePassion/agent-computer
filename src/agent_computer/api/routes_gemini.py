from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_computer.api.deps import get_registry
from agent_computer.models.requests import AnalyzeRequest
from agent_computer.services.registry import ServiceRegistry

router = APIRouter(prefix="/gemini", tags=["gemini"])


@router.post("/ocr")
def ocr(request: AnalyzeRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.gemini.analyze_image(
            image=request.image,
            model=request.model,
            prompt=request.prompt,
            prompt_file=request.prompt_file,
            target_description=request.target_description,
            json_output=request.json_output,
            prompt_output=request.prompt_output,
        )


@router.post("/locate")
def locate(request: AnalyzeRequest, registry: ServiceRegistry = Depends(get_registry)) -> dict:
    with registry.execution_lock:
        return registry.gemini.analyze_image(
            image=request.image,
            model=request.model,
            prompt=request.prompt,
            prompt_file=request.prompt_file,
            target_description=request.target_description,
            json_output=request.json_output,
            prompt_output=request.prompt_output,
        )
