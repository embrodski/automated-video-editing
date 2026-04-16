#!/usr/bin/env python3
"""
Auto-generate camera commands based on speaker heuristics.

Default (`--auto-cuts`) combines:
1. Open on Ben's close-up (`speaker_{ben_speaker_id}`) before the first resolvable clip
   (if no prior `!camera` in the DSL).
2. Never drop or shorten clips — every SegmentCommand is preserved; only `!camera` lines
   are inserted.
3. Guest intro + crosstalk wide (see GUEST_INTRO_PATTERNS and _crosstalk_wide_indices):
   these force `wide` immediately, even if the current shot is under the minimum length.
   Intro wide applies per **transcript row** (each `$segmentN/id`). If one row contains many
   sentences (long duration), the intro phrase can match the **whole row** and incorrectly
   force wide for the entire clip — rows longer than INTRO_WIDE_MAX_ROW_DURATION_SEC skip
   the intro-wide rule (use sentence-level transcript rows for accurate two-sentence wide).
4. Otherwise apply the original pacing heuristics:
   - Hold the current camera through utterances shorter than 1 second (no cut on those
     lines, except forced-wide lines above).
   - Otherwise allow a cut when the speaker changes (once a speaker is established), or
     after at least `min_clip_duration` seconds on the current angle, or when no camera
     is set yet.
   - When a cut picks a new angle, use a 1/8 chance of `wide`, else the active speaker's
     close-up (`speaker_{id}`).

`--auto-cuts-legacy` keeps the old behavior only (no Ben-open, intro, or crosstalk rules).

Maintenance: do not remove or replace documented auto-cut rules without explicit
confirmation from the project owner.
"""

from __future__ import annotations

import random
import re
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Phrases that mean "Ben is introducing the guest" (case-insensitive).
GUEST_INTRO_PATTERNS = (
    re.compile(r"my\s+guest\s+is", re.I),
    re.compile(r"my\s+guest\s+today\s+is", re.I),
    re.compile(r"guest\s+today\s+is", re.I),
    re.compile(r"my\s+guest\s+today", re.I),
)

CROSSTALK_WINDOW_SEC = 6.0
# Within a 6s window, require at least this many Ben↔Guest turns (adjacent changes).
MIN_CROSSTALK_TURNS = 2

# Intro wide is meant for ~one sentence plus the next. If a single transcript row is longer
# than this (seconds), it is treated as a multi-sentence block: we do not force the whole
# row wide just because the phrase appears somewhere inside it.
INTRO_WIDE_MAX_ROW_DURATION_SEC = 22.0


def _get_sentence_meta(segment_id: str) -> Dict:
    """Transcript fields for one DSL segment id."""
    from podcast_dsl import parse_segment_id, load_transcript, SEGMENT_CONFIG

    segment_num, sentence_id = parse_segment_id(segment_id)
    config = SEGMENT_CONFIG[segment_num]
    transcript = load_transcript(config["transcript_file"])

    if sentence_id not in transcript:
        raise ValueError(f"Sentence ID {sentence_id} not found in segment {segment_num}")

    sentence = transcript[sentence_id]
    start = float(sentence["start"])
    end = float(sentence["end"])
    text = (sentence.get("text") or "").strip()
    speaker_id = sentence.get("speaker_id")
    return {
        "speaker_id": speaker_id,
        "start": start,
        "end": end,
        "duration": end - start,
        "text": text,
    }


def _precompute_segment_rows(commands: List) -> Tuple[List[int], List[Dict]]:
    """
    Return (command_indices_for_each_segment, meta_per_segment) in playback order
    for SegmentCommand entries only.
    """
    rows: List[Dict] = []
    cmd_indices: List[int] = []

    for idx, cmd in enumerate(commands):
        if type(cmd).__name__ != "SegmentCommand":
            continue
        try:
            meta = _get_sentence_meta(cmd.segment_id)
        except Exception as e:
            print(f"Warning: Could not load transcript for {cmd.segment_id}: {e}")
            continue
        rows.append(meta)
        cmd_indices.append(idx)

    return cmd_indices, rows


def _merge_index_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not ranges:
        return []
    ranges = sorted(ranges)
    out = [ranges[0]]
    for lo, hi in ranges[1:]:
        plo, phi = out[-1]
        if lo <= phi + 1:
            out[-1] = (plo, max(phi, hi))
        else:
            out.append((lo, hi))
    return out


def _ranges_to_index_set(ranges: List[Tuple[int, int]]) -> Set[int]:
    s: Set[int] = set()
    for lo, hi in ranges:
        s.update(range(lo, hi + 1))
    return s


def _is_guest_intro_ben(text: str) -> bool:
    return any(p.search(text) for p in GUEST_INTRO_PATTERNS)


