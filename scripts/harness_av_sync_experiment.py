#!/usr/bin/env python3
"""
Experimental A/V sync variants + 1-minute podcast autocut renders.

Intended as a sandbox before promoting a fallback into the main harness when
``sync_video_wav_replace`` correlation confidence is low.

Modes:
  host-only-sync  — correlate/mux using Host Raw Audio.wav (host close-mic) instead
                    of the combined clean mix (may improve correlation on Host cam).
  forced-offset   — use combined clean audio but apply detected lag even when
                    peak strength is below the default threshold.

Writes under ``<Temp>/av-sync-experiments/<mode>/`` and renders:
  ``<Output>/1 Min Test host-only sync.mp4``
  ``<Output>/1 Min Test forced offset.mp4``

Uses the episode's existing ``interview.dsl`` and transcript (same cut decisions).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from episode_segments import MAIN_SEGMENT_KEY, save_segments_file, segments_path
from harness_autocut_common import render_dsl, run_cmd
from harness_episode_lib import (
    BEN_HOST_RE,
    REPO_ROOT,
    WIDE_RE,
    load_episode_state,
)
from harness_overwrite_guard import HarnessOverwriteError, OVERWRITE_EXIT_CODE, refuse_overwrite
from harness_episode_lib import pick_interview_videos
from harness_video_sync import (
    find_scope_videos,
    prepped_basename,
    prepped_wav_basename,
    synced_basename,
)


@dataclass(frozen=True)
class ExperimentSpec:
    mode: str
    output_mp4_name: str
    sync_audio_name: str
    force_detected_lag: bool = False


EXPERIMENTS: dict[str, ExperimentSpec] = {
    "host-only-sync": ExperimentSpec(
        mode="host-only-sync",
        output_mp4_name="1 Min Test host-only sync.mp4",
        sync_audio_name="Host Raw Audio.wav",
    ),
    "forced-offset": ExperimentSpec(
        mode="forced-offset",
        output_mp4_name="1 Min Test forced offset.mp4",
        sync_audio_name="Host Clean Audio.wav",
        force_detected_lag=True,
    ),
}


def _resolve_sync_audio(raw_dir: Path, spec: ExperimentSpec, state: dict) -> Path:
    if spec.sync_audio_name == "Host Clean Audio.wav":
        if state.get("main_clean_audio"):
            path = Path(state["main_clean_audio"])
            if path.is_file():
                return path
    candidate = raw_dir / spec.sync_audio_name
    if not candidate.is_file():
        raise FileNotFoundError(f"Sync audio not found for {spec.mode}: {candidate}")
    return candidate


def _run_sync_pass(
    video: Path,
    sync_audio: Path,
    synced_path: Path,
    *,
    force_detected_lag: bool,
) -> dict:
    report_path = synced_path.with_suffix(".json")
    refuse_overwrite(synced_path, allow_overwrite=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "sync_video_wav_replace.py"),
        str(video.resolve()),
        str(sync_audio.resolve()),
        "-o",
        str(synced_path),
        "--json-report",
        str(report_path),
    ]
    if force_detected_lag:
        cmd.append("--force-detected-lag")
    run_cmd(cmd)
    return json.loads(report_path.read_text(encoding="utf-8"))


def _prep_experiment_media(
    raw_dir: Path,
    sync_audio: Path,
    videos: list[Path],
    work_dir: Path,
    *,
    force_detected_lag: bool,
) -> dict:
    sync_dir = work_dir / "synced"
    prepped_dir = work_dir / "prepped"
    sync_dir.mkdir(parents=True, exist_ok=True)
    prepped_dir.mkdir(parents=True, exist_ok=True)

    sync_reports: list[dict] = []
    synced_paths: list[Path] = []
    for video in videos:
        synced_name = synced_basename(video)
        synced_path = sync_dir / synced_name
        report = _run_sync_pass(
            video,
            sync_audio,
            synced_path,
            force_detected_lag=force_detected_lag,
        )
        report["source_video"] = str(video)
        sync_reports.append(report)
        synced_paths.append(synced_path)

    mc_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "multicam_align_trim.py"),
        "--prepped-names",
        "--out-dir",
        str(prepped_dir),
        "--json-report",
        str(work_dir / "video-sync-multicam.json"),
        *[str(p) for p in synced_paths],
    ]
    run_cmd(mc_cmd)

    prepped_paths: list[Path] = []
    for synced in synced_paths:
        prepped = prepped_dir / prepped_basename(synced.name)
        if not prepped.is_file():
            raise FileNotFoundError(f"Missing multicam output: {prepped}")
        prepped_paths.append(prepped)

    anchor_prepped = prepped_dir / prepped_basename(synced_paths[0].name)
    wav_out = prepped_dir / prepped_wav_basename(sync_audio)
    run_cmd(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "extract_mp4_audio_wav.py"),
            str(anchor_prepped),
            str(wav_out),
        ]
    )

    ben, guest, wide = pick_interview_videos([str(p) for p in prepped_paths])
    return {
        "sync_audio": str(sync_audio.resolve()),
        "sync_reports": sync_reports,
        "prepped_videos": [str(ben), str(guest), str(wide)],
        "prepped_audio_wav": str(wav_out.resolve()),
        "work_dir": str(work_dir.resolve()),
    }


def _render_one_min_test(
    episode_folder: Path,
    state: dict,
    prep: dict,
    *,
    output_mp4: Path,
    segments_dir: Path,
    allow_overwrite: bool,
) -> None:
    temp = Path(state["paths"]["temp"])
    interview_dsl = Path(state.get("interview_dsl") or temp / "interview.dsl")
    if not interview_dsl.is_file():
        raise FileNotFoundError(f"interview.dsl not found: {interview_dsl}")

    ben, guest, wide = pick_interview_videos(prep["prepped_videos"])
    simplified = temp / "interview_transcript_simplified.json"
    if not simplified.is_file():
        raise FileNotFoundError(f"Missing simplified transcript: {simplified}")

    segments_dir.mkdir(parents=True, exist_ok=True)
    save_segments_file(
        segments_path(segments_dir),
        {
            MAIN_SEGMENT_KEY: {
                "audio_file": prep["prepped_audio_wav"],
                "audio_offset": 0,
                "enable_color_match": False,
                "video_files": {
                    "speaker_0": {"file": str(ben), "offset": 0},
                    "speaker_1": {"file": str(guest), "offset": 0},
                    "wide": {"file": str(wide), "offset": 0},
                },
                "transcript_file": str(simplified),
            }
        },
    )

    refuse_overwrite(output_mp4, allow_overwrite=allow_overwrite)
    render_dsl(
        interview_dsl,
        output_mp4,
        segments_dir,
        max_seconds=60,
        allow_overwrite=allow_overwrite,
    )


def run_experiment(
    episode_folder: Path,
    mode: str,
    *,
    allow_overwrite: bool = False,
) -> dict:
    if mode not in EXPERIMENTS:
        raise ValueError(f"Unknown mode {mode!r}; choose from {sorted(EXPERIMENTS)}")

    spec = EXPERIMENTS[mode]
    state = load_episode_state(episode_folder)
    raw_dir = Path(state["paths"]["raw"])
    output_dir = Path(state["paths"]["output"])
    temp = Path(state["paths"]["temp"])

    sync_audio = _resolve_sync_audio(raw_dir, spec, state)
    videos = find_scope_videos(raw_dir, "main")
    work_dir = temp / "av-sync-experiments" / spec.mode

    prep = _prep_experiment_media(
        raw_dir,
        sync_audio,
        videos,
        work_dir,
        force_detected_lag=spec.force_detected_lag,
    )
    output_mp4 = output_dir / spec.output_mp4_name
    _render_one_min_test(
        episode_folder,
        state,
        prep,
        output_mp4=output_mp4,
        segments_dir=work_dir / "render-segments",
        allow_overwrite=allow_overwrite,
    )

    summary = {
        "mode": spec.mode,
        "output_mp4": str(output_mp4.resolve()),
        "sync_audio": prep["sync_audio"],
        "force_detected_lag": spec.force_detected_lag,
        "applied_lags_ms": [
            {
                "video": r.get("video_path"),
                "detected_ms": r.get("correlation_lag_ms"),
                "applied_ms": r.get("lag_ms"),
                "strength": r.get("correlation_peak_strength"),
                "start_aligned": r.get("start_aligned"),
            }
            for r in prep["sync_reports"]
        ],
        "work_dir": prep["work_dir"],
    }
    (work_dir / "experiment-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="A/V sync experiment 1-min renders.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument(
        "--mode",
        choices=tuple(EXPERIMENTS) + ("all",),
        default="all",
        help="Experiment to run (default: all).",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Overwrite experiment outputs in Output/ and Temp/av-sync-experiments/.",
    )
    args = parser.parse_args()

    modes = list(EXPERIMENTS) if args.mode == "all" else [args.mode]
    results: list[dict] = []
    try:
        for mode in modes:
            results.append(
                run_experiment(
                    args.episode_folder.resolve(),
                    mode,
                    allow_overwrite=args.allow_overwrite,
                )
            )
    except HarnessOverwriteError:
        return OVERWRITE_EXIT_CODE
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"experiments": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
