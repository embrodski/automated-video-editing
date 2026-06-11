#!/usr/bin/env python3
"""Harness step 25: report final deliverable paths to the user."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import load_episode_state, save_episode_state, step_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 25: finalize message.")
    parser.add_argument("episode_folder", type=Path)
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        complete = state.get("complete_episode_mp4")
        transcript = state.get("human_transcript_txt")
        if not complete or not Path(complete).is_file():
            raise FileNotFoundError(
                "complete_episode_mp4 missing; run harness_run_stitch.py first."
            )
        if not transcript or not Path(transcript).is_file():
            raise FileNotFoundError(
                "human_transcript_txt missing; run harness_run_human_transcript.py first."
            )

        steps = state.setdefault("steps", {})
        steps["25_finalize_deliverables"] = step_state(
            steps,
            "25_finalize_deliverables",
            title="Finalize deliverables",
            status="completed",
            complete_episode_mp4=complete,
            human_transcript_txt=transcript,
        )
        state["resume_at"] = "harness_complete"
        save_episode_state(args.episode_folder, state)

        print("FINAL_DELIVERABLES")
        print(f"Complete episode: {complete}")
        print(f"Human transcript: {transcript}")
        timecodes = state.get("stitch_timecodes") or []
        if timecodes:
            print("STITCH_TIMECODES")
            for line in timecodes:
                print(line)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
