#!/usr/bin/env python3
"""
Stitch an Inkhaven episode from four pre-rendered parts in an Output folder.

Inputs (must exist in output dir):
  - Intro.mp4
  - Reading.mp4
  - Edited Interview.mp4
  - Inkhaven Presents Closing.mp4

Processing:
  - 0.5s fade-in + 0.5s fade-out on EACH clip (video + audio)
  - 0.25s black (with silence) inserted between clips
  - Concatenate in the order above

Output:
  - Complete Episode.mp4 in the same output dir
  - After success, four lines: fade-in start time (mm:ss) + label for Intro / Reading /
    Interview / Sponsor (closing), derived from source durations and black gaps.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from podcast_dsl.video_renderer import (
    DEFAULT_VIDEO_ENCODER,
    _append_video_encoder_args,
    _requested_video_preset,
    _resolved_video_encoder,
)


REQUIRED_FILES = [
    "Intro.mp4",
    "Reading.mp4",
    "Edited Interview.mp4",
    "Inkhaven Presents Closing.mp4",
]

# One-word labels for stdout markers (closing segment = Sponsor).
FADE_IN_MARKER_LABELS = ("Intro", "Reading", "Interview", "Sponsor")
VIDEO_ENCODER_CHOICES = ("auto", "libx264", "h264_nvenc", "h264_qsv", "h264_amf")
DEFAULT_STITCH_VIDEO_PRESET = "fast"


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    width: int
    height: int
    fps: str  # e.g. "24000/1001"
    sample_rate: int


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _summarize_stderr(stderr_text: str, max_lines: int = 20) -> str:
    lines = [line.rstrip() for line in (stderr_text or "").splitlines() if line.strip()]
    if not lines:
        return "(no stderr output)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines] + ["...", f"[truncated {len(lines) - max_lines} more lines]"])


def _ffprobe_json(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,width,height,r_frame_rate,sample_rate",
        "-of",
        "json",
        str(path),
    ]
    p = _run(cmd)
    if p.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{p.stderr.strip()}")
    import json

    return json.loads(p.stdout)


def _validate_video_output(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Expected output file was not created: {path}")
    if path.stat().st_size <= 0:
        raise RuntimeError(f"Output file is empty: {path}")

    stream_info = _ffprobe_json(path)
    video_streams = [s for s in stream_info.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise RuntimeError(f"No video stream found in {path}")

    pix_fmt_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=pix_fmt",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    pix_fmt_result = _run(pix_fmt_cmd)
    if pix_fmt_result.returncode != 0:
        raise RuntimeError(
            f"ffprobe could not inspect pixel format for {path}:\n"
            f"{_summarize_stderr(pix_fmt_result.stderr)}"
        )

    pix_fmt = pix_fmt_result.stdout.strip().lower()
    if not pix_fmt or pix_fmt == "unknown":
        raise RuntimeError(f"Video stream in {path} has an invalid pixel format: {pix_fmt_result.stdout.strip()!r}")

    decode_cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    decode_result = _run(decode_cmd)
    if decode_result.returncode != 0:
        raise RuntimeError(
            f"Video stream decode validation failed for {path}:\n"
            f"{_summarize_stderr(decode_result.stderr)}"
        )


def _get_media_info(path: Path) -> MediaInfo:
    data = _ffprobe_json(path)
    duration_s = float(data["format"]["duration"])

    width = height = None
    fps = None
    sample_rate = None

    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and width is None:
            width = int(s["width"])
            height = int(s["height"])
            fps = str(s.get("r_frame_rate") or "30/1")
        if s.get("codec_type") == "audio" and sample_rate is None:
            # some files may omit sample_rate; default later
            sr = s.get("sample_rate")
            if sr is not None:
                sample_rate = int(sr)

    if width is None or height is None:
        raise RuntimeError(f"No video stream found in {path}")

    if fps is None:
        fps = "30/1"

    if sample_rate is None:
        sample_rate = 48000

    return MediaInfo(
        duration_s=duration_s,
        width=width,
        height=height,
        fps=fps,
        sample_rate=sample_rate,
    )


def _format_mmss_from_start(seconds: float) -> str:
    """Whole seconds from timeline start, as mm:ss (minutes zero-padded to 2 if < 100)."""
    s = max(0, int(round(seconds)))
    m, sec = divmod(s, 60)
    if m < 100:
        return f"{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _fade_in_start_times_s(infos: list[MediaInfo], black_s: float) -> list[float]:
    """Timeline position where each clip's fade-in begins (concat order, after black gaps)."""
    out: list[float] = []
    t = 0.0
    for i, info in enumerate(infos):
        out.append(t)
        t += info.duration_s
        if i < len(infos) - 1:
            t += black_s
    return out


def _print_fade_in_marker_lines(infos: list[MediaInfo], black_s: float) -> None:
    starts = _fade_in_start_times_s(infos, black_s)
    for start_s, label in zip(starts, FADE_IN_MARKER_LABELS):
        print(f"{_format_mmss_from_start(start_s)} {label}")


