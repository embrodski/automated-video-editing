#!/usr/bin/env python3
"""
Create a single WAV for human transcription from up to three video files,
then transcribe it with ElevenLabs and write an SRT-style transcript text file.

Outputs (in working folder):
  - Human Transcript.wav
  - Text Transcript.txt

Also writes ElevenLabs script outputs next to the WAV (JSON, etc).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WAV_NAME = "Human Transcript.wav"
DEFAULT_TXT_NAME = "Text Transcript.txt"
DEFAULT_KEY_FILE = "ElevenLabs 100k Key.txt"


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"Command failed ({r.returncode}): {' '.join(cmd)}\n{(r.stderr or r.stdout).strip()}"
        )


def _read_api_key(key_path: Path) -> str:
    if not key_path.is_file():
        raise FileNotFoundError(f"Missing API key file: {key_path}")
    key = key_path.read_text(encoding="utf-8", errors="replace").strip()
    if not key:
        raise ValueError(f"Empty API key file: {key_path}")
    return key


def _extract_audio_mono_wav(
    video_path: Path,
    out_wav: Path,
    *,
    sample_rate: int,
) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path.resolve()),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(out_wav.resolve()),
        ]
    )


def _concat_wavs(wavs: list[Path], out_wav: Path) -> None:
    # Use concat demuxer for sample-accurate concatenation.
    # All inputs must share codec/channels/rate (we enforce via extraction).
    list_text = "\n".join(f"file '{p.as_posix()}'" for p in wavs) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(list_text)
        list_path = Path(f.name)
    try:
        _run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(out_wav.resolve()),
            ]
        )
    finally:
        try:
            list_path.unlink(missing_ok=True)
        except Exception:
            pass


def create_human_transcript(
    working_folder: Path,
    videos: list[Path],
    *,
    api_key_file: Path,
    out_wav_name: str = DEFAULT_WAV_NAME,
    out_txt_name: str = DEFAULT_TXT_NAME,
    sample_rate: int = 16000,
) -> tuple[Path, Path]:
    working_folder = working_folder.expanduser().resolve()
    working_folder.mkdir(parents=True, exist_ok=True)

    if not (1 <= len(videos) <= 3):
        raise ValueError("Provide between 1 and 3 video files.")

    resolved_videos: list[Path] = []
    for v in videos:
        vp = (working_folder / v).resolve() if not v.is_absolute() else v.resolve()
        if not vp.is_file():
            raise FileNotFoundError(f"Missing video file: {vp}")
        resolved_videos.append(vp)

    out_wav = (working_folder / out_wav_name).resolve()
    out_txt = (working_folder / out_txt_name).resolve()

    api_key = _read_api_key(api_key_file)

    eleven_script = (REPO_ROOT / "scripts" / "elevenlabs_transcribe_wav.py").resolve()
    if not eleven_script.is_file():
        raise FileNotFoundError(f"Missing script: {eleven_script}")

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        parts: list[Path] = []
        for i, vp in enumerate(resolved_videos, start=1):
            part = tdir / f"part_{i:02d}.wav"
            _extract_audio_mono_wav(vp, part, sample_rate=sample_rate)
            parts.append(part)

        _concat_wavs(parts, out_wav)

    # Transcribe and force plain text output. This script will write:
    # - "Human Transcript Text.txt" next to the WAV, plus JSON files.
    _run(
        [
            sys.executable,
            str(eleven_script),
            str(out_wav),
            "--api-key",
            api_key,
            "--text-format",
            "srt",
        ]
    )

    produced_txt = out_wav.with_name(f"{out_wav.stem} Text.txt")
    if not produced_txt.is_file():
        raise RuntimeError(f"Expected ElevenLabs output not found: {produced_txt}")

    out_txt.write_text(produced_txt.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return out_wav, out_txt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("working_folder", type=Path, help="Folder to write outputs into.")
    p.add_argument("video_1", type=Path, help="First video file (absolute or relative to working folder).")
    p.add_argument("video_2", type=Path, nargs="?", default=None)
    p.add_argument("video_3", type=Path, nargs="?", default=None)
    p.add_argument(
        "--api-key-file",
        type=Path,
        default=(REPO_ROOT / DEFAULT_KEY_FILE),
        help=f"Defaults to repo root '{DEFAULT_KEY_FILE}'.",
    )
    p.add_argument("--sample-rate", type=int, default=16000, help="WAV sample rate (default: 16000).")
    args = p.parse_args()

    vids = [args.video_1]
    if args.video_2 is not None:
        vids.append(args.video_2)
    if args.video_3 is not None:
        vids.append(args.video_3)

    try:
        out_wav, out_txt = create_human_transcript(
            args.working_folder,
            vids,
            api_key_file=args.api_key_file,
            sample_rate=int(args.sample_rate),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {out_wav}")
    print(f"Wrote {out_txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

