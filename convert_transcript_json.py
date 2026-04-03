#!/usr/bin/env python3
"""
Convert a JSON transcript into the simplified format expected by podcast_dsl.

Input format:
- Top-level JSON object with a "segments" array
- Each segment has "text", "start_time", "end_time", and an optional nested
  "speaker" object with "id" and/or "name"

Output format:
- JSON object keyed by sentence index as a string
- Each value has:
  - "start": float seconds
  - "end": float seconds
  - "text": utterance text
  - "speaker_id": integer speaker id
  - "speaker_name": optional human-readable speaker name

Example:
  python convert_transcript_json.py Wide_Video_Interview_Audio_Copy_eng.json
  python convert_transcript_json.py input.json -o outputs/segment_1_transcript_simplified.json
  python convert_transcript_json.py input.json --drop-nonspeech
"""

import argparse
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert transcript JSON to podcast_dsl transcript format."
    )
    parser.add_argument(
        "input_json",
        help="Path to the source JSON transcript file",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON path (default: <input>_simplified.json)",
    )
    parser.add_argument(
        "--drop-nonspeech",
        action="store_true",
        help="Drop segments whose text is only bracketed stage directions like [laughs]",
    )
    parser.add_argument(
        "--keep-empty",
        action="store_true",
        help="Keep empty/whitespace-only transcript segments",
    )
    parser.add_argument(
        "--speaker-source",
        choices=["id", "name", "auto"],
        default="auto",
        help="How to derive speaker identity (default: auto)",
    )
    return parser.parse_args()


def infer_output_path(input_path: str) -> str:
    stem, ext = os.path.splitext(input_path)
    if ext.lower() == ".json":
        return f"{stem}_simplified.json"
    return f"{input_path}_simplified.json"


def load_input(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return text.strip()


def is_nonspeech_text(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and bool(re.fullmatch(r"\[[^\]]+\]", stripped))


def extract_speaker_token(segment: Dict, speaker_source: str) -> Tuple[Optional[str], Optional[str]]:
    speaker = segment.get("speaker") or {}
    speaker_id = speaker.get("id")
    speaker_name = speaker.get("name")

    if speaker_source == "id":
        return speaker_id, speaker_name
    if speaker_source == "name":
        return speaker_name, speaker_name

    # auto: prefer explicit speaker id, fall back to human-readable name
    return speaker_id or speaker_name, speaker_name


def convert_speaker_token_to_int(
    token: Optional[str],
    speaker_name: Optional[str],
    speaker_map: Dict[str, int],
) -> Optional[int]:
    if token is None:
        return None

    match = re.fullmatch(r"speaker_(\d+)", str(token))
    if match:
        return int(match.group(1))

    if token not in speaker_map:
        speaker_map[token] = len(speaker_map)
    return speaker_map[token]


def validate_segment(segment: Dict, index: int) -> Tuple[float, float]:
    if "start_time" not in segment or "end_time" not in segment:
        raise ValueError(f"Segment {index} is missing start_time or end_time")

    start = float(segment["start_time"])
    end = float(segment["end_time"])

    if end < start:
        raise ValueError(f"Segment {index} has end_time < start_time")

    return start, end


def convert_segments(
    segments: List[Dict],
    drop_nonspeech: bool,
    keep_empty: bool,
    speaker_source: str,
) -> Tuple[Dict[str, Dict], Dict[str, int]]:
    output: Dict[str, Dict] = {}
    speaker_map: Dict[str, int] = {}
    output_index = 0

    for input_index, segment in enumerate(segments):
        start, end = validate_segment(segment, input_index)
        text = normalize_text(segment.get("text"))

        if not keep_empty and not text:
            continue
        if drop_nonspeech and is_nonspeech_text(text):
            continue

        speaker_token, speaker_name = extract_speaker_token(segment, speaker_source)
        speaker_id = convert_speaker_token_to_int(speaker_token, speaker_name, speaker_map)

        converted = {
            "start": start,
            "end": end,
            "text": text,
        }

        if speaker_id is not None:
            converted["speaker_id"] = speaker_id
        if speaker_name:
            converted["speaker_name"] = speaker_name

        output[str(output_index)] = converted
        output_index += 1

    return output, speaker_map


def main() -> int:
    args = parse_args()

    data = load_input(args.input_json)
    segments = data.get("segments")
    if not isinstance(segments, list):
        print("Error: input JSON must contain a top-level 'segments' array.", file=sys.stderr)
        return 1

    output_path = args.output or infer_output_path(args.input_json)
    converted, speaker_map = convert_segments(
        segments,
        drop_nonspeech=args.drop_nonspeech,
        keep_empty=args.keep_empty,
        speaker_source=args.speaker_source,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(converted, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(converted)} transcript segments to {output_path}")
    if speaker_map:
        print("Speaker mapping:")
        for token, speaker_id in speaker_map.items():
            print(f"  {token} -> {speaker_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
