#!/usr/bin/env python3
"""
Post-process a generated reading.dsl: compress silence gaps of at least
--min-silence-sec between consecutive spoken tokens (word timestamps when
available; otherwise the whole subclip range) by ending the outgoing side at
(last_word_end + tail_sec) and starting the incoming side at (next_word_start -
lead_sec). Every such edit forces a camera change at the cut; if the incoming
camera is the side camera, side→front rules are re-applied per span via
``generate_reading_dsl.apply_inter_word_silence_shorten`` (same as ``--shorten`` there).

Typical use (from repo root, after generate_reading_dsl.py):

  python shorten_reading_dsl_silences.py path/to/reading.dsl --segment 14
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent
_SRC = _REPO_ROOT / "src"
for _p in (_REPO_ROOT, _SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from podcast_dsl.commands import (
    CameraCommand,
    CutCommand,
    OpeningPrerollCommand,
    SegmentCommand,
    ShortenJoinCommand,
)
from podcast_dsl.parser import parse_dsl_line

from generate_reading_dsl import (  # noqa: E402
    SubClip,
    TranscriptRow,
    apply_inter_word_silence_shorten,
    emit_subclip_lines,
    load_transcript,
)


def _parse_dsl_commands(filepath: Path) -> list:
    commands = []
    with filepath.open(encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            try:
                cmd = parse_dsl_line(line)
                if cmd:
                    commands.append(cmd)
            except Exception as e:
                raise ValueError(f"Error parsing line {line_num}: {e}") from e
    return commands


def _dsl_header_lines(commands: list) -> Tuple[Optional[float], Optional[Tuple[float, float]]]:
    """Return (!opening ms, (before_ms, after_ms) from !cut) if present."""
    opening_ms: Optional[float] = None
    cut_pair: Optional[Tuple[float, float]] = None
    for cmd in commands:
        if isinstance(cmd, OpeningPrerollCommand):
            opening_ms = cmd.preroll_ms
        if isinstance(cmd, CutCommand):
            cut_pair = (cmd.before_ms, cmd.after_ms)
    return opening_ms, cut_pair


def _commands_to_subclips(
    commands: list,
    rows_by_idx: dict[int, TranscriptRow],
    default_front: str,
    default_side: str,
) -> Tuple[List[SubClip], str]:
    """Rebuild SubClip list from DSL segment + camera lines."""
    current_cam: Optional[str] = None
    segment_num: Optional[str] = None
    subclips: List[SubClip] = []
    pending_shorten_join = False

    for cmd in commands:
        if isinstance(cmd, ShortenJoinCommand):
            pending_shorten_join = True
            continue
        if isinstance(cmd, CameraCommand):
            current_cam = cmd.camera_name
            continue
        if not isinstance(cmd, SegmentCommand):
            continue

        m = re.match(r"segment(\d+)/(\d+)", cmd.segment_id.strip(), re.I)
        if not m:
            raise ValueError(f"Unrecognized segment id: {cmd.segment_id!r}")
        segment_num = m.group(1)
        row_idx = int(m.group(2))
        if row_idx not in rows_by_idx:
            raise KeyError(f"Row {row_idx} not in transcript while parsing {cmd.segment_id}")

        row = rows_by_idx[row_idx]
        if current_cam is None:
            current_cam = default_front

        a = row.start + (cmd.slice_start or 0.0)
        if cmd.slice_end is not None:
            b = row.start + cmd.slice_end
        else:
            b = row.end
        subclips.append(
            SubClip(
                row=row,
                a=a,
                b=b,
                cam=current_cam,
                shorten_join_before=pending_shorten_join,
            )
        )
        pending_shorten_join = False

    if segment_num is None:
        raise ValueError("No segment commands found in DSL")
    return subclips, segment_num


def _emit_reading_dsl(
    subclips: List[SubClip],
    segment_num: str,
    front: str,
    side: str,
    opening_ms: float,
    cut_before_ms: float,
    cut_after_ms: float,
) -> str:
    lines: List[str] = []
    lines.append(f"// Generated reading DSL (segment {segment_num}) — silence-shortened")
    lines.append(f"// Cameras: {front} (front) / {side} (side)")
    lines.append("")
    lines.append(f"!opening {opening_ms:g}")
    lines.append("")
    lines.append(f"!cut {cut_before_ms:g} {cut_after_ms:g}")
    lines.append("")
    current_camera_ref: List[Optional[str]] = [None]
    emit_subclip_lines(subclips, segment_num, current_camera_ref, lines)
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("dsl", type=Path, help="Path to reading.dsl")
    p.add_argument("--segment", help="Segment number (if omitted, inferred from first $segmentN/...)")
    p.add_argument("--transcript", type=Path, help="Simplified transcript JSON (default: from SEGMENT_CONFIG)")
    p.add_argument("--output", type=Path, help="Output DSL path (default: overwrite input)")
    p.add_argument("--front-camera", default="speaker_0")
    p.add_argument("--side-camera", default="speaker_1")
    p.add_argument("--min-silence-sec", type=float, default=3.0)
    p.add_argument("--tail-sec", type=float, default=1.5, help="Keep this much audio after last word before gap")
    p.add_argument("--lead-sec", type=float, default=1.5, help="Start next clip this many seconds before next word")
    p.add_argument("--side-shot-max-sec", type=float, default=12.0)
    args = p.parse_args()

    dsl_path: Path = args.dsl
    commands = _parse_dsl_commands(dsl_path)
    opening_ms, cut_pair = _dsl_header_lines(commands)
    if opening_ms is None:
        opening_ms = 1000.0
    if cut_pair is None:
        cut_pair = (0.0, 0.0)

    # Infer segment from first segment command
    seg_from_file: Optional[str] = None
    for cmd in commands:
        if isinstance(cmd, SegmentCommand):
            m = re.match(r"segment(\d+)/", cmd.segment_id.strip(), re.I)
            if m:
                seg_from_file = m.group(1)
                break
    segment_num = args.segment or seg_from_file
    if not segment_num:
        raise SystemExit("Could not determine segment number; pass --segment")

    transcript_path: Path
    if args.transcript is not None:
        transcript_path = args.transcript
    else:
        from podcast_dsl.config import SEGMENT_CONFIG

        if segment_num not in SEGMENT_CONFIG:
            raise SystemExit(f"Segment {segment_num} not in SEGMENT_CONFIG; pass --transcript")
        transcript_path = Path(SEGMENT_CONFIG[segment_num]["transcript_file"])

    rows = load_transcript(transcript_path)
    rows_by_idx = {r.idx: r for r in rows}

    subclips, seg2 = _commands_to_subclips(
        commands, rows_by_idx, args.front_camera, args.side_camera
    )
    if seg2 != segment_num:
        print(f"Warning: segment in file ({seg2}) != requested ({segment_num}); using file value {seg2}")
        segment_num = seg2

    apply_inter_word_silence_shorten(
        subclips,
        front_cam=args.front_camera,
        side_cam=args.side_camera,
        min_silence_sec=args.min_silence_sec,
        compress_tail_sec=args.tail_sec,
        compress_lead_sec=args.lead_sec,
        side_shot_max_sec=args.side_shot_max_sec,
    )

    text = _emit_reading_dsl(
        subclips,
        segment_num,
        args.front_camera,
        args.side_camera,
        opening_ms,
        cut_pair[0],
        cut_pair[1],
    )

    out_path = args.output or dsl_path
    out_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote silence-shortened DSL to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
