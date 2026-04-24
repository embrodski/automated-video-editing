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
- **Open on Ben:** for the first `--open-ben-sec` seconds (default 5), every row overlapping
  `[0, open)` is forced to `speaker_0` so there is no cut off Ben during that window
  (row-aligned).
- **Close on Ben:** for the last `--tail-ben-sec` seconds (default 4) of the timeline
  (including `--final-shot-tail-sec` past the last transcript word), every overlapping row
  is forced to `speaker_0` (row-aligned; the first row that intersects that tail window may
  start earlier, so Ben may begin slightly before the exact cut time if there is no row
  boundary at T - tail).
- Applies the core rule: **dense cuts → force wide**
  If there would be more than one camera cut in any rolling window (default 3 seconds), it
  replaces that region with a single `!camera wide` span (sentence-aligned, at least
  `--min-wide-sec`), extending the wide span if another cut would happen within the window.
  Wide spans are trimmed so they never cover the open-Ben or tail-Ben windows.

Use `--no-cameras` to reproduce the legacy behavior (no `!camera` lines, no wide rule).
"""

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CAM_BY_SPEAKER_ID = {
    0: "speaker_0",
    1: "speaker_1",
}

_INTERJECTION_CANONICAL = {
    # Keep this conservative: only short backchannels that should not flip the shot by themselves.
    "mm-hmm",
    "mhm",
    "uh-huh",
    "uh huh",
    "huh",
    "yeah",
    "yep",
    "right",
    "ok",
    "okay",
}

# If a transcript row is <= this duration and matches an interjection above, treat it as a
# "brief interjection" for camera-switch purposes.
_BRIEF_INTERJECTION_MAX_SEC = 0.85

_NORMALIZE_TEXT_RE = re.compile(r"[^a-z0-9\s\-]+")


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
        default=3.0,
        help="Rolling window size in seconds for dense-cuts-wide (default: 3.0)",
    )
    parser.add_argument(
        "--min-wide-sec",
        type=float,
        default=3.0,
        help="Minimum wide span duration in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--final-shot-tail-sec",
        type=float,
        default=2.0,
        help="Extend the final shot this many seconds past the last word if possible "
             "(default: 2.0). If media ends sooner, the renderer will naturally stop at EOF.",
    )
    parser.add_argument(
        "--open-ben-sec",
        type=float,
        default=5.0,
        help="Force speaker_0 for every transcript row overlapping [0, N) seconds on the "
             "timeline (default N=5.0). Set to 0 to disable.",
    )
    parser.add_argument(
        "--tail-ben-sec",
        type=float,
        default=4.0,
        help="Force speaker_0 for rows overlapping the last this many seconds of the "
             "timeline (uses --final-shot-tail-sec for end time). Default: 4.0. Set to 0 "
             "to disable.",
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


def _normalize_interjection_text(text: str) -> str:
    t = text.strip().lower()
    t = t.replace("—", "-").replace("–", "-")
    t = _NORMALIZE_TEXT_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_brief_interjection_row(r: Row) -> bool:
    dur = max(0.0, float(r.end) - float(r.start))
    if dur > _BRIEF_INTERJECTION_MAX_SEC:
        return False

    t = _normalize_interjection_text(r.text)
    if not t:
        return False

    # Two backchannels like "yeah yeah" should count as *not* brief (user wants that to trigger).
    parts = t.split()
    if len(parts) >= 2 and all(p == parts[0] for p in parts):
        return False

    # Very short (1–2 tokens) and exactly one of our canonical interjections.
    if len(parts) > 2:
        return False
    return t in _INTERJECTION_CANONICAL


def _intended_camera(rows: List[Row]) -> List[str]:
    """
    Camera selection per transcript row.

    Rule tweak: a *single* very brief interjection (e.g. "Mm-hmm.", "Yeah.") should not
    flip the camera on its own. Two consecutive interjections, or any longer utterance,
    can still flip as normal.
    """
    base = [CAM_BY_SPEAKER_ID.get(r.speaker_id, "speaker_0") for r in rows]
    if not rows:
        return []

    effective: List[str] = []
    last_cam: Optional[str] = None
    pending_other_cam: Optional[str] = None  # remembers a suppressed one-off interjection cam

    for r, cam in zip(rows, base):
        if last_cam is None:
            effective.append(cam)
            last_cam = cam
            pending_other_cam = None
            continue

        if cam != last_cam and _is_brief_interjection_row(r):
            # One-off interjection: suppress the first one; allow the second in a row to cut.
            if pending_other_cam == cam:
                effective.append(cam)
                last_cam = cam
                pending_other_cam = None
            else:
                effective.append(last_cam)
                pending_other_cam = cam
            continue

        effective.append(cam)
        last_cam = cam
        pending_other_cam = None

    return effective


def _timeline_end(rows: List[Row], final_shot_tail_sec: float) -> float:
    if not rows:
        return 0.0
    return float(rows[-1].end) + max(0.0, float(final_shot_tail_sec))


def _row_overlaps_interval(r: Row, lo: float, hi: float) -> bool:
    """True if [r.start, r.end) intersects [lo, hi) on the timeline."""
    return float(r.start) < float(hi) and float(r.end) > float(lo)


def _apply_open_ben_lock(rows: List[Row], cams: List[str], open_sec: float) -> None:
    """Force speaker_0 on every row overlapping [0, open_sec) (no cut off Ben during that window)."""
    if open_sec <= 0.0 or not rows:
        return
    for i, r in enumerate(rows):
        if _row_overlaps_interval(r, 0.0, open_sec):
            cams[i] = "speaker_0"


def _first_row_overlapping_tail(rows: List[Row], t_lo: float, t_hi: float) -> int:
    """First row index whose [start, end) intersects (t_lo, t_hi) on the timeline."""
    for i, r in enumerate(rows):
        if r.end > t_lo and r.start < t_hi:
            return i
    return len(rows)


def _apply_tail_ben_lock(
    rows: List[Row], cams: List[str], tail_sec: float, final_shot_tail_sec: float
) -> None:
    """Force speaker_0 from the first row that overlaps the last tail_sec of the timeline."""
    if tail_sec <= 0.0 or not rows:
        return
    t_hi = _timeline_end(rows, final_shot_tail_sec)
    t_lo = max(0.0, t_hi - float(tail_sec))
    j = _first_row_overlapping_tail(rows, t_lo, t_hi)
    for i in range(j, len(rows)):
        cams[i] = "speaker_0"


def _merge_row_spans(spans: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not spans:
        return []
    spans = sorted(spans, key=lambda x: (x[0], x[1]))
    out: List[Tuple[int, int]] = [spans[0]]
    for s, e in spans[1:]:
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def _trim_wide_spans_for_ben_locks(
    rows: List[Row],
    spans: List[Tuple[int, int]],
    *,
    open_sec: float,
    tail_sec: float,
    final_shot_tail_sec: float,
) -> List[Tuple[int, int]]:
    """
    Remove wide coverage from the open-Ben window [0, open_sec) and from the tail-Ben
    window [T - tail_sec, T] (row-aligned).
    """
    if not spans:
        return []
    T_end = _timeline_end(rows, final_shot_tail_sec)
    t_cut = (
        max(0.0, T_end - float(tail_sec)) if tail_sec > 0 else float("-inf")
    )
    tail_row0 = (
        _first_row_overlapping_tail(rows, t_cut, T_end) if tail_sec > 0 else len(rows)
    )
    out: List[Tuple[int, int]] = []
    for s, e in spans:
        ss, ee = s, e
        if open_sec > 0:
            while ss < ee and _row_overlaps_interval(rows[ss], 0.0, open_sec):
                ss += 1
        if ss >= ee:
            continue
        if tail_sec > 0 and tail_row0 < len(rows):
            # Wide may not cover any row that overlaps [t_cut, T_end] (tail Ben window).
            ee = min(ee, tail_row0)
        if ss >= ee:
            continue
        out.append((ss, ee))
    return _merge_row_spans(out)


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


def _row_comment(row: Row, *, include_fallback_speaker: bool) -> str:
    text = row.text.strip().replace("\n", " ")
    if row.speaker_name:
        return f"{row.speaker_name}: {text}"
    if include_fallback_speaker:
        fallback = "Speaker 0" if row.speaker_id == 0 else "Speaker 1"
        return f"{fallback}: {text}"
    return text


def _row_segment_line(
    row: Row,
    segment_num: str,
    *,
    include_fallback_speaker: bool,
    is_last: bool,
    final_shot_tail_sec: float,
) -> str:
    segment_ref = f"$segment{segment_num}/{row.idx}"
    if is_last and final_shot_tail_sec > 0:
        slice_end = (row.end - row.start) + final_shot_tail_sec
        segment_ref = f"{segment_ref} slice(:{slice_end:.3f})"
    comment = _row_comment(row, include_fallback_speaker=include_fallback_speaker)
    return f"{segment_ref} // {comment}"


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
        last_idx = len(rows) - 1
        for idx, r in enumerate(rows):
            lines.append(
                _row_segment_line(
                    r,
                    segment_num,
                    include_fallback_speaker=False,
                    is_last=idx == last_idx,
                    final_shot_tail_sec=float(args.final_shot_tail_sec),
                )
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {len(lines)} DSL lines to {output_path}")
        return 0

    cams = _intended_camera(rows)
    _apply_open_ben_lock(rows, cams, float(args.open_ben_sec))
    _apply_tail_ben_lock(rows, cams, float(args.tail_ben_sec), float(args.final_shot_tail_sec))
    spans = _find_wide_spans(
        rows,
        cams,
        window_sec=float(args.cut_window_sec),
        min_wide_sec=float(args.min_wide_sec),
    )
    spans = _trim_wide_spans_for_ben_locks(
        rows,
        spans,
        open_sec=float(args.open_ben_sec),
        tail_sec=float(args.tail_ben_sec),
        final_shot_tail_sec=float(args.final_shot_tail_sec),
    )
    override_map = _spans_to_override_map(spans)

    lines.append("// Generated DSL")
    lines.append(f"// segment{segment_num} | Speaker 0 -> speaker_0, Speaker 1 -> speaker_1")
    lines.append(
        f"// Open: first {float(args.open_ben_sec):.1f}s on speaker_0 (no cuts off Ben before then); "
        f"tail: last {float(args.tail_ben_sec):.1f}s on speaker_0 (timeline includes "
        f"{float(args.final_shot_tail_sec):.1f}s final-shot tail)"
    )
    lines.append(
        f"// Wide rule: if >1 camera cut in {float(args.cut_window_sec):.1f}s, force !camera {args.wide_camera} "
        f"for >= {float(args.min_wide_sec):.1f}s (sentence-aligned), extend if another cut within {float(args.cut_window_sec):.1f}s"
    )
    lines.append("")

    current_cam: Optional[str] = None
    last_idx = len(rows) - 1
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
                lines.append(
                    _row_segment_line(
                        rr,
                        segment_num,
                        include_fallback_speaker=True,
                        is_last=j == last_idx,
                        final_shot_tail_sec=float(args.final_shot_tail_sec),
                    )
                )

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

        lines.append(
            _row_segment_line(
                r,
                segment_num,
                include_fallback_speaker=True,
                is_last=i == last_idx,
                final_shot_tail_sec=float(args.final_shot_tail_sec),
            )
        )
        i += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {len(rows)} DSL lines to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
