#!/usr/bin/env python3
"""Extract loud 4s preview clips for each session audio WAV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from piab_lib import (
    extract_audio_clip,
    find_loud_clip_start,
    load_piab_state,
    mark_step,
    print_json,
    save_piab_state,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract PIAB loud audio preview clips.")
    parser.add_argument("working_folder", type=Path)
    parser.add_argument("--clip-sec", type=float, default=4.0)
    args = parser.parse_args()

    try:
        state = load_piab_state(args.working_folder)
        preview_dir = Path(state["paths"]["previews"])
        preview_dir.mkdir(parents=True, exist_ok=True)
        for stale in preview_dir.glob("Mic *.wav"):
            stale.unlink()
        for stale in preview_dir.glob("audio_*.wav"):
            stale.unlink()

        previews = []
        audio_items = [
            item for item in state.get("session_files", []) if item.get("kind") == "audio"
        ]
        for mic_number, item in enumerate(audio_items, start=1):
            src = Path(item["path"])
            if not src.is_file():
                continue
            start = find_loud_clip_start(src, clip_sec=args.clip_sec)
            mic_label = f"Mic {mic_number}"
            out = preview_dir / f"{mic_label}.wav"
            extract_audio_clip(src, out, start_sec=start, duration_sec=args.clip_sec)
            previews.append(
                {
                    "mic": mic_label,
                    "source": str(src),
                    "source_name": src.name,
                    "preview": str(out),
                    "start_sec": round(start, 3),
                    "clip_sec": args.clip_sec,
                    "duration_sec": item.get("duration_sec"),
                }
            )
        if not previews:
            raise FileNotFoundError(
                "No session audio WAVs found on disk to preview. "
                "Have they already been moved?"
            )
        state["audio_previews"] = previews
        mark_step(
            state,
            "04_label_audio",
            title="Label audio",
            status="awaiting_user",
            preview_count=len(previews),
        )
        state["resume_at"] = "04_label_audio"
        save_piab_state(args.working_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(
        {
            "audio_previews": previews,
            "preview_folder": str(preview_dir),
            "working_folder": str(args.working_folder.resolve()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
