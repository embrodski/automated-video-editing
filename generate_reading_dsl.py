#!/usr/bin/env python3
"""
Generate a DSL file for a "reading" segment: a single speaker reads an article
on camera, switching between two camera angles to cover flubs and re-reads.

Workflow:
  1. Load a simplified transcript JSON (from convert_transcript_json.py) and a
     canonical article text file (paragraphs separated by blank lines, poem lines
     on their own lines).
  2. Split the article into sentence-like chunks (splitting at . ? ! : ; and
     newlines, with abbreviation handling).
  3. For every transcript row from the reader (speaker_id == 0), find the best
     contiguous multi-sentence span in the article (article[a_start..a_end])
     whose concatenated text is closest to the row's text.
  4. Rows with low similarity to any article span are marked off-script (coach
     direction, asides, etc.) and dropped.
  5. Walk rows in reverse, keeping only rows whose matched article range ends
     BEFORE the most recently kept row's article range starts. This naturally
     keeps only the final (latest) take of each article sentence, handles
     speaker rewinds by replacing the affected range with the final contiguous
     correct reading, and drops intermediate partial attempts.
  6. Partition kept rows into "spans": consecutive kept rows that are also
     consecutive in the ORIGINAL transcript (no dropped rows between them).
     Each span boundary is a "cut" that flips the camera (front <-> side).
     The first kept row starts on `front`.
  7. (Removed) The prior "60s no-cut bridge" rule is disabled.
  8. Optional incoming lead-in: only when a camera change crosses a **time gap**
     (discarded transcript between clips). Start the new clip up to
     `cut_lead_in_sec` before its transcript start, clamped so it does not begin
     before the previous clip's end. Outgoing end times are never shortened;
     contiguous cuts (no gap) are left unchanged.
  9. Disfavor the side camera: any contiguous side shot
     longer than `side_shot_max_sec` switches to front at the next comma,
     sentence end (. ? !), or row boundary.
  10. The last transcript row in the edit always uses the front camera.
  11. Emit the DSL.

Example:
  python generate_reading_dsl.py \\
      "D:/.../reading_transcript_simplified.json" \\
      "D:/.../units_of_breath_article.txt" \\
      --segment 14 \\
      --output "D:/.../reading.dsl"
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple


SENTENCE_TERMINALS = ".?!:;"
ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "mt",
    "etc", "vs", "eg", "ie", "fig", "no", "vol", "ch",
})


@dataclass
class ArticleSentence:
    idx: int
    text: str
    norm: str
    paragraph_idx: int


@dataclass
class TranscriptRow:
    idx: int
    start: float
    end: float
    text: str
    norm: str
    speaker_id: int
    words: List["WordToken"]


@dataclass
class WordToken:
    text: str
    start: float
    end: float


@dataclass
class RowMatch:
    row: TranscriptRow
    a_start: Optional[int]
    a_end: Optional[int]
    similarity: float
    off_script: bool = False
    keep_anyway: bool = False


_VISUAL_CALLOUT_RE = re.compile(
    r"\b("
    r"here(?:'s| is)|there(?:'s| is)|this is|you can see|as you can see|"
    r"on (?:the )?screen|on (?:the )?page|in (?:the )?article"
    r")\b.*\b("
    r"diagram|chart|graph|figure|map|photo|image|picture|table|video|clip"
    r")\b",
    re.I,
)


def is_visual_callout_sentence(text: str) -> bool:
    """Return True if the sentence is a likely 'visual callout' the reader says while reading.

    These are not always present in the canonical article text (often they refer to a figure
    embedded in the page), but we still want to keep them in the reading cut.
    """
    t = (text or "").strip()
    if not t:
        return False
    return bool(_VISUAL_CALLOUT_RE.search(t))


@dataclass
class SubClip:
    """One contiguous [a, b) interval on a transcript row with a fixed camera."""
    row: TranscriptRow
    a: float
    b: float
    cam: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("transcript_json", help="Simplified transcript JSON from convert_transcript_json.py")
    p.add_argument("article_txt", help="Canonical article text file")
    p.add_argument("--segment", required=True, help="Segment number to use in DSL (e.g. 14)")
    p.add_argument("--output", required=True, help="Output DSL path")
    p.add_argument("--front-camera", default="speaker_0",
                   help="Camera name used for the initial/title shot (default: speaker_0)")
    p.add_argument("--side-camera", default="speaker_1",
                   help="Camera name used for the alternate shot (default: speaker_1)")
    p.add_argument(
        "--reader-speaker-id",
        type=int,
        default=0,
        help="Transcript speaker_id treated as the reader/narrator (default: 0)",
    )
    p.add_argument("--similarity-threshold", type=float, default=0.55,
                   help="Minimum normalized similarity for a transcript row to be considered on-script (default: 0.55)")
    p.add_argument("--max-span", type=int, default=6,
                   help="Maximum number of consecutive article sentences a single transcript row may cover (default: 6)")
    p.add_argument("--cut-lead-in-sec", type=float, default=0.25,
                   help="When a camera change crosses a transcript time gap, start "
                        "the incoming clip this many seconds earlier (default: 0.25); "
                        "0 disables. Never shortens outgoing clips; no change if no gap.")
    p.add_argument("--side-shot-max-sec", type=float, default=12.0,
                   help="Side camera: switch to front after this many seconds at "
                        "the next comma/sentence/row boundary (default: 12); "
                        "0 disables")
    p.add_argument(
        "--final-shot-tail-sec",
        type=float,
        default=2.0,
        help="Extend the final shot this many seconds past the last word if possible "
             "(default: 2.0). If media ends sooner, the renderer will naturally stop at EOF.",
    )
    p.add_argument("--keep-rows", default="",
                   help="Comma-separated transcript row indices to force-keep (e.g. for picture/graph description exceptions)")
    p.add_argument("--drop-rows", default="",
                   help="Comma-separated transcript row indices to force-drop")
    p.add_argument("--verbose", action="store_true", help="Print alignment debug info")
    return p.parse_args()


def normalize(text: str) -> str:
    """Lowercase, drop punctuation except apostrophes, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_article_line(line: str) -> List[str]:
    """Split one article line into sentence-like chunks at . ? ! : ; (skipping abbreviations).
    If the line has no terminal punctuation, return it as a single chunk."""
    line = line.strip()
    if not line:
        return []

    words = line.split()
    sentences: List[str] = []
    current: List[str] = []
    for w in words:
        current.append(w)
        if not w:
            continue
        last = w[-1]
        if last not in SENTENCE_TERMINALS:
            continue
        if w.endswith("..."):
            continue
        stripped = w.rstrip(SENTENCE_TERMINALS + ",\"'`)")
        stripped_low = stripped.lower().rstrip(".")
        if stripped_low in ABBREVIATIONS:
            continue
        sentences.append(" ".join(current))
        current = []
    if current:
        sentences.append(" ".join(current))
    return sentences


