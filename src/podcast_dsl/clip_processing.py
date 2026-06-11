"""
Clip and segment processing logic.
"""

import json
from typing import List, Dict, Tuple, Optional

from .config import (
    SEGMENT_CONFIG,
    SHORTEN_JOIN_DEFAULT_CROSSFADE_MS,
    SHORTEN_JOIN_DEFAULT_PADDING_MS,
)


# Global cache for transcript files
_TRANSCRIPT_CACHE = {}


def parse_segment_id(segment_id: str) -> Tuple[str, str]:
    """Parse segment ID into (segment_num, sentence_id)"""
    parts = segment_id.strip().split('/')
    if len(parts) != 2:
        raise ValueError(f"Invalid segment ID: {segment_id}")

    segment_name, sentence_id = parts
    if not segment_name.startswith('segment'):
        raise ValueError(f"Invalid segment name: {segment_name}")

    segment_num = segment_name.replace('segment', '')
    if segment_num not in SEGMENT_CONFIG:
        raise ValueError(f"Unknown segment: {segment_num}")

    return segment_num, sentence_id


def load_transcript(transcript_file: str) -> Dict:
    """Load transcript JSON with caching"""
    if transcript_file not in _TRANSCRIPT_CACHE:
        with open(transcript_file, 'r') as f:
            _TRANSCRIPT_CACHE[transcript_file] = json.load(f)
    return _TRANSCRIPT_CACHE[transcript_file]


def get_clip_info(segment_id: str, camera_name: str, slice_start: float = None, slice_end: float = None, margin: float = 0.0):
    """
    Get clip information for a segment with specified camera.

    Args:
        segment_id: Segment identifier (e.g., "segment2/0")
        camera_name: Camera name
        slice_start: Optional start offset in seconds relative to the sentence start
            (negative values begin before the listed transcript start, clamped to t>=0)
        slice_end: Optional end offset in seconds (negative values count from end)
        margin: Extra margin in seconds to add when slicing (extends the slice on both ends)

    Returns:
        Dictionary with audio/video timing information, adjusted for slice parameters
    """
    segment_num, sentence_id = parse_segment_id(segment_id)
    config = SEGMENT_CONFIG[segment_num]

    # Load transcript
    transcript = load_transcript(config['transcript_file'])

    if sentence_id not in transcript:
        raise ValueError(f"Sentence ID {sentence_id} not found in segment {segment_num}")

    sentence = transcript[sentence_id]
    audio_start = sentence['start']
    audio_end = sentence['end']
    duration = audio_end - audio_start

    # Store original start and end for reference
    original_start = audio_start
    original_end = audio_end

    # Apply slice parameters if provided
    if slice_start is not None or slice_end is not None:
        # Calculate actual start and end based on slice parameters
        if slice_start is not None:
            if slice_start < 0:
                # Negative: offset from sentence start (lead-in before listed start)
                audio_start = max(0.0, original_start + slice_start)
            else:
                audio_start = original_start + slice_start

        if slice_end is not None:
            if slice_end < 0:
                # Negative: offset from end
                audio_end = original_end + slice_end
            else:
                # Positive: offset from start
                audio_end = original_start + slice_end

    # Apply margin to ALL clips (whether sliced or not)
    # Margin extends the clip on both ends
    if margin > 0:
        audio_start = max(0, audio_start - margin)
        audio_end = audio_end + margin

    # Update duration
    duration = audio_end - audio_start

    # Ensure duration is positive
    if duration <= 0:
        raise ValueError(f"Invalid slice results in non-positive duration: {duration}s for segment {segment_id} (start={slice_start}, end={slice_end}, margin={margin}, original_duration={original_end - original_start}s)")

    # Get video info for the specified camera
    if camera_name not in config['video_files']:
        raise ValueError(f"Unknown camera: {camera_name}")

    video_info = config['video_files'][camera_name]
    video_start = audio_start + video_info['offset']
    video_end = audio_end + video_info['offset']

    return {
        'audio_file': config['audio_file'],
        'audio_start': audio_start,
        'audio_end': audio_end,
        'video_file': video_info['file'],
        'video_start': video_start,
        'video_end': video_end,
        'duration': duration,
        'camera': camera_name
    }


def _clip_shorten_join_spec(clip: Tuple) -> Optional[Tuple[float, float]]:
    """Return (padding_ms, crossfade_ms) when this clip starts after a shorten join."""
    if len(clip) < 11 or not clip[10]:
        return None
    spec = clip[10]
    if isinstance(spec, tuple):
        return spec
    return (SHORTEN_JOIN_DEFAULT_PADDING_MS, SHORTEN_JOIN_DEFAULT_CROSSFADE_MS)


def _row_spoken_bounds(sentence: dict) -> Tuple[float, float]:
    """First/last word times, or sentence start/end when words are missing."""
    words = sentence.get('words') or []
    if words:
        return float(words[0]['start']), float(words[-1]['end'])
    return float(sentence['start']), float(sentence['end'])


