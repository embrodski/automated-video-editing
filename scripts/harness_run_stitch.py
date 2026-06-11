#!/usr/bin/env python3

"""Harness step 22: Inkhaven-Podcast-Stitch on Output folder."""



from __future__ import annotations



import argparse

import json

import os

import re

import subprocess

import sys

from pathlib import Path



sys.path.insert(0, str(Path(__file__).resolve().parent))



from harness_episode_lib import REPO_ROOT, load_episode_state, save_episode_state, step_state

from harness_output_files import stitch_required_files





def main() -> int:

    parser = argparse.ArgumentParser(description="Harness step 22: stitch episode.")

    parser.add_argument("episode_folder", type=Path)

    parser.add_argument("--video-encoder", default=None)

    args = parser.parse_args()



    try:

        state = load_episode_state(args.episode_folder)

        output_dir = Path(state["paths"]["output"])

        temp_dir = Path(state["paths"]["temp"])

        missing = []

        try:

            files = stitch_required_files(output_dir)

        except FileNotFoundError as exc:

            print(f"ERROR: {exc}", file=sys.stderr)

            for name in ("Intro.mp4", "Edited Reading.mp4", "Edited Interview.mp4", "Closing.mp4"):

                if not (output_dir / name).is_file():

                    missing.append(name)

            steps = state.setdefault("steps", {})

            steps["22_podcast_stitch"] = step_state(

                steps,

                "22_podcast_stitch",

                title="Podcast stitch",

                status="failed",

                missing_files=missing,

                error=str(exc),

            )

            save_episode_state(args.episode_folder, state)

            return 1



        env = os.environ.copy()

        env["TEMP"] = str(temp_dir)

        env["TMP"] = str(temp_dir)

        cmd = [

            sys.executable,

            str(REPO_ROOT / "stitch_episode.py"),

            "--output-dir",

            str(output_dir),

        ]

        if args.video_encoder:

            cmd.extend(["--video-encoder", args.video_encoder])



        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, env=env)

        if proc.returncode != 0:

            raise RuntimeError(

                f"stitch_episode failed.\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"

            )



        complete = output_dir / "Complete Episode.mp4"

        if not complete.is_file():

            raise FileNotFoundError(f"Stitch did not produce {complete}")



        marker_re = re.compile(r"^\d{2}:\d{2}\s+\S+\s*$")

        markers = [ln.strip() for ln in proc.stdout.splitlines() if marker_re.match(ln.strip())]



        steps = state.setdefault("steps", {})

        steps["22_podcast_stitch"] = step_state(

            steps,

            "22_podcast_stitch",

            title="Podcast stitch",

            status="completed",

            output_mp4=str(complete),

            input_files={k: str(v) for k, v in files.items()},

            stitch_timecodes=markers,

            stitch_stdout=proc.stdout,

        )

        steps["23_teaser_line"] = step_state(

            steps,

            "23_teaser_line",

            title="Teaser line (placeholder)",

            status="skipped",

            reason="Placeholder — future Teaser Line skill not implemented.",

        )

        state["complete_episode_mp4"] = str(complete)

        state["stitch_timecodes"] = markers

        state["resume_at"] = "24_human_transcript"

        save_episode_state(args.episode_folder, state)

    except (FileNotFoundError, RuntimeError) as exc:

        print(f"ERROR: {exc}", file=sys.stderr)

        return 1



    print(proc.stdout)

    print(json.dumps(state, indent=2))

    return 0





if __name__ == "__main__":

    raise SystemExit(main())

