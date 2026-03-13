GRID_RULES_PROMPT = """
Coordinate system rules:
- Coordinates must use the tool's real screen coordinate system.
- Screen coordinates always mean: top-left is (0, 0), x increases to the right, y increases downward.
- If the image includes outer ruler bands, those bands are only annotations and are not part of the returned coordinate system.
- If a red coordinate grid is visible:
  - thin grid lines may appear every 50px
  - emphasized major grid lines appear every 100px
  - only the emphasized major grid lines are labeled
  - each vertical label is the exact x coordinate of that major line
  - each horizontal label is the exact y coordinate of that major line
  - unlabeled intermediate 50px grid lines are still valid for estimating precise coordinates
  - use the labeled 100px lines and the unlabeled 50px intermediate lines directly instead of inventing your own scaling or spacing
- Return both `bbox` and `click_point` when an element is actionable.
- `click_point` should be the preferred single pixel target to click.
""".strip()


DEFAULT_OCR_TASK_PROMPT = """
You are a Windows desktop OCR and GUI understanding assistant.

Rules:
- Do not invent text that is not visible.
- If you are uncertain, lower confidence and say so in reason.
- Return only data that fits the provided JSON schema. No markdown fences.
- Prefer elements that are actionable or visually central.
- Keep `screen_text` concise and deduplicated.
""".strip()


def compose_prompt(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


DEFAULT_OCR_PROMPT = compose_prompt(DEFAULT_OCR_TASK_PROMPT, GRID_RULES_PROMPT)


def build_coordinate_rules_prompt(
    image_width: int,
    image_height: int,
    *,
    bounds: list[int] | tuple[int, int, int, int] | None = None,
    grid_enabled: bool = False,
    grid_size: int | None = None,
    major_grid_size: int | None = None,
    annotation_style: str | None = None,
    ruler_band_size: int | None = None,
    content_origin: list[int] | tuple[int, int] | None = None,
    content_bounds_in_image: list[int] | tuple[int, int, int, int] | None = None,
) -> str:
    bottom_right_x = max(0, image_width - 1)
    bottom_right_y = max(0, image_height - 1)
    annotation_label = annotation_style or "raw"

    lines = [
        "Coordinate system contract:",
        f"- The screenshot image is {image_width}px wide and {image_height}px tall.",
        f"- The annotation style is `{annotation_label}`.",
        "- The top-left image pixel is exactly (0, 0).",
        f"- The bottom-right pixel of this screenshot is exactly ({bottom_right_x}, {bottom_right_y}).",
        "- All returned `bbox` and `click_point` values must strictly use real screen coordinates, not annotated image-border pixels.",
        "- Do not rescale, normalize, infer icon spacing, or invent a different coordinate system.",
    ]

    if bounds and len(bounds) == 4:
        left, top, right, bottom = bounds
        screen_width = max(0, right - left)
        screen_height = max(0, bottom - top)
        lines.append(
            f"- Screenshot bounds metadata: left={left}, top={top}, right={right}, bottom={bottom}."
        )
        lines.append(
            f"- The real captured screen/content area is {screen_width}px wide and {screen_height}px tall."
        )
        if left == 0 and top == 0:
            lines.append("- This screenshot is a full-screen capture of the real display.")
        lines.append(
            f"- The real screen/content coordinate range is x={left}..{max(left, right - 1)} and y={top}..{max(top, bottom - 1)}."
        )

    if content_origin and len(content_origin) == 2:
        content_left, content_top = content_origin
        lines.append(
            f"- The inner screenshot content starts at image pixel ({content_left}, {content_top})."
        )

    if content_bounds_in_image and len(content_bounds_in_image) == 4:
        content_left, content_top, content_right, content_bottom = content_bounds_in_image
        lines.append(
            "- The inner screenshot content rectangle in image pixels is "
            f"({content_left}, {content_top}) to ({content_right - 1}, {content_bottom - 1})."
        )
        if bounds and len(bounds) == 4:
            left, top, right, bottom = bounds
            lines.append(
                f"- Image pixel ({content_left}, {content_top}) corresponds to real screen coordinate ({left}, {top})."
            )
            lines.append(
                f"- Image pixel ({content_right - 1}, {content_bottom - 1}) corresponds to real screen coordinate ({right - 1}, {bottom - 1})."
            )

    if ruler_band_size:
        lines.append(f"- The outer ruler band thickness is {ruler_band_size}px on each side.")

    if grid_enabled:
        interval = grid_size if grid_size is not None else "unknown"
        major_interval = major_grid_size if major_grid_size is not None else "unknown"
        lines.extend(
            [
                f"- A red fine grid is visible and adjacent grid lines are spaced every {interval}px.",
                f"- Emphasized major grid lines appear every {major_interval}px.",
                "- Only the emphasized major grid lines are labeled on the ruler band.",
                "- Each vertical major-line label is the exact x coordinate of that major line.",
                "- Each horizontal major-line label is the exact y coordinate of that major line.",
                "- The unlabeled intermediate 50px grid lines are still real coordinate guides and can be used to estimate precise positions between labeled major lines.",
                "- When grid labels are visible, they override any visual guesswork.",
                "- Use the labels, major-line intersections, and intermediate 50px grid lines directly; do not estimate coordinates from neighboring icon spacing.",
            ]
        )
    else:
        lines.append("- No coordinate grid is visible in this screenshot.")

    lines.extend(
        [
            "- If the target is actionable, return both `bbox` and `click_point`.",
            "- `click_point` must be the single best pixel to click.",
        ]
    )

    return "\n".join(lines)


def build_locate_prompt(target: str) -> str:
    locate_task_prompt = f"""
You are locating a target on a Windows desktop screenshot.

Target:
{target}

Rules:
- Return the most relevant actionable element for the target with a precise `click_point`.
- Prefer one best match over many weak guesses.
- If the target is not visible, return an empty `elements` list and explain why in `summary`.
- Return only data that fits the provided JSON schema. No markdown fences.
""".strip()
    return compose_prompt(locate_task_prompt, GRID_RULES_PROMPT)
