from __future__ import annotations

import time
from pathlib import Path

from agent_computer.runtime import metadata_sidecar_path


def _delete_with_sidecar(image_path: Path) -> None:
    try:
        image_path.unlink(missing_ok=True)
    finally:
        metadata_sidecar_path(image_path).unlink(missing_ok=True)


def cleanup_observation_artifacts(observation_dir: Path) -> int:
    deleted = 0
    if not observation_dir.exists():
        return deleted

    for path in observation_dir.iterdir():
        if not path.is_file():
            continue
        if path.name.endswith(".tmp") or path.name.endswith(".part"):
            path.unlink(missing_ok=True)
            deleted += 1
    return deleted


def cleanup_snapshot_artifacts(
    artifacts_dir: Path,
    *,
    keep_days: int,
    keep_count: int,
) -> int:
    deleted = 0
    if not artifacts_dir.exists():
        return deleted

    candidates: list[Path] = []
    for pattern in ("preview_*.*", "grid_*.*", "capture_*.*"):
        for path in artifacts_dir.glob(pattern):
            if not path.is_file():
                continue
            if path.suffix == ".json":
                continue
            candidates.append(path)

    now = time.time()
    max_age_sec = max(0, keep_days) * 24 * 60 * 60
    fresh_candidates: list[Path] = []

    for path in candidates:
        age = now - path.stat().st_mtime
        if max_age_sec and age > max_age_sec:
            _delete_with_sidecar(path)
            deleted += 1
            continue
        fresh_candidates.append(path)

    fresh_candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    for path in fresh_candidates[keep_count:]:
        _delete_with_sidecar(path)
        deleted += 1
    return deleted
