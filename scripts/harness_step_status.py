#!/usr/bin/env python3
"""Update harness step status in <name>-episode.json (approval gates)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import load_episode_state, save_episode_state, should_skip_reading, step_state


STEP_TITLES = {
    "16_reading_test_approval": "Reading 1-min test approval (READING)",
    "17_reading_full_approval": "Reading full approval (READING)",
    "17_reading_full_render": "Reading full render (READING)",
    "18_interview_test_approval": "Interview 1-min test approval",
    "19_interview_five_min_approval": "Interview 5-min test approval",
    "20_full_interview_render": "Full interview render",
    "21_hand_edit_approval": "Hand-edit approval (DaVinci)",
    "22_podcast_stitch": "Podcast stitch",
    "23_teaser_line": "Teaser line (placeholder)",
    "24_human_transcript": "Human transcript",
    "25_finalize_deliverables": "Finalize deliverables",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Update harness step status.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument("--step", required=True, help="Step id, e.g. 16_reading_test_approval")
    parser.add_argument(
        "--status",
        required=True,
        choices=("pending", "awaiting_user", "completed", "skipped", "failed"),
    )
    parser.add_argument("--resume-at", help="Set resume_at to this step id.")
    parser.add_argument("--note", default="", help="Optional note stored on the step.")
    parser.add_argument(
        "--skip-reading-chain",
        action="store_true",
        help="Mark steps 16–17 skipped (user skipped reading approvals/full).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        steps = state.setdefault("steps", {})

        if args.skip_reading_chain or (
            should_skip_reading(state) and args.step.startswith(("16_", "17_"))
        ):
            for sid in ("16_reading_test_approval", "17_reading_full_approval", "17_reading_full_render"):
                steps[sid] = step_state(
                    steps,
                    sid,
                    title=STEP_TITLES.get(sid, sid),
                    status="skipped",
                    reason="skip_reading is true",
                )
            if args.resume_at:
                state["resume_at"] = args.resume_at
            save_episode_state(args.episode_folder, state)
            print(json.dumps(state, indent=2))
            return 0

        title = STEP_TITLES.get(args.step, args.step)
        extra = {"note": args.note} if args.note else {}
        steps[args.step] = step_state(
            steps,
            args.step,
            title=title,
            status=args.status,
            **extra,
        )
        if args.resume_at:
            state["resume_at"] = args.resume_at
        save_episode_state(args.episode_folder, state)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
