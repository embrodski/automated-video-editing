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


# Header line emitted by generate_reading_dsl.py / shorten_reading_dsl_silences.py
READING_DSL_MARKER = "// Generated reading DSL"


def is_reading_dsl_text(dsl_text: str) -> bool:
    """True when DSL was produced by the Inkhaven reading autocut pipeline."""
    return any(line.strip().startswith(READING_DSL_MARKER) for line in dsl_text.splitlines())


def segment_uses_embedded_audio(segment_config: dict, *, dsl_text: str | None = None) -> bool:
    """
    Reading segments use AAC embedded in each camera MP4 (not the master WAV) so
    lip-sync does not drift. Explicit config wins; otherwise infer from reading DSL text.
    """
    if segment_config.get('use_video_embedded_audio'):
        return True
    if dsl_text is not None and is_reading_dsl_text(dsl_text):
        return True
    return False


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
        'use_video_embedded_audio': True,
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
        'use_video_embedded_audio': True,
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
        'use_video_embedded_audio': True,
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
    # Inkhaven Georgia — interview (Ben/Guest/Wide); paths absolute
    '19': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Alice (reading) — Front/Side cameras mapped as speaker_0/speaker_1.
    '20': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Reading Audio.wav',
        'audio_offset': 0,
        'use_video_embedded_audio': True,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Reading Front.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Reading Side.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Alice — interview (Ben/Guest/Wide); paths absolute
    '21': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Alice — interview (Massive Test) — paths absolute
    '22': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Alice\Massive Test\interview_transcript_simplified.json',
    },
    # Inkhaven Scott — interview (Ben/Guest/Wide); paths absolute
    '23': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Scott — Intro episode; paths absolute
    '24': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Intro\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Intro\Input\Ben.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Intro\Input\Guest.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Intro\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Scott\Intro\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Georgia — reading (Bellingcat / van Ess); paths absolute
    '25': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Reading Audio.wav',
        'audio_offset': 0,
        'use_video_embedded_audio': True,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Reading Front.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Input\Reading Side.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Georgia\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Aria — reading (Part 1 of dispelling-beauty-lies); paths absolute
    '26': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Reading Audio.wav',
        'audio_offset': 0,
        'use_video_embedded_audio': True,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Reading Front.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Reading Side.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Aria — intro episode; paths absolute
    '27': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Intro Audio Final.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Intro Ben Final.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Intro Guest Final.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Intro Wide Final.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Aria — interview (Ben/Guest/Wide); paths absolute
    '28': {
        'audio_file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Guest.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Ben.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Input\Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\PodcastRoom\Cursor\Inkhaven Aria\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Emmy — interview (Ben/Guest/Wide); paths absolute
    '29': {
        'audio_file': r'E:\Inkhaven Emmy\Input\Main Audio2.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Emmy\Input\Ben Main.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Emmy\Input\Guest Main.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Emmy\Input\Main Wide 2.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Emmy\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Emmy — Play (Emmy / Zoe / Wide + narrator on wide); paths absolute
    '30': {
        'audio_file': r'E:\Inkhaven Emmy\Input\Play Audio.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Emmy\Input\Play Emmy.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Emmy\Input\Play Zoe.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Emmy\Input\Play Wide.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Emmy\Output\play_transcript_simplified.json',
    },
    # Inkhaven Sammy — intro (Ben/Guest/Wide); paths absolute
    '31': {
        'audio_file': r'E:\Inkhaven Sammy\Input\Intro Audio clean-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Sammy\Input\Intro Ben vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Sammy\Input\Intro Guest vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Sammy\Input\Intro Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Sammy\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Sammy — main (Ben/Guest/Wide); paths absolute
    '32': {
        'audio_file': r'E:\Inkhaven Sammy\Input\Main Audio clean-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Sammy\Input\Main Ben vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Sammy\Input\Main Guest vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Sammy\Input\Main Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Sammy\Output\main_transcript_simplified.json',
    },
    # Inkhaven Lawrence — intro (Ben/Guest/Wide); paths absolute
    '33': {
        'audio_file': r'E:\Inkhaven Lawrence\Input\Intro Audio clean-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Lawrence\Input\Intro Ben vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Lawrence\Input\Intro Guest vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Lawrence\Input\Intro Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Lawrence\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Lawrence — main (Ben/Guest/Wide); paths absolute
    '34': {
        'audio_file': r'E:\Inkhaven Lawrence\Input\Main Audio clean-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Lawrence\Input\Main Guest vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Lawrence\Input\Main Ben vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Lawrence\Input\Main Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Lawrence\Output\main_transcript_simplified.json',
    },
    # Inkhaven Lawrence — reading (Front/Side); paths absolute
    '35': {
        'audio_file': r'E:\Inkhaven Lawrence\Input\Reading raw audio-prepped.wav',
        'audio_offset': 0,
        'use_video_embedded_audio': True,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Lawrence\Input\Reading Front-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Lawrence\Input\Reading side-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Lawrence\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Viv — reading (Front/Side); paths absolute
    '36': {
        'audio_file': r'E:\Inkhaven Viv\Input\Reading audio raw-prepped.wav',
        'audio_offset': 0,
        'use_video_embedded_audio': True,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Viv\Input\Reading front-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Viv\Input\Reading side-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Viv\Output\reading_transcript_simplified.json',
    },
    # Inkhaven Viv — interview (Ben/Guest/Wide); paths absolute
    '37': {
        'audio_file': r'E:\Inkhaven Viv\Input\Main Combined Audio cleaned-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Viv\Input\Main Ben vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Viv\Input\Main Guest vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Viv\Input\Main Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Viv\Output\interview_transcript_simplified.json',
    },
    # Inkhaven Nancy (reading) — Front/Side cameras mapped as speaker_0/speaker_1.
    '38': {
        'audio_file': r'E:\Inkhaven Nancy\Input\Reading audio-prepped.wav',
        'audio_offset': 0,
        'use_video_embedded_audio': True,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Nancy\Input\Reading front-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Nancy\Input\Reading side-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Nancy\Temp\reading_transcript_simplified.json',
    },
    # Inkhaven Nancy — intro interview (Ben/Guest/Wide)
    '39': {
        'audio_file': r'E:\Inkhaven Nancy\Input\Intro Audio Clean-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Nancy\Input\Intro Ben vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Nancy\Input\Intro Guest vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Nancy\Input\Intro Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Nancy\temp\interview_transcript_simplified.json',
    },
    # Inkhaven Nancy — main interview (Ben/Guest/Wide)
    '40': {
        'audio_file': r'E:\Inkhaven Nancy\Input\Main Clean Audio RMS-prepped.wav',
        'audio_offset': 0,
        'enable_color_match': False,
        'video_files': {
            'speaker_0': {
                'file': r'E:\Inkhaven Nancy\Input\Main Ben vid-prepped.mp4',
                'offset': 0,
            },
            'speaker_1': {
                'file': r'E:\Inkhaven Nancy\Input\Main Guest vid-prepped.mp4',
                'offset': 0,
            },
            'wide': {
                'file': r'E:\Inkhaven Nancy\Input\Main Wide vid-prepped.mp4',
                'offset': 0,
            },
        },
        'transcript_file': r'E:\Inkhaven Nancy\temp\interview_transcript_simplified.json',
    },
}


# Normalize media/transcript paths once so rendering is CWD-independent.
for segment in SEGMENT_CONFIG.values():
    segment['audio_file'] = _resolve_repo_path(segment['audio_file'])
    segment['transcript_file'] = _resolve_repo_path(segment['transcript_file'])
    for camera in segment['video_files'].values():
        camera['file'] = _resolve_repo_path(camera['file'])
