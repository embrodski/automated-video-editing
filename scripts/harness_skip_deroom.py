#!/usr/bin/env python3
"""Harness step 7 bypass: copy Combined → Clean (no Audacity DeRoom)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    find_clean_audio_files,
    load_episode_state,
    save_episode_state,
    step_state,
)
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite


def _combined_to_clean(combined: Path, *, allow_overwrite: bool) -> Path:
    if "Combined Audio" in combined.name:
        clean_name = combined.name.replace("Combined Audio", "Clean Audio")
    else:
        clean_name = f"{combined.stem} Clean Audio{combined.suffix}"
    clean = combined.parent / clean_name
    refuse_overwrite(clean, allow_overwrite=allow_overwrite)
    shutil.copy2(combined, clean)
    ref_mtime = combined.stat().st_mtime
    touch = max(time.time(), ref_mtime + 1.0)
    clean.touch()
    import os

    os.utime(clean, (touch, touch))
    return clean


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skip Audacity DeRoom: alias Combined Audio to Clean Audio in Raw."
    )
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite existing Clean WAV copies (requires user approval).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        raw_dir = Path(state["paths"]["raw"])
        main_combined = Path(state["main_combined_audio"]) if state.get("main_combined_audio") else None
        if not main_combined or not main_combined.is_file():
            raise FileNotFoundError("main_combined_audio missing from episode state.")

        intro_combined = (
            Path(state["intro_combined_audio"])
            if state.get("intro_combined_audio")
            else None
        )
        if intro_combined and not intro_combined.is_file():
            intro_combined = None

        _combined_to_clean(main_combined, allow_overwrite=args.allow_overwrite)
        if intro_combined:
            _combined_to_clean(intro_combined, allow_overwrite=args.allow_overwrite)

        clean = find_clean_audio_files(
            raw_dir,
            main_combined=main_combined,
            intro_combined=intro_combined,
        )

        steps = state.setdefault("steps", {})
        steps["07_audacity_deroom"] = step_state(
            steps,
            "07_audacity_deroom",
            title="Audacity DeRoom (user)",
            status="skipped",
            skipped_real_deroom=True,
            note="Combined Audio copied to Clean Audio (no Audacity DeRoom).",
            combined_audio_files=state.get("combined_audio_files", []),
        )
        state["main_clean_audio"] = str(clean["main_clean_audio"])
        if "intro_clean_audio" in clean:
            state["intro_clean_audio"] = str(clean["intro_clean_audio"])

        steps["08_identify_clean_audio"] = step_state(
            steps,
            "08_identify_clean_audio",
            title="Identify clean audio files",
            status="completed",
            main_clean_audio=state["main_clean_audio"],
            intro_clean_audio=state.get("intro_clean_audio"),
            skipped_real_deroom=True,
        )
        state["resume_at"] = "09_intro_video_prep"
        save_episode_state(args.episode_folder, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
