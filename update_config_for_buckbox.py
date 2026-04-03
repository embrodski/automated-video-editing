#!/usr/bin/env python3
"""
Helper script to update config.py paths for BuckBox deployment.
This helps you update the video file paths to point to your high-resolution videos.
"""

import sys

def print_usage():
    print("""
Usage: python update_config_for_buckbox.py

This script will prompt you for the paths to your high-resolution video files
on BuckBox and generate an updated config.py file.

Alternatively, you can manually edit ~/mymovie/src/podcast_dsl/config.py on BuckBox
to update the video file paths in the 'file' fields.

Current config structure:
- 'audio_file': path to audio file
- 'video_files': dict with speaker_0, speaker_1, and wide camera angles
  - Each has 'file' (path) and 'offset' (timing in seconds)
- 'transcript_file': path to transcript JSON

Example paths on BuckBox:
  '../inputs/ryan_highres.mp4'
  '/home/buck/mymovie/inputs/ryan_highres.mp4'
""")

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print_usage()
        return

    print("BuckBox Config Updater")
    print("=" * 50)
    print("\nThis will help you update video file paths for high-resolution videos.")
    print("\nCurrent segments: 2, 3, 6")
    print("\nFor each segment, you need paths for:")
    print("  - speaker_0 (Ryan)")
    print("  - speaker_1 (Buck)")
    print("  - wide (Both)")
    print("\nPress Ctrl+C to cancel at any time.\n")

    try:
        config_lines = []
        config_lines.append('"""')
        config_lines.append('Configuration for podcast segments.')
        config_lines.append('"""')
        config_lines.append('')
        config_lines.append('# Segment configuration')
        config_lines.append('SEGMENT_CONFIG = {')

        for segment in ['2', '3', '6']:
            print(f"\n--- Segment {segment} ---")
            audio = input(f"Audio file path for segment {segment} [../inputs/segment_{segment}_audio.mp3]: ").strip()
            if not audio:
                audio = f'../inputs/segment_{segment}_audio.mp3'

            speaker_0 = input(f"Video file for speaker_0 (Ryan): ").strip()
            speaker_1 = input(f"Video file for speaker_1 (Buck): ").strip()
            wide = input(f"Video file for wide (Both): ").strip()

            print("Note: Using default offsets from original config. Adjust manually if needed.")

            # Default offsets from original config
            offsets = {
                '2': {'speaker_0': 303.964642, 'speaker_1': 303.964642 + 11.017075, 'wide': 303.964642 + 8.111995},
                '3': {'speaker_0': 1377.556, 'speaker_1': 1377.556 + 11.017075, 'wide': 1377.556 + 8.111995},
                '6': {'speaker_0': 12299.414, 'speaker_1': 12299.414 + 11.017075, 'wide': 12299.414 + 8.111995},
            }

            config_lines.append(f"    '{segment}': {{")
            config_lines.append(f"        'audio_file': '{audio}',")
            config_lines.append(f"        'audio_offset': 0,")
            config_lines.append(f"        'video_files': {{")
            config_lines.append(f"            'speaker_0': {{")
            config_lines.append(f"                'file': '{speaker_0}',")
            config_lines.append(f"                'offset': {offsets[segment]['speaker_0']}")
            config_lines.append(f"            }},")
            config_lines.append(f"            'speaker_1': {{")
            config_lines.append(f"                'file': '{speaker_1}',")
            config_lines.append(f"                'offset': {offsets[segment]['speaker_1']}")
            config_lines.append(f"            }},")
            config_lines.append(f"            'wide': {{")
            config_lines.append(f"                'file': '{wide}',")
            config_lines.append(f"                'offset': {offsets[segment]['wide']}")
            config_lines.append(f"            }}")
            config_lines.append(f"        }},")
            config_lines.append(f"        'transcript_file': '../outputs/segment_{segment}_transcript_simplified.json',")
            config_lines.append(f"    }},")

        config_lines.append('}')
        config_lines.append('')

        output = '\n'.join(config_lines)

        print("\n" + "=" * 50)
        print("Generated config.py:")
        print("=" * 50)
        print(output)
        print("=" * 50)

        save = input("\nSave to config_buckbox.py? [y/N]: ").strip().lower()
        if save == 'y':
            with open('config_buckbox.py', 'w') as f:
                f.write(output)
            print("\nSaved to config_buckbox.py")
            print("Copy this to BuckBox with:")
            print("  scp -i ~/.ssh/id_ed25519_buckbox config_buckbox.py 100.107.3.113:~/mymovie/src/podcast_dsl/config.py")

    except KeyboardInterrupt:
        print("\n\nCancelled.")
        return

if __name__ == '__main__':
    main()
