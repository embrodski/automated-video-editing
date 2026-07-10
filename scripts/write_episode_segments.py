#!/usr/bin/env python3
"""Write or update one segment in <temp>/segments.json (manual autocut + debugging)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from episode_segments import (
    MAIN_SEGMENT_KEY,
    READING_SEGMENT_KEY,
    segments_path,
    upsert_segment,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upsert a segment entry into Temp/segments.json."
    )
    parser.add_argument("--temp-dir", type=Path, required=True)
    parser.add_argument(
        "--key",
        required=True,
        choices=(MAIN_SEGMENT_KEY, READING_SEGMENT_KEY),
        help=f"Segment key ({MAIN_SEGMENT_KEY} or {READING_SEGMENT_KEY}).",
    )
    parser.add_argument(
        "--entry-json",
        type=Path,
        required=True,
        help="JSON file containing one segment entry object.",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Replace an existing segment key (requires user approval).",
    )
    args = parser.parse_args()

    try:
        with args.entry_json.open(encoding="utf-8") as fh:
            entry = json.load(fh)
        if not isinstance(entry, dict):
            raise ValueError(f"Entry must be a JSON object: {args.entry_json}")
        path = upsert_segment(
            args.temp_dir,
            args.key,
            entry,
            allow_overwrite=args.allow_overwrite,
        )
    except (FileExistsError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"segments_file": str(path), "key": args.key}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
