#!/usr/bin/env python3
"""Harness steps 11/13: ElevenLabs transcript on *-prepped.wav in Input."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    REPO_ROOT,
    load_episode_state,
    read_elevenlabs_api_key,
    save_episode_state,
    should_skip_reading,
    step_state,
)
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite


def _run_transcribe(wav: Path, api_key: str, *, allow_overwrite: bool) -> Path:
    transcript_json = wav.parent / f"{wav.stem} Transcript.json"
    refuse_overwrite(transcript_json, allow_overwrite=allow_overwrite)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "elevenlabs_transcribe_wav.py"),
        str(wav),
        "--api-key",
        api_key,
        "--language-code",
        "en",
    ]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"elevenlabs_transcribe_wav failed.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    if not transcript_json.is_file():
        raise FileNotFoundError(f"Expected transcript JSON: {transcript_json}")
    return transcript_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness transcribe prepped WAV.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument("--scope", required=True, choices=("reading", "main"))
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite existing transcript JSON in Input (requires user approval).",
    )
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        steps = state.setdefault("steps", {})
        api_key = read_elevenlabs_api_key()

        if args.scope == "reading":
            if should_skip_reading(state):
                steps["11_reading_transcript"] = step_state(
                    steps,
                    "11_reading_transcript",
                    title="Reading transcript (READING)",
                    status="skipped",
                    reason="skip_reading is true",
                )
                save_episode_state(args.episode_folder, state)
                print(json.dumps(state, indent=2))
                return 0
            prepped = state.get("reading_prepped")
            if not prepped or not prepped.get("prepped_audio_wav"):
                raise FileNotFoundError(
                    "reading_prepped missing from episode state; "
                    "run harness_run_video_sync_scope.py --scope reading (step 10) first."
                )
            wav = Path(prepped["prepped_audio_wav"])
            transcript = _run_transcribe(wav, api_key, allow_overwrite=args.allow_overwrite)
            state["reading_transcript_json"] = str(transcript)
            steps["11_reading_transcript"] = step_state(
                steps,
                "11_reading_transcript",
                title="Reading transcript (READING)",
                status="completed",
                wav=str(wav),
                transcript_json=str(transcript),
            )
            state["resume_at"] = "14_reading_autocut_test"
        else:
            prepped = state.get("main_prepped")
            if not prepped or not prepped.get("prepped_audio_wav"):
                raise FileNotFoundError(
                    "main_prepped missing from episode state; "
                    "run harness_run_video_sync_scope.py --scope main (step 12) first."
                )
            wav = Path(prepped["prepped_audio_wav"])
            transcript = _run_transcribe(wav, api_key, allow_overwrite=args.allow_overwrite)
            state["main_transcript_json"] = str(transcript)
            steps["13_main_transcript"] = step_state(
                steps,
                "13_main_transcript",
                title="Main transcript",
                status="completed",
                wav=str(wav),
                transcript_json=str(transcript),
            )
            state["resume_at"] = "15_podcast_autocut_test"

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
