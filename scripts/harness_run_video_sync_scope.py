#!/usr/bin/env python3
"""Harness steps 9/10/12: video-sync for intro, reading, or main."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_av_sync_lib import maybe_write_sync_confidence_flag
from harness_episode_lib import (
    intro_steps_active,
    load_episode_state,
    save_episode_state,
    should_skip_reading,
    step_state,
)
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE
from harness_video_sync import find_scope_videos, run_video_sync


def _resolve_reading_audio_raw(raw_dir: Path) -> Path:
    for path in sorted(raw_dir.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() != ".wav":
            continue
        if "reading" in path.name.lower() and "raw" in path.name.lower():
            return path
    raise FileNotFoundError(f"No Reading audio raw WAV in {raw_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness video-sync by scope.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--scope",
        required=True,
        choices=("intro", "reading", "main"),
    )
    parser.add_argument(
        "--no-downscale-1080p",
        action="store_true",
        help="Pass --no-downscale-1080p to multicam (downscale off).",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite existing synced/prepped media (requires user approval).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        raw_dir = Path(state["paths"]["raw"])
        steps = state.setdefault("steps", {})
        scope = args.scope

        if scope == "intro":
            if not intro_steps_active(state):
                steps["09_intro_video_prep"] = step_state(
                    steps,
                    "09_intro_video_prep",
                    title="Intro video prep",
                    status="skipped",
                    reason="No intro conversation-sync (step 6 skipped).",
                )
                save_episode_state(args.episode_folder, state)
                print(json.dumps(state, indent=2))
                return 0
            if not state.get("intro_clean_audio"):
                raise FileNotFoundError(
                    "intro_clean_audio missing from episode state; "
                    "run harness_identify_clean_audio.py (step 8) first."
                )
            audio = Path(state["intro_clean_audio"])
            videos = find_scope_videos(raw_dir, "intro")
            result = run_video_sync(
                raw_dir, audio, videos, no_downscale_1080p=args.no_downscale_1080p,
                allow_overwrite=args.allow_overwrite,
            )
            state["intro_prepped"] = result
            steps["09_intro_video_prep"] = step_state(
                steps,
                "09_intro_video_prep",
                title="Intro video prep",
                status="completed",
                **result,
            )
            state["resume_at"] = "10_reading_video_prep"

        elif scope == "reading":
            if should_skip_reading(state):
                steps["10_reading_video_prep"] = step_state(
                    steps,
                    "10_reading_video_prep",
                    title="Reading video prep (READING)",
                    status="skipped",
                    reason="skip_reading is true",
                )
                save_episode_state(args.episode_folder, state)
                print(json.dumps(state, indent=2))
                return 0
            audio = _resolve_reading_audio_raw(raw_dir)
            videos = find_scope_videos(raw_dir, "reading")
            result = run_video_sync(
                raw_dir, audio, videos, no_downscale_1080p=args.no_downscale_1080p,
                allow_overwrite=args.allow_overwrite,
            )
            state["reading_prepped"] = result
            steps["10_reading_video_prep"] = step_state(
                steps,
                "10_reading_video_prep",
                title="Reading video prep (READING)",
                status="completed",
                **result,
            )
            state["resume_at"] = "11_reading_transcript"

        else:
            if not state.get("main_clean_audio"):
                raise FileNotFoundError(
                    "main_clean_audio missing from episode state; "
                    "run harness_identify_clean_audio.py (step 8) first."
                )
            audio = Path(state["main_clean_audio"])
            videos = find_scope_videos(raw_dir, "main")
            result = run_video_sync(
                raw_dir, audio, videos, no_downscale_1080p=args.no_downscale_1080p,
                allow_overwrite=args.allow_overwrite,
            )
            state["main_prepped"] = result
            if result.get("sync_reports"):
                maybe_write_sync_confidence_flag(state, result["sync_reports"], scope="main")
            steps["12_main_video_prep"] = step_state(
                steps,
                "12_main_video_prep",
                title="Main video prep",
                status="completed",
                **result,
            )
            state["resume_at"] = "13_main_transcript"

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
