"""
Clip and segment processing logic.
"""

import json
from typing import List, Dict, Tuple, Optional

from .config import SEGMENT_CONFIG


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
        slice_start: Optional start offset in seconds (negative values count from end)
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
                # Negative: offset from end
                audio_start = original_end + slice_start
            else:
                # Positive: offset from start
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
        prev_segment_id, prev_camera, prev_comment, _, _, prev_fade_in, prev_fade_out, _, _, prev_volume = clips_to_render[i-1]
        curr_segment_id, curr_camera, curr_comment, _, _, curr_fade_in, curr_fade_out, _, _, curr_volume = clips_to_render[i]

        # Don't group black clips with anything (they're standalone)
        if prev_segment_id.startswith('__BLACK__') or curr_segment_id.startswith('__BLACK__'):
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