def apply_shorten_join_clip_bounds(
    clips_to_render: List[Tuple],
) -> List[Tuple]:
    """
    At each ``!shorten-join``, extend the outgoing clip through (last_word_end + padding)
    and the incoming clip from (first_word_start - padding), using explicit slices so
    padding applies across render groups, not only inside multi-camera span concat.
    """
    if not clips_to_render:
        return clips_to_render

    updated: List[Tuple] = list(clips_to_render)
    for i in range(len(updated)):
        spec = _clip_shorten_join_spec(updated[i])
        if spec is None or i == 0:
            continue
        prev = list(updated[i - 1])
        curr = list(updated[i])
        if prev[0].startswith('__BLACK__') or curr[0].startswith('__BLACK__'):
            continue

        pad_sec = spec[0] / 1000.0
        prev_seg, prev_sent = parse_segment_id(prev[0])
        curr_seg, curr_sent = parse_segment_id(curr[0])
        if prev_seg != curr_seg:
            continue

        transcript = load_transcript(SEGMENT_CONFIG[prev_seg]['transcript_file'])
        prev_row = transcript[prev_sent]
        curr_row = transcript[curr_sent]
        _, prev_word_end = _row_spoken_bounds(prev_row)
        curr_word_start, _ = _row_spoken_bounds(curr_row)
        tail_abs = prev_word_end + pad_sec
        lead_abs = curr_word_start - pad_sec

        prev_row_start = float(prev_row['start'])
        curr_row_start = float(curr_row['start'])

        prev_sl_start = prev[7]
        prev_sl_end = prev[8]
        prev_info = get_clip_info(prev[0], prev[1], prev_sl_start, prev_sl_end, 0.0)
        new_prev_end = max(prev_info['audio_start'] + 1e-3, tail_abs)
        prev[8] = new_prev_end - prev_row_start

        curr_sl_start = curr[7]
        curr_sl_end = curr[8]
        curr_info = get_clip_info(curr[0], curr[1], curr_sl_start, curr_sl_end, 0.0)
        new_curr_start = min(curr_info['audio_end'] - 1e-3, lead_abs)
        curr[7] = new_curr_start - curr_row_start

        updated[i - 1] = tuple(prev)
        updated[i] = tuple(curr)

    return updated


def group_consecutive_clips(clips_to_render: List[Tuple[str, str, str, float, float, Optional[float], Optional[float], Optional[float], Optional[float], float]], max_gap: Optional[float] = None):
    """
    Group consecutive clips that are close together in time AND sequential in the transcript.

    Args:
        clips_to_render: List of (segment_id, camera, comment, cut_before, cut_after, fade_in_ms, fade_out_ms, slice_start, slice_end, volume) tuples
        max_gap: Maximum gap in seconds to consider clips as consecutive.
            If None, preserve all gaps between sequential transcript sentences.

    Returns:
        List of groups, where each group is a list of (segment_id, camera, comment, cut_before, cut_after, fade_in_ms, fade_out_ms, slice_start, slice_end, volume)
    """
    if not clips_to_render:
        return []

    groups = []
    current_group = [clips_to_render[0]]

    for i in range(1, len(clips_to_render)):
        prev_segment_id, prev_camera, prev_comment, _, _, prev_fade_in, prev_fade_out, _, _, prev_volume, *_ = clips_to_render[i-1]
        curr_segment_id, curr_camera, curr_comment, _, _, curr_fade_in, curr_fade_out, _, _, curr_volume, *_ = clips_to_render[i]

        # Don't group black clips with anything (they're standalone)
        if prev_segment_id.startswith('__BLACK__') or curr_segment_id.startswith('__BLACK__'):
            groups.append(current_group)
            current_group = [clips_to_render[i]]
            continue

        # Shorten joins need their own extraction boundary (padding on each side).
        if _clip_shorten_join_spec(clips_to_render[i]) is not None:
            groups.append(current_group)
            current_group = [clips_to_render[i]]
            continue

        # Don't group if previous clip has fade_out or current clip has fade_in
        # These indicate intentional breaks (fade to/from black)
        if prev_fade_out is not None or curr_fade_in is not None:
            # Start new group
            groups.append(current_group)
            current_group = [clips_to_render[i]]
            continue

        # Don't group if volume changes between clips
        # Volume is applied as post-processing on a per-extraction basis,
        # so clips with different volumes need separate extractions
        if prev_volume != curr_volume:
            groups.append(current_group)
            current_group = [clips_to_render[i]]
            continue

        # Check if they're from the same segment (camera can differ for audio continuity)
        try:
            prev_seg_num, prev_sent_id = parse_segment_id(prev_segment_id)
            curr_seg_num, curr_sent_id = parse_segment_id(curr_segment_id)

            same_segment = prev_seg_num == curr_seg_num

            # IMPORTANT: Only group if sentences are actually consecutive (differ by 1)
            # This prevents accidentally including skipped sentences
            is_sequential = (int(curr_sent_id) == int(prev_sent_id) + 1)

            # Group consecutive clips regardless of camera to ensure audio continuity
            if same_segment and is_sequential:
                # Load transcript to check timing
                config = SEGMENT_CONFIG[prev_seg_num]
                transcript = load_transcript(config['transcript_file'])

                prev_end = transcript[prev_sent_id]['end']
                curr_start = transcript[curr_sent_id]['start']

                gap = curr_start - prev_end

                # Group if gap is within max_gap, or preserve all gaps when max_gap is None.
                if max_gap is None or gap <= max_gap:
                    current_group.append(clips_to_render[i])
                    continue

        except Exception:
            # If there's any error, don't group
            pass

        # Start new group
        groups.append(current_group)
        current_group = [clips_to_render[i]]

    groups.append(current_group)
    return groups
