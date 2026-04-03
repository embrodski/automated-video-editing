#!/usr/bin/env python3
"""
Demo script to test audio crossfading by creating many quick cuts.
This will make audio clicks very obvious if they exist.
"""

import subprocess
import tempfile
import os
import sys
import shutil

def get_video_duration(video_file):
    """Get duration of video in seconds using ffprobe"""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def extract_segment(input_file, start_time, duration, output_file):
    """Extract a segment from a video file"""
    cmd = [
        'ffmpeg', '-y',
        '-ss', str(start_time),
        '-i', input_file,
        '-t', str(duration),
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_file
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def concatenate_without_crossfade(clip_files, output_file):
    """Concatenate clips without crossfading (will have clicks)"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        concat_list = f.name
        for clip_file in clip_files:
            f.write(f"file '{os.path.abspath(clip_file)}'\n")

    try:
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_list,
            '-c', 'copy',
            output_file
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.unlink(concat_list)


def concatenate_with_crossfade(clip_files, output_file, crossfade_duration=0.020):
    """Concatenate clips with audio crossfading (no clicks)"""
    if len(clip_files) == 1:
        shutil.copy2(clip_files[0], output_file)
        return

    # Build FFmpeg filter_complex for video concat and audio crossfades
    video_inputs = ''.join(f'[{i}:v]' for i in range(len(clip_files)))
    video_filter = f'{video_inputs}concat=n={len(clip_files)}:v=1:a=0[v]'

    # Audio: chain of acrossfade filters
    audio_filters = []
    if len(clip_files) == 2:
        audio_filters.append(f'[0:a][1:a]acrossfade=d={crossfade_duration}[a]')
    else:
        for i in range(len(clip_files) - 1):
            if i == 0:
                left_input = '[0:a]'
            else:
                left_input = f'[a{i-1:02d}]'

            right_input = f'[{i+1}:a]'

            if i == len(clip_files) - 2:
                output = '[a]'
            else:
                output = f'[a{i:02d}]'

            audio_filters.append(f'{left_input}{right_input}acrossfade=d={crossfade_duration}{output}')

    filter_complex = video_filter + ';' + ';'.join(audio_filters)

    # Build FFmpeg command
    cmd = ['ffmpeg', '-y']

    # Add all input files
    for clip_file in clip_files:
        cmd.extend(['-i', clip_file])

    # Add filter_complex
    cmd.extend([
        '-filter_complex', filter_complex,
        '-map', '[v]',
        '-map', '[a]',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_file
    ])

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if len(sys.argv) != 2:
        print("Usage: python test_crossfade.py <input_video_file>")
        print("\nThis script will:")
        print("  1. Cut the input video into many small segments (0.4s each)")
        print("  2. Create two output files:")
        print("     - output_no_crossfade.mp4 (will have clicks)")
        print("     - output_with_crossfade.mp4 (smooth, no clicks)")
        print("\nListen to both and compare!")
        sys.exit(1)

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"Error: File not found: {input_file}")
        sys.exit(1)

    print(f"Input file: {input_file}")

    # Get video duration
    duration = get_video_duration(input_file)
    print(f"Duration: {duration:.2f}s")

    # Parameters for cutting
    segment_duration = 0.4  # 400ms segments - short enough to potentially cause clicks
    max_segments = 20  # Limit number of segments for demo

    # Calculate segments
    num_segments = min(int(duration / segment_duration), max_segments)
    print(f"\nCutting into {num_segments} segments of {segment_duration}s each...")

    # Create temp directory for segments
    with tempfile.TemporaryDirectory() as tmpdir:
        print("Extracting segments...")
        segment_files = []

        for i in range(num_segments):
            start_time = i * segment_duration
            segment_file = os.path.join(tmpdir, f'segment_{i:03d}.mp4')
            print(f"  Segment {i+1}/{num_segments}: {start_time:.2f}s - {start_time + segment_duration:.2f}s")
            extract_segment(input_file, start_time, segment_duration, segment_file)
            segment_files.append(segment_file)

        print(f"\nCreating comparison outputs...")

        # Output files
        output_no_crossfade = 'output_no_crossfade.mp4'
        output_with_crossfade = 'output_with_crossfade.mp4'

        print("  1. Concatenating WITHOUT crossfade (may have clicks)...")
        concatenate_without_crossfade(segment_files, output_no_crossfade)
        print(f"     Saved: {output_no_crossfade}")

        print("  2. Concatenating WITH crossfade (should be smooth)...")
        concatenate_with_crossfade(segment_files, output_with_crossfade, crossfade_duration=0.020)
        print(f"     Saved: {output_with_crossfade}")

    print("\n" + "="*70)
    print("DEMO COMPLETE!")
    print("="*70)
    print(f"\nCompare these two files:")
    print(f"  1. {output_no_crossfade}  <- May have clicks between segments")
    print(f"  2. {output_with_crossfade} <- Should be smooth (20ms crossfades)")
    print(f"\nPlay both files and listen carefully at the cuts!")
    print(f"The crossfaded version should have no audible clicks.\n")


if __name__ == '__main__':
    main()
