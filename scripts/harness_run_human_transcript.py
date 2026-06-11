#!/usr/bin/env python3
"""Harness step 24: create-human-transcript from Output deliverables."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import REPO_ROOT, load_episode_state, save_episode_state, step_state
from harness_output_files import find_edited_interview_mp4, find_intro_mp4


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 24: human transcript.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument("--host", default="Ben", help="Host name (default: Ben).")
    args = parser.parse_args()

    try:
        state = load_episode_state(args.episode_folder)
        output_dir = Path(state["paths"]["output"])
        guest = state.get("name") or state.get("guest_name")
        if not guest:
            raise ValueError("Guest name missing from episode state (step 1).")

        intro = find_intro_mp4(output_dir)
        interview = find_edited_interview_mp4(output_dir)

        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "create_human_transcript.py"),
            str(output_dir),
            str(intro),
            str(interview),
            "--host",
            args.host,
            "--guest",
            guest,
        ]
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"create_human_transcript failed.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

        transcript_name = f"{args.host}-{guest} Transcript.txt"
        transcript_path = output_dir / transcript_name
        if not transcript_path.is_file():
            raise FileNotFoundError(f"Expected cleaned transcript: {transcript_path}")

        steps = state.setdefault("steps", {})
        steps["24_human_transcript"] = step_state(
            steps,
            "24_human_transcript",
            title="Human transcript",
            status="completed",
            host=args.host,
            guest=guest,
            video1=str(intro),
            video2=str(interview),
            transcript_txt=str(transcript_path),
        )
        state["human_transcript_txt"] = str(transcript_path)
        state["resume_at"] = "25_finalize_deliverables"
        save_episode_state(args.episode_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(proc.stdout)
    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
