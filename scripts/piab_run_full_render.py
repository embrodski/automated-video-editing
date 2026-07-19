#!/usr/bin/env python3
"""PIAB full interview render after 1-min approval + Estimate B confirmation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE
from harness_podcast_autocut_render import rebuild_interview_dsl
from harness_autocut_common import render_dsl
from piab_lib import (
    estimate_full_render,
    load_piab_state,
    mark_step,
    print_json,
    save_piab_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="PIAB full interview render.")
    parser.add_argument("working_folder", type=Path)
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument(
        "--rebuild-dsl",
        action="store_true",
        help="Regenerate interview.dsl before render (e.g. after speaker-id swap).",
    )
    args = parser.parse_args()
    working = args.working_folder.resolve()

    try:
        state = load_piab_state(working)
        if not state.get("interview_dsl") and not state.get("main_segment_id"):
            raise RuntimeError("Missing interview DSL / segment; run piab_run_prep.py first.")

        dur = float(state.get("source_duration_sec") or 0)
        eta = estimate_full_render(dur)
        state["estimate_full"] = eta
        mark_step(
            state,
            "11_one_min_approval",
            title="1-min test approval",
            status="completed",
        )
        mark_step(
            state,
            "18_interview_test_approval",
            title="Interview 1-min test approval",
            status="completed",
        )
        mark_step(
            state,
            "12_estimate_full",
            title="Estimate full interview render",
            status="completed",
            **eta,
        )

        output_dir = Path(state["paths"]["output"])
        temp = Path(state["paths"]["temp"])
        out_mp4 = output_dir / "Full Interview.mp4"

        if args.rebuild_dsl or not Path(state.get("interview_dsl", "")).is_file():
            dsl = rebuild_interview_dsl(state)
            state["interview_dsl"] = str(dsl)
        else:
            dsl = Path(state["interview_dsl"])

        render_dsl(
            dsl,
            out_mp4,
            temp,
            max_seconds=None,
            allow_overwrite=args.allow_overwrite,
        )

        state["full_interview_mp4"] = str(out_mp4)
        mark_step(
            state,
            "13_full_render",
            title="Full interview render",
            status="completed",
            output_mp4=str(out_mp4),
        )
        mark_step(
            state,
            "20_full_interview_render",
            title="Full interview render",
            status="completed",
            output_mp4=str(out_mp4),
        )
        mark_step(
            state,
            "14_done",
            title="Done",
            status="completed",
            output_mp4=str(out_mp4),
        )
        state["resume_at"] = "14_done"
        save_piab_state(working, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(
        {
            "full_interview": str(out_mp4),
            "message": f"Full render is complete: {out_mp4}",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
