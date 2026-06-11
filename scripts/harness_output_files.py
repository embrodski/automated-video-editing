"""Resolve deliverable MP4s in an episode Output folder."""

from __future__ import annotations

import re
from pathlib import Path

INTRO_RE = re.compile(r"\bintro\b", re.IGNORECASE)
READING_RE = re.compile(r"\breading\b", re.IGNORECASE)
INTERVIEW_RE = re.compile(r"\binterview\b", re.IGNORECASE)
EDITED_RE = re.compile(r"\bedited\b", re.IGNORECASE)
CLOSING_RE = re.compile(r"\bclosing\b", re.IGNORECASE)


def _mp4s(output_dir: Path) -> list[Path]:
    return sorted(
        (p for p in output_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"),
        key=lambda p: p.name.lower(),
    )


def find_intro_mp4(output_dir: Path) -> Path:
    exact = output_dir / "Intro.mp4"
    if exact.is_file():
        return exact
    for path in _mp4s(output_dir):
        if path.name.lower() == "intro.mp4":
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