def _intro_wide_indices(
    rows: List[Dict],
    ben_speaker_id: int,
) -> Set[int]:
    """
    First Ben **row** matching intro phrases → wide for that row index and the next.

    Matching is per transcript row, not per spoken sentence inside the row. Long rows that
    contain the phrase but span many sentences are skipped (see INTRO_WIDE_MAX_ROW_DURATION_SEC).
    """
    for i, row in enumerate(rows):
        sid = row["speaker_id"]
        if sid is None or int(sid) != ben_speaker_id:
            continue
        if not _is_guest_intro_ben(row["text"]):
            continue
        dur = float(row["end"]) - float(row["start"])
        if dur > INTRO_WIDE_MAX_ROW_DURATION_SEC:
            continue
        out = {i}
        if i + 1 < len(rows):
            out.add(i + 1)
        return out
    return set()


def _interval_intersects_window(a0: float, a1: float, b0: float, b1: float) -> bool:
    return not (a1 <= b0 or a0 >= b1)


def _significant_crosstalk(
    speakers_in_order: List[int],
    ben_id: int,
    guest_id: int,
) -> bool:
    seq = [s for s in speakers_in_order if s is not None and int(s) in (ben_id, guest_id)]
    if len(seq) < 3:
        return False
    turns = 0
    for a, b in zip(seq, seq[1:]):
        if int(a) != int(b):
            turns += 1
    return turns >= MIN_CROSSTALK_TURNS


def _crosstalk_wide_indices(
    rows: List[Dict],
    ben_speaker_id: int,
    guest_speaker_id: int,
) -> Set[int]:
    """
    For each utterance start time t, consider [t, t + CROSSTALK_WINDOW_SEC].
    If overlapping utterances show enough Ben↔Guest alternation, mark all overlapping
    segment indices (in `rows` order) for wide.
    """
    n = len(rows)
    ranges: List[Tuple[int, int]] = []

    for anchor in range(n):
        t0 = rows[anchor]["start"]
        t1 = t0 + CROSSTALK_WINDOW_SEC
        overlapping: List[int] = []
        for j in range(n):
            s, e = rows[j]["start"], rows[j]["end"]
            if _interval_intersects_window(s, e, t0, t1):
                overlapping.append(j)
        overlapping.sort(key=lambda j: rows[j]["start"])
        speakers = [rows[j]["speaker_id"] for j in overlapping]
        if _significant_crosstalk(speakers, ben_speaker_id, guest_speaker_id):
            lo, hi = min(overlapping), max(overlapping)
            ranges.append((lo, hi))

    return _ranges_to_index_set(_merge_index_ranges(ranges))


def _forced_wide_segment_indices(
    rows: List[Dict],
    ben_speaker_id: int,
    guest_speaker_id: int,
) -> Set[int]:
    intro = _intro_wide_indices(rows, ben_speaker_id)
    crosstalk = _crosstalk_wide_indices(rows, ben_speaker_id, guest_speaker_id)
    return intro | crosstalk


def insert_auto_cuts(
    commands: List,
    min_clip_duration: float = 5.0,
    legacy: bool = False,
    ben_speaker_id: int = 0,
    guest_speaker_id: int = 1,
) -> List:
    """
    Insert camera commands automatically.

    Args:
        commands: Parsed DSL command list
        min_clip_duration: Minimum seconds on current angle before an optional cut
            (default mode and legacy mode).
        legacy: If True, use older heuristic only (no Ben open, intro, or crosstalk).
        ben_speaker_id: Transcript speaker_id for Ben (close-up speaker_0)
        guest_speaker_id: Transcript speaker_id for the guest (close-up speaker_1)
    """
    if legacy:
        return _insert_auto_cuts_legacy(commands, min_clip_duration=min_clip_duration)
    return _insert_auto_cuts_modern(
        commands,
        ben_speaker_id=ben_speaker_id,
        guest_speaker_id=guest_speaker_id,
        min_clip_duration=min_clip_duration,
    )


