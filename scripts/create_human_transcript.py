#!/usr/bin/env python3
"""
Create a single WAV for human transcription from up to three video files,
then transcribe it with ElevenLabs and write an SRT-style transcript text file.

Intermediate outputs (WAV, raw transcript, ElevenLabs sidecars) go in the
episode Temp folder parallel to the deliverable folder (parent + Temp sibling).
Only the cleaned Host-Guest transcript stays in the deliverable folder when
--host and --guest are supplied.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from hide_console import run as _run_hidden

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_WAV_NAME = "Human Transcript.wav"
DEFAULT_TXT_NAME = "Text Transcript.txt"
DEFAULT_KEY_FILE = "ElevenLabs 100k Key.txt"


def _run(cmd: list[str]) -> None:
    r = _run_hidden(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"Command failed ({r.returncode}): {' '.join(cmd)}\n{(r.stderr or r.stdout).strip()}"
        )


def resolve_episode_temp_folder(deliverable_folder: Path) -> Path:
    """
    Find the episode Temp folder: parent of deliverable_folder, then a child
    directory named Temp (case-insensitive). Creates Temp if missing.
    """
    deliverable_folder = deliverable_folder.expanduser().resolve()
    parent = deliverable_folder.parent
    if parent == deliverable_folder:
        raise ValueError(
            f"Cannot resolve Temp folder for {deliverable_folder}: no parent directory."
        )
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == "temp":
            return child.resolve()
    temp = (parent / "Temp").resolve()
    temp.mkdir(parents=True, exist_ok=True)
    return temp


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
    deliverable_folder: Path,
    videos: list[Path],
    *,
    api_key_file: Path,
    out_wav_name: str = DEFAULT_WAV_NAME,
    out_txt_name: str = DEFAULT_TXT_NAME,
    sample_rate: int = 16000,
) -> tuple[Path, Path, Path]:
    deliverable_folder = deliverable_folder.expanduser().resolve()
    deliverable_folder.mkdir(parents=True, exist_ok=True)
    temp_folder = resolve_episode_temp_folder(deliverable_folder)
    temp_folder.mkdir(parents=True, exist_ok=True)

    if not (1 <= len(videos) <= 3):
        raise ValueError("Provide between 1 and 3 video files.")

    resolved_videos: list[Path] = []
    for v in videos:
        vp = (deliverable_folder / v).resolve() if not v.is_absolute() else v.resolve()
        if not vp.is_file():
            raise FileNotFoundError(f"Missing video file: {vp}")
        resolved_videos.append(vp)

    out_wav = (temp_folder / out_wav_name).resolve()
    out_txt = (temp_folder / out_txt_name).resolve()

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
    return out_wav, out_txt, temp_folder


def write_cleaned_transcript(
    deliverable_folder: Path,
    raw_txt: Path,
    *,
    host: str,
    guest: str,
) -> Path:
    deliverable_folder = deliverable_folder.expanduser().resolve()
    deliverable_folder.mkdir(parents=True, exist_ok=True)
    out_path = deliverable_folder / f"{host}-{guest} Transcript.txt"
    clean_script = (SCRIPTS_DIR / "clean_human_transcript.py").resolve()
    if not clean_script.is_file():
        raise FileNotFoundError(f"Missing script: {clean_script}")
    _run(
        [
            sys.executable,
            str(clean_script),
            str(raw_txt.resolve()),
            "--host",
            host,
            "--guest",
            guest,
            "--output",
            str(out_path),
        ]
    )
    if not out_path.is_file():
        raise RuntimeError(f"Clean step did not produce: {out_path}")
    return out_path.resolve()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "deliverable_folder",
        type=Path,
        help="Folder that receives only the cleaned Host-Guest transcript (e.g. Output).",
    )
    p.add_argument(
        "video_1",
        type=Path,
        help="First video file (absolute or relative to deliverable folder).",
    )
    p.add_argument("video_2", type=Path, nargs="?", default=None)
    p.add_argument("video_3", type=Path, nargs="?", default=None)
    p.add_argument("--host", default=None, help="Host name (Speaker 0); runs clean step when set with --guest.")
    p.add_argument("--guest", default=None, help="Guest name (Speaker 1); runs clean step when set with --host.")
    p.add_argument(
        "--api-key-file",
        type=Path,
        default=(REPO_ROOT / DEFAULT_KEY_FILE),
        help=f"Defaults to repo root '{DEFAULT_KEY_FILE}'.",
    )
    p.add_argument("--sample-rate", type=int, default=16000, help="WAV sample rate (default: 16000).")
    args = p.parse_args()

    if (args.host is None) ^ (args.guest is None):
        print("Error: pass both --host and --guest, or neither.", file=sys.stderr)
        return 1

    vids = [args.video_1]
    if args.video_2 is not None:
        vids.append(args.video_2)
    if args.video_3 is not None:
        vids.append(args.video_3)

    try:
        out_wav, out_txt, temp_folder = create_human_transcript(
            args.deliverable_folder,
            vids,
            api_key_file=args.api_key_file,
            sample_rate=int(args.sample_rate),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"Temp folder: {temp_folder}")
    print(f"Wrote {out_wav}")
    print(f"Wrote {out_txt}")

    if args.host is not None and args.guest is not None:
        try:
            cleaned = write_cleaned_transcript(
                args.deliverable_folder,
                out_txt,
                host=args.host.strip(),
                guest=args.guest.strip(),
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
        print(f"Wrote {cleaned}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

