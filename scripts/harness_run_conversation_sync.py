#!/usr/bin/env python3
"""Harness steps 5–6: run conversation-sync for main (and intro if present)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    combined_audio_output_name,
    find_conversation_wav_pair,
    has_intro_audio_pair,
    load_episode_state,
    run_conversation_sync,
    save_episode_state,
    step_state,
)


def _sync_pair(
    raw_dir: Path,
    *,
    intro: bool,
    label: str,
) -> dict:
    wav1, wav2 = find_conversation_wav_pair(raw_dir, intro=intro)
    output = run_conversation_sync(wav1, wav2)
    return {
        "label": label,
        "wav1": wav1.name,
        "wav2": wav2.name,
        "output": str(output),
        "output_name": output.name,
        "expected_output_name": combined_audio_output_name(wav1),
    }


def run_harness_conversation_sync(episode_folder: Path) -> dict:
    state = load_episode_state(episode_folder)
    raw_dir = Path(state["paths"]["raw"])
    steps = state.setdefault("steps", {})

    if steps.get("04_verify_reading_link", {}).get("status") not in (
        "completed",
        "skipped",
    ):
        raise RuntimeError(
            "Step 4 (verify reading link) must be completed or skipped first."
        )

    main_result = _sync_pair(raw_dir, intro=False, label="main_combined_audio")
    state["main_combined_audio"] = main_result["output"]

    steps["05_main_conversation_sync"] = step_state(
        steps,
        "05_main_conversation_sync",
        title="Main conversation-sync",
        status="completed",
        **main_result,
    )

    intro_result = None
    if has_intro_audio_pair(raw_dir):
        intro_result = _sync_pair(raw_dir, intro=True, label="intro_combined_audio")
        state["intro_combined_audio"] = intro_result["output"]
        steps["06_intro_conversation_sync"] = step_state(
            steps,
            "06_intro_conversation_sync",
            title="Intro conversation-sync",
            status="completed",
            **intro_result,
        )
    else:
        state.pop("intro_combined_audio", None)
        steps["06_intro_conversation_sync"] = step_state(
            steps,
            "06_intro_conversation_sync",
            title="Intro conversation-sync",
            status="skipped",
            reason="No intro audio raw WAV pair found in Raw.",
        )

    combined_paths = [main_result["output"]]
    if intro_result:
        combined_paths.append(intro_result["output"])
    state["combined_audio_files"] = combined_paths

    steps["07_audacity_deroom"] = step_state(
        steps,
        "07_audacity_deroom",
        title="Audacity DeRoom (user)",
        status="awaiting_user",
        combined_audio_files=combined_paths,
    )

    save_episode_state(episode_folder, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Harness steps 5–6: conversation-sync; sets step 7 awaiting user."
    )
    parser.add_argument("episode_folder", type=Path)
    args = parser.parse_args()

    try:
        state = run_harness_conversation_sync(args.episode_folder)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
