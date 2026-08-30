"""Shared helpers for inkhaven-episode-harness."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from hide_console import run as _run_hidden


SUBFOLDERS = ("Raw", "Input", "Output", "Temp")
RAW_NAME_RE = re.compile(r"raw", re.IGNORECASE)
INKHAVEN_PREFIX_RE = re.compile(r"^inkhaven\s+(.+)$", re.IGNORECASE)
BEN_HOST_RE = re.compile(r"\b(ben|host)\b", re.IGNORECASE)
INTRO_RE = re.compile(r"\bintro\b", re.IGNORECASE)
READING_RE = re.compile(r"\breading\b", re.IGNORECASE)
REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_conversation_wavs.py"
ELEVENLABS_KEY_FILE = REPO_ROOT / "ElevenLabs 100k Key.txt"
CONFIG_PATH = REPO_ROOT / "src" / "podcast_dsl" / "config.py"
CLEAN_RE = re.compile(r"clean", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def extract_guest_name(episode_folder: Path) -> str:
    match = INKHAVEN_PREFIX_RE.match(episode_folder.name.strip())
    if not match:
        raise ValueError(
            f"Episode folder name must start with 'Inkhaven ' "
            f"(got {episode_folder.name!r})."
        )
    name = match.group(1).strip()
    if not name:
        raise ValueError(
            f"Guest name is empty after 'Inkhaven ' in {episode_folder.name!r}."
        )
    return name


def episode_json_path(episode_folder: Path, name: str | None = None) -> Path:
    guest = name or extract_guest_name(episode_folder)
    return episode_folder / f"{guest}-episode.json"


def load_episode_state(episode_folder: Path) -> dict:
    episode_folder = episode_folder.resolve()
    path = episode_json_path(episode_folder)
    if not path.is_file():
        raise FileNotFoundError(
            f"Episode state not found ({path}). Run init_inkhaven_episode.py first."
        )
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_episode_state(episode_folder: Path, state: dict) -> Path:
    episode_folder = episode_folder.resolve()
    state["updated_at"] = utc_now_iso()
    path = episode_json_path(episode_folder, state.get("name"))
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")
    return path


def step_state(
    steps: dict,
    step_id: str,
    *,
    title: str,
    status: str,
    **extra: object,
) -> dict:
    prior = steps.get(step_id, {})
    step = {"id": step_id, "title": title, "status": status, **extra}
    if status == "completed":
        step["completed_at"] = utc_now_iso()
    elif status == "skipped":
        step["completed_at"] = utc_now_iso()
        step["skipped"] = True
    elif "completed_at" in prior and status not in ("completed", "skipped"):
        step["completed_at"] = prior["completed_at"]
    return step


def raw_wav_candidates(raw_dir: Path) -> list[Path]:
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Raw folder not found: {raw_dir}")
    out: list[Path] = []
    for path in raw_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() != ".wav":
            continue
        if RAW_NAME_RE.search(path.name) is None:
            continue
        out.append(path)
    return sorted(out, key=lambda p: p.name.lower())


def _filter_scope(files: list[Path], *, intro: bool) -> list[Path]:
    scoped: list[Path] = []
    for path in files:
        name = path.name
        if READING_RE.search(name):
            continue
        is_intro = INTRO_RE.search(name) is not None
        if intro and not is_intro:
            continue
        if not intro and is_intro:
            continue
        scoped.append(path)
    return scoped


def find_conversation_wav_pair(raw_dir: Path, *, intro: bool) -> tuple[Path, Path]:
    """Return (ben/host wav, guest/other wav) for main or intro."""
    scoped = _filter_scope(raw_wav_candidates(raw_dir), intro=intro)
    ben_files = [p for p in scoped if BEN_HOST_RE.search(p.name)]
    guest_files = [p for p in scoped if not BEN_HOST_RE.search(p.name)]

    if len(ben_files) != 1:
        scope = "intro" if intro else "main"
        raise FileNotFoundError(
            f"Expected exactly one {scope} Ben/Host audio raw WAV in {raw_dir}, "
            f"found {len(ben_files)}: {[p.name for p in ben_files]}."
        )
    if len(guest_files) != 1:
        scope = "intro" if intro else "main"
        raise FileNotFoundError(
            f"Expected exactly one {scope} Guest (non-Ben/Host) audio raw WAV "
            f"in {raw_dir}, found {len(guest_files)}: {[p.name for p in guest_files]}."
        )
    return ben_files[0], guest_files[0]


def has_intro_audio_pair(raw_dir: Path) -> bool:
    try:
        find_conversation_wav_pair(raw_dir, intro=True)
        return True
    except FileNotFoundError:
        return False


def combined_audio_output_name(wav1: Path) -> str:
    first_word = wav1.stem.split()[0] if wav1.stem.split() else wav1.stem
    return f"{first_word} Combined Audio.wav"


def read_elevenlabs_api_key() -> str:
    if not ELEVENLABS_KEY_FILE.is_file():
        raise FileNotFoundError(f"Missing API key file: {ELEVENLABS_KEY_FILE}")
    key = ELEVENLABS_KEY_FILE.read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError(f"API key file is empty: {ELEVENLABS_KEY_FILE}")
    return key


def next_segment_id() -> str:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    ids = [int(m.group(1)) for m in re.finditer(r"'(\d+)':\s*\{", text)]
    if not ids:
        raise RuntimeError("Could not find segment IDs in config.py")
    return str(max(ids) + 1)


def register_segment(segment_id: str, entry: dict, *, comment: str) -> None:
    """Append a segment entry to SEGMENT_CONFIG in config.py."""
    lines = [
        f"    # {comment}",
        f"    '{segment_id}': {{",
        f"        'audio_file': r'{entry['audio_file']}',",
        f"        'audio_offset': {entry.get('audio_offset', 0)},",
    ]
    if entry.get("use_video_embedded_audio"):
        lines.append("        'use_video_embedded_audio': True,")
    if entry.get("enable_color_match"):
        lines.append("        'enable_color_match': True,")
    else:
        lines.append("        'enable_color_match': False,")
    lines.append("        'video_files': {")
    for cam_key, cam in entry["video_files"].items():
        lines.append(f"            '{cam_key}': {{")
        lines.append(f"                'file': r'{cam['file']}',")
        lines.append(f"                'offset': {cam.get('offset', 0)},")
        lines.append("            },")
    lines.append("        },")
    lines.append(f"        'transcript_file': r'{entry['transcript_file']}',")
    lines.append("    },")
    block = "\n".join(lines) + "\n"
    text = CONFIG_PATH.read_text(encoding="utf-8")
    marker = "\n\n# Normalize media/transcript paths"
    if marker not in text:
        raise RuntimeError("config.py missing normalize marker")
    if f"'{segment_id}':" in text:
        raise ValueError(f"Segment {segment_id} already exists in config.py")
    pos = text.rfind(marker)
    prefix = text[:pos].rstrip()
    suffix = text[pos:]
    if not prefix.endswith("}"):
        raise RuntimeError("Could not find SEGMENT_CONFIG closing brace before normalize marker")
    prefix = prefix[:-1].rstrip()
    if not prefix.endswith(","):
        prefix = prefix + ","
    CONFIG_PATH.write_text(prefix + "\n" + block + "}\n" + suffix, encoding="utf-8")


def find_clean_audio_files(
    raw_dir: Path,
    *,
    main_combined: Path | None,
    intro_combined: Path | None,
) -> dict[str, Path]:
    """Step 8: locate user-exported DeRoom WAVs newer than combined outputs."""
    results: dict[str, Path] = {}
    wavs = [p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() == ".wav"]

    def pick(scope: str, reference: Path) -> Path:
        ref_mtime = reference.stat().st_mtime
        candidates: list[Path] = []
        for path in wavs:
            if CLEAN_RE.search(path.name) is None:
                continue
            if path.stat().st_mtime <= ref_mtime:
                continue
            name = path.name
            is_intro = INTRO_RE.search(name) is not None
            is_reading = READING_RE.search(name) is not None
            if scope == "main":
                if is_intro or is_reading:
                    continue
            elif scope == "intro":
                if not is_intro or is_reading:
                    continue
            else:
                raise ValueError(scope)
            candidates.append(path)
        if not candidates:
            raise FileNotFoundError(
                f"No clean audio in {raw_dir} for {scope} "
                f"(newer than {reference.name})."
            )
        return max(candidates, key=lambda p: p.stat().st_mtime)

    if main_combined and main_combined.is_file():
        results["main_clean_audio"] = pick("main", main_combined)
    if intro_combined and intro_combined.is_file():
        results["intro_clean_audio"] = pick("intro", intro_combined)
    return results


def podcast_swap_speaker_ids_cli_args(state: dict) -> list[str]:
    """CLI args for convert_transcript_json.py --swap-speaker-ids."""
    if state.get("swap_speaker_ids"):
        return ["--swap-speaker-ids"]
    return []


def reading_keep_rows_cli_args(state: dict) -> list[str]:
    """CLI args for generate_reading_dsl.py --keep-rows from episode state."""
    rows = state.get("reading_keep_rows")
    if not rows:
        return []
    return ["--keep-rows", ",".join(str(int(r)) for r in rows)]


def should_skip_reading(state: dict) -> bool:
    return bool(state.get("skip_reading"))


def intro_steps_active(state: dict) -> bool:
    step6 = state.get("steps", {}).get("06_intro_conversation_sync", {})
    return step6.get("status") == "completed"


def run_conversation_sync(wav1: Path, wav2: Path) -> Path:
    if not SYNC_SCRIPT.is_file():
        raise FileNotFoundError(f"Missing sync script: {SYNC_SCRIPT}")
    cmd = [sys.executable, str(SYNC_SCRIPT), str(wav1), str(wav2)]
    proc = _run_hidden(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "conversation-sync failed.\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    output = wav1.parent / combined_audio_output_name(wav1)
    if not output.is_file():
        raise FileNotFoundError(
            f"Expected combined output missing after sync: {output}"
        )
    return output