def _insert_auto_cuts_modern(
    commands: List,
    ben_speaker_id: int,
    guest_speaker_id: int,
    min_clip_duration: float = 5.0,
    short_segment_keep_camera_threshold: float = 1.0,
) -> List:
    """
    Default auto-cuts: Ben open + intro/crosstalk wide + legacy pacing (5s, random wide,
    <1s hold). Forced-wide segments bypass the 5s and short-hold rules.
    """
    from podcast_dsl import CameraCommand

    cmd_indices, rows = _precompute_segment_rows(commands)
    index_to_row: Dict[int, int] = {cmd_indices[i]: i for i in range(len(cmd_indices))}
    forced_wide: Set[int] = set()
    if rows:
        forced_wide = _forced_wide_segment_indices(rows, ben_speaker_id, guest_speaker_id)

    new_commands: List = []
    current_camera: Optional[str] = None
    current_speaker: Optional[int] = None
    time_on_current_camera = 0.0
    inserted_start_ben = False
    ben_cam = f"speaker_{ben_speaker_id}"

    for idx, cmd in enumerate(commands):
        cmd_type = type(cmd).__name__

        if cmd_type == "CameraCommand":
            current_camera = cmd.camera_name
            time_on_current_camera = 0.0
            new_commands.append(cmd)
            continue

        if cmd_type != "SegmentCommand":
            new_commands.append(cmd)
            continue

        if idx not in index_to_row:
            new_commands.append(cmd)
            continue

        row_idx = index_to_row[idx]
        meta = rows[row_idx]
        segment_duration = meta["duration"]
        raw_sid = meta["speaker_id"]
        speaker_id: Optional[int] = int(raw_sid) if raw_sid is not None else None

        if not inserted_start_ben:
            if current_camera is None:
                new_commands.append(CameraCommand(ben_cam))
                current_camera = ben_cam
                time_on_current_camera = 0.0
            inserted_start_ben = True

        if row_idx in forced_wide:
            if current_camera != "wide":
                new_commands.append(CameraCommand("wide"))
                current_camera = "wide"
                time_on_current_camera = 0.0
            new_commands.append(cmd)
            time_on_current_camera += segment_duration
            if speaker_id is not None:
                current_speaker = speaker_id
            continue

        if current_camera is not None and segment_duration < short_segment_keep_camera_threshold:
            new_commands.append(cmd)
            if current_speaker is None and speaker_id is not None:
                current_speaker = speaker_id
            time_on_current_camera += segment_duration
            continue

        should_cut = False
        if current_speaker is not None and current_speaker != speaker_id:
            should_cut = True
        elif time_on_current_camera >= min_clip_duration:
            should_cut = True
        elif current_camera is None:
            should_cut = True

        if should_cut:
            if speaker_id is None:
                new_camera = "wide"
            else:
                new_camera = _choose_camera_for_speaker_random(speaker_id)
            if new_camera != current_camera:
                new_commands.append(CameraCommand(new_camera))
                current_camera = new_camera
                time_on_current_camera = 0.0

        new_commands.append(cmd)
        current_speaker = speaker_id
        time_on_current_camera += segment_duration

    return new_commands


def _insert_auto_cuts_legacy(commands: List, min_clip_duration: float = 5.0) -> List:
    """Previous heuristic: random wide, 5s minimum, hold camera on sub-1s utterances."""
    from podcast_dsl import CameraCommand, SegmentCommand

    segment_metadata: Dict[int, Tuple[int, float]] = {}
    for idx, cmd in enumerate(commands):
        if type(cmd).__name__ != "SegmentCommand":
            continue
        try:
            meta = _get_sentence_meta(cmd.segment_id)
            sid = meta["speaker_id"]
            if sid is None:
                print(f"Warning: No speaker_id for {cmd.segment_id}, skipping auto metadata")
                continue
            segment_metadata[idx] = (int(sid), meta["duration"])
        except Exception as e:
            print(f"Warning: Could not determine speaker for {cmd.segment_id}: {e}")

    new_commands: List = []
    current_camera = None
    current_speaker = None
    time_on_current_camera = 0.0
    short_segment_keep_camera_threshold = 1.0

    for idx, cmd in enumerate(commands):
        cmd_type = type(cmd).__name__
        if cmd_type == "CameraCommand":
            current_camera = cmd.camera_name
            time_on_current_camera = 0.0
            new_commands.append(cmd)

        elif cmd_type == "SegmentCommand":
            if idx not in segment_metadata:
                new_commands.append(cmd)
                continue

            speaker_id, segment_duration = segment_metadata[idx]

            if current_camera is not None and segment_duration < short_segment_keep_camera_threshold:
                new_commands.append(cmd)
                if current_speaker is None:
                    current_speaker = speaker_id
                time_on_current_camera += segment_duration
                continue

            should_cut = False
            if current_speaker is not None and current_speaker != speaker_id:
                should_cut = True
            elif time_on_current_camera >= min_clip_duration:
                should_cut = True
            elif current_camera is None:
                should_cut = True

            if should_cut:
                new_camera = _choose_camera_for_speaker_random(speaker_id)
                if new_camera != current_camera:
                    new_commands.append(CameraCommand(new_camera))
                    current_camera = new_camera
                    time_on_current_camera = 0.0

            new_commands.append(cmd)
            current_speaker = speaker_id
            time_on_current_camera += segment_duration

        else:
            new_commands.append(cmd)

    return new_commands


def _choose_camera_for_speaker_random(speaker_id: int) -> str:
    if random.random() < 0.125:
        return "wide"
    return f"speaker_{speaker_id}"


def get_speaker_and_duration(segment_id: str) -> Tuple[int, float]:
    """Backward-compatible helper: speaker_id and duration for a segment."""
    meta = _get_sentence_meta(segment_id)
    if meta["speaker_id"] is None:
        raise ValueError(f"No speaker_id for {segment_id}")
    return int(meta["speaker_id"]), meta["duration"]
