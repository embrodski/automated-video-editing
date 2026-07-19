#!/usr/bin/env python3
"""Print prep or full-render time estimates for a PIAB session."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from piab_lib import (
    estimate_full_render,
    estimate_prep_through_one_min,
    load_piab_state,
    mark_step,
    print_json,
    save_piab_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="PIAB runtime estimates.")
    parser.add_argument("working_folder", type=Path)
    parser.add_argument(
        "--which",
        choices=("prep", "full"),
        required=True,
        help="prep=through 1-min test; full=full interview render only",
    )
    parser.add_argument(
        "--mark-awaiting",
        action="store_true",
        help="Update state step to awaiting_user for this estimate gate.",
    )
    args = parser.parse_args()

    try:
        state = load_piab_state(args.working_folder)
        dur = float(state.get("source_duration_sec") or 0)
        if dur <= 0:
            raise ValueError("source_duration_sec missing from state")
        if args.which == "prep":
            eta = estimate_prep_through_one_min(dur)
            state["estimate_prep"] = eta
            if args.mark_awaiting:
                mark_step(
                    state,
                    "05_estimate_prep",
                    title="Estimate prep through 1-min test",
                    status="awaiting_user",
                    **eta,
                )
                state["resume_at"] = "05_estimate_prep"
        else:
            eta = estimate_full_render(dur)
            state["estimate_full"] = eta
            if args.mark_awaiting:
                mark_step(
                    state,
                    "12_estimate_full",
                    title="Estimate full interview render",
                    status="awaiting_user",
                    **eta,
                )
                state["resume_at"] = "12_estimate_full"
        save_piab_state(args.working_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json({"which": args.which, "estimate": eta})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
