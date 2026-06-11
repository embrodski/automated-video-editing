#!/usr/bin/env python3
"""Harness step 15: Inkhaven-Podcast-Autocut 1-minute test."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    REPO_ROOT,
    load_episode_state,
    next_segment_id,
    register_segment,
    save_episode_state,
    should_skip_reading,
    step_state,
)

BEN_HOST_RE = re.compile(r"\b(ben|host)\b", re.IGNORECASE)
WIDE_RE = re.compile(r"\bwide\b", re.IGNORECASE)


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


def _pick_interview_videos(prepped_videos: list[str]) -> tuple[Path, Path, Path]:
    paths = [Path(p) for p in prepped_videos]
    ben = next((p for p in paths if BEN_HOST_RE.search(p.name)), None)
    wide = next((p for p in paths if WIDE_RE.search(p.name)), None)
    guest = next(
        (p for p in paths if not BEN_HOST_RE.search(p.name) and not WIDE_RE.search(p.name)),
        None,
    )
    if not ben or not guest or not wide:
        raise FileNotFoundError(f"Could not find Ben/Guest/Wide prepped in {prepped_videos}")
    return ben, guest, wide


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 15: podcast 1-min test.")
    parser.add_argument("episode_folder", type=Path)
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        temp.mkdir(parents=True, exist_ok=True)

        ben, guest, wide = _pick_interview_videos(state["main_prepped"]["prepped_videos"])
        audio_wav = Path(state["main_prepped"]["prepped_audio_wav"])
        detail_json = Path(state["main_transcript_json"])

        simplified = temp / "interview_transcript_simplified.json"
        interview_dsl = temp / "interview.dsl"

        _run(
            [
                sys.executable,
                str(REPO_ROOT / "convert_transcript_json.py"),
                str(detail_json),
                "-o",
                str(simplified),
            ]
        )

        segment_id = state.get("main_segment_id") or next_segment_id()
        if not state.get("main_segment_id"):
            register_segment(
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
                comment=f"Inkhaven harness {state['name']} — main interview",
            )
            state["main_segment_id"] = segment_id

        _run(
            [
                sys.executable,
                str(REPO_ROOT / "generate_full_dsl.py"),
                str(simplified),
                "--segment",
                segment_id,
                "--output",
                str(interview_dsl),
            ]
        )

        out_mp4 = output_dir / "1 Min Test.mp4"
        env = os.environ.copy()
        env["TEMP"] = str(temp)
        env["TMP"] = str(temp)
        _run(
            [
                sys.executable,
                "-m",
                "podcast_dsl",
                str(interview_dsl),
                "-o",
                str(out_mp4),
                "--workers",
                "6",
                "--max-seconds",
                "60",
            ],
            cwd=REPO_ROOT / "src",
            env=env,
        )

        state["podcast_autocut_test_mp4"] = str(out_mp4)
        steps = state.setdefault("steps", {})
        steps["15_podcast_autocut_test"] = step_state(
            steps,
            "15_podcast_autocut_test",
            title="Podcast autocut 1-min test",
            status="completed",
            output_mp4=str(out_mp4),
            interview_dsl=str(interview_dsl),
            segment_id=segment_id,
        )
        state["interview_dsl"] = str(interview_dsl)
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
        save_episode_state(args.episode_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
