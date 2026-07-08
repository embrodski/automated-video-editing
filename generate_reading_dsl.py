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
  5. Walk rows in reverse, keeping a row unless a later kept row strictly
     covers its article span (rewind / full re-read). Same-span duplicates
     keep the highest-similarity take so a weak late match cannot erase a
     strong earlier read. Adjacent same-span split rows still use split-chunk
     rescue.
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
  11. After gap lead-in, extend each subclip end by a short post-word tail (default
      0.4s after the last word in that clip), clamped so the cut never enters the next
      word, the next subclip, or past row.end; then extend the final shot tail.
  12. Optionally (--shorten), compress inter-word silences longer than a threshold
      before the final-shot tail extension; off by default.
  13. Emit the DSL.

Renders of the generated DSL use **embedded audio from each camera MP4** by default
(see ``segment_uses_embedded_audio`` in ``src/podcast_dsl/config.py``). The master
WAV in ``SEGMENT_CONFIG`` is for transcript timing, not final mux.

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
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Tuple


SENTENCE_TERMINALS = ".?!:;"
ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "ave", "mt",
    "etc", "vs", "eg", "ie", "fig", "no", "vol", "ch",
})

# Token-coverage thresholds for stitch rescue and partial-coverage audits.
PARTIAL_COVERAGE_THRESHOLD = 0.55
STITCH_COVERAGE_GAIN = 0.05
MAX_STITCH_GAP_ROWS = 4
MIN_ARTICLE_WORDS_PARTIAL = 7
SPURIOUS_COVERAGE_FLOOR = 0.20
GAP_FILL_OFF_SCRIPT_MIN_SIM = 0.35
GAP_FILL_MIDDLE_GAIN = 0.03


@dataclass
class ArticleSentence:
    idx: int
    text: str
    norm: str
    norm_had: str
    paragraph_idx: int


@dataclass
class TranscriptRow:
    idx: int
    start: float
    end: float
    text: str
    norm: str
    norm_had: str
    speaker_id: int
    words: List["WordToken"]
    # Optional: trim usable start (drop in-row restart).
    # This only affects emitted DSL slices (not the transcript JSON itself).
    trim_start: Optional[float] = None
    # Optional: trim usable end (drop tail retaken by the next kept row).
    trim_end: Optional[float] = None


def _row_effective_start(row: TranscriptRow) -> float:
    return row.trim_start if row.trim_start is not None else row.start


def _row_effective_end(row: TranscriptRow) -> float:
    return row.trim_end if row.trim_end is not None else row.end


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


_SECTION_HEADER_CALLOUT_RE = re.compile(
    r"\b("
    r"(?:this|the next|next) section is called|"
    r"the section title is|"
    r"section\s+\d+\b"
    r")",
    re.I,
)


def is_visual_callout_sentence(text: str) -> bool:
    """Return True if the sentence is a likely non-article callout while reading.

    These are not always present in the canonical article text (often they refer to a figure
    embedded in the page, or a visible section header), but we still want to keep them in the
    reading cut.
    """
    t = (text or "").strip()
    if not t:
        return False
    return bool(_VISUAL_CALLOUT_RE.search(t) or _SECTION_HEADER_CALLOUT_RE.search(t))


@dataclass
class SubClip:
    """One contiguous [a, b) interval on a transcript row with a fixed camera."""
    row: TranscriptRow
    a: float
    b: float
    cam: str
    shorten_join_before: bool = False


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
    p.add_argument(
        "--post-word-tail-sec",
        type=float,
        default=0.4,
        help="Extend each subclip end this many seconds after the last word end in that "
             "clip, clamped so the cut never enters the next word (or the next subclip / "
             "row boundary). Set to 0 to disable (default: 0.4).",
    )
    p.add_argument(
        "--shorten",
        action="store_true",
        help="After post-word tail, compress inter-word silences longer than "
             "--shorten-min-silence-sec (same behavior as shorten_reading_dsl_silences.py). "
             "Off by default.",
    )
    p.add_argument(
        "--shorten-min-silence-sec",
        type=float,
        default=3.0,
        help="With --shorten: treat gaps this many seconds or longer as long silences (default: 3.0).",
    )
    p.add_argument(
        "--shorten-tail-sec",
        type=float,
        default=1.5,
        help="With --shorten: keep this many seconds after the last word before a long gap (default: 1.5).",
    )
    p.add_argument(
        "--shorten-lead-sec",
        type=float,
        default=1.5,
        help="With --shorten: start the incoming clip this many seconds before the next word (default: 1.5).",
    )
    p.add_argument("--keep-rows", default="",
                   help="Comma-separated transcript row indices to force-keep (e.g. for picture/graph description exceptions)")
    p.add_argument("--drop-rows", default="",
                   help="Comma-separated transcript row indices to force-drop")
    p.add_argument("--verbose", action="store_true", help="Print alignment debug info")
    return p.parse_args()


_APOSTROPHE_VARIANTS = str.maketrans({
    "\u2018": "'",  # left single quotation mark
    "\u2019": "'",  # right single quotation mark
    "\u2032": "'",  # prime
    "\u0060": "'",  # grave accent
    "\u00b4": "'",  # acute accent
})

# Applied after normalize_base(); longer / more specific patterns first.
_CONTRACTION_SHARED: Tuple[Tuple[str, str], ...] = (
    (r"\bwon't\b", "will not"),
    (r"\bwouldn't\b", "would not"),
    (r"\bshouldn't\b", "should not"),
    (r"\bcouldn't\b", "could not"),
    (r"\bmustn't\b", "must not"),
    (r"\bneedn't\b", "need not"),
    (r"\baren't\b", "are not"),
    (r"\bwasn't\b", "was not"),
    (r"\bweren't\b", "were not"),
    (r"\bhasn't\b", "has not"),
    (r"\bhaven't\b", "have not"),
    (r"\bhadn't\b", "had not"),
    (r"\bdoesn't\b", "does not"),
    (r"\bdon't\b", "do not"),
    (r"\bdidn't\b", "did not"),
    (r"\bisn't\b", "is not"),
    (r"\bcan't\b", "can not"),
    (r"\blet's\b", "let us"),
    (r"\bthat's\b", "that is"),
    (r"\bwhat's\b", "what is"),
    (r"\bwho's\b", "who is"),
    (r"\bwhere's\b", "where is"),
    (r"\bwhen's\b", "when is"),
    (r"\bwhy's\b", "why is"),
    (r"\bhow's\b", "how is"),
    (r"\bhere's\b", "here is"),
    (r"\bthere's\b", "there is"),
    (r"\bit's\b", "it is"),
    (r"\byou're\b", "you are"),
    (r"\bi'm\b", "i am"),
    (r"\bi've\b", "i have"),
    (r"\bi'll\b", "i will"),
    (r"\b([a-z]+)'re\b", r"\1 are"),
    (r"\b([a-z]+)'ve\b", r"\1 have"),
    (r"\b([a-z]+)'ll\b", r"\1 will"),
    (r"\b([a-z]+)'m\b", r"\1 am"),
    (r"\b([a-z]+)n't\b", r"\1 not"),
)

# ``'d`` → would (e.g. you'd ↔ you would).
_CONTRACTION_WOULD_D: Tuple[Tuple[str, str], ...] = (
    (r"\byou'd\b", "you would"),
    (r"\bi'd\b", "i would"),
    (r"\bhe'd\b", "he would"),
    (r"\bshe'd\b", "she would"),
    (r"\bwe'd\b", "we would"),
    (r"\bthey'd\b", "they would"),
    (r"\bit'd\b", "it would"),
    (r"\bwho'd\b", "who would"),
    (r"\bwhat'd\b", "what would"),
    (r"\bthat'd\b", "that would"),
    (r"\bthere'd\b", "there would"),
    (r"\bhere'd\b", "here would"),
    (r"\bwhere'd\b", "where would"),
    (r"\bwhen'd\b", "when would"),
    (r"\bwhy'd\b", "why would"),
    (r"\bhow'd\b", "how would"),
    (r"\b([a-z]+)'d\b", r"\1 would"),
)

# ``'d`` → had (e.g. I'd ↔ I had). ``you'd`` still maps to ``you would`` in both variants.
_CONTRACTION_HAD_D: Tuple[Tuple[str, str], ...] = (
    (r"\byou'd\b", "you would"),
    (r"\bi'd\b", "i had"),
    (r"\bhe'd\b", "he had"),
    (r"\bshe'd\b", "she had"),
    (r"\bwe'd\b", "we had"),
    (r"\bthey'd\b", "they had"),
    (r"\bit'd\b", "it had"),
    (r"\bwho'd\b", "who had"),
    (r"\bwhat'd\b", "what had"),
    (r"\bthat'd\b", "that had"),
    (r"\bthere'd\b", "there had"),
    (r"\bhere'd\b", "here had"),
    (r"\bwhere'd\b", "where had"),
    (r"\bwhen'd\b", "when had"),
    (r"\bwhy'd\b", "why had"),
    (r"\bhow'd\b", "how had"),
    (r"\b([a-z]+)'d\b", r"\1 had"),
)