def load_article(path: Path) -> List[ArticleSentence]:
    out: List[ArticleSentence] = []
    paragraph_idx = -1
    prev_blank = True
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            prev_blank = True
            continue
        if prev_blank:
            paragraph_idx += 1
            prev_blank = False
        for chunk in split_article_line(line):
            norm = normalize(chunk)
            if not norm:
                continue
            out.append(ArticleSentence(
                idx=len(out),
                text=chunk,
                norm=norm,
                paragraph_idx=paragraph_idx,
            ))
    return out


def load_transcript(path: Path) -> List[TranscriptRow]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[TranscriptRow] = []
    for key in sorted(data.keys(), key=int):
        v = data[key]
        text = str(v.get("text", "")).strip()
        words_in = v.get("words") if isinstance(v, dict) else None
        words: List[WordToken] = []
        if isinstance(words_in, list):
            for w in words_in:
                if not isinstance(w, dict):
                    continue
                w_text = str(w.get("text", ""))
                try:
                    w_start = float(w.get("start"))
                    w_end = float(w.get("end"))
                except Exception:
                    continue
                if w_end <= w_start:
                    continue
                words.append(WordToken(text=w_text, start=w_start, end=w_end))
        out.append(TranscriptRow(
            idx=int(key),
            start=float(v.get("start", 0.0)),
            end=float(v.get("end", 0.0)),
            text=text,
            norm=normalize(text),
            speaker_id=int(v.get("speaker_id", 0)),
            words=words,
        ))
    return out


