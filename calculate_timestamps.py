#!/usr/bin/env python3
"""
Calculate timestamps in the final video where subheadings appear.
Uses text matching to find the right clips since markdown entry numbers
don't directly map to segment clip IDs.
"""

import json
import re
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

SEGMENT_CONFIG = {
    '2': {'transcript_file': os.path.join(SCRIPT_DIR, 'outputs/segment_2_transcript_simplified.json')},
    '3': {'transcript_file': os.path.join(SCRIPT_DIR, 'outputs/segment_3_transcript_simplified.json')},
    '6': {'transcript_file': os.path.join(SCRIPT_DIR, 'outputs/segment_6_transcript_simplified.json')},
}


def load_transcript(transcript_file):
    with open(transcript_file, 'r') as f:
        return json.load(f)


def normalize_text(text):
    """Normalize text for fuzzy matching."""
    text = re.sub(r'[^\w\s]', '', text.lower())
    return ' '.join(text.split())


def parse_dsl_line(line):
    line = line.strip()
    if not line or line.startswith('#'):
        return None

    # Handle special commands that add time
    if line.startswith('!'):
        # !fade to black 200 / !fade from black 200 - adds 200ms each
        fade_match = re.match(r'!fade\s+(?:to|from)\s+black\s+(\d+)', line)
        if fade_match:
            ms = int(fade_match.group(1))
            return {'type': 'fade', 'duration': ms / 1000.0}

        # !black 2 - adds 2 seconds of black
        black_match = re.match(r'!black\s+([\d.]+)', line)
        if black_match:
            secs = float(black_match.group(1))
            return {'type': 'black', 'duration': secs}

        return None

    match = re.match(r'\$segment(\d+)/(\d+)(?:\s+slice\(([^)]+)\))?', line)
    if not match:
        return None

    segment_num = match.group(1)
    clip_id = match.group(2)
    slice_spec = match.group(3)

    slice_start = None
    slice_end = None
    if slice_spec:
        parts = slice_spec.split(':')
        if len(parts) == 2:
            if parts[0]:
                slice_start = float(parts[0])
            if parts[1]:
                slice_end = float(parts[1])

    return {
        'type': 'clip',
        'segment': segment_num,
        'clip_id': clip_id,
        'slice_start': slice_start,
        'slice_end': slice_end
    }


def get_clip_times(segment_num, clip_id, slice_start, slice_end, transcripts):
    if segment_num not in transcripts:
        return None, None
    transcript = transcripts[segment_num]
    if clip_id not in transcript:
        return None, None

    sentence = transcript[clip_id]
    audio_start = sentence['start']
    audio_end = sentence['end']
    original_start, original_end = audio_start, audio_end

    if slice_start is not None:
        audio_start = original_end + slice_start if slice_start < 0 else original_start + slice_start
    if slice_end is not None:
        audio_end = original_end + slice_end if slice_end < 0 else original_start + slice_end

    return audio_start, audio_end


def build_clip_sequence_with_gaps(dsl_file, transcripts):
    # First pass: parse all DSL lines into items (clips and timing commands)
    items = []
    with open(dsl_file, 'r') as f:
        for line in f:
            parsed = parse_dsl_line(line)
            if parsed:
                if parsed.get('type') == 'clip':
                    start, end = get_clip_times(
                        parsed['segment'], parsed['clip_id'],
                        parsed['slice_start'], parsed['slice_end'], transcripts
                    )
                    if start is not None:
                        items.append({
                            'type': 'clip',
                            'segment': parsed['segment'],
                            'clip_id': parsed['clip_id'],
                            'audio_start': start,
                            'audio_end': end,
                        })
                elif parsed.get('type') in ('fade', 'black'):
                    items.append(parsed)

    # Second pass: build sequence with proper timing
    result = []
    cumulative_time = 0.0
    i = 0

    while i < len(items):
        item = items[i]

        # Handle timing commands
        if item['type'] in ('fade', 'black'):
            cumulative_time += item['duration']
            i += 1
            continue

        # Handle clips - group consecutive ones
        group = [item]
        group_start_idx = i

        while i + 1 < len(items):
            next_item = items[i + 1]

            # Stop grouping if we hit a timing command
            if next_item['type'] in ('fade', 'black'):
                break

            curr = items[i]
            same_segment = curr['segment'] == next_item['segment']
            try:
                sequential = int(next_item['clip_id']) == int(curr['clip_id']) + 1
            except:
                sequential = False

            if same_segment and sequential:
                gap = next_item['audio_start'] - curr['audio_end']
                if gap <= 5.0:
                    i += 1
                    group.append(items[i])
                    continue
            break

        group_duration = group[-1]['audio_end'] - group[0]['audio_start']
        for clip in group:
            offset_in_group = clip['audio_start'] - group[0]['audio_start']
            result.append({
                'segment': clip['segment'],
                'clip_id': clip['clip_id'],
                'video_start_time': cumulative_time + offset_in_group,
            })
        cumulative_time += group_duration
        i += 1

    return result, cumulative_time


