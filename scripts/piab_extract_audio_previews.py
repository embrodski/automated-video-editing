#!/usr/bin/env python3
"""Extract loud preview clips for each audible session audio WAV."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from piab_lib import (
    DEFAULT_PREVIEW_CLIP_SEC,
    DEFAULT_PREVIEW_SECTIONS,
    extract_audio_clip,
    find_loud_clip_starts,
    load_piab_state,
    mark_step,
    print_json,
    save_piab_state,
    wav_has_audible_content,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract PIAB loud audio preview clips.")
    parser.add_argument("working_folder", type=Path)
    parser.add_argument("--clip-sec", type=float, default=DEFAULT_PREVIEW_CLIP_SEC)
    parser.add_argument(
        "--section-fractions",
        type=float,
        nargs="+",
        default=list(DEFAULT_PREVIEW_SECTIONS),
        help="File fractions (0-1) where each clip's search region begins.",
    )
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
        skipped_silent: list[dict] = []
        audio_items = [
            item for item in state.get("session_files", []) if item.get("kind") == "audio"
        ]
        mic_number = 0
        for item in audio_items:
            src = Path(item["path"])
            if not src.is_file():
                continue
            if not wav_has_audible_content(src):
                skipped_silent.append(
                    {
                        "source": str(src),
                        "source_name": src.name,
                        "reason": "silent or no audible content",
                    }
                )
                continue

            mic_number += 1
            starts = find_loud_clip_starts(
                src,
                clip_sec=args.clip_sec,
                section_fractions=tuple(args.section_fractions),
            )
            clip_labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            for clip_index, start in enumerate(starts):
                clip_label = clip_labels[clip_index]
                mic_label = f"Mic {mic_number}"
                out = preview_dir / f"{mic_label} {clip_label}.wav"
                extract_audio_clip(
                    src,
                    out,
                    start_sec=start,
                    duration_sec=args.clip_sec,
                )
                previews.append(
                    {
                        "mic": mic_label,
                        "clip": clip_label,
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
                "No audible session audio WAVs found on disk to preview. "
                "Have they already been moved, or are all tracks silent?"
            )
        state["audio_previews"] = previews
        state["audio_previews_skipped_silent"] = skipped_silent
        mark_step(
            state,
            "04_label_audio",
            title="Label audio",
            status="awaiting_user",
            preview_count=len(previews),
            skipped_silent_count=len(skipped_silent),
        )
        state["resume_at"] = "04_label_audio"
        save_piab_state(args.working_folder, state)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(
        {
            "audio_previews": previews,
            "skipped_silent": skipped_silent,
            "preview_folder": str(preview_dir),
            "working_folder": str(args.working_folder.resolve()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
