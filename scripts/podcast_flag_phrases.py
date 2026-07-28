"""Flag phrase detection and final-cut timestamp reporting for podcast DSL."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Sequence

from episode_segments import segments_path
from harness_episode_lib import REPO_ROOT
from podcast_phrase_gates import flag_phrases_from_gates, load_phrase_gates

_SRC = str((REPO_ROOT / "src").resolve())
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

_NORMALIZE_TEXT_RE = re.compile(r"[^a-z0-9\s\-]+")


@dataclass(frozen=True)
class FlagHit:
    """A flag phrase match in source audio time."""

    source_start_sec: float
    matched_phrase: str
    row_id: str
    segment_num: str


def flag_phrases_from_gates_or_defaults(gates: dict[str, Any] | None = None) -> list[str]:
    phrases = flag_phrases_from_gates(gates or load_phrase_gates())
    return phrases


def _normalize_token(text: str) -> str:
    t = text.strip().lower()
    t = t.replace("—", " ").replace("–", " ").replace("-", " ")
    t = _NORMALIZE_TEXT_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokenize_phrase(phrase: str) -> list[str]:
    return [t for t in _normalize_token(phrase).split() if t]


def phrase_token_variants(phrase: str) -> list[list[str]]:
    """
    Token sequences for one configured phrase.

    ``timestamp`` also matches spoken ``time stamp`` as two words.
    """
    base = _tokenize_phrase(phrase)
    if not base:
        return []
    if "timestamp" not in base:
        return [base]
    idx = base.index("timestamp")
    expanded = base[:idx] + ["time", "stamp"] + base[idx + 1 :]
    return [base, expanded]


def _row_words(row: dict) -> list[tuple[str, float, float]]:
    words: list[tuple[str, float, float]] = []
    for w in row.get("words") or []:
        if not isinstance(w, dict):
            continue
        text = str(w.get("text", "") or "").strip()
        if not text:
            continue
        token = _normalize_token(text)
        if not token:
            continue
        try:
            start = float(w.get("start", w.get("start_time")))
            end = float(w.get("end", w.get("end_time")))
        except (TypeError, ValueError):
            continue
        words.append((token, start, end))
    return words


def _token_match_advance(
    words: Sequence[tuple[str, float, float]], i: int, token: str
) -> int:
    if i >= len(words):
        return 0
    if token == "timestamp":
        if words[i][0] == "timestamp":
            return 1
        if i + 1 < len(words) and words[i][0] == "time" and words[i + 1][0] == "stamp":
            return 2
        return 0
    if words[i][0] == token:
        return 1
    return 0


def _phrase_matches_at(
    words: Sequence[tuple[str, float, float]], start: int, tokens: Sequence[str]
) -> bool:
    pos = start
    for token in tokens:
        step = _token_match_advance(words, pos, token)
        if step <= 0:
            return False
        pos += step
    return True


def find_flag_hits_in_row(
    row: dict,
    *,
    row_id: str,
    segment_num: str,
    phrases: Sequence[str],
) -> list[FlagHit]:
    words = _row_words(row)
    if not words:
        return []
    hits: list[FlagHit] = []
    seen: set[tuple[str, float]] = set()
    for phrase in phrases:
        for tokens in phrase_token_variants(phrase):
            for i in range(0, max(0, len(words) - 1)):
                if not _phrase_matches_at(words, i, tokens):
                    continue
                source_start = float(words[i][1])
                key = (row_id, round(source_start, 3))
                if key in seen:
                    break
                seen.add(key)
                hits.append(
                    FlagHit(
                        source_start_sec=source_start,
                        matched_phrase=phrase,
                        row_id=row_id,
                        segment_num=segment_num,
                    )
                )
                break
    hits.sort(key=lambda h: h.source_start_sec)
    return hits


def format_hhmmss(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_flag_timestamp_report(output_times_sec: Sequence[float]) -> str:
    lines = ["Flags Dropped At These Timestamps:"]
    if not output_times_sec:
        lines.append("-none-")
    else:
        for t in sorted(float(x) for x in output_times_sec):
            lines.append(format_hhmmss(t))
    return "\n".join(lines)


def print_flag_timestamp_report(output_times_sec: Sequence[float]) -> None:
    print(format_flag_timestamp_report(output_times_sec), flush=True)


def _ensure_podcast_dsl_env(temp_dir: Path) -> None:
    seg = segments_path(temp_dir)
    if not seg.is_file():
        raise FileNotFoundError(f"segments.json not found: {seg}")
    os.environ["PODCAST_DSL_SEGMENTS_FILE"] = str(seg)
    src = str((REPO_ROOT / "src").resolve())
    if src not in sys.path:
        sys.path.insert(0, src)
    from podcast_dsl.config import load_segments_overlay

    load_segments_overlay(seg)


def scan_dsl_flag_output_times(
    dsl_path: Path,
    temp_dir: Path,
    *,
    flag_phrases: Sequence[str] | None = None,
) -> list[float]:
    """
    Walk segment lines in ``dsl_path`` and map flag phrase hits to output timeline seconds.
    """
    from podcast_dsl.clip_processing import get_clip_info, load_transcript, parse_segment_id
    from podcast_dsl.commands import (
        CutCommand,
        OpeningPrerollCommand,
        SegmentCommand,
    )
    from podcast_dsl.parser import parse_dsl_file

    phrases = list(flag_phrases or flag_phrases_from_gates_or_defaults())
    if not phrases:
        return []

    _ensure_podcast_dsl_env(temp_dir)
    commands = parse_dsl_file(str(dsl_path))

    cut_before_ms = 0.0
    cut_after_ms = 0.0
    opening_preroll_ms: float | None = None
    current_camera = "speaker_0"
    cumulative = 0.0
    clip_index = 0
    output_times: list[float] = []

    for cmd in commands:
        if isinstance(cmd, CutCommand):
            cut_before_ms = float(cmd.before_ms)
            cut_after_ms = float(cmd.after_ms)
            continue
        if isinstance(cmd, OpeningPrerollCommand):
            opening_preroll_ms = float(cmd.preroll_ms)
            continue
        from podcast_dsl.commands import CameraCommand

        if isinstance(cmd, CameraCommand):
            current_camera = cmd.camera_name
            continue
        if not isinstance(cmd, SegmentCommand):
            continue

        segment_num, sentence_id = parse_segment_id(cmd.segment_id)
        config = __import__(
            "podcast_dsl.config", fromlist=["get_segment_config"]
        ).get_segment_config(segment_num)
        transcript = load_transcript(config["transcript_file"])
        row = transcript[sentence_id]
        hits = find_flag_hits_in_row(
            row,
            row_id=str(sentence_id),
            segment_num=str(segment_num),
            phrases=phrases,
        )

        info = get_clip_info(
            cmd.segment_id,
            current_camera,
            cmd.slice_start,
            cmd.slice_end,
            margin=0.0,
        )
        playback_start = float(info["audio_start"])
        playback_end = float(info["audio_end"])
        if clip_index == 0 and opening_preroll_ms is not None:
            opening_lead_in = max(cut_before_ms / 1000.0, opening_preroll_ms / 1000.0)
            playback_start = max(0.0, playback_start - opening_lead_in)

        duration = playback_end - playback_start
        if duration <= 0:
            clip_index += 1
            continue

        for hit in hits:
            t = float(hit.source_start_sec)
            if t + 1e-6 < playback_start or t > playback_end + 1e-6:
                continue
            output_times.append(cumulative + (t - playback_start))

        cumulative += duration
        cumulative += cut_after_ms / 1000.0
        clip_index += 1

    # Stable order, allow multiple flags in the same second.
    output_times.sort()
    return output_times


def report_flag_timestamps_after_render(
    dsl_path: Path,
    temp_dir: Path,
    *,
    state: dict | None = None,
    write_report_file: bool = True,
) -> dict[str, Any]:
    """
    Scan ``dsl_path``, print the user-facing report, optionally write Temp copy.
    """
    phrases = flag_phrases_from_gates_or_defaults(
        load_phrase_gates(state_overrides=state or {})
    )
    times = scan_dsl_flag_output_times(dsl_path, temp_dir, flag_phrases=phrases)
    report_text = format_flag_timestamp_report(times)
    print_flag_timestamp_report(times)

    report_path: Path | None = None
    if write_report_file:
        report_path = temp_dir / "interview-flag-timestamps.txt"
        report_path.write_text(report_text + "\n", encoding="utf-8")

    return {
        "flag_phrases": phrases,
        "flag_timestamps_sec": times,
        "flag_timestamps_hhmmss": [format_hhmmss(t) for t in times],
        "flag_report": report_text,
        "flag_report_file": str(report_path) if report_path else None,
    }
