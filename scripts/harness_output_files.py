"""Resolve deliverable MP4s in an episode Output folder."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness_episode_lib import (
    CLOSING_RE,
    EDITED_RE,
    INTRO_RE,
    INTERVIEW_RE,
    READING_RE,
)
from harness_overwrite_guard import refuse_overwrite

SKIP_READING_PLACEHOLDER_NAME = "Skip Reading Placeholder.mp4"


def _mp4s(output_dir: Path) -> list[Path]:
    return sorted(
        (p for p in output_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"),
        key=lambda p: p.name.lower(),
    )


def find_intro_mp4(output_dir: Path) -> Path:
    exact = output_dir / "Intro.mp4"
    if exact.is_file():
        return exact
    edited_exact = output_dir / "Edited Intro.mp4"
    if edited_exact.is_file():
        return edited_exact
    for path in _mp4s(output_dir):
        if path.name.lower() == "intro.mp4":
            return path
        if path.name.lower() == "edited intro.mp4":
            return path
        # Prefer an Edited Intro export (common DaVinci name) over raw Intro.
        if INTRO_RE.search(path.stem) and EDITED_RE.search(path.stem):
            if READING_RE.search(path.stem) or INTERVIEW_RE.search(path.stem):
                continue
            return path
        if INTRO_RE.search(path.stem) and not EDITED_RE.search(path.stem):
            if READING_RE.search(path.stem) or INTERVIEW_RE.search(path.stem):
                continue
            return path
    raise FileNotFoundError(f"Intro.mp4 not found in {output_dir}")


def find_edited_interview_mp4(output_dir: Path) -> Path:
    exact = output_dir / "Edited Interview.mp4"
    if exact.is_file():
        return exact
    for path in _mp4s(output_dir):
        if EDITED_RE.search(path.stem) and INTERVIEW_RE.search(path.stem):
            return path
    raise FileNotFoundError(f"Edited Interview.mp4 not found in {output_dir}")


def find_edited_reading_mp4(output_dir: Path) -> Path:
    exact = output_dir / "Edited Reading.mp4"
    if exact.is_file():
        return exact
    for path in _mp4s(output_dir):
        if EDITED_RE.search(path.stem) and READING_RE.search(path.stem):
            return path
    raise FileNotFoundError(f"Edited Reading.mp4 not found in {output_dir}")


def find_closing_mp4(output_dir: Path) -> Path:
    exact = output_dir / "Closing.mp4"
    if exact.is_file():
        return exact
    for path in _mp4s(output_dir):
        if CLOSING_RE.search(path.stem):
            return path
    raise FileNotFoundError(f"Closing.mp4 not found in {output_dir}")


def stitch_required_files(output_dir: Path) -> dict[str, Path]:
    return {
        "intro": find_intro_mp4(output_dir),
        "edited_reading": find_edited_reading_mp4(output_dir),
        "edited_interview": find_edited_interview_mp4(output_dir),
        "closing": find_closing_mp4(output_dir),
    }


def _probe_video_audio_props(reference: Path) -> tuple[int, int, float, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,sample_rate",
        "-of",
        "json",
        str(reference),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {reference}:\n{proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    width = height = None
    fps = 30.0
    sample_rate = 48000
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and width is None:
            width = int(stream["width"])
            height = int(stream["height"])
            rate = str(stream.get("r_frame_rate") or "30/1")
            if "/" in rate:
                num, den = rate.split("/", 1)
                fps = float(num) / float(den or 1)
            else:
                fps = float(rate)
        if stream.get("codec_type") == "audio" and stream.get("sample_rate"):
            sample_rate = int(stream["sample_rate"])
    if width is None or height is None:
        raise RuntimeError(f"No video stream found in {reference}")
    return width, height, fps, sample_rate


def generate_black_reading_placeholder(
    reference_video: Path,
    output_path: Path,
    *,
    duration_s: float = 1.0,
) -> Path:
    """Create a short black/silent MP4 for skip_reading stitch (Reading slot)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height, fps, sample_rate = _probe_video_audio_props(reference_video)
    fps_text = f"{fps:.6f}".rstrip("0").rstrip(".")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r={fps_text}:d={duration_s}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={sample_rate}:cl=stereo:d={duration_s}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed creating reading placeholder:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    if not output_path.is_file():
        raise FileNotFoundError(f"Placeholder was not created: {output_path}")
    return output_path


def resolve_stitch_input_files(
    output_dir: Path,
    *,
    skip_reading: bool,
    temp_dir: Path,
    allow_overwrite: bool = False,
) -> dict[str, Path]:
    """
    Resolve the four stitch inputs, using a Temp placeholder when reading is skipped.
    """
    intro = find_intro_mp4(output_dir)
    interview = find_edited_interview_mp4(output_dir)
    closing = find_closing_mp4(output_dir)
    if skip_reading:
        placeholder = temp_dir / SKIP_READING_PLACEHOLDER_NAME
        refuse_overwrite(placeholder, allow_overwrite=allow_overwrite, label=placeholder.name)
        reading = generate_black_reading_placeholder(intro, placeholder)
    else:
        reading = find_edited_reading_mp4(output_dir)
    return {
        "intro": intro,
        "edited_reading": reading,
        "edited_interview": interview,
        "closing": closing,
    }