def stitch_episode(
    output_dir: Path,
    fade_s: float = 0.5,
    black_s: float = 0.25,
    *,
    video_encoder: str,
    video_preset: str,
) -> Path:
    missing = [name for name in REQUIRED_FILES if not (output_dir / name).exists()]
    if missing:
        missing_list = "\n".join(f"- {m}" for m in missing)
        raise FileNotFoundError(
            "Missing required file(s) in output folder:\n"
            f"{missing_list}\n\n"
            f"Output folder: {output_dir}"
        )

    inputs = [output_dir / name for name in REQUIRED_FILES]
    infos = [_get_media_info(p) for p in inputs]

    # Use the first clip as the canonical output geometry/timebase.
    base = infos[0]
    out_w, out_h = base.width, base.height
    out_fps = base.fps
    out_sr = base.sample_rate

    # Compute fade-out start times per clip.
    # Guard against too-short clips: if duration <= fade_s, clamp to 0.
    fade_out_starts = [max(0.0, info.duration_s - fade_s) for info in infos]

    # Build filter_complex.
    #
    # For each clip i:
    #   - normalize geometry/fps/sar
    #   - apply video fades in/out
    #   - apply audio fades in/out
    #
    # Between clips, generate black video + silent audio segments.
    #
    # Finally concat all 7 segments: clip0, black, clip1, black, clip2, black, clip3
    parts: list[str] = []
    v_labels: list[str] = []
    a_labels: list[str] = []

    for i in range(4):
        v_out = f"v{i}"
        a_out = f"a{i}"

        v_chain = (
            f"[{i}:v]"
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={out_fps},setsar=1,"
            f"fade=t=in:st=0:d={fade_s},"
            f"fade=t=out:st={fade_out_starts[i]}:d={fade_s}"
            f"[{v_out}]"
        )
        a_chain = (
            f"[{i}:a]"
            f"aresample={out_sr},"
            f"loudnorm=I=-16:LRA=11:TP=-1.5,"
            f"afade=t=in:st=0:d={fade_s},"
            f"afade=t=out:st={fade_out_starts[i]}:d={fade_s}"
            f"[{a_out}]"
        )

        parts.append(v_chain)
        parts.append(a_chain)
        v_labels.append(f"[{v_out}]")
        a_labels.append(f"[{a_out}]")

    # black gaps (3)
    for j in range(3):
        bv = f"bv{j}"
        ba = f"ba{j}"
        parts.append(f"color=c=black:s={out_w}x{out_h}:r={out_fps}:d={black_s}[{bv}]")
        parts.append(f"anullsrc=r={out_sr}:cl=stereo:d={black_s}[{ba}]")
        v_labels.insert(1 + 2 * j, f"[{bv}]")
        a_labels.insert(1 + 2 * j, f"[{ba}]")

    concat_n = len(v_labels)  # should be 7
    # concat expects interleaved pairs: [v0][a0][v1][a1]...
    concat_inputs = "".join(v + a for v, a in zip(v_labels, a_labels))
    parts.append(f"{concat_inputs}concat=n={concat_n}:v=1:a=1[v][a]")

    filter_complex = ";".join(parts)

    output_path = output_dir / "Complete Episode.mp4"
    tmp_out = output_dir / "Complete Episode._tmp.mp4"
    resolved_video_encoder = _resolved_video_encoder(video_preset)

    # Default to showing progress so long stitches don't look "stuck".
    # ffmpeg writes progress to stderr when `-stats` is enabled.
    cmd = ["ffmpeg", "-hide_banner", "-stats", "-loglevel", "warning", "-y"]
    for p in inputs:
        cmd.extend(["-i", str(p)])
    cmd.extend(
        [
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
        ]
    )
    _append_video_encoder_args(cmd, resolved_video_encoder, video_preset, quality_level=18)
    cmd.extend([
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-movflags",
        "+faststart",
        str(tmp_out),
    ])

    print("Stitching episode parts with ffmpeg (this can take a while for long interviews)...")
    print(f"Video encoder: {video_encoder}")
    if video_encoder == "auto":
        print(f"Resolved encoder: {resolved_video_encoder}")
    print(f"Video preset: {video_preset}")
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed. Re-run and watch ffmpeg output above; if it flashes by, "
            "re-run from a console with scrollback and capture the error details."
        )

    _validate_video_output(tmp_out)

    # Atomic-ish replace
    if output_path.exists():
        output_path.unlink()
    tmp_out.replace(output_path)

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Output was not created or is empty: {output_path}")

    _print_fade_in_marker_lines(infos, black_s)

    return output_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Stitch Inkhaven episode parts into Complete Episode.mp4")
    ap.add_argument("--output-dir", required=True, help="Output folder containing the four required MP4 parts")
    ap.add_argument(
        "--video-encoder",
        choices=VIDEO_ENCODER_CHOICES,
        default=DEFAULT_VIDEO_ENCODER,
        help="Video encoder for the stitched output. Defaults to auto hardware detection with libx264 fallback.",
    )
    ap.add_argument(
        "--video-preset",
        default=DEFAULT_STITCH_VIDEO_PRESET,
        help=f"Preset for the selected video encoder (default: {DEFAULT_STITCH_VIDEO_PRESET})",
    )
    args = ap.parse_args()

    out_dir = Path(args.output_dir).expanduser().resolve()
    if not out_dir.exists():
        print(f"Error: output dir not found: {out_dir}", file=sys.stderr)
        return 2

    os.environ["PODCAST_DSL_VIDEO_ENCODER"] = args.video_encoder
    os.environ["PODCAST_DSL_VIDEO_PRESET"] = args.video_preset

    try:
        out_file = stitch_episode(
            out_dir,
            video_encoder=args.video_encoder,
            video_preset=_requested_video_preset(DEFAULT_STITCH_VIDEO_PRESET),
        )
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Done! Output: {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

