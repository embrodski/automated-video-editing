#!/usr/bin/env python3
"""Scan E:\\PodcastRoom (or --root) for the latest MultiCorder session cluster."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from piab_lib import (
    DEFAULT_SCAN_ROOT,
    cluster_session_files,
    format_duration,
    list_top_level_multicorder,
    print_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan for latest MultiCorder session.")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_SCAN_ROOT,
        help=f"Folder to scan (default: {DEFAULT_SCAN_ROOT})",
    )
    parser.add_argument("--mtime-tol-sec", type=float, default=60.0)
    parser.add_argument("--duration-tol-sec", type=float, default=2.0)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Limit candidates to this local modified date (YYYY-MM-DD).",
    )
    args = parser.parse_args()

    try:
        skipped: list[dict] = []
        files = list_top_level_multicorder(args.root, skipped=skipped)
        if args.date:
            files = [
                item
                for item in files
                if date.fromisoformat(item.mtime_iso[:10]) == args.date
            ]
        cluster = cluster_session_files(
            files,
            mtime_tol_sec=args.mtime_tol_sec,
            duration_tol_sec=args.duration_tol_sec,
        )
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    videos = [f for f in cluster if f.kind == "video"]
    audios = [f for f in cluster if f.kind == "audio"]
    durations = [f.duration_sec for f in cluster]
    mtimes = [f.mtime for f in cluster]
    payload = {
        "scan_root": str(args.root.resolve()),
        "date_filter": args.date.isoformat() if args.date else None,
        "file_count": len(cluster),
        "video_count": len(videos),
        "audio_count": len(audios),
        "mtime_span_sec": round(max(mtimes) - min(mtimes), 3),
        "duration_span_sec": round(max(durations) - min(durations), 3),
        "typical_duration_sec": sorted(durations)[len(durations) // 2],
        "typical_duration_human": format_duration(sorted(durations)[len(durations) // 2]),
        "typical_mtime_iso": sorted(cluster, key=lambda f: f.mtime)[-1].mtime_iso,
        "skipped_unreadable": skipped,
        "files": [
            {
                "path": f.path,
                "name": f.name,
                "kind": f.kind,
                "mtime_iso": f.mtime_iso,
                "duration_sec": f.duration_sec,
                "duration_human": format_duration(f.duration_sec),
            }
            for f in cluster
        ],
    }
    print_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
