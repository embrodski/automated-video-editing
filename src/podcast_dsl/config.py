"""
Configuration for podcast segments.
"""

from pathlib import Path


_PATH_BASE = Path(__file__).resolve().parents[1]


def _resolve_repo_path(path_str: str) -> str:
    """Resolve a path relative to the historical config base (`src`)."""
    path = Path(path_str)
    if path.is_absolute():
        return str(path)
    return str((_PATH_BASE / path_str).resolve())


# Segment configuration
SEGMENT_CONFIG = {
    '1': {
        'audio_file': '../derived_media/Interview Audio Mix.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': "../original_media/Eneasz Video (Interview).mp4",
                'offset': 0,
            },
            'speaker_1': {
                'file': "../original_media/Ben's Video (Interview).mp4",
                'offset': 0,
            },
            'wide': {
                'file': '../original_media/Wide Video (Interview).mp4',
                'offset': 0,
            }
        },
        'transcript_file': '../Wide_Video_Interview_Audio_Copy_eng_simplified.json',
    },
    '7': {
        'audio_file': '../derived_media/Adobe Enhanced Ben:Eneasz Interview Part 2.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': "../original_media/Eneasz Video (Interview) - Part 2.mp4",
                'offset': 0.25,
            },
            'speaker_1': {
                'file': "../original_media/Ben's Video (Interview) - Part 2.mp4",
                'offset': 0,
            },
            'wide': {
                'file': '../original_media/Wide Video (Interview) - Part 2.mp4',
                'offset': 0,
            }
        },
        'transcript_file': '../Wide_Video_Interview_Audio_Copy_eng_simplified_part2.json',
    },
    '8': {
        'audio_file': '../derived_media/Eneasz Audio (Reading) trimmed.wav',
        'audio_offset': 0,
        'video_files': {
            'straight': {
                'file': '../derived_media/Eneasz Vid (Reading) trimmed exact.mp4',
                'offset': 0,
            },
            'side': {
                'file': '../derived_media/Eneasz Side Vid (Reading) trimmed exact.mp4',
                'offset': 0,
            }
        },
        'transcript_file': '../Eneasz_Audio_Reading_trimmed_eng_cleaned.json',
    },
    '9': {
        'audio_file': '../derived_media/Adobe Enhanced Ben:Eneasz Interview Part 1.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': "../original_media/Eneasz Video (Interview) - Part 1.mp4",
                'offset': 0,
            },
            'speaker_1': {
                'file': "../original_media/Ben's Video (Interview) - Part 1.mp4",
                'offset': 0,
            },
            'wide': {
                'file': '../original_media/Wide Video (Interview) - Part 1.mp4',
                'offset': 0,
            }
        },
        'transcript_file': '../Wide_Video_Interview_Audio_Copy_eng_simplified_first_6m53s.json',
    },
    '2': {
        'audio_file': '../inputs/segment_2_first_real_mastered.mp3',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': '../inputs/ryan_20250802_0044_640p.mp4',
                'offset': 303.964642
            },
            'speaker_1': {
                'file': '../inputs/buck_20250802_0405_640p.mp4',
                'offset': 303.964642 + 11.017075
            },
            'wide': {
                'file': '../inputs/both_20250802_0412_640p.mp4',
                'offset': 303.964642 + 8.111995
            }
        },
        'transcript_file': '../outputs/segment_2_transcript_simplified.json',
    },
    '3': {
        'audio_file': '../inputs/segment_3_main_recording_mastered.mp3',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': '../inputs/ryan_20250802_0044_640p.mp4',
                'offset': 1377.556
            },
            'speaker_1': {
                'file': '../inputs/buck_20250802_0405_640p.mp4',
                'offset': 1377.556 + 11.017075
            },
            'wide': {
                'file': '../inputs/both_20250802_0412_640p.mp4',
                'offset': 1377.556 + 8.111995
            }
        },
        'transcript_file': '../outputs/segment_3_transcript_simplified.json',
    },
    '6': {
        'audio_file': '../inputs/segment_6_final_mastered.mp3',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': '../inputs/ryan_20250802_0044_640p.mp4',
                'offset': 12299.414
            },
            'speaker_1': {
                'file': '../inputs/buck_20250802_0405_640p.mp4',
                'offset': 12299.414 + 11.017075
            },
            'wide': {
                'file': '../inputs/both_20250802_0412_640p.mp4',
                'offset': 12299.414 + 8.111995
            }
        },
        'transcript_file': '../outputs/segment_6_transcript_simplified.json',
    },
    '10': {
        'audio_file': '../Jason_Crawford/Crawford-Ben Enhanced Audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': '../Jason_Crawford/Ben Interview Video.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': '../Jason_Crawford/Crawford Interview Video.mp4',
                'offset': 0,
            },
            'wide': {
                'file': '../Jason_Crawford/Interview Wide Video.mp4',
                'offset': 0,
            }
        },
        'transcript_file': '../Jason_Crawford/Interview_Transcript_simplified.json',
    },
    '4': {
        'audio_file': '../John_Nerst/Nerst audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': '../John_Nerst/Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': '../John_Nerst/Nerst.mp4',
                'offset': 0,
            },
            'wide': {
                'file': '../John_Nerst/wide.mp4',
                'offset': 0,
            }
        },
        'transcript_file': '../John_Nerst/Nerst Detail Transcript_simplified.json',
    },
    # Inkhaven Thessaly — paths absolute so project folder can live outside this repo
    '11': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Thessaly\Input\interview audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Thessaly\Input\Ben Close.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Thessaly\Input\Guest Close.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Thessaly\Input\Interview Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Thessaly\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Alec — paths absolute so project folder can live outside this repo
    '12': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Alec\Input\Audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alec\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alec\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alec\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Alec\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Nerst — paths absolute so project folder can live outside this repo
    '13': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Nerst\Input\Audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Nerst\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Nerst\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Nerst\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Nerst\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Drew (reading) — Front/Side cameras (mapped as speaker_0/speaker_1
    # so that the wide-referenced auto color match in video_renderer applies),
    # Wide.mp4 is NOT used in any shot but is the color-correction reference.
    '14': {
        'audio_file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Reading Audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Reading Front.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Reading Side.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Drew — interview (Ben/Guest/Wide); paths absolute
    '15': {
        'audio_file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Audio.wav',
        'audio_offset': 0,
        'video_files': {
            'speaker_0': {
                'file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'D:\PodcastRoom\Cursor\Inkhaven Drew\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Decker (reading) — Front/Side cameras plus Wide reference for color match.
    '16': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\clean Decker Reading Audio.wav',
        'audio_offset': 0,
        'enable_color_match': True,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Decker Reading Front Vid.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Decker Reading Side Vid.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Decker Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Decker — interview (Ben/Guest/Wide); paths absolute
    '17': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': True,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Decker\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Rusty — interview (Ben/Guest/Wide); paths absolute
    '18': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Rusty\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Rusty\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Rusty\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Rusty\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Rusty\output\interview_transcript_simplified.json',
    },
}


# Normalize media/transcript paths once so rendering is CWD-independent.
for segment in SEGMENT_CONFIG.values():
    segment['audio_file'] = _resolve_repo_path(segment['audio_file'])
    segment['transcript_file'] = _resolve_repo_path(segment['transcript_file'])
    for camera in segment['video_files'].values():
        camera['file'] = _resolve_repo_path(camera['file'])
