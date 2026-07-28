#!/usr/bin/env python3
"""Show PIAB prep resume status or run prep with --resume (via piab_run_prep.py)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from piab_lib import load_piab_state, print_json, save_piab_state
from piab_resume import (
    build_prep_resume_plan,
    detect_prep_completion,
    is_prep_resumable,
    plan_to_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or plan resume for interrupted PIAB prep."
    )
    parser.add_argument("working_folder", type=Path)
    parser.add_argument(
        "--from-step",
        help="Preview resume starting at this step (see piab_run_prep.py --from-step).",
    )
    parser.add_argument(
        "--apply-rehydrate",
        action="store_true",
        help="Write rehydrated paths from disk into podcast-in-a-box.json.",
    )
    args = parser.parse_args()

    try:
        working = args.working_folder.resolve()
        state = load_piab_state(working)
        completion = detect_prep_completion(state)
        plan = build_prep_resume_plan(
            state,
            working,
            resume=True,
            from_step=args.from_step,
        )
        if args.apply_rehydrate and plan.rehydrated:
            save_piab_state(working, state)
        payload = {
            **plan_to_json(plan),
            "resumable": is_prep_resumable(state, working),
            "completion": completion,
        }
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
