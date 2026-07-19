#!/usr/bin/env python3
"""Create a Podcast In A Box working folder and state after the user confirms a scan."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite
from piab_lib import (
    DEFAULT_SCAN_ROOT,
    MediaInfo,
    cluster_session_files,
    ensure_subfolders,
    list_top_level_multicorder,
    mark_step,
    new_piab_state,
    print_json,
    save_piab_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Init Podcast In A Box working folder.")
    parser.add_argument(
        "--name",
        required=True,
        help="Working folder name under --root (user-chosen).",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_SCAN_ROOT)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Limit re-scan candidates to this local modified date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--from-scan-json",
        type=Path,
        help="Optional JSON from piab_scan_session.py (skips re-scan).",
    )
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    working = (root / args.name.strip()).resolve()
    if working.parent != root:
        print("ERROR: --name must be a single folder name, not a path.", file=sys.stderr)
        return 1

    try:
        if working.exists() and any(working.iterdir()):
            refuse_overwrite(
                working / "podcast-in-a-box.json",
                allow_overwrite=args.allow_overwrite,
                label="existing working folder state",
            )

        if args.from_scan_json:
            data = json.loads(args.from_scan_json.read_text(encoding="utf-8"))
            session_files = [
                MediaInfo(
                    path=f["path"],
                    name=f["name"],
                    kind=f["kind"],
                    mtime=Path(f["path"]).stat().st_mtime,
                    mtime_iso=f["mtime_iso"],
                    duration_sec=float(f["duration_sec"]),
                )
                for f in data["files"]
            ]
        else:
            candidates = list_top_level_multicorder(root)
            if args.date:
                candidates = [
                    item
                    for item in candidates
                    if date.fromisoformat(item.mtime_iso[:10]) == args.date
                ]
            session_files = cluster_session_files(candidates)

        working.mkdir(parents=True, exist_ok=True)
        ensure_subfolders(working)
        state = new_piab_state(
            working,
            name=args.name.strip(),
            scan_root=root,
            session_files=session_files,
        )
        mark_step(
            state,
            "01_scan_confirm",
            title="Scan and confirm session files",
            status="completed",
            file_count=len(session_files),
        )
        mark_step(
            state,
            "02_create_folder",
            title="Create working folder",
            status="completed",
            working_folder=str(working),
        )
        state["resume_at"] = "03_label_videos"
        save_piab_state(working, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
