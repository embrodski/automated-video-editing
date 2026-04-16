#!/usr/bin/env python3
"""
Generate a full sequential DSL file from a simplified transcript JSON.

Example:
  python generate_full_dsl.py Wide_Video_Interview_Audio_Copy_eng_simplified.json \
      --segment 1 \
      --output podcast_sequences/interview_full.dsl

By default this generator:
- Outputs one `$segmentN/id` line per transcript row
- Adds `!camera ...` commands based on `speaker_id` (0 -> speaker_0, 1 -> speaker_1)
- Applies the core rule: **dense cuts → force wide**
  If there would be more than one camera cut in any rolling 5-second window, it replaces
  that region with a single `!camera wide` span (sentence-aligned, at least 5 seconds),
  extending the wide span if another cut would happen within 5 seconds.

Use `--no-cameras` to reproduce the legacy behavior (no `!camera` lines, no wide rule).
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CAM_BY_SPEAKER_ID = {
    0: "speaker_0",
    1: "speaker_1",
}


@dataclass(frozen=True)
class Row:
    idx: int
    start: float
    end: float
    text: str
    speaker_id: int
    speaker_name: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a sequential DSL file from a simplified transcript."
    )
    parser.add_argument("transcript_json", help="Path to simplified transcript JSON")
    parser.add_argument(
        "--segment",
        required=True,
        help="Segment number to use in generated DSL entries, e.g. 1",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output DSL file",
    )
    parser.add_argument(
        "--max-start",
        type=float,
        default=None,
        help="Include only transcript rows with start_time < seconds",
    )
    parser.add_argument(
        "--no-cameras",
        action="store_true",
        help="Do not emit !camera lines (legacy output). Disables dense-cuts-wide too.",
    )
    parser.add_argument(
        "--wide-camera",
        default="wide",
        help='Camera name for forced wide spans (default: "wide")',
    )
    parser.add_argument(
        "--cut-window-sec",
        type=float,
        default=5.0,
        help="Rolling window size in seconds for dense-cuts-wide (default: 5.0)",
    )
    parser.add_argument(
        "--min-wide-sec",
        type=float,
        default=5.0,
        help="Minimum wide span duration in seconds (default: 5.0)",
    )
    return parser.parse_args()


def _load_rows(transcript: Dict[str, Dict]) -> List[Row]:
    keys = sorted(transcript.keys(), key=int)
    rows: List[Row] = []
    for k in keys:
        v = transcript[k]
        rows.append(
            Row(
                idx=int(k),
                start=float(v.get("start", 0.0)),
                end=float(v.get("end", 0.0)),
                text=str(v.get("text", "")),
                speaker_id=int(v.get("speaker_id", 0)),
                speaker_name=str(v.get("speaker_name", "") or ""),
            )
        )
    return rows


def _intended_camera(rows: List[Row]) -> List[str]:
    return [CAM_BY_SPEAKER_ID.get(r.speaker_id, "speaker_0") for r in rows]


def _camera_cut_boundaries(rows: List[Row], cams: List[str]) -> List[Tuple[float, int]]:
    cuts: List[Tuple[float, int]] = []
    for i in range(1, len(rows)):
        if cams[i] != cams[i - 1]:
            cuts.append((rows[i].start, i))
    return cuts


def _find_wide_spans(
    rows: List[Row],
    cams: List[str],
    window_sec: float,
    min_wide_sec: float,
) -> List[Tuple[int, int]]:
    cuts = _camera_cut_boundaries(rows, cams)
    if len(cuts) < 2:
        return []

    spans: List[Tuple[int, int]] = []
    k = 0
    while k < len(cuts) - 1:
        t0, i0 = cuts[k]
        t1, _ = cuts[k + 1]
        if (t1 - t0) >= window_sec:
            k += 1
            continue

        # Dense cutting detected: start wide at the first cut boundary.
        start_idx = i0
        start_time = rows[start_idx].start

        # End wide at the first sentence boundary that makes the span >= min_wide_sec.
        end_idx = start_idx + 1
        while end_idx < len(rows) and (rows[end_idx].start - start_time) < min_wide_sec:
            end_idx += 1
        if end_idx > len(rows):
            end_idx = len(rows)

        # Extension exception: if another cut would happen within window_sec of the end boundary,
        # extend to that cut boundary; repeat until no such cut exists.
        while True:
            end_time = rows[end_idx].start if end_idx < len(rows) else rows[-1].end
            next_cut: Optional[Tuple[float, int]] = None
            for tc, ic in cuts:
                # strictly after the current boundary to avoid infinite loops
                if ic > end_idx:
                    next_cut = (tc, ic)
                    break
            if next_cut is None:
                break
            tc, ic = next_cut
            if (tc - end_time) < window_sec:
                end_idx = ic
                continue
            break

        # Merge overlaps/adjacent.
        if spans and start_idx <= spans[-1][1]:
            ps, pe = spans[-1]
            spans[-1] = (ps, max(pe, end_idx))
        else:
            spans.append((start_idx, end_idx))

        # Advance past cuts inside this span.
        while k < len(cuts) and cuts[k][1] < end_idx:
            k += 1

    return [(s, e) for (s, e) in spans if 0 <= s < e <= len(rows)]


def _spans_to_override_map(spans: List[Tuple[int, int]]) -> Dict[int, int]:
    m: Dict[int, int] = {}
    for s, e in spans:
        for i in range(s, e):
            m[i] = e
    return m


def main() -> int:
    args = parse_args()

    transcript_path = Path(args.transcript_json)
    output_path = Path(args.output)

    with transcript_path.open("r", encoding="utf-8") as f:
        transcript = json.load(f)

    segment_num = str(args.segment)
    rows = _load_rows(transcript)
    if args.max_start is not None:
        rows = [r for r in rows if r.start < float(args.max_start)]
    lines: List[str] = []

    if args.no_cameras:
        for r in rows:
            text = r.text.strip().replace("\n", " ")
            speaker_name = r.speaker_name
            comment = f" // {speaker_name}: {text}" if speaker_name else f" // {text}"
            lines.append(f"$segment{segment_num}/{r.idx}{comment}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {len(lines)} DSL lines to {output_path}")
        return 0

    cams = _intended_camera(rows)
    spans = _find_wide_spans(
        rows,
        cams,
        window_sec=float(args.cut_window_sec),
        min_wide_sec=float(args.min_wide_sec),
    )
    override_map = _spans_to_override_map(spans)

    lines.append("// Generated DSL")
    lines.append(f"// segment{segment_num} | Speaker 0 -> speaker_0, Speaker 1 -> speaker_1")
    lines.append(
        f"// Wide rule: if >1 camera cut in {float(args.cut_window_sec):.1f}s, force !camera {args.wide_camera} "
        f"for >= {float(args.min_wide_sec):.1f}s (sentence-aligned), extend if another cut within {float(args.cut_window_sec):.1f}s"
    )
    lines.append("")

    current_cam: Optional[str] = None
    i = 0
    while i < len(rows):
        r = rows[i]
        if i in override_map:
            end_i = override_map[i]
            if current_cam != args.wide_camera:
                lines.append(f"!camera {args.wide_camera}")
                current_cam = args.wide_camera

            for j in range(i, end_i):
                rr = rows[j]
                speaker_name = rr.speaker_name
                who = speaker_name if speaker_name else ("Speaker 0" if rr.speaker_id == 0 else "Speaker 1")
                text = rr.text.strip().replace("\n", " ")
                lines.append(f"$segment{segment_num}/{rr.idx} // {who}: {text}")

            # Return to intended camera for the first sentence after the wide span.
            i = end_i
            if i < len(rows):
                next_cam = cams[i]
                if current_cam != next_cam:
                    lines.append(f"!camera {next_cam}")
                    current_cam = next_cam
            continue

        intended = cams[i]
        if current_cam != intended:
            lines.append(f"!camera {intended}")
            current_cam = intended

        speaker_name = r.speaker_name
        who = speaker_name if speaker_name else ("Speaker 0" if r.speaker_id == 0 else "Speaker 1")
        text = r.text.strip().replace("\n", " ")
        lines.append(f"$segment{segment_num}/{r.idx} // {who}: {text}")
        i += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {len(rows)} DSL lines to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
