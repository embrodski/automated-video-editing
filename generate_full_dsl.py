#!/usr/bin/env python3
"""
Generate a full sequential DSL file from a simplified transcript JSON.

Example:
  python generate_full_dsl.py Wide_Video_Interview_Audio_Copy_eng_simplified.json \
      --segment 1 \
      --output podcast_sequences/interview_full.dsl
"""

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a sequential DSL file from a simplified transcript."
    )
    parser.add_argument("transcript_json", help="Path to simplified transcript JSON")
    parser.add_argument(
        "--segment",
        required=True,
        help="Segment number to use in generated DSL entries, e.g. 1",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output DSL file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    transcript_path = Path(args.transcript_json)
    output_path = Path(args.output)

    with transcript_path.open("r", encoding="utf-8") as f:
        transcript = json.load(f)

    segment_num = str(args.segment)
    lines = []

    for key in sorted(transcript.keys(), key=int):
        entry = transcript[key]
        text = entry.get("text", "").strip().replace("\n", " ")
        speaker_name = entry.get("speaker_name")
        comment = f" // {speaker_name}: {text}" if speaker_name else f" // {text}"
        lines.append(f"$segment{segment_num}/{key}{comment}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} DSL lines to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
