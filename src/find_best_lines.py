#!/usr/bin/env python3
"""
Find the best standalone lines from each section of the podcast.
Uses Claude via anthropic API to analyze sections.
"""

import json
import sys
import os
from typing import List, Dict

def load_transcript(filepath: str) -> List[Dict]:
    """Load and parse transcript JSON."""
    with open(filepath, 'r') as f:
        data = json.load(f)

    # Convert dict to list if needed
    if isinstance(data, dict):
        # Sort by numeric key and convert to list
        items = []
        for key in sorted(data.keys(), key=int):
            item = data[key]
            item['id'] = int(key)
            items.append(item)
        return items
    return data

def group_into_sections(transcript: List[Dict], lines_per_section: int = 30) -> List[List[Dict]]:
    """Group transcript into sections."""
    sections = []
    for i in range(0, len(transcript), lines_per_section):
        section = transcript[i:i+lines_per_section]
        if section:
            sections.append(section)
    return sections

def format_section_text(section: List[Dict]) -> str:
    """Format a section for analysis."""
    lines = []
    for i, item in enumerate(section):
        speaker = "Ryan" if item['speaker_id'] == 0 else "Buck"
        text = item['text'].strip()
        lines.append(f"{i}: {speaker}: {text}")
    return "\n".join(lines)

def get_segment_id(section: List[Dict], section_start_idx: int) -> str:
    """Get the segment ID for referencing in DSL."""
    if section:
        # Use the first item's index in the overall transcript
        return f"{section_start_idx}/{section[0]['id']}"
    return ""

def analyze_with_claude(section: List[Dict], section_num: int, segment_num: str) -> Dict:
    """
    Analyze section with Claude to find the best standalone line.

    Returns dict with 'line_index', 'speaker', 'text', 'reason'
    """
    try:
        from bucklib.chat import Chat
    except ImportError:
        print("Error: bucklib package not installed.")
        sys.exit(1)

    section_text = format_section_text(section)

    chat = Chat()
    chat.user_say(f"""Analyze this section of a podcast transcript and identify the single best standalone line - the most memorable, funny, insightful, or quotable moment.

{section_text}

Please respond with ONLY a JSON object in this exact format:
{{
  "line_index": <the line number from the transcript above>,
  "text": "<the exact text of the line>",
  "reason": "<brief explanation why this is the best standalone line>"
}}""")

    response_text = chat.ask_model("claude-sonnet-4-5-20250929", jsonify=True)

    # Parse JSON response
    try:
        # Handle potential markdown code blocks
        if isinstance(response_text, str):
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            result = json.loads(response_text)
        else:
            result = response_text  # Already parsed by jsonify=True
        return result
    except (json.JSONDecodeError, TypeError) as e:
        print(f"Warning: Could not parse Claude response as JSON: {response_text}")
        return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_best_lines.py <segment_number> [output_file]")
        print("Example: python find_best_lines.py 2")
        print("Example: python find_best_lines.py 2 report.txt")
        sys.exit(1)

    segment_num = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    transcript_file = f'../outputs/segment_{segment_num}_transcript_simplified.json'

    print(f"Loading transcript from {transcript_file}...")
    transcript = load_transcript(transcript_file)
    print(f"Loaded {len(transcript)} lines")

    sections = group_into_sections(transcript, lines_per_section=30)
    print(f"Grouped into {len(sections)} sections\n")

    best_lines = []

    for i, section in enumerate(sections, 1):
        section_start_idx = (i - 1) * 30
        print(f"Analyzing section {i}/{len(sections)}...", end=" ", flush=True)

        result = analyze_with_claude(section, i, segment_num)

        if result:
            print(f"✓")
            line_idx = result.get('line_index', 0)
            speaker = "Ryan" if section[line_idx]['speaker_id'] == 0 else "Buck"
            segment_id = f"segment{segment_num}/{section[line_idx]['id']}"

            best_lines.append({
                'section': i,
                'segment_id': segment_id,
                'speaker': speaker,
                'text': result.get('text', ''),
                'reason': result.get('reason', 'No reason provided')
            })
        else:
            print("✗ (parsing error)")

    # Format results
    output = []
    output.append(f"\n{'='*70}")
    output.append(f"BEST STANDALONE LINES FROM SEGMENT {segment_num}")
    output.append(f"{'='*70}\n")

    for line in best_lines:
        output.append(f"Section {line['section']}: ${line['segment_id']}")
        output.append(f"{line['speaker']}: {line['text']}")
        output.append(f"Why: {line['reason']}")
        output.append("")

    result_text = "\n".join(output)

    # Print to console
    print(result_text)

    # Save to file if specified
    if output_file:
        with open(output_file, 'a') as f:
            f.write(result_text)
            f.write("\n")
        print(f"Results appended to {output_file}")

    return best_lines

if __name__ == '__main__':
    main()
