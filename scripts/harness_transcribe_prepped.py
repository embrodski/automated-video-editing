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


def _run_transcribe(wav: Path, api_key: str) -> Path:
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
    json_path = wav.parent / f"{wav.stem} Transcript.json"
    if not json_path.is_file():
        raise FileNotFoundError(f"Expected transcript JSON: {json_path}")
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness transcribe prepped WAV.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument("--scope", required=True, choices=("reading", "main"))
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
            wav = Path(state["reading_prepped"]["prepped_audio_wav"])
            transcript = _run_transcribe(wav, api_key)
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
            wav = Path(state["main_prepped"]["prepped_audio_wav"])
            transcript = _run_transcribe(wav, api_key)
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
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
