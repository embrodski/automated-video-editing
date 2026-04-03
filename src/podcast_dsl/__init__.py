"""
Domain-specific language for podcast editing.

This package provides a DSL for specifying podcast video editing operations
including camera switches, cuts, fades, and segment playback.
"""

# Export configuration
from .config import SEGMENT_CONFIG

# Export command classes
from .commands import (
    DSLCommand,
    CameraCommand,
    CutCommand,
    FadeToBlackCommand,
    FadeFromBlackCommand,
    BlackCommand,
    SegmentCommand
)

# Export parser functions
from .parser import parse_dsl_line, parse_dsl_file

# Export clip processing functions
from .clip_processing import (
    parse_segment_id,
    load_transcript,
    get_clip_info,
    group_consecutive_clips
)

# Export rendering functions
from .video_renderer import (
    concatenate_clips,
    generate_black_clip,
    extract_clip_group,
    render_dsl
)

__all__ = [
    # Config
    'SEGMENT_CONFIG',

    # Commands
    'DSLCommand',
    'CameraCommand',
    'CutCommand',
    'FadeToBlackCommand',
    'FadeFromBlackCommand',
    'BlackCommand',
    'SegmentCommand',

    # Parser
    'parse_dsl_line',
    'parse_dsl_file',

    # Clip processing
    'parse_segment_id',
    'load_transcript',
    'get_clip_info',
    'group_consecutive_clips',

    # Rendering
    'concatenate_clips',
    'generate_black_clip',
    'extract_clip_group',
    'render_dsl',
]
