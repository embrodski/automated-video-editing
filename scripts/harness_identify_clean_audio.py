#!/usr/bin/env python3
"""Harness step 8: find user-exported clean audio WAVs in Raw."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    find_clean_audio_files,
    load_episode_state,
    save_episode_state,
    step_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 8: identify clean audio.")
    parser.add_argument("episode_folder", type=Path)
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        raw_dir = Path(state["paths"]["raw"])
        main_combined = Path(state["main_combined_audio"]) if state.get("main_combined_audio") else None
        intro_combined = (
            Path(state["intro_combined_audio"]) if state.get("intro_combined_audio") else None
        )
        if not main_combined or not main_combined.is_file():
            raise FileNotFoundError("main_combined_audio missing from episode state.")

        clean = find_clean_audio_files(
            raw_dir,
            main_combined=main_combined,
            intro_combined=intro_combined if intro_combined and intro_combined.is_file() else None,
        )
        intro_sync_completed = (
            state.get("steps", {}).get("06_intro_conversation_sync", {}).get("status")
            == "completed"
        )
        if intro_sync_completed and "intro_clean_audio" not in clean:
            raise FileNotFoundError(
                "Intro conversation-sync completed but no Intro clean WAV was found in Raw. "
                "Export a DeRoomed file with 'Clean' in the filename and 'Intro' in the name, "
                f"newer than {intro_combined.name if intro_combined else 'intro combined audio'}."
            )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    steps = state.setdefault("steps", {})
    if steps.get("07_audacity_deroom", {}).get("status") != "completed":
        steps["07_audacity_deroom"] = step_state(
            steps,
            "07_audacity_deroom",
            title="Audacity DeRoom (user)",
            status="completed",
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
    )
    state["resume_at"] = "09_intro_video_prep"

    save_episode_state(args.episode_folder, state)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
