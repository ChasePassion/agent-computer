from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_computer.gemini_client import GeminiDesktopOCR
from agent_computer.prompts import DEFAULT_OCR_PROMPT, build_locate_prompt
from agent_computer.runtime import write_json, write_text
from agent_computer.services.capture_service import CaptureService
from agent_computer.services.session_service import SessionService


def _load_prompt(
    *,
    prompt: str | None = None,
    prompt_file: str | None = None,
    target_description: str | None = None,
) -> str:
    if prompt_file:
        return Path(prompt_file).read_text(encoding="utf-8")
    if prompt:
        return prompt
    if target_description:
        return build_locate_prompt(target_description)
    return DEFAULT_OCR_PROMPT


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


class GeminiService:
    def __init__(self, session: SessionService) -> None:
        self.session = session
        self._default_client = GeminiDesktopOCR()

    def _get_client(self, model: str | None = None) -> GeminiDesktopOCR:
        if not model or model == self._default_client.model:
            return self._default_client
        return GeminiDesktopOCR(model=model)

    def analyze_image(
        self,
        *,
        image: str,
        model: str | None = None,
        prompt: str | None = None,
        prompt_file: str | None = None,
        target_description: str | None = None,
        json_output: str | None = None,
        prompt_output: str | None = None,
    ) -> dict[str, Any]:
        effective_prompt = _load_prompt(
            prompt=prompt,
            prompt_file=prompt_file,
            target_description=target_description,
        )
        client = self._get_client(model)
        result = client.analyze_image(image_path=image, prompt=effective_prompt)
        if json_output:
            write_json(json_output, result)
        if prompt_output:
            write_text(prompt_output, result["effective_prompt"])
        self.session.set_last_analysis(result)
        return result

    def capture_and_analyze(
        self,
        *,
        capture_service: CaptureService,
        capture_options: dict[str, Any],
        analysis_options: dict[str, Any],
    ) -> dict[str, Any]:
        capture_payload = capture_service.capture(**capture_options)
        result = self.analyze_image(
            image=capture_payload["image_path"],
            model=analysis_options.get("model"),
            prompt=analysis_options.get("prompt"),
            prompt_file=analysis_options.get("prompt_file"),
            target_description=analysis_options.get("target_description"),
        )
        result["capture"] = capture_payload
        result = _enrich_analysis(result, capture_payload)
        if analysis_options.get("json_output"):
            write_json(analysis_options["json_output"], result)
        if analysis_options.get("prompt_output"):
            write_text(analysis_options["prompt_output"], result["effective_prompt"])
        self.session.set_last_analysis(result)
        return result
