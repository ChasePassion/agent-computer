from __future__ import annotations

from pathlib import Path

from PIL import Image

from agent_computer.capture import GRID_LINE_COLOR, RULER_BAND_SIZE, export_live_display_image, zoom
from agent_computer.cli import build_parser
from agent_computer.runtime import zoom_latest_path


def _create_source_image(path: Path, *, size: tuple[int, int]) -> None:
    image = Image.new("RGB", size, color=(240, 240, 240))
    image.save(path, format="PNG")


def test_zoom_generates_absolute_grid_overlay(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "zoom.png"
    _create_source_image(source_path, size=(200, 200))

    result = zoom(
        source_path,
        output_path,
        x=40,
        y=40,
        width=40,
        height=40,
        scale=2,
        padding=20,
        grid_size=50,
        image_format="png",
    )

    assert result.requested_bounds == (40, 40, 80, 80)
    assert result.crop_bounds == (20, 20, 100, 100)
    assert result.width == 304
    assert result.height == 304
    assert result.major_grid_size == 100

    with Image.open(output_path) as zoomed:
        vertical_minor_x = RULER_BAND_SIZE + ((50 - 20) * 2)
        interior_y = RULER_BAND_SIZE + 15
        assert zoomed.getpixel((vertical_minor_x, interior_y)) == GRID_LINE_COLOR


def test_zoom_clamps_padding_to_source_bounds(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "zoom.png"
    _create_source_image(source_path, size=(30, 30))

    result = zoom(
        source_path,
        output_path,
        x=5,
        y=6,
        width=10,
        height=8,
        scale=3,
        padding=20,
        grid_size=50,
        image_format="png",
    )

    assert result.crop_bounds == (0, 0, 30, 30)
    assert result.requested_bounds == (5, 6, 15, 14)


def test_cli_zoom_parser_defaults() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "zoom",
            "--input",
            "artifacts/observation/preview_latest.jpg",
            "--x",
            "1200",
            "--y",
            "430",
            "--width",
            "220",
            "--height",
            "120",
        ]
    )

    assert args.command == "zoom"
    assert args.output == str(zoom_latest_path())
    assert args.scale == 3
    assert args.padding == 20
    assert args.grid_size == 50


def test_export_live_display_image_downsizes_large_image(tmp_path: Path) -> None:
    source_path = tmp_path / "source.jpg"
    output_path = tmp_path / "live.jpg"
    _create_source_image(source_path, size=(3200, 1800))

    export_live_display_image(
        source_path,
        output_path,
        max_dimension=1200,
        jpeg_quality=40,
    )

    with Image.open(output_path) as exported:
        assert exported.format == "JPEG"
        assert exported.width == 1200
        assert exported.height == 675
