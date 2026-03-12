from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

from agent_computer.prompts import DEFAULT_OCR_PROMPT, build_coordinate_rules_prompt, compose_prompt
from agent_computer.schemas import ScreenAnalysis

DEFAULT_MODEL = "gemini-3.1-pro-preview"
DEFAULT_TIMEOUT_MS = 180_000
DEFAULT_RETRIES = 3
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _maybe_parse_json(text: str) -> dict[str, Any] | None:
    cleaned = _strip_code_fences(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None


def _sidecar_metadata_path(image_path: Path) -> Path:
    return Path(str(image_path) + ".meta.json")


def _load_image_metadata(image_path: Path) -> dict[str, Any]:
    metadata_path = _sidecar_metadata_path(image_path)
    if metadata_path.exists():
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


class GeminiDesktopOCR:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "Missing GEMINI_API_KEY. Put it in .env or your environment variables."
            )
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        timeout_ms_raw = os.getenv("GEMINI_TIMEOUT_MS")
        try:
            self.timeout_ms = int(timeout_ms_raw) if timeout_ms_raw else DEFAULT_TIMEOUT_MS
        except ValueError as exc:
            raise RuntimeError("GEMINI_TIMEOUT_MS must be an integer number of milliseconds.") from exc
        retries_raw = os.getenv("GEMINI_RETRIES")
        try:
            self.retries = int(retries_raw) if retries_raw else DEFAULT_RETRIES
        except ValueError as exc:
            raise RuntimeError("GEMINI_RETRIES must be an integer.") from exc
        if self.retries < 1:
            raise RuntimeError("GEMINI_RETRIES must be at least 1.")

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(timeout=self.timeout_ms),
        )

    def analyze_image(
        self,
        image_path: str | Path,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        path = Path(image_path)
        data = path.read_bytes()
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        task_prompt = prompt or DEFAULT_OCR_PROMPT
        with Image.open(path) as image:
            image_width, image_height = image.size

        metadata = _load_image_metadata(path)
        coordinate_prompt = build_coordinate_rules_prompt(
            image_width=image_width,
            image_height=image_height,
            bounds=metadata.get("bounds"),
            grid_enabled=bool(metadata.get("grid_enabled", False)),
            grid_size=metadata.get("grid_size"),
            annotation_style=metadata.get("annotation_style"),
            ruler_band_size=metadata.get("ruler_band_size"),
            content_origin=metadata.get("content_origin"),
            content_bounds_in_image=metadata.get("content_bounds_in_image"),
        )
        final_prompt = compose_prompt(task_prompt, coordinate_prompt)
        last_error: Exception | None = None
        errors: list[str] = []
        response = None

        for attempt in range(1, self.retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Part.from_bytes(data=data, mime_type=mime_type),
                        final_prompt,
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_json_schema=ScreenAnalysis.model_json_schema(),
                        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
                        temperature=0,
                    ),
                )
                break
            except Exception as exc:
                last_error = exc
                errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt < self.retries:
                    time.sleep(min(attempt, 3))

        if response is None:
            raise RuntimeError(
                "Gemini image analysis failed after retries.\n" + "\n".join(errors)
            ) from last_error

        text = response.text or ""
        parsed = _maybe_parse_json(text)
        if parsed is None and getattr(response, "parsed", None):
            maybe_parsed = response.parsed
            if isinstance(maybe_parsed, dict):
                parsed = maybe_parsed
            elif hasattr(maybe_parsed, "model_dump"):
                parsed = maybe_parsed.model_dump()

        return {
            "model": self.model,
            "timeout_ms": self.timeout_ms,
            "retries": self.retries,
            "attempts_used": len(errors) + 1,
            "errors": errors,
            "image_path": str(path),
            "image_width": image_width,
            "image_height": image_height,
            "image_metadata": metadata,
            "effective_prompt": final_prompt,
            "raw_text": text,
            "parsed_json": parsed,
        }
