#!/usr/bin/env python3
"""
PIAB prep: conversation-sync → Combined-as-Clean (DeRoom placeholder) →
video-sync → transcribe → podcast autocut 1-min test.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import (
    combined_audio_output_name,
    find_conversation_wav_pair,
    read_elevenlabs_api_key,
    run_conversation_sync,
)
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite
from harness_transcribe_prepped import _run_transcribe
from harness_video_sync import find_scope_videos, run_video_sync
from piab_lib import load_piab_state, mark_step, print_json, save_piab_state


def _alias_combined_as_clean(
    combined: Path,
    *,
    allow_overwrite: bool,
) -> Path:
    """DeRoom placeholder: copy Combined → Clean so video-sync can proceed."""
    # Prefer "Host Clean Audio.wav" when combined is "Host Combined Audio.wav"
    name = combined.name
    if "Combined Audio" in name:
        clean_name = name.replace("Combined Audio", "Clean Audio")
    else:
        clean_name = f"{combined.stem} Clean Audio{combined.suffix}"
    clean = combined.parent / clean_name
    refuse_overwrite(clean, allow_overwrite=allow_overwrite)
    shutil.copy2(combined, clean)
    return clean


def main() -> int:
    parser = argparse.ArgumentParser(description="PIAB prep through 1-min test.")
    parser.add_argument("working_folder", type=Path)
    parser.add_argument("--allow-overwrite", action="store_true")
    parser.add_argument(
        "--use-clean-pair",
        action="store_true",
        help=(
            "One-off exception: run conversation-sync on Raw/Host Clean Audio.wav "
            "and Raw/Guest Clean Audio.wav, then use the combined output directly "
            "as the clean master."
        ),
    )
    parser.add_argument(
        "--skip-one-min",
        action="store_true",
        help="Stop after transcript (do not render 1 Min Test).",
    )
    args = parser.parse_args()
    working = args.working_folder.resolve()

    try:
        state = load_piab_state(working)
        raw = Path(state["paths"]["raw"])

        mark_step(
            state,
            "05_estimate_prep",
            title="Estimate prep through 1-min test",
            status="completed",
        )

        # --- conversation-sync ---
        if args.use_clean_pair:
            wav1 = raw / "Host Clean Audio.wav"
            wav2 = raw / "Guest Clean Audio.wav"
            missing = [str(path) for path in (wav1, wav2) if not path.is_file()]
            if missing:
                raise FileNotFoundError(
                    "Missing requested one-off clean audio source(s): "
                    + ", ".join(missing)
                )
        else:
            wav1, wav2 = find_conversation_wav_pair(raw, intro=False)
        combined_path = raw / combined_audio_output_name(wav1)
        refuse_overwrite(combined_path, allow_overwrite=args.allow_overwrite)
        combined = run_conversation_sync(wav1, wav2)
        state["main_combined_audio"] = str(combined)
        mark_step(
            state,
            "06_conversation_sync",
            title="Conversation-sync",
            status="completed",
            wav1=wav1.name,
            wav2=wav2.name,
            output=str(combined),
        )

        # --- DeRoom placeholder ---
        if args.use_clean_pair:
            clean = combined
            deroom_note = (
                "One-off exception: conversation-sync used Host/Guest Clean Audio "
                "exports; the combined output is the clean master."
            )
        else:
            clean = _alias_combined_as_clean(
                combined, allow_overwrite=args.allow_overwrite
            )
            deroom_note = (
                "Future: real DeRoom. For now Combined Audio is copied to Clean Audio."
            )
        state["main_clean_audio"] = str(clean)
        mark_step(
            state,
            "07_deroom_placeholder",
            title="Clean audio selection",
            status="completed",
            skipped_real_deroom=not args.use_clean_pair,
            used_clean_pair=args.use_clean_pair,
            main_clean_audio=str(clean),
            note=deroom_note,
        )

        # --- video-sync ---
        videos = find_scope_videos(raw, "main")
        result = run_video_sync(
            raw,
            clean,
            videos,
            allow_overwrite=args.allow_overwrite,
        )
        state["main_prepped"] = result
        mark_step(
            state,
            "08_video_sync",
            title="Video-sync (main)",
            status="completed",
            **result,
        )

        # --- transcribe ---
        api_key = read_elevenlabs_api_key()
        wav = Path(result["prepped_audio_wav"])
        transcript = _run_transcribe(wav, api_key, allow_overwrite=args.allow_overwrite)
        state["main_transcript_json"] = str(transcript)
        mark_step(
            state,
            "09_transcribe",
            title="Transcribe prepped WAV",
            status="completed",
            wav=str(wav),
            transcript_json=str(transcript),
        )
        save_piab_state(working, state)

        if args.skip_one_min:
            state["resume_at"] = "10_one_min_test"
            save_piab_state(working, state)
            print_json(state)
            return 0

        # --- 1-min podcast autocut (reuse harness script via state file) ---
        from harness_autocut_common import render_dsl, run_cmd
        from harness_episode_lib import REPO_ROOT, podcast_phrase_cli_args, podcast_swap_speaker_ids_cli_args
        from episode_segments import MAIN_SEGMENT_KEY, segments_path, upsert_segment
        from harness_podcast_autocut_test import _pick_interview_videos

        temp = Path(state["paths"]["temp"])
        output_dir = Path(state["paths"]["output"])
        temp.mkdir(parents=True, exist_ok=True)
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

        segment_id = MAIN_SEGMENT_KEY
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
        # Keep harness-compatible step ids for render script reuse.
        mark_step(
            state,
            "15_podcast_autocut_test",
            title="Podcast autocut 1-min test",
            status="completed",
            output_mp4=str(out_mp4),
        )
        mark_step(
            state,
            "18_interview_test_approval",
            title="Interview 1-min test approval",
            status="awaiting_user",
        )
        state["resume_at"] = "11_one_min_approval"
        save_piab_state(working, state)
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(
        {
            "one_min_test": str(out_mp4),
            "message": (
                f"1 Min Test is ready for review: {out_mp4}. "
                "Stop and wait for user approval. If Host/Guest cameras feel swapped, "
                "run piab_swap.py --speaker-ids toggle and re-run the 1-min test."
            ),
            "state_path": state["paths"]["state"],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
