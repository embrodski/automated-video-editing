#!/usr/bin/env python3
"""
Generate a podcast_dsl timeline from a simplified transcript JSON.

Adds an optional "dense cuts -> wide" rule:
- Define "cut" as a camera change (speaker_0 <-> speaker_1) at a sentence boundary.
- If there would be >1 cut within any rolling 3-second window (i.e. at least two cuts less
  than 3 seconds apart), replace that region with a single wide shot.
- Wide spans are sentence-aligned and must last at least 3 seconds.
- After wide ends, return to the intended camera of the first sentence after the span.
- Exception: if there's another cut within 3 seconds of the wide span end, extend the wide
  to that cut boundary; repeat until no such cut exists.
"""

from __future__ import annotations

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


def _load_rows(path: Path) -> List[Row]:
    data: Dict[str, Dict] = json.loads(path.read_text(encoding="utf-8"))
    keys = sorted(data.keys(), key=int)
    rows: List[Row] = []
    for k in keys:
        v = data[k]
        rows.append(
            Row(
                idx=int(k),
                start=float(v["start"]),
                end=float(v["end"]),
                text=str(v.get("text", "")),
                speaker_id=int(v.get("speaker_id", 0)),
            )
        )
    return rows


def _intended_camera(rows: List[Row]) -> List[str]:
    cams: List[str] = []
    for r in rows:
        cams.append(CAM_BY_SPEAKER_ID.get(r.speaker_id, "speaker_0"))
    return cams


def _camera_cut_boundaries(rows: List[Row], cams: List[str]) -> List[Tuple[float, int]]:
    """
    Return a list of (cut_time_seconds, sentence_index) where a camera change would occur.
    The boundary index is the sentence index where the new camera would start.
    """
    cuts: List[Tuple[float, int]] = []
    for i in range(1, len(rows)):
        if cams[i] != cams[i - 1]:
            cuts.append((rows[i].start, i))
    return cuts


def _find_wide_spans(
    rows: List[Row],
    cams: List[str],
    window_sec: float = 3.0,
    min_wide_sec: float = 3.0,
) -> List[Tuple[int, int]]:
    """
    Compute sentence-aligned wide spans as (start_sentence_index, end_sentence_index),
    where end is exclusive.
    """
    cuts = _camera_cut_boundaries(rows, cams)
    if len(cuts) < 2:
        return []

    spans: List[Tuple[int, int]] = []
    k = 0
    while k < len(cuts) - 1:
        t0, i0 = cuts[k]
        t1, _i1 = cuts[k + 1]
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

        # If we ran off the end, wide goes to end of rows.
        if end_idx > len(rows):
            end_idx = len(rows)

        # Exception: if there's a cut within window_sec of the *end* boundary time,
        # extend wide to that cut boundary; repeat.
        while True:
            end_time = rows[end_idx].start if end_idx < len(rows) else rows[-1].end
            next_cut: Optional[Tuple[float, int]] = None
            for tc, ic in cuts:
                # Strictly after the current end boundary, otherwise we can loop forever
                # when a cut boundary is exactly at end_idx.
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

        # Merge overlapping/adjacent spans.
        if spans and start_idx <= spans[-1][1]:
            prev_start, prev_end = spans[-1]
            spans[-1] = (prev_start, max(prev_end, end_idx))
        else:
            spans.append((start_idx, end_idx))

        # Advance k to the first cut boundary not inside this span.
        while k < len(cuts) and cuts[k][1] < end_idx:
            k += 1

    # Drop any degenerate spans.
    spans = [(s, e) for (s, e) in spans if 0 <= s < e <= len(rows)]
    return spans


def _spans_to_override_map(spans: List[Tuple[int, int]]) -> Dict[int, int]:
    """
    Map each sentence index inside a wide span to the span end index.
    """
    m: Dict[int, int] = {}
    for s, e in spans:
        for i in range(s, e):
            m[i] = e
    return m


def generate_dsl(
    rows: List[Row],
    segment_num: str,
    max_start_time: Optional[float],
    apply_wide_rule: bool,
    wide_camera_name: str,
    window_sec: float,
    min_wide_sec: float,
) -> str:
    if max_start_time is not None:
        rows = [r for r in rows if r.start < max_start_time]

    cams = _intended_camera(rows)
    wide_spans = (
        _find_wide_spans(rows, cams, window_sec=window_sec, min_wide_sec=min_wide_sec)
        if apply_wide_rule
        else []
    )
    override_map = _spans_to_override_map(wide_spans)

    out: List[str] = []
    out.append("// Generated DSL")
    out.append(f"// segment{segment_num} | Speaker 0 -> speaker_0, Speaker 1 -> speaker_1")
    if max_start_time is not None:
        out.append(f"// Included rows with start_time < {max_start_time:.2f}s")
    if apply_wide_rule:
        out.append(
            f"// Wide rule: if >1 camera cut in {window_sec:.1f}s, force !camera {wide_camera_name} "
            f"for >= {min_wide_sec:.1f}s (sentence-aligned), extend if another cut within {window_sec:.1f}s"
        )
    out.append("")

    current_cam: Optional[str] = None
    i = 0
    while i < len(rows):
        r = rows[i]

        if i in override_map:
            # Enter wide span at sentence boundary i.
            if current_cam != wide_camera_name:
                out.append(f"!camera {wide_camera_name}")
                current_cam = wide_camera_name
            end_i = override_map[i]
            for j in range(i, end_i):
                rr = rows[j]
                who = "Ben" if rr.speaker_id == 0 else "Guest"
                text = rr.text.strip().replace("\n", " ")
                out.append(f"$segment{segment_num}/{rr.idx} // {who}: {text}")

            # After wide ends, return to intended cam for the *first* sentence after the span (option A).
            i = end_i
            if i < len(rows):
                next_cam = cams[i]
                if current_cam != next_cam:
                    out.append(f"!camera {next_cam}")
                    current_cam = next_cam
            continue

        intended = cams[i]
        if current_cam != intended:
            out.append(f"!camera {intended}")
            current_cam = intended

        who = "Ben" if r.speaker_id == 0 else "Guest"
        text = r.text.strip().replace("\n", " ")
        out.append(f"$segment{segment_num}/{r.idx} // {who}: {text}")
        i += 1

    out.append("")
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate podcast DSL from simplified transcript JSON.")
    p.add_argument("transcript_json", help="Path to simplified transcript JSON")
    p.add_argument("--segment", required=True, help="Segment number, e.g. 11")
    p.add_argument("--output", required=True, help="Output DSL path")
    p.add_argument("--max-start", type=float, default=None, help="Include only rows with start < seconds")

    p.add_argument("--wide-on-dense-cuts", action="store_true", help="Enable dense-cut wide rule")
    p.add_argument("--wide-camera", default="wide", help="Camera name to use for forced wide (default: wide)")
    p.add_argument("--cut-window-sec", type=float, default=3.0, help="Rolling window size in seconds (default: 3)")
    p.add_argument("--min-wide-sec", type=float, default=3.0, help="Minimum wide duration in seconds (default: 3)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rows = _load_rows(Path(args.transcript_json))
    dsl = generate_dsl(
        rows=rows,
        segment_num=str(args.segment),
        max_start_time=args.max_start,
        apply_wide_rule=bool(args.wide_on_dense_cuts),
        wide_camera_name=str(args.wide_camera),
        window_sec=float(args.cut_window_sec),
        min_wide_sec=float(args.min_wide_sec),
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(dsl)
    print(f"Wrote DSL to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