def sim(a: str, b: str) -> float:
    """Symmetric character-level similarity on normalized strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def best_multi_match(
    row: TranscriptRow,
    article: List[ArticleSentence],
    max_span: int,
    start_hint: Optional[int] = None,
    window: int = 12,
) -> Tuple[Optional[int], Optional[int], float]:
    """Find the best contiguous article range [a_start..a_end] whose concatenated
    normalized text matches row.norm most closely.

    If start_hint is given, only consider a_start values within [hint - window, hint + window]
    to speed things up and avoid spurious far-away matches.
    """
    if not row.norm:
        return None, None, 0.0

    if start_hint is None:
        a_start_range = range(len(article))
    else:
        lo = max(0, start_hint - window)
        hi = min(len(article), start_hint + window + 1)
        a_start_range = range(lo, hi)

    best: Tuple[Optional[int], Optional[int], float] = (None, None, 0.0)
    for a_start in a_start_range:
        pieces: List[str] = []
        prev_score = -1.0
        for a_end in range(a_start, min(a_start + max_span, len(article))):
            pieces.append(article[a_end].norm)
            candidate = " ".join(pieces)
            score = sim(row.norm, candidate)
            if score > best[2]:
                best = (a_start, a_end, score)
            if score + 1e-9 < prev_score:
                break
            prev_score = score
    return best


def align_rows(
    rows: List[TranscriptRow],
    article: List[ArticleSentence],
    threshold: float,
    max_span: int,
    force_keep: set,
    force_drop: set,
    reader_speaker_id: int,
) -> List[RowMatch]:
    matches: List[RowMatch] = []
    last_good_a_start: Optional[int] = None
    for row in rows:
        if row.idx in force_drop:
            matches.append(RowMatch(row=row, a_start=None, a_end=None, similarity=0.0, off_script=True))
            continue

        if row.speaker_id != reader_speaker_id and row.idx not in force_keep:
            matches.append(RowMatch(row=row, a_start=None, a_end=None, similarity=0.0, off_script=True))
            continue

        # Reading exception: keep "visual callout" sentences even if they are not
        # part of the canonical article text.
        if (
            row.speaker_id == reader_speaker_id
            and row.idx not in force_drop
            and row.idx not in force_keep
            and is_visual_callout_sentence(row.text)
        ):
            matches.append(RowMatch(
                row=row,
                a_start=None,
                a_end=None,
                similarity=0.0,
                off_script=False,
                keep_anyway=True,
            ))
            continue

        # First try a windowed search around the last good match to avoid spurious
        # far-away matches. Only fall back to a full search if the hint search
        # fails to produce any match at all.
        a_start, a_end, score = best_multi_match(
            row, article, max_span=max_span, start_hint=last_good_a_start,
        )
        if a_start is None:
            a_start, a_end, score = best_multi_match(row, article, max_span=max_span)

        off_script = score < threshold and row.idx not in force_keep
        if not off_script and a_start is not None:
            last_good_a_start = a_start
        matches.append(RowMatch(
            row=row,
            a_start=a_start,
            a_end=a_end,
            similarity=score,
            off_script=off_script,
        ))
    return matches


def _match_article_norm(m: RowMatch, article: List[ArticleSentence]) -> str:
    if m.a_start is None or m.a_end is None:
        return ""
    return " ".join(article[i].norm for i in range(m.a_start, m.a_end + 1))


def _combined_rows_similarity(rows: List[TranscriptRow], article_norm: str) -> float:
    joined = normalize(" ".join(row.text for row in rows))
    return sim(joined, article_norm)


def _tail_same_range_cluster(
    kept_reversed: List[RowMatch],
    a_start: int,
    a_end: int,
) -> List[RowMatch]:
    """Return the newest kept tail-cluster that shares the same article range."""
    cluster: List[RowMatch] = []
    for kept in reversed(kept_reversed):
        if kept.a_start != a_start or kept.a_end != a_end:
            break
        if not cluster:
            cluster.append(kept)
            continue
        if kept.row.idx == cluster[-1].row.idx + 1:
            cluster.append(kept)
            continue
        break
    return cluster


def _should_keep_split_chunk(
    current: RowMatch,
    tail_cluster: List[RowMatch],
    article: List[ArticleSentence],
) -> bool:
    """Keep adjacent same-chunk rows when together they cover the chunk better."""
    if not tail_cluster:
        return False
    if current.a_start is None or current.a_end is None:
        return False
    if current.row.idx + 1 != tail_cluster[0].row.idx:
        return False

    article_norm = _match_article_norm(current, article)
    if not article_norm:
        return False

    existing_rows = [m.row for m in tail_cluster]
    combined_rows = [current.row] + existing_rows
    existing_score = _combined_rows_similarity(existing_rows, article_norm)
    combined_score = _combined_rows_similarity(combined_rows, article_norm)

    # Require a real improvement so true duplicate rereads still collapse.
    # Allow a slightly weaker first half if the combined coverage is clearly better.
    return combined_score > existing_score + 0.08 and (
        not current.off_script or current.similarity >= 0.40
    )


def _can_rescue_row_in_split_pair(
    candidate: RowMatch,
    kept_rows: List[RowMatch],
    article: List[ArticleSentence],
) -> bool:
    if candidate.a_start is None or candidate.a_end is None:
        return False
    if not kept_rows:
        return False
    article_norm = _match_article_norm(candidate, article)
    if not article_norm:
        return False

    existing_score = _combined_rows_similarity([m.row for m in kept_rows], article_norm)
    combined_score = _combined_rows_similarity(
        [m.row for m in sorted([candidate] + kept_rows, key=lambda m: m.row.idx)],
        article_norm,
    )
    return combined_score > existing_score + 0.08 and (
        not candidate.off_script or candidate.similarity >= 0.40
    )


def _augment_split_chunk_pairs(
    matches: List[RowMatch],
    kept: List[RowMatch],
    article: List[ArticleSentence],
    selection_notes: List[str],
) -> List[RowMatch]:
    kept_by_idx = {m.row.idx: m for m in kept}

    for i in range(len(matches) - 1):
        left = matches[i]
        right = matches[i + 1]
        if left.a_start is None or right.a_start is None:
            continue
        if left.a_start != right.a_start or left.a_end != right.a_end:
            continue
        if right.row.idx != left.row.idx + 1:
            continue

        left_kept = left.row.idx in kept_by_idx
        right_kept = right.row.idx in kept_by_idx
        if left_kept == right_kept:
            continue

        if left_kept:
            candidate = right
            existing = [left]
            partner_rows = "44"  # placeholder overwritten below
        else:
            candidate = left
            existing = [right]
            partner_rows = "43"  # placeholder overwritten below

        if not _can_rescue_row_in_split_pair(candidate, existing, article):
            continue

        kept_by_idx[candidate.row.idx] = candidate
        partner_rows = ",".join(str(m.row.idx) for m in existing)
        selection_notes.append(
            f"Rescued split chunk: kept row {candidate.row.idx} together with later row(s) "
            f"{partner_rows} for article [{candidate.a_start}:{candidate.a_end}]"
        )

    return sorted(kept_by_idx.values(), key=lambda m: m.row.idx)


def select_kept(
    matches: List[RowMatch],
    force_keep: set,
    article: List[ArticleSentence],
) -> Tuple[List[RowMatch], List[str]]:
    """Walk rows in reverse; keep the row if its matched article range STARTS
    strictly before the most recently kept row's article range starts. This
    means the row contributes earlier-in-article content not already covered
    by a later (final) take, so it correctly:
    - drops previous takes of the same single article chunk (a_start == last)
    - keeps multi-chunk rows whose range overlaps the next kept row by one
      chunk but adds new earlier content (a_start < last)
    - drops rows from before a rewind (any later take of an earlier chunk
      resets `last` back, so pre-rewind rows whose a_start >= current last
      get dropped)."""
    last_a_start = float("inf")
    kept_reversed: List[RowMatch] = []
    selection_notes: List[str] = []
    for m in reversed(matches):
        if m.keep_anyway or m.row.idx in force_keep:
            # Keep forced/exception rows in transcript order without affecting
            # the article-coverage rewind logic.
            if not m.off_script:
                kept_reversed.append(m)
            continue
        if m.a_start is None:
            continue
        if m.a_start < last_a_start:
            if m.off_script and m.row.idx not in force_keep:
                continue
            kept_reversed.append(m)
            last_a_start = m.a_start
            continue

        if kept_reversed and m.a_start == last_a_start:
            tail_cluster = _tail_same_range_cluster(kept_reversed, m.a_start, m.a_end)
            if _should_keep_split_chunk(m, tail_cluster, article):
                kept_reversed.append(m)
                covered_rows = ",".join(str(k.row.idx) for k in reversed(tail_cluster))
                selection_notes.append(
                    f"Rescued split chunk: kept row {m.row.idx} together with later row(s) "
                    f"{covered_rows} for article [{m.a_start}:{m.a_end}]"
                )
                continue

        if m.off_script and m.row.idx not in force_keep:
            continue
    kept_reversed.reverse()
    kept = _augment_split_chunk_pairs(matches, kept_reversed, article, selection_notes)
    return kept, selection_notes


def build_spans(kept: List[RowMatch]) -> List[List[TranscriptRow]]:
    """Group kept rows into "spans" = runs of rows whose transcript indices are
    directly consecutive. Each span boundary is a user-driven cut. Cameras are
    assigned later (they depend on the camera state at each boundary)."""
    spans: List[List[TranscriptRow]] = []
    current: List[TranscriptRow] = []
    for i, m in enumerate(kept):
        if current and kept[i - 1].row.idx + 1 != m.row.idx:
            spans.append(current)
            current = []
        current.append(m.row)
    if current:
        spans.append(current)
    return spans


def collect_sentence_terminal_boundary_times(span_rows: List[TranscriptRow]) -> List[float]:
    """Absolute boundary times at true word ends for sentence-like terminals.
    Uses word-level timestamps when available; falls back to row end."""
    ts: set[float] = set()
    for row in span_rows:
        if row.words:
            for w in row.words:
                t = w.text.strip().rstrip('"\'')  # tolerate quoted tokens
                if not t:
                    continue
                if t.endswith("?") or t.endswith("!") or t.endswith("."):
                    ts.add(w.end)
        else:
            ts.add(row.end)
    return sorted(ts)


def collect_linguistic_boundary_times(span_rows: List[TranscriptRow]) -> List[float]:
    """Absolute boundary times at true word ends for comma boundaries.
    Uses word-level timestamps when available; falls back to row edges."""
    ts: set[float] = set()
    for row in span_rows:
        ts.add(row.start)
        ts.add(row.end)
        if row.words:
            for w in row.words:
                t = w.text.strip().rstrip('"\'')
                if t.endswith(","):
                    ts.add(w.end)
    return sorted(ts)


def collect_side_flip_boundary_times(span_rows: List[TranscriptRow]) -> List[float]:
    """Boundaries for forced side→front: row edges, comma/space, sentence terminals."""
    merged: set[float] = set(collect_linguistic_boundary_times(span_rows))
    merged.update(collect_sentence_terminal_boundary_times(span_rows))
    return sorted(merged)


def enforce_side_max_durations(
    subclips: List[SubClip],
    span_rows: List[TranscriptRow],
    side_cam: str,
    front_cam: str,
    max_side_sec: float,
) -> List[SubClip]:
    """If side (disfavored) runs longer than max_side_sec, switch to front at the
    next comma, sentence terminal, or row edge."""
    if max_side_sec <= 0 or not subclips:
        return subclips
    bounds_list = collect_side_flip_boundary_times(span_rows)
    bounds: set[float] = set(bounds_list)
    bounds_sorted = sorted(bounds)

    def next_boundary_after(t_low: float, t_hi: float) -> Optional[float]:
        for t in bounds_sorted:
            if t > t_low + 1e-9 and t <= t_hi + 1e-9:
                return t
        return None

    out: List[SubClip] = []
    i = 0
    n = len(subclips)
    while i < n:
        c = subclips[i]
        if c.cam != side_cam:
            out.append(c)
            i += 1
            continue
        # Do not require contiguous transcript timestamps: small ASR gaps between
        # rows would otherwise cap each row separately and never exceed 12s.
        j = i + 1
        while (
            j < n
            and subclips[j].cam == side_cam
        ):
            j += 1
        run = subclips[i:j]
        run_start, run_end = run[0].a, run[-1].b
        if run_end - run_start <= max_side_sec + 1e-9:
            out.extend(run)
            i = j
            continue
        B = next_boundary_after(run_start + max_side_sec, run_end)
        if B is None:
            B = run_end
        if B <= run_start + max_side_sec + 1e-9:
            out.extend(run)
            i = j
            continue
        for rc in run:
            if B <= rc.a + 1e-9:
                out.append(SubClip(rc.row, rc.a, rc.b, front_cam))
            elif B >= rc.b - 1e-9:
                out.append(SubClip(rc.row, rc.a, rc.b, side_cam))
            else:
                out.append(SubClip(rc.row, rc.a, B, side_cam))
                out.append(SubClip(rc.row, B, rc.b, front_cam))
        i = j
    return out


def collect_span_subclips(
    span_rows: List[TranscriptRow],
    main_cam: str,
) -> List[SubClip]:
    out: List[SubClip] = []
    for row in span_rows:
        out.append(SubClip(row=row, a=row.start, b=row.end, cam=main_cam))
    return out


def ensure_last_sentence_on_front(subclips: List[SubClip], front_cam: str) -> None:
    """Every subclip for the final transcript row (last in timeline) uses front."""
    if not subclips:
        return
    last_row_idx = subclips[-1].row.idx
    for clip in subclips:
        if clip.row.idx == last_row_idx:
            clip.cam = front_cam


def extend_final_shot(subclips: List[SubClip], extra_sec: float) -> None:
    """Extend the very last subclip by `extra_sec` seconds.

    This is used to hold on the last shot after the last spoken word. If the
    underlying source media ends sooner, ffmpeg-based trimming will stop at EOF.
    """
    if not subclips or extra_sec <= 0:
        return
    subclips[-1].b = subclips[-1].b + extra_sec


def apply_cut_lead_in(
    subclips: List[SubClip],
    lead_sec: float,
    min_clip_sec: float = 0.05,
    gap_epsilon: float = 2e-3,
) -> None:
    """Only when a camera change crosses a time gap (discarded footage): move the
    incoming clip's start earlier by up to `lead_sec`, never before `prev.b`.
    Outgoing `prev.b` is never reduced. Contiguous cuts (gap <= gap_epsilon) are
    unchanged."""
    if lead_sec <= 0:
        return
    for i in range(1, len(subclips)):
        prev, cur = subclips[i - 1], subclips[i]
        if prev.cam == cur.cam:
            continue
        gap = cur.a - prev.b
        if gap <= gap_epsilon:
            continue
        new_cur_a = max(prev.b, cur.a - lead_sec)
        if new_cur_a >= cur.b - min_clip_sec:
            continue
        cur.a = new_cur_a


def emit_subclip_lines(
    subclips: List[SubClip],
    segment_num: str,
    current_camera_ref: List[Optional[str]],
    lines: List[str],
) -> None:
    for clip in subclips:
        if clip.cam != current_camera_ref[0]:
            lines.append(f"!camera {clip.cam}")
            current_camera_ref[0] = clip.cam
        row = clip.row
        a, b = clip.a, clip.b
        sl_start = a - row.start
        sl_end = b - row.start
        is_full_row = (abs(a - row.start) < 1e-6 and abs(b - row.end) < 1e-6)
        text_summary = row.text.replace("\n", " ").strip()
        if len(text_summary) > 90:
            text_summary = text_summary[:87] + "..."
        if is_full_row:
            lines.append(f"$segment{segment_num}/{row.idx} // {text_summary}")
        else:
            lines.append(
                f"$segment{segment_num}/{row.idx} slice({sl_start:.3f}:{sl_end:.3f}) "
                f"// {text_summary}"
            )


def generate_dsl(
    rows: List[TranscriptRow],
    article: List[ArticleSentence],
    matches: List[RowMatch],
    kept: List[RowMatch],
    segment_num: str,
    front_cam: str,
    side_cam: str,
    cut_lead_in_sec: float,
    side_shot_max_sec: float,
    final_shot_tail_sec: float,
) -> str:
    spans = build_spans(kept)

    lines: List[str] = []
    lines.append(f"// Generated reading DSL (segment {segment_num})")
    lines.append(f"// Cameras: {front_cam} (front, starting) / {side_cam} (side, alternate)")
    lines.append(
        f"// Cuts: camera flips at each user-driven cut (dropped rows between kept rows)"
    )
    lines.append(
        f"// Gap lead-in only: if camera change crosses discarded time, start incoming "
        f"up to {cut_lead_in_sec:.2f}s early (never shorten outgoing; no change if contiguous)"
    )
    lines.append("// Opening: start about 1.0s before the title read, not from media t=0")
    if side_shot_max_sec > 0:
        lines.append(
            f"// Side camera cap: >{side_shot_max_sec:.0f}s → front at next comma / "
            f"sentence end / row edge"
        )
    lines.append(f"// Last transcript row is always {front_cam} (front)")
    lines.append(f"// Kept {len(kept)}/{len(rows)} rows in {len(spans)} span(s)")
    lines.append("")
    lines.append("!opening 1000")
    lines.append("")
    # Readings: no padding between cuts (prevents tiny audio overlaps at camera switches).
    lines.append("!cut 0 0")
    lines.append("")

    # The first span's main camera is the front camera (rule 1: title on Front).
    # Each subsequent span's main camera flips from whatever camera was on screen
    # at the end of the previous span. This guarantees every user-driven cut is
    # visibly a camera change.
    span_metas: List[Tuple[str, List[SubClip]]] = []
    all_subclips: List[SubClip] = []
    next_main_cam: Optional[str] = front_cam
    for span_rows in spans:
        t_start = span_rows[0].start
        t_end = span_rows[-1].end
        duration = t_end - t_start

        main_cam = next_main_cam
        alt_cam = side_cam if main_cam == front_cam else front_cam
        comment = (
            f"// Span on {main_cam}: {t_start:.2f}s -> {t_end:.2f}s "
            f"({duration:.1f}s)"
        )

        span_sub = collect_span_subclips(span_rows, main_cam)
        span_sub = enforce_side_max_durations(
            span_sub, span_rows, side_cam, front_cam, side_shot_max_sec,
        )
        span_metas.append((comment, span_sub))
        all_subclips.extend(span_sub)

        end_cam = span_sub[-1].cam if span_sub else main_cam
        next_main_cam = main_cam if end_cam == alt_cam else alt_cam

    apply_cut_lead_in(all_subclips, cut_lead_in_sec)
    ensure_last_sentence_on_front(all_subclips, front_cam)
    extend_final_shot(all_subclips, final_shot_tail_sec)

    current_camera_ref: List[Optional[str]] = [None]
    for comment, span_sub in span_metas:
        lines.append(comment)
        lines.append("")
        emit_subclip_lines(span_sub, segment_num, current_camera_ref, lines)
        lines.append("")

    return "\n".join(lines) + "\n"


def write_alignment_report(
    rows: List[TranscriptRow],
    matches: List[RowMatch],
    kept_row_ids: set,
    article: List[ArticleSentence],
    report_path: Path,
    selection_notes: List[str],
) -> None:
    header = (
        f"Alignment report: {len(matches)} rows, {len(kept_row_ids)} kept, "
        f"{len(article)} article chunks\n"
        + "=" * 80 + "\n"
    )
    parts = [header]
    if selection_notes:
        parts.append("Selection notes:\n")
        for note in selection_notes:
            parts.append(f"  - {note}\n")
        parts.append("=" * 80 + "\n")
    for m in matches:
        status = "KEEP" if m.row.idx in kept_row_ids else ("OFF" if m.off_script else "DROP")
        art_txt = ""
        if m.a_start is not None and m.a_end is not None:
            joined = " ".join(article[i].text for i in range(m.a_start, m.a_end + 1))
            if len(joined) > 80:
                joined = joined[:77] + "..."
            art_txt = f"-> [{m.a_start}:{m.a_end}] {joined}"
        parts.append(
            f"{status:4s} row={m.row.idx:3d} spk={m.row.speaker_id} "
            f"t={m.row.start:7.2f}-{m.row.end:7.2f} sim={m.similarity:.2f} "
            f"| {m.row.text[:60]!r} {art_txt}\n"
        )
    report_path.write_text("".join(parts), encoding="utf-8")


def build_sanity_report(
    article: List[ArticleSentence],
    kept: List[RowMatch],
    selection_notes: List[str],
    article_path: Path,
    transcript_path: Path,
) -> dict:
    covered_chunks = sorted({
        i
        for m in kept
        if m.a_start is not None and m.a_end is not None
        for i in range(m.a_start, m.a_end + 1)
    })
    covered_set = set(covered_chunks)
    missing = [i for i in range(len(article)) if i not in covered_set]

    trailing_start = len(article)
    while trailing_start > 0 and (trailing_start - 1) not in covered_set:
        trailing_start -= 1
    trailing_missing = [i for i in missing if i >= trailing_start]
    internal_missing = [i for i in missing if i < trailing_start]

    def _entry(idx: int) -> dict:
        return {"idx": idx, "text": article[idx].text}

    return {
        "version": 1,
        "article_path": str(article_path),
        "transcript_path": str(transcript_path),
        "article_chunks": len(article),
        "covered_chunks": covered_chunks,
        "selection_notes": selection_notes,
        # Missing chunks are allowed: the reader may skip sentences (including captions),
        # and the canonical article text may contain lines that were not spoken aloud.
        "blocking_issues": [],
        "warnings": [
            {
                "kind": "missing_chunk",
                "idx": idx,
                "text": article[idx].text,
            }
            for idx in missing
        ],
        "summary": {
            "covered_count": len(covered_chunks),
            "missing_count": len(missing),
            "internal_missing_count": len(internal_missing),
            "trailing_missing_count": len(trailing_missing),
        },
        "missing_chunks": [_entry(idx) for idx in missing],
    }


def write_sanity_report(report: dict, path: Path) -> None:
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    transcript_path = Path(args.transcript_json)
    article_path = Path(args.article_txt)
    output_path = Path(args.output)

    force_keep = {int(x) for x in args.keep_rows.split(",") if x.strip()}
    force_drop = {int(x) for x in args.drop_rows.split(",") if x.strip()}

    article = load_article(article_path)
    rows = load_transcript(transcript_path)

    matches = align_rows(
        rows, article,
        threshold=args.similarity_threshold,
        max_span=args.max_span,
        force_keep=force_keep,
        force_drop=force_drop,
        reader_speaker_id=args.reader_speaker_id,
    )

    kept, selection_notes = select_kept(matches, force_keep=force_keep, article=article)
    kept_row_ids = {m.row.idx for m in kept}

    dsl = generate_dsl(
        rows, article, matches, kept,
        segment_num=str(args.segment),
        front_cam=args.front_camera,
        side_cam=args.side_camera,
        cut_lead_in_sec=args.cut_lead_in_sec,
        side_shot_max_sec=args.side_shot_max_sec,
        final_shot_tail_sec=args.final_shot_tail_sec,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dsl, encoding="utf-8", newline="\n")

    report_path = output_path.with_suffix(output_path.suffix + ".alignment.txt")
    write_alignment_report(rows, matches, kept_row_ids, article, report_path, selection_notes)

    sanity_report = build_sanity_report(
        article=article,
        kept=kept,
        selection_notes=selection_notes,
        article_path=article_path,
        transcript_path=transcript_path,
    )
    sanity_path = output_path.with_suffix(output_path.suffix + ".sanity.json")
    write_sanity_report(sanity_report, sanity_path)

    article_coverage = sanity_report["covered_chunks"]
    missing = [entry["idx"] for entry in sanity_report["missing_chunks"]]
    print(f"Wrote DSL to {output_path}")
    print(f"Alignment report: {report_path}")
    print(f"Sanity report: {sanity_path}")
    print(f"Kept {len(kept)}/{len(rows)} rows across {len(build_spans(kept))} span(s)")
    print(f"Article coverage: {len(article_coverage)}/{len(article)} chunks")
    if sanity_report["blocking_issues"]:
        print(
            f"Sanity check would block render: "
            f"{len(sanity_report['blocking_issues'])} internal missing chunk(s)"
        )
    if missing:
        print(f"Warning: {len(missing)} article chunks not explicitly matched by any kept row:")
        for i in missing[:15]:
            txt = article[i].text
            if len(txt) > 70:
                txt = txt[:67] + "..."
            print(f"  [{i}] {txt}")
        if len(missing) > 15:
            print(f"  ... and {len(missing) - 15} more")

    if args.verbose:
        print("\nPer-row matches:")
        for m in matches:
            status = "KEEP" if m.row.idx in kept_row_ids else ("OFF" if m.off_script else "DROP")
            print(f"  {status:4s} {m.row.idx:3d} sim={m.similarity:.2f} "
                  f"art=[{m.a_start}:{m.a_end}] text={m.row.text[:50]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
