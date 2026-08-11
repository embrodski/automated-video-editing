#!/usr/bin/env python3
"""Harness step 15: Inkhaven-Podcast-Autocut 1-minute test."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_av_sync_lib import (
    ONE_MIN_DEFAULT,
    load_failed_sync_confidence_flag,
    mark_sync_ab_steps,
    run_sync_ab_one_min_tests,
)
from harness_autocut_common import render_dsl, run_cmd
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite
from episode_segments import MAIN_SEGMENT_KEY, segments_path, upsert_segment
from harness_episode_lib import (
    REPO_ROOT,
    load_episode_state,
    pick_interview_videos,
    podcast_phrase_cli_args,
    podcast_swap_speaker_ids_cli_args,
    save_episode_state,
    should_skip_reading,
    step_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 15: podcast 1-min test.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite existing test MP4 / Temp DSL artifacts (requires user approval).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        temp.mkdir(parents=True, exist_ok=True)

        ben, guest, wide = pick_interview_videos(state["main_prepped"]["prepped_videos"])
        audio_wav = Path(state["main_prepped"]["prepped_audio_wav"])
        detail_json = Path(state["main_transcript_json"])

        simplified = temp / "interview_transcript_simplified.json"
        interview_dsl = temp / "interview.dsl"
        for path in (simplified, interview_dsl):
            refuse_overwrite(path, allow_overwrite=args.allow_overwrite)

        convert_cmd = [
            sys.executable,
            str(REPO_ROOT / "convert_transcript_json.py"),
            str(detail_json),
            "-o",
            str(simplified),
        ]
        convert_cmd.extend(podcast_swap_speaker_ids_cli_args(state))
        run_cmd(convert_cmd)

        segment_id = MAIN_SEGMENT_KEY
        upsert_segment(
            temp,
            segment_id,
            {
                "audio_file": str(audio_wav),
                "audio_offset": 0,
                "enable_color_match": False,
                "video_files": {
                    "speaker_0": {"file": str(ben), "offset": 0},
                    "speaker_1": {"file": str(guest), "offset": 0},
                    "wide": {"file": str(wide), "offset": 0},
                },
                "transcript_file": str(simplified),
            },
            allow_overwrite=args.allow_overwrite,
        )
        state["main_segment_id"] = segment_id
        state["segments_file"] = str(segments_path(temp))

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

        state["interview_dsl"] = str(interview_dsl)
        sync_flag = load_failed_sync_confidence_flag(temp)
        if sync_flag is None and state.get("sync_confidence_failed"):
            sync_flag = {"failed": True}

        if sync_flag:
            ab_result = run_sync_ab_one_min_tests(state, allow_overwrite=args.allow_overwrite)
            mark_sync_ab_steps(state, ab_result=ab_result)
            out_mp4 = Path(ab_result["one_min_no_offset"])
        else:
            out_mp4 = output_dir / ONE_MIN_DEFAULT
            render_dsl(
                interview_dsl,
                out_mp4,
                temp,
                max_seconds=60,
                allow_overwrite=args.allow_overwrite,
            )
            state["podcast_autocut_test_mp4"] = str(out_mp4)
            steps = state.setdefault("steps", {})
            steps["18_interview_test_approval"] = step_state(
                steps,
                "18_interview_test_approval",
                title="Interview 1-min test approval",
                status="awaiting_user",
            )
            if should_skip_reading(state):
                state["resume_at"] = "18_interview_test_approval"
            else:
                state["resume_at"] = "16_reading_test_approval"

        steps = state.setdefault("steps", {})
        steps["15_podcast_autocut_test"] = step_state(
            steps,
            "15_podcast_autocut_test",
            title="Podcast autocut 1-min test",
            status="completed",
            output_mp4=str(out_mp4),
            interview_dsl=str(interview_dsl),
            segment_id=segment_id,
            sync_ab=bool(sync_flag),
        )
        save_episode_state(args.episode_folder, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
