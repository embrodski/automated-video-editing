#!/usr/bin/env python3
"""Initialize an Inkhaven episode folder for inkhaven-episode-harness."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


SUBFOLDERS = ("Raw", "Input", "Output", "Temp")
RAW_NAME_RE = re.compile(r"raw", re.IGNORECASE)
INKHAVEN_PREFIX_RE = re.compile(r"^inkhaven\s+(.+)$", re.IGNORECASE)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_guest_name(episode_folder: Path) -> str:
    match = INKHAVEN_PREFIX_RE.match(episode_folder.name.strip())
    if not match:
        raise ValueError(
            f"Episode folder name must start with 'Inkhaven ' "
            f"(got {episode_folder.name!r})."
        )
    name = match.group(1).strip()
    if not name:
        raise ValueError(
            f"Guest name is empty after 'Inkhaven ' in {episode_folder.name!r}."
        )
    return name


def episode_json_path(episode_folder: Path, name: str) -> Path:
    return episode_folder / f"{name}-episode.json"


def _load_episode_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _step_state(
    existing: dict,
    step_id: str,
    *,
    title: str,
    status: str,
    **extra: object,
) -> dict:
    prior = existing.get(step_id, {})
    step = {
        "id": step_id,
        "title": title,
        "status": status,
        **extra,
    }
    if status == "completed":
        step["completed_at"] = _utc_now_iso()
    elif "completed_at" in prior and status != "completed":
        step["completed_at"] = prior["completed_at"]
    return step


def is_raw_source_file(path: Path) -> bool:
    return path.is_file() and RAW_NAME_RE.search(path.name) is not None


def init_episode(episode_folder: Path, *, dry_run: bool = False) -> dict:
    episode_folder = episode_folder.resolve()
    if not episode_folder.is_dir():
        raise FileNotFoundError(f"Episode folder not found: {episode_folder}")

    name = extract_guest_name(episode_folder)
    json_path = episode_json_path(episode_folder, name)
    prior = _load_episode_state(json_path)

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

    now = _utc_now_iso()
    steps = prior.get("steps", {})
    steps["01_launch"] = _step_state(
        steps,
        "01_launch",
        title="Launch",
        status="completed",
    )
    prep_status = "failed" if move_errors else "completed"
    steps["02_prep_folders"] = _step_state(
        steps,
        "02_prep_folders",
        title="Prep folders and raw files",
        status=prep_status,
        created_subfolders=created_subfolders,
        raw_files_moved=moved_raw_files,
        closing_mp4_moved=closing_moved,
        errors=move_errors,
    )
    if steps.get("03_reading_link", {}).get("status") != "completed":
        steps["03_reading_link"] = _step_state(
            steps,
            "03_reading_link",
            title="Reading source link",
            status="pending",
        )
    if steps.get("04_verify_reading_link", {}).get("status") not in (
        "completed",
        "skipped",
    ):
        steps["04_verify_reading_link"] = _step_state(
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
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")

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
