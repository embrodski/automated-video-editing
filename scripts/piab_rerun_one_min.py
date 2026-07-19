#!/usr/bin/env python3
"""Re-render PIAB 1 Min Test after approval-loop fixes (e.g. speaker-id swap)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from episode_segments import MAIN_SEGMENT_KEY, segments_path, upsert_segment
from harness_autocut_common import render_dsl, run_cmd
from harness_episode_lib import REPO_ROOT, podcast_phrase_cli_args, podcast_swap_speaker_ids_cli_args
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite
from harness_podcast_autocut_test import _pick_interview_videos
from piab_lib import load_piab_state, mark_step, print_json, save_piab_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-render PIAB 1 Min Test.")
    parser.add_argument("working_folder", type=Path)
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()
    working = args.working_folder.resolve()

    try:
        state = load_piab_state(working)
        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        ben, guest, wide = _pick_interview_videos(state["main_prepped"]["prepped_videos"])
        audio_wav = Path(state["main_prepped"]["prepped_audio_wav"])
        detail_json = Path(state["main_transcript_json"])
        simplified = temp / "interview_transcript_simplified.json"
        interview_dsl = temp / "interview.dsl"
        out_mp4 = output_dir / "1 Min Test.mp4"
        for path in (simplified, interview_dsl, out_mp4):
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

        segment_id = state.get("main_segment_id") or MAIN_SEGMENT_KEY
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
        render_dsl(
            interview_dsl,
            out_mp4,
            temp,
            max_seconds=60,
            allow_overwrite=args.allow_overwrite,
        )
        state["podcast_autocut_test_mp4"] = str(out_mp4)
        state["interview_dsl"] = str(interview_dsl)
        mark_step(
            state,
            "10_one_min_test",
            title="Podcast autocut 1-min test",
            status="completed",
            output_mp4=str(out_mp4),
        )
        mark_step(
            state,
            "11_one_min_approval",
            title="1-min test approval",
            status="awaiting_user",
        )
        state["resume_at"] = "11_one_min_approval"
        save_piab_state(working, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json({"one_min_test": str(out_mp4), "swap_speaker_ids": state.get("swap_speaker_ids")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
