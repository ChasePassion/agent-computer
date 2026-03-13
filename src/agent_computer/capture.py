from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import mss
from PIL import Image, ImageDraw, ImageFont
import win32gui

from agent_computer.windowing import find_window

CaptureTarget = Literal["active-window", "primary-screen"]
ImageFormat = Literal["png", "jpeg"]
RULER_BAND_SIZE = 72
RULER_BACKGROUND = (18, 20, 24)
RULER_TEXT_COLOR = (250, 250, 250)
RULER_TICK_COLOR = (255, 96, 96)
GRID_LINE_COLOR = (255, 64, 64)
MAJOR_GRID_LINE_COLOR = (255, 96, 96)
CONTENT_BORDER_COLOR = (255, 96, 96)
LABEL_FONT_SIZE = 26


@dataclass
class CaptureResult:
    image_path: str
    target: str
    width: int
    height: int
    image_format: str
    grid_enabled: bool
    grid_size: int | None = None
    window_title: str | None = None
    window_handle: int | None = None
    bounds: tuple[int, int, int, int] | None = None
    annotation_style: str = "raw"
    ruler_band_size: int | None = None
    major_grid_size: int | None = None
    content_origin: tuple[int, int] | None = None
    content_bounds_in_image: tuple[int, int, int, int] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_ruler_font(size: int = LABEL_FONT_SIZE) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windows_dir / "Fonts" / "consolab.ttf",
        windows_dir / "Fonts" / "consola.ttf",
        windows_dir / "Fonts" / "lucon.ttf",
        windows_dir / "Fonts" / "courbd.ttf",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_band_label(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    center_y: int,
    text: str,
    *,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    draw.text(
        (center_x, center_y),
        text,
        fill=RULER_TEXT_COLOR,
        font=font,
        anchor="mm",
        stroke_width=2,
        stroke_fill=(0, 0, 0),
    )


def _draw_grid(image: Image.Image, grid_size: int, offset_x: int = 0, offset_y: int = 0) -> tuple[Image.Image, dict[str, tuple[int, int] | tuple[int, int, int, int] | int | str]]:
    content = image.convert("RGB")
    content_width, content_height = content.size
    band = RULER_BAND_SIZE
    major_grid_size = max(grid_size * 2, 100)
    annotated = Image.new(
        "RGB",
        (content_width + band * 2, content_height + band * 2),
        color=RULER_BACKGROUND,
    )
    annotated.paste(content, (band, band))

    draw = ImageDraw.Draw(annotated)
    font = _load_ruler_font()
    content_left = band
    content_top = band
    content_right = content_left + content_width
    content_bottom = content_top + content_height

    draw.rectangle(
        [content_left, content_top, content_right - 1, content_bottom - 1],
        outline=CONTENT_BORDER_COLOR,
        width=2,
    )

    for x in range(0, content_width, grid_size):
        image_x = content_left + x
        screen_x = offset_x + x
        is_major_line = screen_x % major_grid_size == 0
        draw.line(
            [(image_x, content_top), (image_x, content_bottom - 1)],
            fill=MAJOR_GRID_LINE_COLOR if is_major_line else GRID_LINE_COLOR,
            width=2 if is_major_line else 1,
        )
        if is_major_line:
            draw.line(
                [(image_x, content_top - 14), (image_x, content_top)],
                fill=RULER_TICK_COLOR,
                width=2,
            )
            draw.line(
                [(image_x, content_bottom - 1), (image_x, content_bottom + 13)],
                fill=RULER_TICK_COLOR,
                width=2,
            )
            label = str(screen_x)
            _draw_band_label(draw, image_x, band // 2, label, font=font)
            _draw_band_label(draw, image_x, content_bottom + band // 2, label, font=font)

    for y in range(0, content_height, grid_size):
        image_y = content_top + y
        screen_y = offset_y + y
        is_major_line = screen_y % major_grid_size == 0
        draw.line(
            [(content_left, image_y), (content_right - 1, image_y)],
            fill=MAJOR_GRID_LINE_COLOR if is_major_line else GRID_LINE_COLOR,
            width=2 if is_major_line else 1,
        )
        if is_major_line:
            draw.line(
                [(content_left - 14, image_y), (content_left, image_y)],
                fill=RULER_TICK_COLOR,
                width=2,
            )
            draw.line(
                [(content_right - 1, image_y), (content_right + 13, image_y)],
                fill=RULER_TICK_COLOR,
                width=2,
            )
            label = str(screen_y)
            _draw_band_label(draw, band // 2, image_y, label, font=font)
            _draw_band_label(draw, content_right + band // 2, image_y, label, font=font)

    return annotated, {
        "annotation_style": "outer-ruler-band",
        "ruler_band_size": band,
        "major_grid_size": major_grid_size,
        "content_origin": (content_left, content_top),
        "content_bounds_in_image": (
            content_left,
            content_top,
            content_right,
            content_bottom,
        ),
    }


def _grab_region(region: dict) -> Image.Image:
    with mss.mss() as sct:
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.rgb)


def _get_primary_monitor_region() -> dict:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        return {
            "left": monitor["left"],
            "top": monitor["top"],
            "width": monitor["width"],
            "height": monitor["height"],
        }


def _get_active_window_region() -> tuple[dict, str | None, int]:
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        raise RuntimeError("No active window found.")

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = max(0, right - left)
    height = max(0, bottom - top)
    if width <= 0 or height <= 0:
        raise RuntimeError("Active window has invalid bounds.")

    region = {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }
    title = win32gui.GetWindowText(hwnd) or None
    return region, title, hwnd


def _get_window_region_by_title(title_query: str, exact: bool) -> tuple[dict, str | None, int]:
    window = find_window(title_query, exact=exact)
    hwnd = window.hwnd
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    width = max(0, right - left)
    height = max(0, bottom - top)
    if width <= 0 or height <= 0:
        raise RuntimeError(f"Window has invalid bounds: {title_query}")

    region = {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }
    return region, window.title, hwnd


def capture(
    output_path: str | Path,
    target: CaptureTarget = "active-window",
    draw_grid: bool = False,
    grid_size: int = 50,
    window_title_query: str | None = None,
    window_exact: bool = False,
    image_format: ImageFormat | None = None,
    jpeg_quality: int = 75,
) -> CaptureResult:
    output = Path(output_path)
    _ensure_parent(output)

    if window_title_query:
        region, title, hwnd = _get_window_region_by_title(window_title_query, exact=window_exact)
        bounds = (
            region["left"],
            region["top"],
            region["left"] + region["width"],
            region["top"] + region["height"],
        )
    elif target == "active-window":
        region, title, hwnd = _get_active_window_region()
        bounds = (
            region["left"],
            region["top"],
            region["left"] + region["width"],
            region["top"] + region["height"],
        )
    else:
        region = _get_primary_monitor_region()
        title = None
        hwnd = None
        bounds = (
            region["left"],
            region["top"],
            region["left"] + region["width"],
            region["top"] + region["height"],
        )

    image = _grab_region(region)
    annotation_style = "raw"
    ruler_band_size: int | None = None
    content_origin: tuple[int, int] | None = None
    content_bounds_in_image: tuple[int, int, int, int] | None = None
    if draw_grid:
        image, annotation_meta = _draw_grid(
            image,
            grid_size=grid_size,
            offset_x=region["left"],
            offset_y=region["top"],
        )
        annotation_style = str(annotation_meta["annotation_style"])
        ruler_band_size = int(annotation_meta["ruler_band_size"])
        content_origin = tuple(annotation_meta["content_origin"])
        content_bounds_in_image = tuple(annotation_meta["content_bounds_in_image"])
    final_format = image_format
    if final_format is None:
        suffix = output.suffix.lower()
        final_format = "jpeg" if suffix in {".jpg", ".jpeg"} else "png"

    save_kwargs: dict = {}
    if final_format == "jpeg":
        if image.mode != "RGB":
            image = image.convert("RGB")
        save_kwargs["format"] = "JPEG"
        save_kwargs["quality"] = jpeg_quality
        save_kwargs["optimize"] = True
    else:
        save_kwargs["format"] = "PNG"

    image.save(output, **save_kwargs)

    return CaptureResult(
        image_path=str(output),
        target=target,
        width=image.width,
        height=image.height,
        image_format=final_format,
        grid_enabled=draw_grid,
        grid_size=grid_size if draw_grid else None,
        window_title=title,
        window_handle=hwnd,
        bounds=bounds,
        annotation_style=annotation_style,
        ruler_band_size=ruler_band_size,
        major_grid_size=int(annotation_meta["major_grid_size"]) if draw_grid else None,
        content_origin=content_origin,
        content_bounds_in_image=content_bounds_in_image,
    )
