#!/usr/bin/env python3
"""
Convert a JSON transcript into the simplified format expected by podcast_dsl.

Input format (two transcript shapes are accepted; both produce the same output):

1. Manual UI export shape:
   - Top-level JSON object with a "segments" array
   - Each segment has "text", "start_time", "end_time", and an optional nested
     "speaker" object with "id" and/or "name"
   - Optional per-segment "words" array with { "text", "start_time", "end_time" }

2. ElevenLabs API "segmented_json" export shape:
   - Top-level JSON object with a "segments" array
   - Each segment has "text" and a "words" array; segment-level start/end and
     speaker block are NOT present.
   - Each word has { "text", "start", "end", "type", "speaker_id", ... }
     (note "start"/"end" instead of "start_time"/"end_time", and a per-word
     "speaker_id" string like "speaker_0").
   When loading this shape, segment start/end is derived from the first/last
   timed word, and segment speaker is inferred from the most common per-word
   "speaker_id" within the segment.

Output format:
- JSON object keyed by sentence index as a string
- Each value has:
  - "start": float seconds
  - "end": float seconds
  - "text": utterance text
  - "speaker_id": integer speaker id
  - "speaker_name": optional human-readable speaker name

By default, if a segment includes a non-empty "words" list, the converter splits that
segment into one simplified row per detected sentence (using word timestamps for start/end).
That gives auto-cuts and DSL one line per sentence instead of one long paragraph per segment.
Segments without "words" still emit a single row each.

Rows where the ASR gives end <= start are kept (sentence IDs stay consecutive for grouping):
end is bumped to start + MIN_UTTERANCE_DURATION_SEC so the renderer can extract a valid clip.

Example:
  python convert_transcript_json.py Wide_Video_Interview_Audio_Copy_eng.json
  python convert_transcript_json.py input.json -o outputs/segment_1_transcript_simplified.json
  python convert_transcript_json.py input.json --drop-nonspeech
  python convert_transcript_json.py detail.json --no-split-sentences
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

# Word tokens ending a sentence (after strip); excludes common abbreviations.
_ABBREV_ENDINGS = frozenset(
    x.lower()
    for x in (
        "mr.",
        "mrs.",
        "ms.",
        "dr.",
        "prof.",
        "sr.",
        "jr.",
        "etc.",
        "e.g.",
        "i.e.",
        "vs.",
        "st.",
        "ave.",
    )
)

# Zero-length ASR sentences are expanded so every sentence keeps a row id and the renderer
# gets a positive duration (preserves consecutive grouping / timeline gaps).
MIN_UTTERANCE_DURATION_SEC = 0.02

# If ASR word-level punctuation is weak/missing, we fall back to splitting on pauses.
# This dramatically increases "true sentence-level" rows, which improves cut opportunities.
PAUSE_SPLIT_GAP_SEC = 0.65
PAUSE_SPLIT_MIN_WORDS = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert transcript JSON to podcast_dsl transcript format."
    )
    parser.add_argument(
        "input_json",
        help="Path to the source JSON transcript file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON path (default: <input>_simplified.json)",
    )
    parser.add_argument(
        "--drop-nonspeech",
        action="store_true",
        help="Drop segments whose text is only bracketed stage directions like [laughs]",
    )
    parser.add_argument(
        "--keep-empty",
        action="store_true",
        help="Keep empty/whitespace-only transcript segments",
    )
    parser.add_argument(
        "--speaker-source",
        choices=["id", "name", "auto"],
        default="auto",
        help="How to derive speaker identity (default: auto)",
    )
    parser.add_argument(
        "--no-split-sentences",
        action="store_true",
        help="One simplified row per input segment only (ignore word-level sentence splits).",
    )
    parser.add_argument(
        "--pause-split-gap-sec",
        type=float,
        default=PAUSE_SPLIT_GAP_SEC,
        help=f"Pause gap (seconds) that triggers a sentence split when punctuation is missing (default: {PAUSE_SPLIT_GAP_SEC}).",
    )
    parser.add_argument(
        "--pause-split-min-words",
        type=int,
        default=PAUSE_SPLIT_MIN_WORDS,
        help=f"Minimum buffered word tokens before pause-based split is allowed (default: {PAUSE_SPLIT_MIN_WORDS}).",
    )
    parser.add_argument(
        "--swap-speaker-ids",
        action="store_true",
        help=(
            "Swap speaker_id 0 and 1 in every output row after conversion. Use when "
            "ElevenLabs diarization labeled the host as speaker_1 and the guest as "
            "speaker_0 (Ben must end up as speaker_id 0 for podcast autocut)."
        ),
    )
    return parser.parse_args()


def infer_output_path(input_path: str) -> str:
    stem, ext = os.path.splitext(input_path)
    if ext.lower() == ".json":
        return f"{stem}_simplified.json"
    return f"{input_path}_simplified.json"


def load_input(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _word_start_time(w: Dict) -> Optional[float]:
    """Return a word's start time in seconds.

    Accepts either ``start_time`` (manual UI export) or ``start``
    (ElevenLabs API ``segmented_json`` export). Returns ``None`` if neither
    key is present or the value can't be coerced to float.
    """
    val = w.get("start_time")
    if val is None:
        val = w.get("start")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _word_end_time(w: Dict) -> Optional[float]:
    """Return a word's end time in seconds (mirrors ``_word_start_time``)."""
    val = w.get("end_time")
    if val is None:
        val = w.get("end")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return text.strip()