def build_text_index(transcripts):
    """Build index of normalized text -> (segment, clip_id)."""
    index = {}
    for seg_num, transcript in transcripts.items():
        for clip_id, data in transcript.items():
            norm = normalize_text(data['text'])
            # Use first 50 chars as key
            key = norm[:50]
            if key and len(key) > 15:
                index[key] = (seg_num, clip_id)
    return index


def find_clip_by_text(text, text_index, transcripts):
    """Find clip by matching text content."""
    norm = normalize_text(text)

    # Try exact prefix match
    key = norm[:50]
    if key in text_index:
        return text_index[key]

    # Try fuzzy matching with shorter prefixes
    for index_key, clip_info in text_index.items():
        if norm[:30] in index_key or index_key[:30] in norm:
            return clip_info

    # Try even shorter matches for harder cases
    for index_key, clip_info in text_index.items():
        if norm[:20] in index_key or index_key[:20] in norm:
            return clip_info

    # Try word-based matching
    norm_words = set(norm.split()[:8])
    for index_key, clip_info in text_index.items():
        key_words = set(index_key.split()[:8])
        if len(norm_words & key_words) >= 5:
            return clip_info

    # Try matching distinctive words anywhere in the text
    distinctive_words = [w for w in norm.split() if len(w) > 6]
    for index_key, clip_info in text_index.items():
        for word in distinctive_words[:5]:
            if word in index_key:
                return clip_info

    return None


def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def main():
    intro_duration = 72.789

    transcripts = {}
    for seg_num, config in SEGMENT_CONFIG.items():
        transcripts[seg_num] = load_transcript(config['transcript_file'])

    text_index = build_text_index(transcripts)

    clips, total_calculated = build_clip_sequence_with_gaps(
        'podcast_sequences/all_but_intro.dsl', transcripts
    )

    clip_first_occurrence = {}
    for clip in clips:
        key = (clip['segment'], clip['clip_id'])
        if key not in clip_first_occurrence:
            clip_first_occurrence[key] = clip['video_start_time']

    with open('transcript_with_subheadings.md', 'r') as f:
        md_lines = f.readlines()

    results = []
    i = 0
    while i < len(md_lines):
        line = md_lines[i].strip()

        if line.startswith('#'):
            heading_match = re.match(r'^(#+)\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip('*').strip()

                if title == "Podcast Transcript":
                    i += 1
                    continue

                # Find next speaker entry and use its text to match
                clip_key = None
                for j in range(i+1, min(i+20, len(md_lines))):
                    next_line = md_lines[j].strip()
                    # Match with or without entry number
                    speaker_match = re.match(r'\*\*(\w+)\*\*\s*(?:\(\d+\))?:\s*(.+)', next_line)
                    if speaker_match:
                        text_sample = speaker_match.group(2)
                        clip_key = find_clip_by_text(text_sample, text_index, transcripts)
                        break

                if clip_key and clip_key in clip_first_occurrence:
                    time_in_allbutintro = clip_first_occurrence[clip_key]
                    video_time = intro_duration + time_in_allbutintro
                    timestamp_str = format_timestamp(video_time)
                else:
                    timestamp_str = "??:??"
                    video_time = None

                results.append({
                    'level': level,
                    'title': title,
                    'timestamp': timestamp_str,
                    'video_time': video_time,
                })

        i += 1

    # Handle special cases where text matching fails
    special_cases = {
        'P(doom)': intro_duration,  # First section, starts right after intro
        'Hyperstition': 10434.0,  # segment6/122
        'Will control backfire by preventing warning shots?': 11842.6,  # segment6/403
    }
    for r in results:
        if r['title'] in special_cases and r['video_time'] is None:
            r['video_time'] = special_cases[r['title']]
            r['timestamp'] = format_timestamp(r['video_time'])

    results_with_time = [r for r in results if r['video_time'] is not None]
    results_without_time = [r for r in results if r['video_time'] is None]
    results_with_time.sort(key=lambda x: x['video_time'])

    print("=" * 80)
    print("SUBHEADING TIMESTAMPS IN FINAL VIDEO")
    print("(Intro: ~1:13, Total: ~3:56:09)")
    print("=" * 80)
    print()

    for r in results_with_time:
        level = r['level']
        indent = "  " * max(0, level - 2)
        print(f"{r['timestamp']:>10}  {indent}{r['title']}")

    if results_without_time:
        print()
        print("--- Sections with unknown timestamps ---")
        for r in results_without_time:
            print(f"{'??:??':>10}  {'#' * r['level']} {r['title']}")

    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
