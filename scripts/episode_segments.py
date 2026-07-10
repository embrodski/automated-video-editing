"""Per-episode segment config in Temp/segments.json (harness + manual autocut)."""

from __future__ import annotations

import json
from pathlib import Path

SEGMENTS_FILENAME = "segments.json"
MAIN_SEGMENT_KEY = "main"
READING_SEGMENT_KEY = "reading"


def segments_path(temp_dir: Path) -> Path:
    return temp_dir.resolve() / SEGMENTS_FILENAME


def load_segments_file(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Segments file must be a JSON object: {path}")
    return {str(key): dict(value) for key, value in data.items() if isinstance(value, dict)}


def save_segments_file(path: Path, segments: dict[str, dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(segments, fh, indent=2)
        fh.write("\n")
    return path


def upsert_segment(
    temp_dir: Path,
    key: str,
    entry: dict,
    *,
    allow_overwrite: bool = False,
) -> Path:
    """
    Merge one segment entry into ``<temp_dir>/segments.json``.

    Raises ``FileExistsError`` when the key already exists and ``allow_overwrite`` is false.
    """
    path = segments_path(temp_dir)
    segments = load_segments_file(path) if path.is_file() else {}
    if key in segments and not allow_overwrite:
        raise FileExistsError(
            f"Segment {key!r} already exists in {path}. "
            "Get user approval, then re-run with --allow-overwrite."
        )
    normalized = dict(entry)
    if "enable_color_match" not in normalized:
        normalized["enable_color_match"] = False
    segments[key] = normalized
    return save_segments_file(path, segments)


def podcast_dsl_env_for_segments(temp_dir: Path) -> dict[str, str]:
    """Environment variables for subprocesses that invoke ``python -m podcast_dsl``."""
    import os

    env = os.environ.copy()
    path = segments_path(temp_dir)
    if path.is_file():
        env["PODCAST_DSL_SEGMENTS_FILE"] = str(path)
    return env


def podcast_dsl_segments_args(temp_dir: Path) -> list[str]:
    """CLI args for ``python -m podcast_dsl`` when ``segments.json`` exists."""
    path = segments_path(temp_dir)
    if not path.is_file():
        return []
    return ["--segments-file", str(path)]
