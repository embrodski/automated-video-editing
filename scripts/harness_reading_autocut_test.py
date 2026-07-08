#!/usr/bin/env python3
"""Harness step 14: Inkhaven-Reading-Autocut 1-minute test with Shorten."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_overwrite_guard import refuse_overwrite
from harness_episode_lib import (
    REPO_ROOT,
    load_episode_state,
    next_segment_id,
    reading_keep_rows_cli_args,
    register_segment,
    save_episode_state,
    should_skip_reading,
    step_state,
)

FRONT_RE = __import__("re").compile(r"\bfront\b", __import__("re").IGNORECASE)
SIDE_RE = __import__("re").compile(r"\bside\b", __import__("re").IGNORECASE)


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


def _pick_reading_videos(prepped_videos: list[str]) -> tuple[Path, Path]:
    paths = [Path(p) for p in prepped_videos]
    front = next((p for p in paths if FRONT_RE.search(p.name)), None)
    side = next((p for p in paths if SIDE_RE.search(p.name)), None)
    if not front or not side:
        raise FileNotFoundError(f"Could not find front/side prepped videos in {prepped_videos}")
    return front, side


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 14: reading 1-min test.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite existing test MP4 / Temp DSL artifacts (requires user approval).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        steps = state.setdefault("steps", {})

        if should_skip_reading(state):
            steps["14_reading_autocut_test"] = step_state(
                steps,
                "14_reading_autocut_test",
                title="Reading autocut 1-min test (READING)",
                status="skipped",
                reason="skip_reading is true",
            )
            save_episode_state(args.episode_folder, state)
            print(json.dumps(state, indent=2))
            return 0

        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        temp.mkdir(parents=True, exist_ok=True)

        front, side = _pick_reading_videos(state["reading_prepped"]["prepped_videos"])
        audio_wav = Path(state["reading_prepped"]["prepped_audio_wav"])
        detail_json = Path(state["reading_transcript_json"])
        reading_link = state.get("reading_link")
        if not reading_link:
            raise ValueError("reading_link missing from episode state")

        simplified = temp / "reading_transcript_simplified.json"
        article_txt = temp / "reading_article.txt"
        reading_dsl = temp / "reading.dsl"
        out_mp4 = output_dir / "1 Min Test Reading.mp4"
        for path in (simplified, article_txt, reading_dsl, out_mp4):
            refuse_overwrite(path, allow_overwrite=args.allow_overwrite)

        _run(
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
        _run(
            [
                sys.executable,
                str(REPO_ROOT / "fetch_article_to_reading_article.py"),
                "--url",
                reading_link,
                "--output-dir",
                str(temp),
            ]
        )

        segment_id = state.get("reading_segment_id") or next_segment_id()
        if not state.get("reading_segment_id"):
            register_segment(
                segment_id,
                {
                    "audio_file": str(audio_wav),
                    "audio_offset": 0,
                    "use_video_embedded_audio": True,
                    "enable_color_match": False,
                    "video_files": {
                        "speaker_0": {"file": str(front), "offset": 0},
                        "speaker_1": {"file": str(side), "offset": 0},
                    },
                    "transcript_file": str(simplified),
                },
                comment=f"Inkhaven harness {state['name']} — reading",
            )
            state["reading_segment_id"] = segment_id

        gen_cmd = [
            sys.executable,
            str(REPO_ROOT / "generate_reading_dsl.py"),
            str(simplified),
            str(article_txt),
            "--segment",
            segment_id,
            "--output",
            str(reading_dsl),
            "--reader-speaker-id",
            str(state.get("reader_speaker_id", 0)),
        ]
        gen_cmd.extend(reading_keep_rows_cli_args(state))
        _run(gen_cmd)
        _run(
            [
                sys.executable,
                str(REPO_ROOT / "shorten_reading_dsl_silences.py"),
                str(reading_dsl),
                "--segment",
                segment_id,
            ]
        )

        env = os.environ.copy()
        env["TEMP"] = str(temp)
        env["TMP"] = str(temp)
        _run(
            [
                sys.executable,
                "-m",
                "podcast_dsl",
                str(reading_dsl),
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

        state["reading_autocut_test_mp4"] = str(out_mp4)
        steps["14_reading_autocut_test"] = step_state(
            steps,
            "14_reading_autocut_test",
            title="Reading autocut 1-min test (READING)",
            status="completed",
            output_mp4=str(out_mp4),
            reading_dsl=str(reading_dsl),
            segment_id=segment_id,
        )
        steps["16_reading_test_approval"] = step_state(
            steps,
            "16_reading_test_approval",
            title="Reading 1-min test approval (READING)",
            status="awaiting_user",
        )
        state["reading_dsl"] = str(reading_dsl)
        state["resume_at"] = "16_reading_test_approval"
        save_episode_state(args.episode_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