def _apply_contraction_expanders(text: str, expanders: Tuple[Tuple[str, str], ...]) -> str:
    if not text:
        return text
    out = text
    for pattern, repl in expanders:
        out = re.sub(pattern, repl, out)
    return out


_CARDINAL_ONES: Tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
)
_CARDINAL_TEENS: Tuple[str, ...] = (
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
)
_CARDINAL_TENS: dict[int, str] = {
    10: "ten",
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
}

_ORDINAL_ONES: Tuple[str, ...] = (
    "zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
    "eighth", "ninth",
)
_ORDINAL_TEENS: Tuple[str, ...] = (
    "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
    "sixteenth", "seventeenth", "eighteenth", "nineteenth",
)
_ORDINAL_TENS: dict[int, str] = {
    20: "twentieth",
    30: "thirtieth",
    40: "fortieth",
    50: "fiftieth",
    60: "sixtieth",
    70: "seventieth",
    80: "eightieth",
    90: "ninetieth",
    100: "hundredth",
}


def _cardinal_under_100_to_words(n: int) -> str:
    if n < 0 or n > 99:
        return str(n)
    if n < 10:
        return _CARDINAL_ONES[n]
    if n < 20:
        return _CARDINAL_TEENS[n - 10]
    tens, ones = divmod(n, 10)
    tens_word = _CARDINAL_TENS[tens * 10]
    if ones == 0:
        return tens_word
    return f"{tens_word} {_CARDINAL_ONES[ones]}"


def _ordinal_to_words(n: int) -> str:
    if n <= 0 or n > 100:
        return str(n)
    if n < 10:
        return _ORDINAL_ONES[n]
    if n < 20:
        return _ORDINAL_TEENS[n - 10]
    if n % 10 == 0:
        return _ORDINAL_TENS[n]
    tens, ones = divmod(n, 10)
    return f"{_CARDINAL_TENS[tens * 10]} {_ORDINAL_ONES[ones]}"


def _year_to_words(n: int) -> str:
    if 1900 <= n <= 1999:
        tail = n % 100
        if tail == 0:
            return "nineteen hundred"
        return f"nineteen {_cardinal_under_100_to_words(tail)}"
    if 2000 <= n <= 2099:
        tail = n % 100
        if tail == 0:
            return "two thousand"
        return f"twenty {_cardinal_under_100_to_words(tail)}"
    return str(n)


def expand_numbers_in_text(text: str) -> str:
    """Expand digit/ordinal forms so they match spoken transcript tokens."""
    if not text:
        return text

    def _sub_ordinal(match: re.Match[str]) -> str:
        return _ordinal_to_words(int(match.group(1)))

    out = re.sub(r"\b(\d{1,3})(st|nd|rd|th)\b", _sub_ordinal, text)

    def _sub_year(match: re.Match[str]) -> str:
        return _year_to_words(int(match.group(0)))

    out = re.sub(r"\b(20\d{2}|19\d{2})\b", _sub_year, out)

    def _sub_two_digit(match: re.Match[str]) -> str:
        return _cardinal_under_100_to_words(int(match.group(0)))

    out = re.sub(r"\b(\d{2})\b", _sub_two_digit, out)

    def _sub_one_digit(match: re.Match[str]) -> str:
        return _CARDINAL_ONES[int(match.group(0))]

    out = re.sub(r"\b(\d)\b", _sub_one_digit, out)
    return out


def normalize_base(text: str) -> str:
    """Lowercase, unify apostrophes, drop other punctuation, collapse whitespace."""
    text = text.lower().translate(_APOSTROPHE_VARIANTS)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = expand_numbers_in_text(text)
    return re.sub(r"\s+", " ", text).strip()


def expand_contractions_would(text: str) -> str:
    """Expand contractions with ``'d`` → would (plus shared n't / 're / …)."""
    return _apply_contraction_expanders(text, _CONTRACTION_SHARED + _CONTRACTION_WOULD_D)


def expand_contractions_had(text: str) -> str:
    """Expand contractions with ``'d`` → had (plus shared n't / 're / …)."""
    return _apply_contraction_expanders(text, _CONTRACTION_SHARED + _CONTRACTION_HAD_D)


def expand_contractions(text: str) -> str:
    """Alias for :func:`expand_contractions_would` (backward compatible)."""
    return expand_contractions_would(text)


def normalize_had(text: str) -> str:
    """Like :func:`normalize` but ``'d`` pronouns expand to had where ambiguous."""
    return expand_contractions_had(normalize_base(text))


def normalize(text: str) -> str:
    """Normalized text for matching (would-biased ``'d`` expansion)."""
    return expand_contractions_would(normalize_base(text))


def normalize_pair(text: str) -> Tuple[str, str]:
    """Return (would-expanded, had-expanded) norms for cross-matching."""
    base = normalize_base(text)
    return expand_contractions_would(base), expand_contractions_had(base)


def _norm_substring_match(needle_would: str, needle_had: str, hay_would: str, hay_had: str) -> bool:
    return (
        needle_would in hay_would
        or needle_had in hay_had
        or needle_would in hay_had
        or needle_had in hay_would
    )


def _word_norm(w: str) -> str:
    return normalize(w).strip()


def _find_last_subsequence(haystack: List[str], needle: List[str]) -> Optional[int]:
    """Return the start index of the last occurrence of needle in haystack."""
    if not needle or not haystack or len(needle) > len(haystack):
        return None
    for i in range(len(haystack) - len(needle), -1, -1):
        if haystack[i : i + len(needle)] == needle:
            return i
    return None