def is_nonspeech_text(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and bool(re.fullmatch(r"\[[^\]]+\]", stripped))


def extract_speaker_token(segment: Dict, speaker_source: str) -> Tuple[Optional[str], Optional[str]]:
    speaker = segment.get("speaker") or {}
    speaker_id = speaker.get("id")
    speaker_name = speaker.get("name")

    # ElevenLabs API segmented_json export has no segment-level "speaker" block
    # but every word carries a "speaker_id" string (e.g. "speaker_0"). Fall
    # back to the most common per-word speaker_id within this segment.
    if not speaker_id and not speaker_name:
        words = segment.get("words")
        if isinstance(words, list) and words:
            counts: Dict[str, int] = {}
            for w in words:
                if not isinstance(w, dict):
                    continue
                sid = w.get("speaker_id")
                if isinstance(sid, str) and sid:
                    counts[sid] = counts.get(sid, 0) + 1
            if counts:
                speaker_id = max(counts.items(), key=lambda kv: kv[1])[0]

    if speaker_source == "id":
        return speaker_id, speaker_name
    if speaker_source == "name":
        return speaker_name, speaker_name

    # auto: prefer explicit speaker id, fall back to human-readable name
    return speaker_id or speaker_name, speaker_name


def convert_speaker_token_to_int(
    token: Optional[str],
    speaker_name: Optional[str],
    speaker_map: Dict[str, int],
) -> Optional[int]:
    if token is None:
        return None

    match = re.fullmatch(r"speaker_(\d+)", str(token))
    if match:
        return int(match.group(1))

    if token not in speaker_map:
        speaker_map[token] = len(speaker_map)
    return speaker_map[token]


def _strip_trailing_quote(s: str) -> str:
    t = s.strip()
    if t.endswith(('"', "'")) and len(t) > 1:
        t = t[:-1].rstrip()
    return t


def is_sentence_terminal_token(text: str) -> bool:
    """
    Heuristic: ASR word token ends a sentence (., ?, !, …).
    Conservative about abbreviations, ellipses, and very short tokens.
    """
    t = _strip_trailing_quote(text)
    if len(t) < 2:
        return False
    if t.lower() in _ABBREV_ENDINGS:
        return False
    # Treat ellipses as terminal; many ASR outputs use "..." where a sentence boundary exists.
    if t.endswith("...") or t.endswith("…"):
        return True
    if t.endswith("?") or t.endswith("!"):
        return True
    if t.endswith("."):
        if len(t) >= 2 and t[-2] == ".":
            return False
        return True
    return False


def _next_substantive_word_index(words: List[Dict], start_i: int) -> Optional[int]:
    """Index of next word dict after ``start_i`` whose text is non-empty after strip.

    Many ASR JSON dumps include whitespace-only ``"text": " "`` tokens between real
    words. Pause-based splitting must measure gaps between **spoken** tokens, or a
    real mid-sentence pause (e.g. before a restart) gets hidden behind a tiny
    space-token gap and never triggers a row split.
    """
    for j in range(start_i + 1, len(words)):
        wj = words[j]
        if not isinstance(wj, dict):
            continue
        if (wj.get("text") or "").strip():
            return j
    return None


def words_to_sentence_rows(
    segment: Dict,
    speaker_id: Optional[int],
    speaker_name: Optional[str],
    *,
    pause_split_gap_sec: float,
    pause_split_min_words: int,
) -> Optional[List[Dict]]:
    """
    Split segment.words into sentence-sized rows with start/end from first/last word.
    Returns None if words are missing or unusable (caller should use whole segment).
    """
    words = segment.get("words")
    if not isinstance(words, list) or not words:
        return None

    rows: List[Dict] = []
    buf: List[Dict] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        substantive = [w for w in buf if (w.get("text") or "").strip()]
        if not substantive:
            buf = []
            return
        text = "".join(w.get("text") or "" for w in buf)
        text = normalize_text(re.sub(r"\s+", " ", text))
        start_first = _word_start_time(substantive[0])
        end_last = _word_end_time(substantive[-1])
        if start_first is None or end_last is None:
            buf = []
            return
        start = start_first
        end = end_last
        if end <= start:
            end = start + MIN_UTTERANCE_DURATION_SEC
        # Preserve word-level timestamps so downstream logic can snap cuts to
        # true word boundaries (comma / sentence end) rather than char-to-time heuristics.
        words_out: List[Dict] = []
        for w in substantive:
            w_text = (w.get("text") or "")
            w_start = _word_start_time(w)
            w_end = _word_end_time(w)
            if w_start is None or w_end is None:
                continue
            if w_end <= w_start:
                w_end = w_start + MIN_UTTERANCE_DURATION_SEC
            words_out.append({"text": w_text, "start": w_start, "end": w_end})

        row: Dict = {"start": start, "end": end, "text": text, "words": words_out}
        if speaker_id is not None:
            row["speaker_id"] = speaker_id
        if speaker_name:
            row["speaker_name"] = speaker_name
        rows.append(row)
        buf = []

    # Iterate with lookahead so we can split on pauses (word timing gaps).
    for wi, w in enumerate(words):
        if not isinstance(w, dict):
            continue
        if _word_start_time(w) is None or _word_end_time(w) is None:
            return None
        buf.append(w)
        piece = (w.get("text") or "").strip()
        if not piece:
            continue

        terminal = is_sentence_terminal_token(w.get("text") or "")
        pause_split = False
        if not terminal:
            nxt_i = _next_substantive_word_index(words, wi)
            if nxt_i is not None:
                nxt = words[nxt_i]
                if isinstance(nxt, dict):
                    nxt_start = _word_start_time(nxt)
                    cur_end = _word_end_time(w)
                    if nxt_start is not None and cur_end is not None:
                        gap = nxt_start - cur_end
                        if gap >= pause_split_gap_sec:
                            substantive_ct = sum(1 for ww in buf if (ww.get("text") or "").strip())
                            if substantive_ct >= pause_split_min_words:
                                pause_split = True

        if terminal or pause_split:
            flush()

    flush()
    return rows if rows else None


def validate_segment(segment: Dict, index: int) -> Tuple[float, float]:
    start: Optional[float] = None
    end: Optional[float] = None
    if "start_time" in segment:
        try:
            start = float(segment["start_time"])
        except (TypeError, ValueError):
            start = None
    if "end_time" in segment:
        try:
            end = float(segment["end_time"])
        except (TypeError, ValueError):
            end = None

    # ElevenLabs API segmented_json export omits segment-level start/end; derive
    # them from the first/last timed word in the segment.
    if start is None or end is None:
        words = segment.get("words")
        if isinstance(words, list) and words:
            first_start: Optional[float] = None
            last_end: Optional[float] = None
            for w in words:
                if not isinstance(w, dict):
                    continue
                ws = _word_start_time(w)
                we = _word_end_time(w)
                if ws is not None and first_start is None:
                    first_start = ws
                if we is not None:
                    last_end = we
            if start is None and first_start is not None:
                start = first_start
            if end is None and last_end is not None:
                end = last_end

    if start is None or end is None:
        raise ValueError(f"Segment {index} is missing start_time or end_time")

    if end < start:
        raise ValueError(f"Segment {index} has end_time < start_time")

    return start, end


def convert_segments(
    segments: List[Dict],
    drop_nonspeech: bool,
    keep_empty: bool,
    speaker_source: str,
    split_sentences: bool,
    *,
    pause_split_gap_sec: float = PAUSE_SPLIT_GAP_SEC,
    pause_split_min_words: int = PAUSE_SPLIT_MIN_WORDS,
) -> Tuple[Dict[str, Dict], Dict[str, int]]:
    output: Dict[str, Dict] = {}
    speaker_map: Dict[str, int] = {}
    output_index = 0

    for input_index, segment in enumerate(segments):
        start, end = validate_segment(segment, input_index)
        text = normalize_text(segment.get("text"))

        if not keep_empty and not text:
            continue
        if drop_nonspeech and is_nonspeech_text(text):
            continue

        speaker_token, speaker_name = extract_speaker_token(segment, speaker_source)
        speaker_id = convert_speaker_token_to_int(speaker_token, speaker_name, speaker_map)

        sentence_rows: Optional[List[Dict]] = None
        if split_sentences:
            sentence_rows = words_to_sentence_rows(
                segment,
                speaker_id,
                speaker_name,
                pause_split_gap_sec=pause_split_gap_sec,
                pause_split_min_words=pause_split_min_words,
            )

        if sentence_rows:
            for row in sentence_rows:
                st = row["text"]
                if not keep_empty and not normalize_text(st):
                    continue
                if drop_nonspeech and is_nonspeech_text(st):
                    continue
                rs, re_ = float(row["start"]), float(row["end"])
                if re_ <= rs:
                    re_ = rs + MIN_UTTERANCE_DURATION_SEC
                output[str(output_index)] = {
                    "start": rs,
                    "end": re_,
                    "text": normalize_text(st),
                }
                if row.get("words"):
                    output[str(output_index)]["words"] = row["words"]
                if "speaker_id" in row:
                    output[str(output_index)]["speaker_id"] = row["speaker_id"]
                if row.get("speaker_name"):
                    output[str(output_index)]["speaker_name"] = row["speaker_name"]
                output_index += 1
            continue

        if end <= start:
            end = start + MIN_UTTERANCE_DURATION_SEC
        converted = {
            "start": start,
            "end": end,
            "text": text,
        }

        if speaker_id is not None:
            converted["speaker_id"] = speaker_id
        if speaker_name:
            converted["speaker_name"] = speaker_name

        output[str(output_index)] = converted
        output_index += 1

    return output, speaker_map


def swap_speaker_ids_in_output(output: Dict[str, Dict]) -> int:
    """Swap speaker_id 0 <-> 1 in place. Returns number of rows touched."""
    touched = 0
    for row in output.values():
        sid = row.get("speaker_id")
        if sid == 0:
            row["speaker_id"] = 1
            touched += 1
        elif sid == 1:
            row["speaker_id"] = 0
            touched += 1
    return touched


def main() -> int:
    args = parse_args()

    data = load_input(args.input_json)
    segments = data.get("segments")
    if not isinstance(segments, list):
        print("Error: input JSON must contain a top-level 'segments' array.", file=sys.stderr)
        return 1

    output_path = args.output or infer_output_path(args.input_json)
    split_sentences = not args.no_split_sentences
    converted, speaker_map = convert_segments(
        segments,
        drop_nonspeech=args.drop_nonspeech,
        keep_empty=args.keep_empty,
        speaker_source=args.speaker_source,
        split_sentences=split_sentences,
        pause_split_gap_sec=float(args.pause_split_gap_sec),
        pause_split_min_words=int(args.pause_split_min_words),
    )

    if args.swap_speaker_ids:
        n = swap_speaker_ids_in_output(converted)
        print(f"Applied --swap-speaker-ids to {n} rows (0 <-> 1).")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(converted, f, indent=2, ensure_ascii=False)
        f.write("\n")

    mode = "per-sentence (from word timings)" if split_sentences else "one row per input segment"
    print(f"Wrote {len(converted)} transcript rows ({mode}) to {output_path}")
    if split_sentences:
        print("  Re-run with --no-split-sentences to match legacy one-row-per-segment indices.")
    if speaker_map:
        print("Speaker mapping:")
        for token, speaker_id in speaker_map.items():
            print(f"  {token} -> {speaker_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
