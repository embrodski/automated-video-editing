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
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REQUIRED_FILES = [
    "Intro.mp4",
    "Reading.mp4",
    "Edited Interview.mp4",
    "Inkhaven Presents Closing.mp4",
]


@dataclass(frozen=True)
class MediaInfo:
    duration_s: float
    width: int
    height: int
    fps: str  # e.g. "24000/1001"
    sample_rate: int


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


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


def stitch_episode(output_dir: Path, fade_s: float = 0.5, black_s: float = 0.25) -> Path:
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

    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error", "-y"]
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
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            str(tmp_out),
        ]
    )

    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{p.stderr.strip()}")

    # Atomic-ish replace
    if output_path.exists():
        output_path.unlink()
    tmp_out.replace(output_path)

    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError(f"Output was not created or is empty: {output_path}")

    return output_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Stitch Inkhaven episode parts into Complete Episode.mp4")
    ap.add_argument("--output-dir", required=True, help="Output folder containing the four required MP4 parts")
    args = ap.parse_args()

    out_dir = Path(args.output_dir).expanduser().resolve()
    if not out_dir.exists():
        print(f"Error: output dir not found: {out_dir}", file=sys.stderr)
        return 2

    try:
        out_file = stitch_episode(out_dir)
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