def _trim_restart_within_row(row: TranscriptRow, matched_article_text: str) -> Optional[float]:
    """If a row contains a re-read/restart, trim to the last matched article occurrence.

    The rewind logic mostly works at the row level, but sometimes the reader flubs and
    restarts *within* a single transcript row (e.g. "... men never col- ... men never ...").
    When we can locate the matched article words inside the row's word tokens more than
    once, we can safely drop the earlier attempt by moving the row's effective start time.
    """
    if not row.words:
        return None

    # Prefer anchoring on the opening prefix of the matched sentence (more robust than
    # matching the full sentence, since restarts often insert a few wrong words mid-row).
    target_tokens = [_word_norm(t) for t in matched_article_text.split()]
    target_tokens = [t for t in target_tokens if t]
    prefix_len = min(6, len(target_tokens))
    if prefix_len < 4:
        return None
    prefix = target_tokens[:prefix_len]

    row_tokens: List[str] = []
    starts: List[float] = []
    for w in row.words:
        t = _word_norm(w.text)
        if not t:
            continue
        row_tokens.append(t)
        starts.append(w.start)

    if len(row_tokens) < len(prefix):
        return None

    hits: List[int] = []
    for i in range(0, len(row_tokens) - len(prefix) + 1):
        if row_tokens[i : i + len(prefix)] == prefix:
            hits.append(i)
    if len(hits) < 2:
        return None

    last = hits[-1]
    t0 = starts[last]
    return t0 if t0 > row.start + 1e-3 else None


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
            norm, norm_had = normalize_pair(chunk)
            if not norm:
                continue
            out.append(ArticleSentence(
                idx=len(out),
                text=chunk,
                norm=norm,
                norm_had=norm_had,
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
        norm, norm_had = normalize_pair(text)
        out.append(TranscriptRow(
            idx=int(key),
            start=float(v.get("start", 0.0)),
            end=float(v.get("end", 0.0)),
            text=text,
            norm=norm,
            norm_had=norm_had,
            speaker_id=int(v.get("speaker_id", 0)),
            words=words,
        ))
    return out


def sim(a: str, b: str) -> float:
    """Symmetric character-level similarity on normalized strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def sim_match(a: str, a_had: str, b: str, b_had: str) -> float:
    """Best similarity across would/had contraction variants (both directions)."""
    return max(
        sim(a, b),
        sim(a_had, b_had),
        sim(a, b_had),
        sim(a_had, b),
    )


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
        pieces_would: List[str] = []
        pieces_had: List[str] = []
        prev_score = -1.0
        for a_end in range(a_start, min(a_start + max_span, len(article))):
            pieces_would.append(article[a_end].norm)
            pieces_had.append(article[a_end].norm_had)
            candidate_would = " ".join(pieces_would)
            candidate_had = " ".join(pieces_had)
            score = sim_match(row.norm, row.norm_had, candidate_would, candidate_had)
            if score > best[2]:
                best = (a_start, a_end, score)
            if score + 1e-9 < prev_score:
                break
            prev_score = score
    return best


def _single_chunk_substring_match(
    row: TranscriptRow,
    article: List[ArticleSentence],
    last_good: Optional[int],
    current_score: float,
) -> Optional[Tuple[int, int, float]]:
    """If ``row.norm`` occurs verbatim inside one article chunk's norm, prefer that chunk.

    This fixes common failures where a short spoken clause is part of a single long
    article sentence: SequenceMatcher(row, long_sentence) can be low enough that a
    wrong, shorter chunk wins inside the local search window.
    """
    if not row.norm or len(row.norm) < 12 or len(row.norm) > 120:
        return None

    def best_in_range(lo: int, hi: int) -> Optional[Tuple[int, int, float]]:
        best: Optional[Tuple[int, int, float]] = None
        anchor = last_good if last_good is not None else 0
        for i in range(max(0, lo), min(len(article), hi)):
            an = article[i].norm
            an_had = article[i].norm_had
            if not an or not _norm_substring_match(row.norm, row.norm_had, an, an_had):
                continue
            sc = max(sim_match(row.norm, row.norm_had, an, an_had), 0.90)
            if best is None:
                best = (i, i, sc)
                continue
            bi, _, bs = best
            if sc > bs + 1e-9:
                best = (i, i, sc)
            elif abs(sc - bs) < 1e-9 and abs(i - anchor) < abs(bi - anchor):
                best = (i, i, sc)
        return best

    cand_local = (
        best_in_range(last_good - 55, last_good + 56) if last_good is not None else None
    )
    cand_global = best_in_range(0, len(article))
    if cand_local is None and cand_global is None:
        return None
    if cand_local is None:
        cand = cand_global
    elif cand_global is None:
        cand = cand_local
    elif cand_local[2] > cand_global[2] + 1e-9:
        cand = cand_local
    elif cand_global[2] > cand_local[2] + 1e-9:
        cand = cand_global
    else:
        anchor = last_good if last_good is not None else 0
        cand = cand_local if abs(cand_local[0] - anchor) <= abs(cand_global[0] - anchor) else cand_global
    if cand is None or cand[2] <= current_score + 1e-9:
        return None
    return cand


_LOOSE_MATCH_STOPWORDS = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "of", "and", "or", "is", "it", "as", "by",
    "for", "we", "he", "she", "they", "his", "her", "their", "this", "that", "with",
})


def _loose_single_chunk_match(
    row: TranscriptRow,
    article: List[ArticleSentence],
    last_good: Optional[int],
    current_score: float,
) -> Optional[Tuple[int, int, float]]:
    """Fuzzy single-chunk rescues when exact substring fails.

    - Collapsed spaces containment (handles spacing/line-break drift).
    - Stopword-filtered token subset (handles small phrasing differences).
    """
    if not row.norm or len(row.norm) < 12 or len(row.norm) > 120:
        return None

    row_tok_would = [t for t in row.norm.split() if len(t) > 1 and t not in _LOOSE_MATCH_STOPWORDS]
    row_tok_had = [t for t in row.norm_had.split() if len(t) > 1 and t not in _LOOSE_MATCH_STOPWORDS]
    if len(row_tok_would) < 3 and len(row_tok_had) < 3:
        return None

    row_compact_would = row.norm.replace(" ", "")
    row_compact_had = row.norm_had.replace(" ", "")

    def score_chunk(an: str, an_had: str) -> Optional[float]:
        if not an:
            return None
        sc_parts: List[float] = []
        ac_would = an.replace(" ", "")
        ac_had = an_had.replace(" ", "")
        if len(row_compact_would) >= 12 and row_compact_would in ac_would:
            sc_parts.append(0.87)
        if len(row_compact_had) >= 12 and row_compact_had in ac_had:
            sc_parts.append(0.87)
        if len(row_compact_would) >= 12 and row_compact_would in ac_had:
            sc_parts.append(0.87)
        if len(row_compact_had) >= 12 and row_compact_had in ac_would:
            sc_parts.append(0.87)
        ch_set_would = set(an.split())
        ch_set_had = set(an_had.split())
        if row_tok_would and all(t in ch_set_would for t in row_tok_would):
            sc_parts.append(max(0.84, sim_match(row.norm, row.norm_had, an, an_had)))
        if row_tok_had and all(t in ch_set_had for t in row_tok_had):
            sc_parts.append(max(0.84, sim_match(row.norm, row.norm_had, an, an_had)))
        if not sc_parts:
            return None
        return max(sc_parts)

    def best_in_range(lo: int, hi: int) -> Optional[Tuple[int, int, float]]:
        best: Optional[Tuple[int, int, float]] = None
        anchor = last_good if last_good is not None else 0
        for i in range(max(0, lo), min(len(article), hi)):
            sc = score_chunk(article[i].norm, article[i].norm_had)
            if sc is None:
                continue
            if best is None:
                best = (i, i, sc)
                continue
            bi, _, bs = best
            if sc > bs + 1e-9:
                best = (i, i, sc)
            elif abs(sc - bs) < 1e-9 and abs(i - anchor) < abs(bi - anchor):
                best = (i, i, sc)
        return best

    cand_local = (
        best_in_range(last_good - 55, last_good + 56) if last_good is not None else None
    )
    cand_global = best_in_range(0, len(article))
    if cand_local is None and cand_global is None:
        return None
    if cand_local is None:
        cand = cand_global
    elif cand_global is None:
        cand = cand_local
    elif cand_local[2] > cand_global[2] + 1e-9:
        cand = cand_local
    elif cand_global[2] > cand_local[2] + 1e-9:
        cand = cand_global
    else:
        anchor = last_good if last_good is not None else 0
        cand = cand_local if abs(cand_local[0] - anchor) <= abs(cand_global[0] - anchor) else cand_global
    if cand is None or cand[2] <= current_score + 1e-9:
        return None
    return cand


def _match_row_to_article(
    row: TranscriptRow,
    article: List[ArticleSentence],
    max_span: int,
    threshold: float,
    last_good_a_start: Optional[int],
) -> Tuple[Optional[int], Optional[int], float]:
    """Windowed span, full-article retry if weak, then single-chunk substring/loose rescues."""
    a_start, a_end, score = best_multi_match(
        row, article, max_span=max_span, start_hint=last_good_a_start,
    )
    if a_start is None:
        return best_multi_match(row, article, max_span=max_span)

    if score < threshold:
        g_a, g_e, g_s = best_multi_match(row, article, max_span=max_span)
        if g_a is not None and g_s > score + 1e-9:
            a_start, a_end, score = g_a, g_e, g_s

    sub = _single_chunk_substring_match(row, article, last_good_a_start, score)
    if sub is not None:
        a_start, a_end, score = sub

    loose = _loose_single_chunk_match(row, article, last_good_a_start, score)
    if loose is not None:
        a_start, a_end, score = loose

    return a_start, a_end, score


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

        # Reading exception: keep visual and section-header callouts even if
        # they are not part of the canonical article text.
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

        # Windowed span match for speed + reading-order locality. When the local best
        # is weak, retry globally and then allow single-chunk substring/loose rescues
        # so short clauses inside long article sentences aren't dropped.
        a_start, a_end, score = _match_row_to_article(
            row, article, max_span, threshold, last_good_a_start,
        )

        off_script = score < threshold and row.idx not in force_keep
        if (
            not off_script
            and row.idx not in force_drop
            and row.idx not in force_keep
            and a_start is not None
            and a_end is not None
        ):
            # If the reader restarts *within* a row, trim to the last correct take.
            matched_text = " ".join(article[i].text for i in range(a_start, a_end + 1))
            trimmed_start = _trim_restart_within_row(row, matched_text)
            if trimmed_start is not None:
                row.trim_start = trimmed_start

        # Forced rows can still get a junk article span; don't advance the hint from them
        # unless they actually clear the threshold.
        if not off_script and a_start is not None:
            if row.idx not in force_keep or score >= threshold:
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
    if m.a_start < 0 or m.a_end >= len(article) or m.a_start > m.a_end:
        return ""
    return " ".join(article[i].norm for i in range(m.a_start, m.a_end + 1))


def _combined_rows_similarity(rows: List[TranscriptRow], article_norm: str) -> float:
    joined = normalize(" ".join(row.text for row in rows))
    return sim(joined, article_norm)


def _article_span_tokens(
    article: List[ArticleSentence],
    a_start: int,
    a_end: int,
) -> List[str]:
    if a_start < 0 or a_end >= len(article) or a_start > a_end:
        return []
    return normalize(
        " ".join(article[i].text for i in range(a_start, a_end + 1))
    ).split()


def _row_tokens(row: TranscriptRow) -> List[str]:
    return normalize(row.text).split()


def _token_subsequence_coverage(
    utterance_tokens: List[str],
    article_tokens: List[str],
) -> float:
    """Fraction of article_tokens matched in order within utterance_tokens."""
    if not article_tokens:
        return 1.0
    j = 0
    for t in utterance_tokens:
        if j < len(article_tokens) and t == article_tokens[j]:
            j += 1
    return j / len(article_tokens)


def _first_matched_article_token_index(
    utterance_tokens: List[str],
    article_tokens: List[str],
) -> Optional[int]:
    j = 0
    first_idx: Optional[int] = None
    for t in utterance_tokens:
        if j < len(article_tokens) and t == article_tokens[j]:
            if first_idx is None:
                first_idx = j
            j += 1
    return first_idx


def _combined_match_tokens(matches: List[RowMatch]) -> List[str]:
    ordered = sorted(matches, key=lambda m: m.row.idx)
    return normalize(" ".join(m.row.text for m in ordered)).split()


def _skip_stumble_tokens(tokens: List[str]) -> List[str]:
    """Drop obvious false-start fragments that block ordered article matching."""
    out: List[str] = []
    for t in tokens:
        if t in {"uh", "um", "er", "ah"}:
            continue
        if t.endswith("--"):
            continue
        out.append(t)
    return out


def _advance_article_cursor(
    utterance_tokens: List[str],
    article_tokens: List[str],
    start_j: int = 0,
) -> int:
    j = start_j
    for t in utterance_tokens:
        if j < len(article_tokens) and t == article_tokens[j]:
            j += 1
    return j


def _row_article_cursor(
    match: RowMatch,
    article_tokens: List[str],
    start_j: int = 0,
    *,
    skip_stumbles: bool = True,
) -> int:
    tokens = _row_tokens(match.row)
    if skip_stumbles:
        tokens = _skip_stumble_tokens(tokens)
    return _advance_article_cursor(tokens, article_tokens, start_j)


def _ordered_span_coverage(
    matches: List[RowMatch],
    article_tokens: List[str],
    *,
    skip_stumbles: bool = True,
) -> float:
    """Fraction of article_tokens matched in order across rows (transcript order)."""
    if not article_tokens:
        return 1.0
    j = 0
    for m in sorted(matches, key=lambda x: x.row.idx):
        tokens = _row_tokens(m.row)
        if skip_stumbles:
            tokens = _skip_stumble_tokens(tokens)
        j = _advance_article_cursor(tokens, article_tokens, j)
    return j / len(article_tokens)


def _is_complementary_span_pair(
    earlier: RowMatch,
    later: RowMatch,
    article_tokens: List[str],
) -> bool:
    """True when *later* continues *earlier* through the article (not a duplicate re-read)."""
    if earlier.row.idx >= later.row.idx:
        return False
    if not article_tokens:
        return False

    j_e = _row_article_cursor(earlier, article_tokens, 0)
    j_el = _row_article_cursor(later, article_tokens, j_e)
    j_l = _row_article_cursor(later, article_tokens, 0)
    n = len(article_tokens)

    if j_el <= max(j_e, j_l) + 1:
        return False
    # Two full reads of the same span — keep only the stronger take.
    if j_e >= 0.45 * n and j_l >= 0.45 * n and abs(j_e - j_l) <= 2:
        return False

    gain_frac = (j_el - max(j_e, j_l)) / n
    if gain_frac >= STITCH_COVERAGE_GAIN:
        return True
    return j_e >= 3 and j_el > j_e + 1


def _matches_span_coverage(
    matches: List[RowMatch],
    article: List[ArticleSentence],
    a_start: int,
    a_end: int,
) -> float:
    article_tokens = _article_span_tokens(article, a_start, a_end)
    if not article_tokens:
        return 1.0
    ordered = _ordered_span_coverage(matches, article_tokens)
    article_norm = _article_span_norm(article, a_start, a_end)
    if not article_norm:
        return ordered
    sim = _combined_rows_similarity(
        [m.row for m in sorted(matches, key=lambda x: x.row.idx)],
        article_norm,
    )
    return max(ordered, sim)


def _same_span_should_stitch(
    earlier: RowMatch,
    later: RowMatch,
    article: List[ArticleSentence],
) -> bool:
    """True when two same-span rows complement each other (continuation), not duplicate re-reads."""
    if earlier.a_start is None or later.a_start is None:
        return False
    if earlier.a_start != later.a_start or earlier.a_end != later.a_end:
        return False
    if earlier.row.idx >= later.row.idx:
        return False

    article_tokens = _article_span_tokens(article, earlier.a_start, earlier.a_end)
    if len(article_tokens) < 4:
        return False

    return _is_complementary_span_pair(earlier, later, article_tokens)


def _eligible_gap_fill_row(candidate: RowMatch, force_keep: set) -> bool:
    if candidate.row.idx in force_keep or candidate.keep_anyway:
        return True
    if not candidate.off_script:
        return True
    return candidate.similarity >= GAP_FILL_OFF_SCRIPT_MIN_SIM


def _can_rescue_stitch_candidate(
    candidate: RowMatch,
    kept_on_span: List[RowMatch],
    article: List[ArticleSentence],
    *,
    force_keep: set,
) -> bool:
    if candidate.a_start is None or candidate.a_end is None:
        return False
    if candidate.row.idx in force_keep:
        return True
    a_start, a_end = candidate.a_start, candidate.a_end
    article_tokens = _article_span_tokens(article, a_start, a_end)
    if len(article_tokens) < 4:
        return False

    before_cov = _matches_span_coverage(kept_on_span, article, a_start, a_end)
    trial = sorted(kept_on_span + [candidate], key=lambda m: m.row.idx)
    after_cov = _matches_span_coverage(trial, article, a_start, a_end)
    if after_cov <= before_cov + STITCH_COVERAGE_GAIN:
        return False

    if not _eligible_gap_fill_row(candidate, force_keep):
        return False

    for kept in kept_on_span:
        earlier, later = (
            (candidate, kept) if candidate.row.idx < kept.row.idx else (kept, candidate)
        )
        if earlier.row.idx == later.row.idx:
            continue
        if _is_complementary_span_pair(earlier, later, article_tokens):
            return True
    return after_cov > before_cov + STITCH_COVERAGE_GAIN


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
    gap = tail_cluster[0].row.idx - current.row.idx
    if gap < 1 or gap > MAX_STITCH_GAP_ROWS:
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


def _trailing_cursor_continuation(
    prev_m: RowMatch,
    candidate: RowMatch,
    article_tokens: List[str],
) -> bool:
    """True when *candidate* continues the article cursor after *prev_m*."""
    j_prev = _row_article_cursor(prev_m, article_tokens, 0)
    j_after = _row_article_cursor(candidate, article_tokens, j_prev)
    return j_after > j_prev + 1


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
        gap = right.row.idx - left.row.idx
        if gap < 1 or gap > MAX_STITCH_GAP_ROWS:
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


def _article_span_norm(
    article: List[ArticleSentence],
    a_start: int,
    a_end: int,
) -> str:
    if a_start < 0 or a_end >= len(article) or a_start > a_end:
        return ""
    return " ".join(article[i].norm for i in range(a_start, a_end + 1))


def _row_norm_is_prefix_of_article_span(
    row_norm: str,
    article: List[ArticleSentence],
    a_start: int,
    a_end: int,
    *,
    min_len: int = 12,
) -> bool:
    """True when ``row_norm`` is a leading substring of the matched article span."""
    if not row_norm or len(row_norm) < min_len:
        return False
    if a_start is None or a_end is None or a_start < 0 or a_end >= len(article):
        return False
    span_norm = _article_span_norm(article, a_start, a_end)
    if not span_norm.startswith(row_norm):
        return False
    # Require a proper prefix (first half of a split sentence), not the full span text.
    if len(row_norm) >= len(span_norm):
        return False
    return span_norm[len(row_norm)] == " "


def _can_rescue_prefix_chunk_pair(
    prefix_row: RowMatch,
    kept_partner: RowMatch,
    article: List[ArticleSentence],
) -> bool:
    """Keep the first half of a split article sentence when the next row kept the span."""
    if kept_partner.a_start is None or kept_partner.a_end is None:
        return False
    if prefix_row.row.idx + 1 != kept_partner.row.idx:
        return False
    return _row_norm_is_prefix_of_article_span(
        prefix_row.row.norm,
        article,
        kept_partner.a_start,
        kept_partner.a_end,
    )


def _augment_prefix_chunk_pairs(
    matches: List[RowMatch],
    kept: List[RowMatch],
    article: List[ArticleSentence],
    selection_notes: List[str],
) -> List[RowMatch]:
    """Rescue a dropped row when it is the spoken prefix of a kept partner's article span."""
    kept_by_idx = {m.row.idx: m for m in kept}

    for i in range(len(matches) - 1):
        prefix = matches[i]
        partner = matches[i + 1]
        gap = partner.row.idx - prefix.row.idx
        if gap < 1 or gap > MAX_STITCH_GAP_ROWS:
            continue
        if partner.row.idx not in kept_by_idx:
            continue
        if prefix.row.idx in kept_by_idx:
            continue
        kept_partner = kept_by_idx[partner.row.idx]
        if not _can_rescue_prefix_chunk_pair(prefix, kept_partner, article):
            continue

        kept_by_idx[prefix.row.idx] = RowMatch(
            row=prefix.row,
            a_start=kept_partner.a_start,
            a_end=kept_partner.a_end,
            similarity=max(prefix.similarity, 0.88),
            off_script=False,
        )
        selection_notes.append(
            f"Rescued prefix chunk: kept row {prefix.row.idx} as lead-in to row "
            f"{partner.row.idx} for article [{kept_partner.a_start}:{kept_partner.a_end}]"
        )

    return sorted(kept_by_idx.values(), key=lambda m: m.row.idx)


def _is_strictly_superseded_by_later_kept(
    m: RowMatch,
    kept_reversed: List[RowMatch],
) -> bool:
    """True when a later (already kept) row's article span fully contains m's and is larger.

    Equal spans are handled separately (best-similarity wins) so a weak fuzzy match on a
    header cannot drop a strong read of the same chunk, and split-chunk pairs are not
  treated as supersets."""
    if m.a_start is None or m.a_end is None:
        return False
    for k in kept_reversed:
        if k.a_start is None or k.a_end is None:
            continue
        if k.a_start <= m.a_start and k.a_end >= m.a_end:
            if k.a_start < m.a_start or k.a_end > m.a_end:
                return True
    return False


def _try_replace_same_span_weaker_match(
    m: RowMatch,
    kept_reversed: List[RowMatch],
    *,
    allow_adjacent: bool = False,
    force_keep: Optional[set] = None,
    article: Optional[List[ArticleSentence]] = None,
) -> Optional[str]:
    """If a later kept row matches the same article span, keep the higher-similarity row.

    Returns ``"replaced"``, ``"dropped_weaker"``, ``"stitch"``, or ``None``.
    """
    if m.a_start is None or m.a_end is None:
        return None
    fk = force_keep or set()
    for i, k in enumerate(kept_reversed):
        if k.a_start != m.a_start or k.a_end != m.a_end:
            continue
        if article is not None and 1 <= abs(m.row.idx - k.row.idx) <= MAX_STITCH_GAP_ROWS:
            earlier, later = (m, k) if m.row.idx < k.row.idx else (k, m)
            if _same_span_should_stitch(earlier, later, article):
                return "stitch"
        # Consecutive rows on one chunk are often one sentence split in two; let
        # split-chunk rescue decide instead of keeping only the higher-sim half.
        if not allow_adjacent and abs(m.row.idx - k.row.idx) == 1:
            return None
        if m.similarity > k.similarity + 1e-6:
            if k.row.idx in fk:
                return "dropped_weaker"
            kept_reversed[i] = m
            return "replaced"
        if m.row.idx in fk:
            return None
        return "dropped_weaker"
    return None


def select_kept(
    matches: List[RowMatch],
    force_keep: set,
    article: List[ArticleSentence],
) -> Tuple[List[RowMatch], List[str]]:
    """Walk rows in reverse and build the final take set.

    - Drop a row when a later kept row's article span **strictly contains** its span
      (true rewind: a later row re-read from an earlier chunk through more text).
    - For the **same** article span, keep the highest-similarity row (drops weak late
      fuzzy matches that would otherwise erase a good earlier read of that chunk).
    - Adjacent rows on the same span can still be rescued as a split-chunk pair.
    """
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

        same_span = _try_replace_same_span_weaker_match(
            m, kept_reversed, force_keep=force_keep, article=article,
        )
        if same_span == "dropped_weaker":
            continue
        if same_span == "replaced":
            continue
        if same_span == "stitch":
            kept_reversed.append(m)
            selection_notes.append(
                f"Stitched continuation: kept row {m.row.idx} with same-span partner(s) "
                f"for article [{m.a_start}:{m.a_end}]"
            )
            continue

        if _is_strictly_superseded_by_later_kept(m, kept_reversed):
            continue

        if kept_reversed:
            tail_cluster = _tail_same_range_cluster(kept_reversed, m.a_start, m.a_end)
            if tail_cluster and m.a_start == tail_cluster[0].a_start:
                if _should_keep_split_chunk(m, tail_cluster, article):
                    kept_reversed.append(m)
                    covered_rows = ",".join(str(k.row.idx) for k in reversed(tail_cluster))
                    selection_notes.append(
                        f"Rescued split chunk: kept row {m.row.idx} together with later row(s) "
                        f"{covered_rows} for article [{m.a_start}:{m.a_end}]"
                    )
                    continue
                if abs(m.row.idx - tail_cluster[0].row.idx) == 1:
                    # Same chunk, consecutive rows, but not a complementary split → duplicate take.
                    same_span = _try_replace_same_span_weaker_match(
                        m, kept_reversed, allow_adjacent=True, force_keep=force_keep,
                        article=article,
                    )
                    if same_span in ("dropped_weaker", "replaced"):
                        continue

        if m.off_script and m.row.idx not in force_keep:
            continue
        kept_reversed.append(m)
    kept_reversed.reverse()
    kept = _augment_split_chunk_pairs(matches, kept_reversed, article, selection_notes)
    kept = _augment_prefix_chunk_pairs(matches, kept, article, selection_notes)
    kept = _augment_same_span_stitches(matches, kept, article, selection_notes, force_keep)
    kept = _augment_gap_fill_rows(matches, kept, article, selection_notes, force_keep)
    kept = _prune_spurious_kept_rows(kept, article, force_keep, selection_notes)
    return kept, selection_notes


def _augment_same_span_stitches(
    matches: List[RowMatch],
    kept: List[RowMatch],
    article: List[ArticleSentence],
    selection_notes: List[str],
    force_keep: set,
) -> List[RowMatch]:
    """Rescue dropped/off rows on the same article span when they fill coverage gaps."""
    kept_by_idx = {m.row.idx: m for m in kept}
    spans: dict[Tuple[int, int], List[RowMatch]] = {}
    for m in kept:
        if m.a_start is None or m.a_end is None:
            continue
        spans.setdefault((m.a_start, m.a_end), []).append(m)

    for (a_start, a_end), kept_on_span in spans.items():
        if a_start < 0 or a_end >= len(article):
            continue
        article_tokens = _article_span_tokens(article, a_start, a_end)
        if len(article_tokens) < MIN_ARTICLE_WORDS_PARTIAL:
            continue

        current = sorted(kept_on_span, key=lambda m: m.row.idx)
        coverage = _matches_span_coverage(current, article, a_start, a_end)
        if coverage >= PARTIAL_COVERAGE_THRESHOLD:
            continue

        min_idx = current[0].row.idx
        max_idx = current[-1].row.idx
        candidates = [
            m
            for m in matches
            if m.a_start == a_start
            and m.a_end == a_end
            and m.row.idx not in kept_by_idx
            and min_idx - MAX_STITCH_GAP_ROWS <= m.row.idx <= max_idx + MAX_STITCH_GAP_ROWS
        ]

        improved = True
        while improved and coverage < PARTIAL_COVERAGE_THRESHOLD:
            improved = False
            best: Optional[RowMatch] = None
            best_cov = coverage
            for cand in sorted(candidates, key=lambda m: m.row.idx):
                if cand.row.idx in kept_by_idx:
                    continue
                if not _can_rescue_stitch_candidate(
                    cand, current, article, force_keep=force_keep
                ):
                    continue
                trial_cov = _matches_span_coverage(
                    sorted(current + [cand], key=lambda m: m.row.idx),
                    article,
                    a_start,
                    a_end,
                )
                if trial_cov > best_cov + STITCH_COVERAGE_GAIN:
                    best = cand
                    best_cov = trial_cov
            if best is not None:
                rescued = RowMatch(
                    row=best.row,
                    a_start=best.a_start,
                    a_end=best.a_end,
                    similarity=max(best.similarity, 0.88),
                    off_script=False,
                    keep_anyway=best.keep_anyway,
                )
                kept_by_idx[rescued.row.idx] = rescued
                current = sorted(current + [rescued], key=lambda m: m.row.idx)
                coverage = best_cov
                improved = True
                selection_notes.append(
                    f"Rescued stitch row {rescued.row.idx} for article [{a_start}:{a_end}] "
                    f"(coverage -> {coverage:.0%})"
                )

    return sorted(kept_by_idx.values(), key=lambda m: m.row.idx)


def _augment_gap_fill_rows(
    matches: List[RowMatch],
    kept: List[RowMatch],
    article: List[ArticleSentence],
    selection_notes: List[str],
    force_keep: set,
) -> List[RowMatch]:
    """Rescue dropped rows that sit in transcript gaps between kept same-span takes."""
    kept_by_idx = {m.row.idx: m for m in kept}
    match_by_idx = {m.row.idx: m for m in matches}

    spans: dict[Tuple[int, int], List[RowMatch]] = {}
    for m in kept:
        if m.a_start is not None and m.a_end is not None:
            spans.setdefault((m.a_start, m.a_end), []).append(m)

    for (a_start, a_end), kept_on_span in spans.items():
        article_tokens = _article_span_tokens(article, a_start, a_end)
        if len(article_tokens) < 4:
            continue

        improved = True
        while improved:
            improved = False
            span_kept = sorted(
                [m for m in kept_by_idx.values() if m.a_start == a_start and m.a_end == a_end],
                key=lambda m: m.row.idx,
            )
            if not span_kept:
                break
            kept_ids = {m.row.idx for m in span_kept}
            coverage = _matches_span_coverage(span_kept, article, a_start, a_end)
            min_idx = span_kept[0].row.idx
            max_idx = span_kept[-1].row.idx

            best: Optional[RowMatch] = None
            best_cov = coverage
            best_label = ""

            for cand in matches:
                if cand.row.idx in kept_by_idx:
                    continue
                if not _eligible_gap_fill_row(cand, force_keep):
                    continue

                prev_kept = max((i for i in kept_ids if i < cand.row.idx), default=None)
                next_kept = min((i for i in kept_ids if i > cand.row.idx), default=None)

                on_span = cand.a_start == a_start and cand.a_end == a_end
                rescue_match = cand
                if not on_span:
                    if prev_kept is None:
                        continue
                    prev_m = kept_by_idx[prev_kept]
                    if cand.row.idx - prev_kept > MAX_STITCH_GAP_ROWS:
                        continue
                    article_tokens = _article_span_tokens(article, prev_m.a_start, prev_m.a_end)
                    if not (
                        _can_rescue_row_in_split_pair(cand, [prev_m], article)
                        or _trailing_cursor_continuation(prev_m, cand, article_tokens)
                    ):
                        continue
                    rescue_match = RowMatch(
                        row=cand.row,
                        a_start=prev_m.a_start,
                        a_end=prev_m.a_end,
                        similarity=max(cand.similarity, 0.88),
                        off_script=False,
                        keep_anyway=cand.keep_anyway,
                    )
                    label = f"after row {prev_kept} (re-aligned span)"
                elif prev_kept is not None and next_kept is not None:
                    if not (prev_kept < cand.row.idx < next_kept):
                        continue
                    if cand.row.idx - prev_kept > MAX_STITCH_GAP_ROWS:
                        continue
                    if next_kept - cand.row.idx > MAX_STITCH_GAP_ROWS:
                        continue
                    label = f"between rows {prev_kept} and {next_kept}"
                elif prev_kept is not None:
                    gap = cand.row.idx - prev_kept
                    if gap < 1 or gap > MAX_STITCH_GAP_ROWS:
                        continue
                    label = f"after row {prev_kept}"
                elif next_kept is not None:
                    gap = next_kept - cand.row.idx
                    if gap < 1 or gap > MAX_STITCH_GAP_ROWS:
                        continue
                    label = f"before row {next_kept}"
                else:
                    continue

                if cand.row.idx < min_idx - MAX_STITCH_GAP_ROWS or cand.row.idx > max_idx + MAX_STITCH_GAP_ROWS:
                    continue

                trial = sorted(span_kept + [rescue_match], key=lambda m: m.row.idx)
                after_cov = _matches_span_coverage(trial, article, a_start, a_end)
                needed_gain = STITCH_COVERAGE_GAIN
                if (
                    prev_kept is not None
                    and next_kept is not None
                    and prev_kept < cand.row.idx < next_kept
                ):
                    needed_gain = GAP_FILL_MIDDLE_GAIN
                if after_cov <= best_cov + needed_gain:
                    continue

                if after_cov > best_cov + needed_gain:
                    best = rescue_match
                    best_cov = after_cov
                    best_label = label

            if best is not None:
                rescued = RowMatch(
                    row=best.row,
                    a_start=best.a_start,
                    a_end=best.a_end,
                    similarity=max(best.similarity, 0.88),
                    off_script=False,
                    keep_anyway=best.keep_anyway,
                )
                kept_by_idx[rescued.row.idx] = rescued
                improved = True
                selection_notes.append(
                    f"Gap-fill: kept row {rescued.row.idx} {best_label} "
                    f"for article [{a_start}:{a_end}] (coverage -> {best_cov:.0%})"
                )

    return sorted(kept_by_idx.values(), key=lambda m: m.row.idx)


def _prune_spurious_kept_rows(
    kept: List[RowMatch],
    article: List[ArticleSentence],
    force_keep: set,
    selection_notes: List[str],
) -> List[RowMatch]:
    """Drop kept rows that barely overlap their matched article span (e.g. footer junk)."""
    by_span: dict[Tuple[int, int], List[RowMatch]] = {}
    for m in kept:
        if m.a_start is not None and m.a_end is not None:
            by_span.setdefault((m.a_start, m.a_end), []).append(m)

    pruned: List[RowMatch] = []
    for m in kept:
        if m.row.idx in force_keep or m.keep_anyway:
            pruned.append(m)
            continue
        if m.a_start is None or m.a_end is None:
            pruned.append(m)
            continue
        article_tokens = _article_span_tokens(article, m.a_start, m.a_end)
        if not article_tokens:
            selection_notes.append(
                f"Pruned spurious kept row {m.row.idx} "
                f"(invalid article span [{m.a_start}:{m.a_end}])"
            )
            continue

        span_mates = [
            k for k in by_span.get((m.a_start, m.a_end), [])
            if k.row.idx != m.row.idx
        ]
        if span_mates:
            with_cov = _matches_span_coverage(
                span_mates + [m], article, m.a_start, m.a_end,
            )
            without_cov = _matches_span_coverage(
                span_mates, article, m.a_start, m.a_end,
            )
            if with_cov > without_cov + STITCH_COVERAGE_GAIN:
                pruned.append(m)
                continue

        cov = _token_subsequence_coverage(_row_tokens(m.row), article_tokens)
        if cov >= SPURIOUS_COVERAGE_FLOOR:
            pruned.append(m)
            continue
        if len(article_tokens) < MIN_ARTICLE_WORDS_PARTIAL:
            selection_notes.append(
                f"Pruned spurious kept row {m.row.idx} (coverage {cov:.0%} on "
                f"short article [{m.a_start}:{m.a_end}])"
            )
            continue
        selection_notes.append(
            f"Pruned spurious kept row {m.row.idx} (coverage {cov:.0%} on "
            f"article [{m.a_start}:{m.a_end}])"
        )
    return pruned


def apply_overlap_tail_trim(
    kept: List[RowMatch],
    article: List[ArticleSentence],
    selection_notes: Optional[List[str]] = None,
) -> None:
    """Trim earlier kept rows when a consecutive later row retakes overlapping article chunks.

    ``select_kept`` can keep row *i* because its article match *starts* before row *i+1*,
    even when *i*'s range still includes audio for chunks that *i+1* re-reads correctly
    (e.g. *i* matches [202:203] while *i+1* matches [203:203]). Drop the overlapping tail
    on *i* by setting ``row.trim_end`` after the last word that completes the exclusive
    prefix ``article[i.a_start : i+1.a_start]``.
    """
    if selection_notes is None:
        selection_notes = []

    def merge_trim_end(row: TranscriptRow, candidate_end: float) -> None:
        lo = _row_effective_start(row)
        if candidate_end <= lo + 0.05:
            return
        if row.trim_end is None:
            row.trim_end = candidate_end
        else:
            row.trim_end = min(row.trim_end, candidate_end)

    ordered = sorted(kept, key=lambda m: m.row.idx)
    for i in range(len(ordered) - 1):
        prev_m, nxt_m = ordered[i], ordered[i + 1]
        pr, nx = prev_m.row, nxt_m.row
        if nx.idx != pr.idx + 1:
            continue
        if prev_m.a_start is None or prev_m.a_end is None or nxt_m.a_start is None or nxt_m.a_end is None:
            continue
        if prev_m.a_end < nxt_m.a_start:
            continue

        if nxt_m.a_start <= prev_m.a_start:
            # Same or earlier article chunk start: treat ``nx`` as a continuation take.
            cut = nx.start - 2e-2
            last_end = pr.start
            for w in pr.words or []:
                if w.end <= cut:
                    last_end = max(last_end, w.end)
            if last_end > pr.start + 0.05:
                merge_trim_end(pr, last_end)
                selection_notes.append(
                    f"Overlap tail trim: row {pr.idx} end -> {last_end:.2f}s "
                    f"(continuation row {nx.idx} at t={nx.start:.2f}s)"
                )
            continue

        prefix_parts = [article[j].text for j in range(prev_m.a_start, nxt_m.a_start)]
        want_tokens = normalize(" ".join(prefix_parts).strip()).split()
        if not want_tokens:
            continue

        wi = 0
        last_end: Optional[float] = None
        ok = True
        for w in pr.words or []:
            for tok in normalize(w.text).split():
                if not tok:
                    continue
                if wi >= len(want_tokens):
                    break
                if tok == want_tokens[wi]:
                    wi += 1
                    last_end = w.end
                else:
                    ok = False
                    break
            if not ok:
                break
            if wi >= len(want_tokens):
                break

        if not ok or last_end is None or wi < len(want_tokens):
            continue

        merge_trim_end(pr, last_end)
        selection_notes.append(
            f"Overlap tail trim: row {pr.idx} end -> {last_end:.2f}s "
            f"(exclusive article chunks [{prev_m.a_start}:{nxt_m.a_start - 1}])"
        )


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
        eff_end = _row_effective_end(row)
        if row.words:
            for w in row.words:
                if w.end > eff_end + 1e-3:
                    continue
                t = w.text.strip().rstrip('"\'')  # tolerate quoted tokens
                if not t:
                    continue
                if t.endswith("?") or t.endswith("!") or t.endswith("."):
                    ts.add(w.end)
        else:
            ts.add(eff_end)
    return sorted(ts)


def collect_linguistic_boundary_times(span_rows: List[TranscriptRow]) -> List[float]:
    """Absolute boundary times at true word ends for comma boundaries.
    Uses word-level timestamps when available; falls back to row edges."""
    ts: set[float] = set()
    for row in span_rows:
        ts.add(_row_effective_start(row))
        ts.add(_row_effective_end(row))
        if row.words:
            eff_end = _row_effective_end(row)
            for w in row.words:
                if w.end > eff_end + 1e-3:
                    continue
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
        a = _row_effective_start(row)
        b = _row_effective_end(row)
        out.append(SubClip(row=row, a=a, b=b, cam=main_cam))
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


_WORD_OVERLAP_EPS = 1e-3


def _last_word_end_in_subclip(row: TranscriptRow, a: float, b: float) -> float:
    """Latest word end time among words overlapping [a, b); falls back to ``b`` if none."""
    if not row.words:
        return b
    e = _WORD_OVERLAP_EPS
    ends: List[float] = []
    for w in row.words:
        if w.start >= b - e:
            continue
        if w.end <= a + e:
            continue
        ends.append(min(w.end, b))
    if not ends:
        return b
    return min(b, max(ends))


def _next_word_start_after(row: TranscriptRow, t: float) -> Optional[float]:
    """Smallest word start strictly after ``t`` on this row, or None."""
    if not row.words:
        return None
    e = _WORD_OVERLAP_EPS
    best: Optional[float] = None
    for w in row.words:
        if w.start <= t + e:
            continue
        best = w.start if best is None else min(best, w.start)
    return best


def apply_post_word_tail_extension(
    subclips: List[SubClip],
    tail_sec: float,
    eps: float = 1e-3,
) -> None:
    """Extend each subclip's end by ``tail_sec`` after the last word in the clip, without
    crossing into the next word on the row, the next subclip on the same row, the next
    timeline subclip on a different row, or the row's effective end (``trim_end`` /
    ``row.end``)."""
    if tail_sec <= 0 or not subclips:
        return

    n = len(subclips)
    next_same_row_j: List[Optional[int]] = [None] * n
    for i in range(n):
        for j in range(i + 1, n):
            if subclips[j].row.idx == subclips[i].row.idx:
                next_same_row_j[i] = j
                break

    for i, c in enumerate(subclips):
        row = c.row
        L = _last_word_end_in_subclip(row, c.a, c.b)
        target_b = L + tail_sec
        hard_max = _row_effective_end(row)

        nw = _next_word_start_after(row, L)
        if nw is not None:
            hard_max = min(hard_max, nw - eps)

        j = next_same_row_j[i]
        if j is not None:
            hard_max = min(hard_max, subclips[j].a - eps)
        elif i + 1 < n:
            nxt = subclips[i + 1]
            if nxt.row.idx != c.row.idx:
                hard_max = min(hard_max, nxt.a - eps)

        new_b = min(target_b, hard_max)
        if new_b > c.b + _WORD_OVERLAP_EPS:
            c.b = new_b

    for i in range(n - 1):
        if subclips[i].b > subclips[i + 1].a - eps:
            subclips[i].b = subclips[i + 1].a - eps


# --- Optional inter-word silence shortening (same rules as shorten_reading_dsl_silences.py) ---


def _inter_word_shorten_other_cam(cam: str, front: str, side: str) -> str:
    if cam == front:
        return side
    if cam == side:
        return front
    raise ValueError(f"Camera {cam!r} is not front={front!r} nor side={side!r}")


def _inter_word_shorten_flat_tokens(subclips: List[SubClip]) -> List[Tuple[float, float, int]]:
    out: List[Tuple[float, float, int]] = []
    for si, sc in enumerate(subclips):
        if sc.b <= sc.a + 1e-6:
            continue
        if sc.row.words:
            for w in sc.row.words:
                if w.end <= sc.a or w.start >= sc.b:
                    continue
                out.append((w.start, w.end, si))
        else:
            out.append((sc.a, sc.b, si))
    out.sort(key=lambda t: (t[0], t[1], t[2]))
    return out


def _inter_word_shorten_row_spans(subclips: List[SubClip]) -> List[List[SubClip]]:
    if not subclips:
        return []
    spans: List[List[SubClip]] = []
    cur: List[SubClip] = [subclips[0]]
    for c in subclips[1:]:
        if c.row.idx == cur[-1].row.idx + 1:
            cur.append(c)
        else:
            spans.append(cur)
            cur = [c]
    spans.append(cur)
    return spans


def _inter_word_shorten_apply_one_gap(
    subclips: List[SubClip],
    i_left: int,
    i_right: int,
    tail_end: float,
    lead_start: float,
    front: str,
    side: str,
) -> bool:
    left = subclips[i_left]
    right = subclips[i_right]

    if i_left == i_right:
        tail_end = min(max(tail_end, left.a + 1e-3), left.b)
        lead_start = min(max(lead_start, left.a + 1e-3), left.b)
        if lead_start <= tail_end + 1e-4:
            return False
        cam2 = _inter_word_shorten_other_cam(left.cam, front, side)
        first = SubClip(row=left.row, a=left.a, b=tail_end, cam=left.cam)
        second = SubClip(
            row=left.row, a=lead_start, b=left.b, cam=cam2, shorten_join_before=True,
        )
        subclips[i_left : i_left + 1] = [first, second]
        return True

    tail_end = min(max(tail_end, left.a + 1e-3), left.b)
    lead_start = min(max(lead_start, right.a + 1e-3), right.b)

    changed = False
    if left.b > tail_end + 1e-6:
        left.b = tail_end
        changed = True
    if right.a < lead_start - 1e-6:
        right.a = lead_start
        changed = True

    if i_right > i_left + 1:
        to_remove: List[int] = []
        for k in range(i_left + 1, i_right):
            sc = subclips[k]
            if sc.a >= tail_end - 1e-6 and sc.b <= lead_start + 1e-6:
                to_remove.append(k)
                continue
            if sc.a < tail_end:
                sc.a = min(max(sc.a, tail_end), sc.b - 1e-3)
            if sc.b > lead_start:
                sc.b = max(min(sc.b, lead_start), sc.a + 1e-3)
            if sc.b <= sc.a + 1e-4:
                to_remove.append(k)
        for k in reversed(to_remove):
            del subclips[k]
            changed = True

    try:
        li = subclips.index(left)
        ri = subclips.index(right)
    except ValueError:
        return changed
    if ri == li + 1:
        if right.cam == left.cam:
            right.cam = _inter_word_shorten_other_cam(left.cam, front, side)
            changed = True
    elif ri > li + 1:
        nxt = subclips[li + 1]
        if nxt.cam == left.cam:
            nxt.cam = _inter_word_shorten_other_cam(left.cam, front, side)
            changed = True
    if changed:
        try:
            li = subclips.index(left)
            if li + 1 < len(subclips):
                subclips[li + 1].shorten_join_before = True
        except ValueError:
            pass
    return changed


def _inter_word_shorten_run_passes(
    subclips: List[SubClip],
    front: str,
    side: str,
    min_silence: float,
    tail_sec: float,
    lead_sec: float,
) -> None:
    resolved: set[Tuple[float, float]] = set()
    max_passes = max(64, len(subclips) * 24)
    for _ in range(max_passes):
        flat = _inter_word_shorten_flat_tokens(subclips)
        if len(flat) < 2:
            break
        progressed = False
        for idx in range(len(flat) - 1):
            _w0s, w0e, i0 = flat[idx]
            w1s, _w1e, i1 = flat[idx + 1]
            gap = w1s - w0e
            if gap + 1e-6 < min_silence:
                continue
            key = (round(w0e, 4), round(w1s, 4))
            if key in resolved:
                continue
            tail_t = w0e + tail_sec
            lead_t = w1s - lead_sec
            if tail_t >= lead_t - 1e-6:
                resolved.add(key)
                continue
            applied = _inter_word_shorten_apply_one_gap(subclips, i0, i1, tail_t, lead_t, front, side)
            resolved.add(key)
            if applied:
                progressed = True
                break
        if not progressed:
            break


def _inter_word_shorten_reassemble_side(
    subclips: List[SubClip],
    front: str,
    side: str,
    side_shot_max_sec: float,
) -> List[SubClip]:
    out: List[SubClip] = []
    for span in _inter_word_shorten_row_spans(subclips):
        by_idx = {c.row.idx: c.row for c in span}
        span_rows_unique = [by_idx[i] for i in sorted(by_idx)]
        fixed = enforce_side_max_durations(
            span,
            span_rows_unique,
            side_cam=side,
            front_cam=front,
            max_side_sec=side_shot_max_sec,
        )
        out.extend(fixed)
    return out


def apply_inter_word_silence_shorten(
    subclips: List[SubClip],
    *,
    front_cam: str,
    side_cam: str,
    min_silence_sec: float = 3.0,
    compress_tail_sec: float = 1.5,
    compress_lead_sec: float = 1.5,
    side_shot_max_sec: float = 12.0,
) -> None:
    """Mutate ``subclips`` in place: compress long silences between consecutive spoken tokens.

    Same rules as ``shorten_reading_dsl_silences.py`` (camera flip per cut, side-cap, last row on front).
    """
    _inter_word_shorten_run_passes(
        subclips,
        front_cam,
        side_cam,
        min_silence_sec,
        compress_tail_sec,
        compress_lead_sec,
    )
    subclips[:] = [c for c in subclips if c.b > c.a + 1e-3]
    subclips[:] = _inter_word_shorten_reassemble_side(
        subclips, front_cam, side_cam, side_shot_max_sec,
    )
    ensure_last_sentence_on_front(subclips, front_cam)


def _chunk_subclips_for_emit_comments(subclips: List[SubClip]) -> List[List[SubClip]]:
    """Group subclips into runs separated by a gap in transcript row indices (span boundaries)."""
    if not subclips:
        return []
    chunks: List[List[SubClip]] = []
    cur: List[SubClip] = [subclips[0]]
    for c in subclips[1:]:
        pr = cur[-1].row.idx
        if c.row.idx == pr or c.row.idx == pr + 1:
            cur.append(c)
        else:
            chunks.append(cur)
            cur = [c]
    chunks.append(cur)
    return chunks


def emit_subclip_lines(
    subclips: List[SubClip],
    segment_num: str,
    current_camera_ref: List[Optional[str]],
    lines: List[str],
) -> None:
    for clip in subclips:
        if clip.shorten_join_before:
            lines.append("!shorten-join")
        if clip.cam != current_camera_ref[0]:
            lines.append(f"!camera {clip.cam}")
            current_camera_ref[0] = clip.cam
        row = clip.row
        a, b = clip.a, clip.b
        sl_start = a - row.start
        sl_end = b - row.start
        # ``podcast_dsl`` reloads transcript JSON from disk (no trim_* fields). Any
        # in-memory trim must become an explicit ``slice(...)`` or the renderer uses
        # the full sentence ``start``/``end`` from the JSON file.
        emit_plain = (
            not clip.shorten_join_before
            and row.trim_start is None
            and row.trim_end is None
            and abs(a - row.start) < 1e-6
            and abs(b - row.end) < 1e-6
        )
        text_summary = row.text.replace("\n", " ").strip()
        if len(text_summary) > 90:
            text_summary = text_summary[:87] + "..."
        if emit_plain:
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
    post_word_tail_sec: float,
    shorten_inter_word_silences: bool = False,
    shorten_min_silence_sec: float = 3.0,
    shorten_compress_tail_sec: float = 1.5,
    shorten_compress_lead_sec: float = 1.5,
) -> str:
    spans = build_spans(kept)

    lines: List[str] = []
    header = f"// Generated reading DSL (segment {segment_num})"
    if shorten_inter_word_silences:
        header += " — inter-word silence shortened"
    lines.append(header)
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
    if post_word_tail_sec > 0:
        lines.append(
            f"// Post-word tail: extend each clip end up to {post_word_tail_sec:.2f}s after "
            f"the last word, without crossing the next word or the next clip boundary"
        )
    if shorten_inter_word_silences:
        lines.append(
            f"// Shorten: gaps >={shorten_min_silence_sec:.2f}s → "
            f"{shorten_compress_tail_sec:.2f}s after last word + "
            f"{shorten_compress_lead_sec:.2f}s before next word (camera flip per cut)"
        )
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
    all_subclips: List[SubClip] = []
    next_main_cam: Optional[str] = front_cam
    for span_rows in spans:
        main_cam = next_main_cam
        alt_cam = side_cam if main_cam == front_cam else front_cam

        span_sub = collect_span_subclips(span_rows, main_cam)
        span_sub = enforce_side_max_durations(
            span_sub, span_rows, side_cam, front_cam, side_shot_max_sec,
        )
        all_subclips.extend(span_sub)

        end_cam = span_sub[-1].cam if span_sub else main_cam
        next_main_cam = main_cam if end_cam == alt_cam else alt_cam

    apply_cut_lead_in(all_subclips, cut_lead_in_sec)
    ensure_last_sentence_on_front(all_subclips, front_cam)
    apply_post_word_tail_extension(all_subclips, post_word_tail_sec)
    if shorten_inter_word_silences:
        apply_inter_word_silence_shorten(
            all_subclips,
            front_cam=front_cam,
            side_cam=side_cam,
            min_silence_sec=shorten_min_silence_sec,
            compress_tail_sec=shorten_compress_tail_sec,
            compress_lead_sec=shorten_compress_lead_sec,
            side_shot_max_sec=side_shot_max_sec,
        )
    extend_final_shot(all_subclips, final_shot_tail_sec)

    current_camera_ref: List[Optional[str]] = [None]
    for chunk in _chunk_subclips_for_emit_comments(all_subclips):
        t_lo = min(c.a for c in chunk)
        t_hi = max(c.b for c in chunk)
        label_cam = chunk[0].cam
        lines.append(
            f"// Span on {label_cam}: {t_lo:.2f}s -> {t_hi:.2f}s ({t_hi - t_lo:.1f}s)"
        )
        lines.append("")
        emit_subclip_lines(chunk, segment_num, current_camera_ref, lines)
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

    partial_coverage: List[dict] = []
    span_groups: dict[int, List[RowMatch]] = {}
    for m in kept:
        if m.a_start is None or m.a_end is None or m.a_start != m.a_end:
            continue
        span_groups.setdefault(m.a_start, []).append(m)

    for idx, group in span_groups.items():
        if idx not in covered_set:
            continue
        article_tokens = _article_span_tokens(article, idx, idx)
        if len(article_tokens) < MIN_ARTICLE_WORDS_PARTIAL:
            continue
        cov = _matches_span_coverage(group, article, idx, idx)
        if cov < PARTIAL_COVERAGE_THRESHOLD:
            partial_coverage.append({
                "kind": "partial_coverage",
                "idx": idx,
                "coverage": round(cov, 3),
                "kept_rows": [m.row.idx for m in sorted(group, key=lambda x: x.row.idx)],
                "text": article[idx].text,
            })

    warnings = [
        {
            "kind": "missing_chunk",
            "idx": idx,
            "text": article[idx].text,
        }
        for idx in missing
    ]
    warnings.extend(partial_coverage)

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
        "warnings": warnings,
        "summary": {
            "covered_count": len(covered_chunks),
            "missing_count": len(missing),
            "internal_missing_count": len(internal_missing),
            "trailing_missing_count": len(trailing_missing),
            "partial_coverage_count": len(partial_coverage),
        },
        "missing_chunks": [_entry(idx) for idx in missing],
        "partial_coverage_chunks": partial_coverage,
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

    overlap_notes: List[str] = []
    apply_overlap_tail_trim(kept, article, overlap_notes)
    selection_notes.extend(overlap_notes)

    dsl = generate_dsl(
        rows, article, matches, kept,
        segment_num=str(args.segment),
        front_cam=args.front_camera,
        side_cam=args.side_camera,
        cut_lead_in_sec=args.cut_lead_in_sec,
        side_shot_max_sec=args.side_shot_max_sec,
        final_shot_tail_sec=args.final_shot_tail_sec,
        post_word_tail_sec=args.post_word_tail_sec,
        shorten_inter_word_silences=args.shorten,
        shorten_min_silence_sec=args.shorten_min_silence_sec,
        shorten_compress_tail_sec=args.shorten_tail_sec,
        shorten_compress_lead_sec=args.shorten_lead_sec,
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
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        for i in missing[:15]:
            txt = article[i].text
            if len(txt) > 70:
                txt = txt[:67] + "..."
            safe = txt.encode(enc, errors="replace").decode(enc, errors="replace")
            print(f"  [{i}] {safe}")
        if len(missing) > 15:
            print(f"  ... and {len(missing) - 15} more")

    partial = sanity_report.get("partial_coverage_chunks") or []
    if partial:
        print(f"Warning: {len(partial)} article chunk(s) with partial audio coverage:")
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        for entry in partial[:15]:
            txt = entry["text"]
            if len(txt) > 70:
                txt = txt[:67] + "..."
            safe = txt.encode(enc, errors="replace").decode(enc, errors="replace")
            print(
                f"  [{entry['idx']}] {entry['coverage']:.0%} covered "
                f"(rows {entry['kept_rows']}): {safe}"
            )
        if len(partial) > 15:
            print(f"  ... and {len(partial) - 15} more")

    if args.verbose:
        print("\nPer-row matches:")
        for m in matches:
            status = "KEEP" if m.row.idx in kept_row_ids else ("OFF" if m.off_script else "DROP")
            print(f"  {status:4s} {m.row.idx:3d} sim={m.similarity:.2f} "
                  f"art=[{m.a_start}:{m.a_end}] text={m.row.text[:50]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
