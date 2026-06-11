#!/usr/bin/env python3
"""Render reading autocut (1-min test or full) using step-14 pipeline state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_autocut_common import render_dsl, run_cmd
from harness_episode_lib import REPO_ROOT, load_episode_state, save_episode_state, should_skip_reading, step_state

def rebuild_reading_dsl(state: dict) -> Path:
    temp = Path(state["paths"]["temp"])
    reading_dsl = temp / "reading.dsl"
    simplified = temp / "reading_transcript_simplified.json"
    article_txt = temp / "reading_article.txt"
    segment_id = state["reading_segment_id"]
    reading_link = state.get("reading_link")
    detail_json = Path(state["reading_transcript_json"])

    if not simplified.is_file():
        run_cmd(
            [
                sys.executable,
                str(REPO_ROOT / "convert_transcript_json.py"),
                str(detail_json),
                "-o",
                str(simplified),
                "--pause-split-gap-sec",
                "0.60",
                "--pause-split-min-words",
                "4",
            ]
        )
    if not article_txt.is_file() and reading_link:
        run_cmd(
            [
                sys.executable,
                str(REPO_ROOT / "fetch_article_to_reading_article.py"),
                "--url",
                reading_link,
                "--output-dir",
                str(temp),
            ]
        )
    gen_cmd = [
        sys.executable,
        str(REPO_ROOT / "generate_reading_dsl.py"),
        str(simplified),
        str(article_txt),
        "--segment",
        segment_id,
        "--output",
        str(reading_dsl),
    ]
    reader_id = state.get("reader_speaker_id")
    if reader_id is not None:
        gen_cmd.extend(["--reader-speaker-id", str(reader_id)])
    run_cmd(gen_cmd)
    run_cmd(
        [
            sys.executable,
            str(REPO_ROOT / "shorten_reading_dsl_silences.py"),
            str(reading_dsl),
            "--segment",
            segment_id,
        ]
    )
    return reading_dsl


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness reading autocut render.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--mode",
        choices=("test", "full"),
        required=True,
        help="test=1 Min Test Reading.mp4; full=Full Reading.mp4",
    )
    parser.add_argument(
        "--rebuild-dsl",
        action="store_true",
        help="Regenerate reading.dsl (after transcript/article tweaks).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        if should_skip_reading(state):
            print("Reading skipped (skip_reading=true).", file=sys.stderr)
            return 0

        if not state.get("reading_segment_id"):
            raise RuntimeError("reading_segment_id missing; run harness_reading_autocut_test.py first.")

        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        reading_dsl = Path(state.get("reading_dsl") or temp / "reading.dsl")

        if args.rebuild_dsl:
            reading_dsl = rebuild_reading_dsl(state)
        elif not reading_dsl.is_file():
            raise FileNotFoundError(f"reading.dsl not found: {reading_dsl}")

        if args.mode == "test":
            out_mp4 = output_dir / "1 Min Test Reading.mp4"
            max_seconds = 60
        else:
            out_mp4 = output_dir / "Full Reading.mp4"
            max_seconds = None

        render_dsl(
            reading_dsl,
            out_mp4,
            temp,
            max_seconds=max_seconds,
        )

        state["reading_dsl"] = str(reading_dsl)
        if args.mode == "test":
            state["reading_autocut_test_mp4"] = str(out_mp4)
        else:
            state["reading_final_mp4"] = str(out_mp4)

        steps = state.setdefault("steps", {})
        if args.mode == "test":
            steps["16_reading_test_approval"] = step_state(
                steps,
                "16_reading_test_approval",
                title="Reading 1-min test approval (READING)",
                status="awaiting_user",
                last_render=str(out_mp4),
                rebuild_dsl=args.rebuild_dsl,
            )
        else:
            steps["17_reading_full_render"] = step_state(
                steps,
                "17_reading_full_render",
                title="Reading full render (READING)",
                status="completed",
                output_mp4=str(out_mp4),
            )
            steps["17_reading_full_approval"] = step_state(
                steps,
                "17_reading_full_approval",
                title="Reading full approval (READING)",
                status="awaiting_user",
                last_render=str(out_mp4),
            )
            state["resume_at"] = "17_reading_full_approval"

        save_episode_state(args.episode_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
