#!/usr/bin/env python3
"""
Auto-generate camera cuts based on speaker heuristics.

Heuristics:
1. Always show the person who is speaking
2. Don't make clips less than 5 seconds long
3. Randomly switch between solo shot and wide shot
4. Only cut between sequence elements (segments)
"""

import random
from typing import Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from podcast_dsl import DSLCommand, CameraCommand, SegmentCommand


def get_speaker_and_duration(segment_id: str) -> Tuple[int, float]:
    """
    Get speaker_id and duration for a segment from transcript.
    Combined function to avoid loading transcript twice.
    """
    # Import here to avoid circular dependency
    from podcast_dsl import parse_segment_id, load_transcript, SEGMENT_CONFIG

    segment_num, sentence_id = parse_segment_id(segment_id)

    # Load transcript to get speaker and duration
    config = SEGMENT_CONFIG[segment_num]
    transcript = load_transcript(config['transcript_file'])

    if sentence_id not in transcript:
        raise ValueError(f"Sentence ID {sentence_id} not found in segment {segment_num}")

    sentence = transcript[sentence_id]
    speaker_id = sentence['speaker_id']
    duration = sentence['end'] - sentence['start']

    return speaker_id, duration


def choose_camera_for_speaker(speaker_id: int) -> str:
    """
    Choose a camera angle for a speaker.
    Randomly chooses between solo shot and wide shot.

    Args:
        speaker_id: 0 or 1

    Returns:
        Camera name: 'speaker_0', 'speaker_1', or 'wide'
    """
    # 1/8 chance of wide, otherwise use the active speaker shot.
    if random.random() < 0.125:
        return 'wide'
    else:
        return f'speaker_{speaker_id}'


def _precompute_segment_metadata(commands: List) -> Dict[int, Tuple[int, float]]:
    """Cache (speaker_id, duration) for each SegmentCommand by command index."""
    segment_metadata = {}

    for idx, cmd in enumerate(commands):
        if type(cmd).__name__ != 'SegmentCommand':
            continue

        try:
            segment_metadata[idx] = get_speaker_and_duration(cmd.segment_id)
        except Exception as e:
            print(f"Warning: Could not determine speaker for {cmd.segment_id}: {e}")

    return segment_metadata


def insert_auto_cuts(commands: List, min_clip_duration: float = 5.0) -> List:
    """
    Insert camera commands automatically based on speaker heuristics.

    Args:
        commands: List of parsed DSL commands
        min_clip_duration: Minimum clip duration in seconds before allowing a cut

    Returns:
        New list of commands with camera commands inserted
    """
    # Import here to avoid circular dependency
    from podcast_dsl import CameraCommand, SegmentCommand

    new_commands = []
    current_camera = None
    current_speaker = None
    time_on_current_camera = 0.0
    short_segment_keep_camera_threshold = 1.0
    segment_metadata = _precompute_segment_metadata(commands)

    for idx, cmd in enumerate(commands):
        cmd_type = type(cmd).__name__
        if cmd_type == 'CameraCommand':
            # User manually specified a camera - respect it
            current_camera = cmd.camera_name
            time_on_current_camera = 0.0
            new_commands.append(cmd)

        elif cmd_type == 'SegmentCommand':
            if idx not in segment_metadata:
                new_commands.append(cmd)
                continue

            speaker_id, segment_duration = segment_metadata[idx]

            # Keep the current angle for very short transcript segments.
            # These tiny interjections are usually better handled as visual holdovers
            # rather than instant ping-pong cuts.
            if current_camera is not None and segment_duration < short_segment_keep_camera_threshold:
                new_commands.append(cmd)
                if current_speaker is None:
                    current_speaker = speaker_id
                time_on_current_camera += segment_duration
                continue

            # Decide if we should cut
            should_cut = False

            # Always cut when the speaker changes.
            if current_speaker is not None and current_speaker != speaker_id:
                should_cut = True

            # Can also cut if we've been on this camera for >= min duration
            elif time_on_current_camera >= min_clip_duration:
                should_cut = True

            # If no camera set yet, set one
            elif current_camera is None:
                should_cut = True

            if should_cut:
                # Choose new camera
                new_camera = choose_camera_for_speaker(speaker_id)

                # Only insert camera command if it's different from current
                if new_camera != current_camera:
                    new_commands.append(CameraCommand(new_camera))
                    current_camera = new_camera
                    time_on_current_camera = 0.0

            # Add the segment
            new_commands.append(cmd)
            current_speaker = speaker_id
            time_on_current_camera += segment_duration

        else:
            # Other commands (cut, fade, etc.) - pass through
            new_commands.append(cmd)

    return new_commands
