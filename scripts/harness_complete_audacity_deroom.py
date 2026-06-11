#!/usr/bin/env python3
"""Mark harness step 7 complete after user finishes Audacity DeRoom."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import load_episode_state, save_episode_state, step_state


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mark step 07_audacity_deroom completed after user confirmation."
    )
    parser.add_argument("episode_folder", type=Path)
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    steps = state.setdefault("steps", {})
    prior = steps.get("07_audacity_deroom", {})
    if prior.get("status") != "awaiting_user":
        print(
            f"WARNING: step 07 status is {prior.get('status')!r}, not awaiting_user.",
            file=sys.stderr,
        )

    steps["07_audacity_deroom"] = step_state(
        steps,
        "07_audacity_deroom",
        title="Audacity DeRoom (user)",
        status="completed",
        combined_audio_files=state.get("combined_audio_files", []),
    )
    state["resume_at"] = "08_identify_clean_audio"
    save_episode_state(args.episode_folder, state)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
