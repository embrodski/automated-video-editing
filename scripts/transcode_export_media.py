#!/usr/bin/env python3
"""Transcode video/audio to compact HEVC + MP3 for export/offload."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv"}
AUDIO_EXTS = {".wav", ".flac", ".aiff", ".aif"}


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"{proc.stderr or proc.stdout}"
        )


def video_encoder_args(encoder: str, cq: int) -> list[str]:
    if encoder == "hevc_nvenc":
        return [
            "-c:v",
            "hevc_nvenc",
            "-preset",
            "p5",
            "-rc",
            "vbr",
            "-cq",
            str(cq),
            "-b:v",
            "0",
        ]
    if encoder == "hevc_qsv":
        return ["-c:v", "hevc_qsv", "-global_quality", str(cq)]
    if encoder == "hevc_amf":
        return ["-c:v", "hevc_amf", "-rc", "vbr_latency", "-qp_i", str(cq), "-qp_p", str(cq)]
    if encoder == "libx265":
        return ["-c:v", "libx265", "-crf", str(cq), "-preset", "medium", "-tag:v", "hvc1"]
    raise ValueError(f"Unsupported encoder: {encoder}")


def _encoder_usable(encoder: str) -> bool:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x256:d=0.1",
        *video_encoder_args(encoder, cq=30),
        "-f",
        "null",
        "-",
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def resolve_video_encoder(requested: str) -> str:
    if requested != "auto":
        if not _encoder_usable(requested):
            raise RuntimeError(f"Video encoder not usable: {requested}")
        return requested
    for enc in ("hevc_nvenc", "hevc_qsv", "hevc_amf", "libx265"):
        if _encoder_usable(enc):
            return enc
    raise RuntimeError("No usable HEVC encoder found")


def transcode_video(
    src: Path,
    dst: Path,
    *,
    encoder: str,
    cq: int,
    audio_bitrate: str,
    allow_overwrite: bool,
) -> bool:
    if dst.is_file() and not allow_overwrite:
        print(f"Skip (exists): {dst}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.stem}.partial{dst.suffix}")
    if tmp.is_file():
        tmp.unlink()

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        *video_encoder_args(encoder, cq),
        "-c:a",
        "libmp3lame",
        "-b:a",
        audio_bitrate,
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    print(f"Video: {src.name} -> {dst}")
    _run(cmd)
    tmp.replace(dst)
    return True


def transcode_audio(
    src: Path,
    dst: Path,
    *,
    audio_bitrate: str,
    allow_overwrite: bool,
) -> bool:
    if dst.is_file() and not allow_overwrite:
        print(f"Skip (exists): {dst}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f"{dst.stem}.partial.mp3")
    if tmp.is_file():
        tmp.unlink()

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
        "-i",
        str(src),
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        audio_bitrate,
        str(tmp),
    ]
    print(f"Audio: {src.name} -> {dst}")
    _run(cmd)
    tmp.replace(dst)
    return True


def export_tree(
    src_root: Path,
    dst_root: Path,
    *,
    encoder: str,
    cq: int,
    audio_bitrate: str,
    allow_overwrite: bool,
) -> int:
    src_root = src_root.resolve()
    dst_root = dst_root.resolve()
    count = 0
    for path in sorted(src_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src_root)
        ext = path.suffix.lower()
        if ext in VIDEO_EXTS:
            out = dst_root / rel.with_suffix(".mp4")
            if transcode_video(
                path,
                out,
                encoder=encoder,
                cq=cq,
                audio_bitrate=audio_bitrate,
                allow_overwrite=allow_overwrite,
            ):
                count += 1
        elif ext in AUDIO_EXTS:
            out = dst_root / rel.with_suffix(".mp3")
            if transcode_audio(
                path,
                out,
                audio_bitrate=audio_bitrate,
                allow_overwrite=allow_overwrite,
            ):
                count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Export media as HEVC MP4 + MP3.")
    parser.add_argument(
        "source_dirs",
        nargs="+",
        type=Path,
        help="Source folders to mirror under --out-dir (e.g. Raw Input).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Export root (mirrors each source folder name).",
    )
    parser.add_argument("--video-encoder", default="auto")
    parser.add_argument("--cq", type=int, default=30, help="HEVC quality (lower=better, bigger).")
    parser.add_argument("--audio-bitrate", default="192k")
    parser.add_argument("--allow-overwrite", action="store_true")
    args = parser.parse_args()

    encoder = resolve_video_encoder(args.video_encoder)
    print(f"Using video encoder: {encoder} (cq={args.cq}), audio: MP3 {args.audio_bitrate}")

    total = 0
    for src in args.source_dirs:
        src = src.resolve()
        if not src.is_dir():
            print(f"Missing source dir: {src}", file=sys.stderr)
            return 1
        dst = args.out_dir.resolve() / src.name
        print(f"\n=== {src.name} -> {dst} ===")
        total += export_tree(
            src,
            dst,
            encoder=encoder,
            cq=args.cq,
            audio_bitrate=args.audio_bitrate,
            allow_overwrite=args.allow_overwrite,
        )

    print(f"\nTranscoded {total} file(s) under {args.out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
