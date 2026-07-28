#!/usr/bin/env python3
"""Render podcast autocut test / 5-min / full using step-15 pipeline state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_autocut_common import render_dsl, run_cmd
from harness_episode_lib import (
    REPO_ROOT,
    load_episode_state,
    podcast_phrase_cli_args,
    podcast_swap_speaker_ids_cli_args,
    save_episode_state,
    step_state,
)
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE
from podcast_flag_phrases import report_flag_timestamps_after_render


def rebuild_interview_dsl(state: dict) -> Path:
    temp = Path(state["paths"]["temp"])
    interview_dsl = temp / "interview.dsl"
    simplified = temp / "interview_transcript_simplified.json"
    segment_id = state["main_segment_id"]
    detail_json = Path(state["main_transcript_json"])

    convert_cmd = [
        sys.executable,
        str(REPO_ROOT / "convert_transcript_json.py"),
        str(detail_json),
        "-o",
        str(simplified),
    ]
    convert_cmd.extend(podcast_swap_speaker_ids_cli_args(state))
    run_cmd(convert_cmd)
    run_cmd(
        [
            sys.executable,
            str(REPO_ROOT / "generate_full_dsl.py"),
            str(simplified),
            "--segment",
            segment_id,
            "--output",
            str(interview_dsl),
            *podcast_phrase_cli_args(state),
        ]
    )
    return interview_dsl


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness podcast autocut render.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--mode",
        choices=("test", "five_min", "full"),
        required=True,
        help="test=1 Min Test; five_min=5 Min Test; full=Full Interview",
    )
    parser.add_argument(
        "--rebuild-dsl",
        action="store_true",
        help="Regenerate interview.dsl before render.",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite existing output MP4 (requires explicit user approval).",
    )
    args = parser.parse_args()

    outputs = {
        "test": ("1 Min Test.mp4", 60, "18_interview_test_approval"),
        "five_min": ("5 Min Test.mp4", 300, "19_interview_five_min_approval"),
        "full": ("Full Interview.mp4", None, "20_full_interview_render"),
    }
    filename, max_seconds, _ = outputs[args.mode]

    try:
        state = load_episode_state(args.episode_folder)
        if not state.get("main_segment_id"):
            raise RuntimeError("main_segment_id missing; run harness_podcast_autocut_test.py first.")

        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        interview_dsl = Path(state.get("interview_dsl") or temp / "interview.dsl")

        if args.rebuild_dsl:
            interview_dsl = rebuild_interview_dsl(state)
        elif not interview_dsl.is_file():
            raise FileNotFoundError(f"interview.dsl not found: {interview_dsl}")

        out_mp4 = output_dir / filename
        render_dsl(
            interview_dsl,
            out_mp4,
            temp,
            max_seconds=max_seconds,
            allow_overwrite=args.allow_overwrite,
        )

        flag_summary = None
        if args.mode == "full":
            flag_summary = report_flag_timestamps_after_render(
                interview_dsl,
                temp,
                state=state,
            )
            state["flag_timestamps"] = flag_summary

        state["interview_dsl"] = str(interview_dsl)
        if args.mode == "test":
            state["podcast_autocut_test_mp4"] = str(out_mp4)
        elif args.mode == "five_min":
            state["podcast_autocut_five_min_mp4"] = str(out_mp4)
        else:
            state["podcast_autocut_full_mp4"] = str(out_mp4)

        steps = state.setdefault("steps", {})
        if args.mode == "test":
            steps["18_interview_test_approval"] = step_state(
                steps,
                "18_interview_test_approval",
                title="Interview 1-min test approval",
                status="awaiting_user",
                last_render=str(out_mp4),
            )
        elif args.mode == "five_min":
            steps["19_interview_five_min_approval"] = step_state(
                steps,
                "19_interview_five_min_approval",
                title="Interview 5-min test approval",
                status="awaiting_user",
                last_render=str(out_mp4),
            )
        else:
            steps["20_full_interview_render"] = step_state(
                steps,
                "20_full_interview_render",
                title="Full interview render",
                status="completed",
                output_mp4=str(out_mp4),
            )
            steps["21_hand_edit_approval"] = step_state(
                steps,
                "21_hand_edit_approval",
                title="Hand-edit approval (DaVinci)",
                status="awaiting_user",
                note="User exports Intro, Edited Reading, Edited Interview to Output.",
            )
            state["resume_at"] = "21_hand_edit_approval"

        save_episode_state(args.episode_folder, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
