#!/usr/bin/env python3
"""Initialize an Inkhaven episode folder for inkhaven-episode-harness."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    RAW_NAME_RE,
    SUBFOLDERS,
    audit_raw_source_inventory,
    episode_json_path,
    extract_guest_name,
    load_episode_state_if_exists,
    save_episode_state,
    step_state,
    utc_now_iso,
)


def is_raw_source_file(path: Path) -> bool:
    return path.is_file() and RAW_NAME_RE.search(path.name) is not None


def init_episode(episode_folder: Path, *, dry_run: bool = False) -> dict:
    episode_folder = episode_folder.resolve()
    if not episode_folder.is_dir():
        raise FileNotFoundError(f"Episode folder not found: {episode_folder}")

    name = extract_guest_name(episode_folder)
    json_path = episode_json_path(episode_folder, name)
    prior = load_episode_state_if_exists(episode_folder)

    raw_dir = episode_folder / "Raw"
    input_dir = episode_folder / "Input"
    output_dir = episode_folder / "Output"
    temp_dir = episode_folder / "Temp"

    created_subfolders: list[str] = []
    for sub in SUBFOLDERS:
        sub_path = episode_folder / sub
        if not sub_path.exists():
            created_subfolders.append(sub)
            if not dry_run:
                sub_path.mkdir(parents=True, exist_ok=True)

    moved_raw_files: list[str] = []
    move_errors: list[str] = []
    for item in sorted(episode_folder.iterdir(), key=lambda p: p.name.lower()):
        if not is_raw_source_file(item):
            continue
        dest = raw_dir / item.name
        if dest.exists():
            move_errors.append(
                f"Skipped {item.name}: already exists in Raw ({dest})."
            )
            continue
        moved_raw_files.append(item.name)
        if not dry_run:
            shutil.move(str(item), str(dest))

    closing_moved = False
    closing_source = episode_folder.parent / "Closing.mp4"
    closing_dest = output_dir / "Closing.mp4"
    if closing_source.is_file():
        if closing_dest.exists():
            move_errors.append(
                f"Closing.mp4 already exists in Output ({closing_dest}); "
                f"left source at {closing_source}."
            )
        else:
            closing_moved = True
            if not dry_run:
                shutil.move(str(closing_source), str(closing_dest))

    raw_inventory = audit_raw_source_inventory(raw_dir)
    now = utc_now_iso()
    steps = prior.get("steps", {})
    steps["01_launch"] = step_state(
        steps,
        "01_launch",
        title="Launch",
        status="completed",
    )
    prep_status = "failed" if move_errors else "completed"
    steps["02_prep_folders"] = step_state(
        steps,
        "02_prep_folders",
        title="Prep folders and raw files",
        status=prep_status,
        created_subfolders=created_subfolders,
        raw_files_moved=moved_raw_files,
        closing_mp4_moved=closing_moved,
        errors=move_errors,
        raw_inventory=raw_inventory,
    )
    if steps.get("03_reading_link", {}).get("status") != "completed":
        steps["03_reading_link"] = step_state(
            steps,
            "03_reading_link",
            title="Reading source link",
            status="pending",
        )
    if steps.get("04_verify_reading_link", {}).get("status") not in (
        "completed",
        "skipped",
    ):
        steps["04_verify_reading_link"] = step_state(
            steps,
            "04_verify_reading_link",
            title="Verify reading link",
            status="pending",
        )

    state = {
        "harness": "inkhaven-episode-harness",
        "name": name,
        "episode_folder": str(episode_folder),
        "reading_link": prior.get("reading_link"),
        "skip_reading": prior.get("skip_reading", False),
        "paths": {
            "raw": str(raw_dir),
            "input": str(input_dir),
            "output": str(output_dir),
            "temp": str(temp_dir),
        },
        "created_at": prior.get("created_at", now),
        "updated_at": now,
        "steps": steps,
    }

    if not dry_run:
        save_episode_state(episode_folder, state)

    state["episode_json"] = str(json_path)
    state["dry_run"] = dry_run
    return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize an Inkhaven episode folder (steps 1–2)."
    )
    parser.add_argument(
        "episode_folder",
        type=Path,
        help="Episode working folder (e.g. E:\\Inkhaven Viv)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report actions without creating folders, moving files, or writing JSON.",
    )
    args = parser.parse_args()

    try:
        result = init_episode(args.episode_folder, dry_run=args.dry_run)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    if result.get("steps", {}).get("02_prep_folders", {}).get("errors"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
