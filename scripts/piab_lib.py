"""Shared helpers for Lighthaven Podcast In A Box."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from harness_episode_lib import (
    PIAB_STATE_FILENAME,
    SUBFOLDERS,
    load_episode_state,
    save_episode_state,
    step_state,
    utc_now_iso,
)

DEFAULT_SCAN_ROOT = Path(r"E:\PodcastRoom")

VIDEO_NAME_RE = re.compile(
    r"^MultiCorder\d+\s*-\s*DeckLink Quad HDMI Recorder",
    re.IGNORECASE,
)
AUDIO_NAME_RE = re.compile(
    r"^MultiCorder\d+\s*-\s*Output\s+\d+",
    re.IGNORECASE,
)

HOST_RAW_VIDEO = "Host Raw Video.mp4"
GUEST_RAW_VIDEO = "Guest Raw Video.mp4"
WIDE_RAW_VIDEO = "Wide Raw Video.mp4"
HOST_RAW_AUDIO = "Host Raw Audio.wav"
GUEST_RAW_AUDIO = "Guest Raw Audio.wav"

VIDEO_ROLES = ("host", "guest", "wide", "do_not_use")
AUDIO_ROLES = ("host", "guest", "do_not_use")

# Coarse realtime multipliers for Estimate A/B (wall-clock vs source duration).
EST_CONVERSATION_SYNC_X = 0.08
EST_VIDEO_SYNC_X = 2.5  # three cameras + multicam re-encode
EST_TRANSCRIBE_X = 0.15
EST_ONE_MIN_RENDER_SEC = 12 * 60
# Parallel podcast_dsl cut/assemble from prepped media. BayesVishal (2026-07-16)
# finished at ~0.41×; 0.5× keeps a small cushion on this machine.
EST_FULL_RENDER_X = 0.5
EST_PAD_FRACTION = 0.25  # widen into a range


@dataclass
class MediaInfo:
    path: str
    name: str
    kind: str  # "video" | "audio"
    mtime: float
    mtime_iso: str
    duration_sec: float

    @property
    def path_obj(self) -> Path:
        return Path(self.path)


def ffprobe_duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}:\n{proc.stderr.strip()}")
    text = (proc.stdout or "").strip()
    if not text:
        raise RuntimeError(f"ffprobe returned no duration for {path}")
    return float(text)


def classify_multicorder(path: Path) -> str | None:
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    if suffix == ".mp4" and VIDEO_NAME_RE.search(path.name):
        return "video"
    if suffix == ".wav" and AUDIO_NAME_RE.search(path.name):
        return "audio"
    return None


def list_top_level_multicorder(
    root: Path,
    *,
    skipped: list[dict] | None = None,
) -> list[MediaInfo]:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Scan root not found: {root}")
    out: list[MediaInfo] = []
    for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        kind = classify_multicorder(path)
        if kind is None:
            continue
        size = path.stat().st_size
        if size <= 0:
            if skipped is not None:
                skipped.append(
                    {
                        "path": str(path),
                        "name": path.name,
                        "kind": kind,
                        "reason": "empty file (0 bytes)",
                    }
                )
            continue
        try:
            duration = ffprobe_duration(path)
        except RuntimeError as exc:
            if skipped is not None:
                skipped.append(
                    {
                        "path": str(path),
                        "name": path.name,
                        "kind": kind,
                        "reason": str(exc).split("\n", 1)[0],
                    }
                )
            continue
        mtime = path.stat().st_mtime
        out.append(
            MediaInfo(
                path=str(path),
                name=path.name,
                kind=kind,
                mtime=mtime,
                mtime_iso=datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
                duration_sec=round(duration, 3),
            )
        )
    return out


def cluster_session_files(
    files: list[MediaInfo],
    *,
    mtime_tol_sec: float = 60.0,
    duration_tol_sec: float = 2.0,
) -> list[MediaInfo]:
    """
    Return the most recent session cluster.

    A cluster is the connected set of files around the newest mtime where each
    included file is within ``mtime_tol_sec`` of some member, and all durations
    are within ``duration_tol_sec`` of the cluster median duration.
    """
    if not files:
        raise FileNotFoundError("No MultiCorder video/audio files found.")

    by_mtime = sorted(files, key=lambda f: f.mtime, reverse=True)
    seed = by_mtime[0]
    cluster = [seed]
    changed = True
    while changed:
        changed = False
        members = {f.path for f in cluster}
        for cand in by_mtime:
            if cand.path in members:
                continue
            if any(abs(cand.mtime - m.mtime) <= mtime_tol_sec for m in cluster):
                cluster.append(cand)
                changed = True

    durations = sorted(f.duration_sec for f in cluster)
    median = durations[len(durations) // 2]
    filtered = [f for f in cluster if abs(f.duration_sec - median) <= duration_tol_sec]
    if not filtered:
        raise RuntimeError(
            "Session cluster found by mtime but no files share duration within "
            f"{duration_tol_sec}s of median {median:.3f}s."
        )

    # Prefer keeping the densest duration group if filtering emptied videos or audios.
    videos = [f for f in filtered if f.kind == "video"]
    audios = [f for f in filtered if f.kind == "audio"]
    if not videos or not audios:
        raise RuntimeError(
            "Most recent mtime cluster did not contain both MultiCorder videos and "
            f"audio WAVs after duration filter (videos={len(videos)}, audios={len(audios)})."
        )
    return sorted(filtered, key=lambda f: (f.kind, f.name.lower()))


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_eta_range(center_sec: float) -> dict:
    low = max(60.0, center_sec * (1.0 - EST_PAD_FRACTION))
    high = center_sec * (1.0 + EST_PAD_FRACTION)
    return {
        "center_sec": int(round(center_sec)),
        "low_sec": int(round(low)),
        "high_sec": int(round(high)),
        "center_human": format_duration(center_sec),
        "low_human": format_duration(low),
        "high_human": format_duration(high),
        "summary": f"about {format_duration(low)}–{format_duration(high)}",
    }


def estimate_prep_through_one_min(source_duration_sec: float) -> dict:
    center = (
        source_duration_sec * EST_CONVERSATION_SYNC_X
        + source_duration_sec * EST_VIDEO_SYNC_X
        + source_duration_sec * EST_TRANSCRIBE_X
        + EST_ONE_MIN_RENDER_SEC
    )
    detail = {
        "source_duration_sec": source_duration_sec,
        "source_duration_human": format_duration(source_duration_sec),
        "conversation_sync_sec": int(source_duration_sec * EST_CONVERSATION_SYNC_X),
        "video_sync_sec": int(source_duration_sec * EST_VIDEO_SYNC_X),
        "transcribe_sec": int(source_duration_sec * EST_TRANSCRIBE_X),
        "one_min_render_sec": EST_ONE_MIN_RENDER_SEC,
    }
    return {**format_eta_range(center), "breakdown": detail}


def estimate_full_render(source_duration_sec: float) -> dict:
    center = source_duration_sec * EST_FULL_RENDER_X
    return {
        **format_eta_range(center),
        "breakdown": {
            "source_duration_sec": source_duration_sec,
            "source_duration_human": format_duration(source_duration_sec),
            "full_render_x": EST_FULL_RENDER_X,
        },
    }


def new_piab_state(
    working_folder: Path,
    *,
    name: str,
    scan_root: Path,
    session_files: list[MediaInfo],
) -> dict:
    working_folder = working_folder.resolve()
    now = utc_now_iso()
    median_dur = sorted(f.duration_sec for f in session_files)[len(session_files) // 2]
    return {
        "kind": "podcast_in_a_box",
        "name": name,
        "created_at": now,
        "updated_at": now,
        "skip_reading": True,
        "swap_speaker_ids": False,
        "scan_root": str(scan_root.resolve()),
        "source_duration_sec": median_dur,
        "session_files": [asdict(f) for f in session_files],
        "paths": {
            "episode_folder": str(working_folder),
            "raw": str(working_folder / "Raw"),
            "input": str(working_folder / "Input"),
            "output": str(working_folder / "Output"),
            "temp": str(working_folder / "Temp"),
            "previews": str(working_folder / "Temp" / "piab-previews"),
            "state": str(working_folder / PIAB_STATE_FILENAME),
        },
        "labels": {"videos": {}, "audios": {}},
        "original_paths": {},
        "resume_at": "03_label_videos",
        "steps": {},
    }


def ensure_subfolders(working_folder: Path) -> None:
    for sub in SUBFOLDERS:
        (working_folder / sub).mkdir(parents=True, exist_ok=True)
    (working_folder / "Temp" / "piab-previews").mkdir(parents=True, exist_ok=True)


def load_piab_state(working_folder: Path) -> dict:
    state = load_episode_state(working_folder)
    if state.get("kind") != "podcast_in_a_box":
        raise ValueError(
            f"{working_folder} is not a Podcast In A Box session "
            f"(expected {PIAB_STATE_FILENAME} with kind=podcast_in_a_box)."
        )
    return state


def save_piab_state(working_folder: Path, state: dict) -> Path:
    state["kind"] = "podcast_in_a_box"
    return save_episode_state(working_folder, state)


def mark_step(
    state: dict,
    step_id: str,
    *,
    title: str,
    status: str,
    **extra: object,
) -> None:
    steps = state.setdefault("steps", {})
    steps[step_id] = step_state(steps, step_id, title=title, status=status, **extra)


def extract_midpoint_frame(video: Path, out_jpg: Path) -> Path:
    duration = ffprobe_duration(video)
    mid = max(0.0, duration / 2.0)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{mid:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_jpg),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not out_jpg.is_file():
        raise RuntimeError(
            f"ffmpeg frame extract failed for {video}:\n{proc.stderr.strip()}"
        )
    return out_jpg


def _wav_mono_float(path: Path) -> tuple[np.ndarray, int]:
    """Load audio as mono float32 via ffmpeg (handles non-PCM MultiCorder WAVs)."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "wav",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg decode failed for loudness scan of {path}:\n{proc.stderr.strip()}"
            )
        with wave.open(str(tmp_path), "rb") as wf:
            rate = wf.getframerate()
            n_frames = wf.getnframes()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(n_frames)
        if sampwidth == 2:
            data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            raise RuntimeError(f"Unexpected decoded sample width {sampwidth} for {path}")
        return data, rate
    finally:
        tmp_path.unlink(missing_ok=True)


def find_loud_clip_start(
    path: Path,
    *,
    clip_sec: float = 4.0,
    after_fraction: float = 0.25,
    window_sec: float = 0.5,
) -> float:
    """Return start time (sec) of a loud clip_sec window after after_fraction of the file."""
    audio, rate = _wav_mono_float(path)
    n = len(audio)
    if n < rate:
        return 0.0
    start_idx = int(n * after_fraction)
    clip_samples = int(clip_sec * rate)
    win = max(1, int(window_sec * rate))
    if start_idx + clip_samples >= n:
        return max(0.0, (n - clip_samples) / rate)

    search = audio[start_idx:]
    # RMS over hopping windows; pick loudest window whose clip fits.
    best_local = 0
    best_rms = -1.0
    hop = win // 2 or 1
    max_local = len(search) - clip_samples
    for i in range(0, max(1, max_local + 1), hop):
        seg = search[i : i + win]
        if len(seg) < win // 2:
            break
        rms = float(np.sqrt(np.mean(np.square(seg))))
        if rms > best_rms:
            best_rms = rms
            best_local = i
    # Center-ish: start a bit before the loud window so speech is in the clip.
    start = start_idx + best_local
    start = max(start_idx, min(start, n - clip_samples))
    return start / rate


def extract_audio_clip(
    wav: Path,
    out_wav: Path,
    *,
    start_sec: float,
    duration_sec: float = 4.0,
) -> Path:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(wav),
            "-ac",
            "1",
            str(out_wav),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not out_wav.is_file():
        raise RuntimeError(
            f"ffmpeg audio clip failed for {wav}:\n{proc.stderr.strip()}"
        )
    return out_wav


def role_to_video_name(role: str) -> str:
    mapping = {
        "host": HOST_RAW_VIDEO,
        "guest": GUEST_RAW_VIDEO,
        "wide": WIDE_RAW_VIDEO,
    }
    if role not in mapping:
        raise ValueError(f"Video role {role!r} has no destination filename.")
    return mapping[role]


def role_to_audio_name(role: str) -> str:
    mapping = {"host": HOST_RAW_AUDIO, "guest": GUEST_RAW_AUDIO}
    if role not in mapping:
        raise ValueError(f"Audio role {role!r} has no destination filename.")
    return mapping[role]


def validate_video_labels(labels: dict[str, str]) -> None:
    roles = list(labels.values())
    for required in ("host", "guest", "wide"):
        if roles.count(required) != 1:
            raise ValueError(
                f"Expected exactly one video labeled {required!r}, "
                f"got {roles.count(required)} in {labels}"
            )
    for role in roles:
        if role not in VIDEO_ROLES:
            raise ValueError(f"Invalid video role {role!r}")


def validate_audio_labels(labels: dict[str, str]) -> None:
    roles = list(labels.values())
    for required in ("host", "guest"):
        if roles.count(required) != 1:
            raise ValueError(
                f"Expected exactly one audio labeled {required!r}, "
                f"got {roles.count(required)} in {labels}"
            )
    for role in roles:
        if role not in AUDIO_ROLES:
            raise ValueError(f"Invalid audio role {role!r}")


def move_labeled_media(
    state: dict,
    *,
    video_labels: dict[str, str],
    audio_labels: dict[str, str],
    allow_overwrite: bool = False,
) -> dict:
    """Move labeled sources into Raw with standard names. Keys are source paths."""
    from harness_overwrite_guard import refuse_overwrite

    validate_video_labels(video_labels)
    validate_audio_labels(audio_labels)
    raw = Path(state["paths"]["raw"])
    raw.mkdir(parents=True, exist_ok=True)
    original_paths: dict[str, str] = {}
    moved: dict[str, str] = {}

    for src_str, role in video_labels.items():
        if role == "do_not_use":
            continue
        src = Path(src_str)
        if not src.is_file():
            raise FileNotFoundError(f"Labeled video missing: {src}")
        dest = raw / role_to_video_name(role)
        refuse_overwrite(dest, allow_overwrite=allow_overwrite)
        if dest.exists():
            dest.unlink()
        shutil.move(str(src), str(dest))
        original_paths[dest.name] = str(src)
        moved[role] = str(dest)

    for src_str, role in audio_labels.items():
        if role == "do_not_use":
            continue
        src = Path(src_str)
        if not src.is_file():
            raise FileNotFoundError(f"Labeled audio missing: {src}")
        dest = raw / role_to_audio_name(role)
        refuse_overwrite(dest, allow_overwrite=allow_overwrite)
        if dest.exists():
            dest.unlink()
        shutil.move(str(src), str(dest))
        original_paths[dest.name] = str(src)
        moved[role + "_audio"] = str(dest)

    state["labels"] = {
        "videos": {Path(k).name: v for k, v in video_labels.items()},
        "audios": {Path(k).name: v for k, v in audio_labels.items()},
    }
    state["original_paths"] = original_paths
    state["moved_raw"] = moved
    return state


def swap_host_guest_files(raw_dir: Path, *, kind: str) -> list[str]:
    """Swap Host/Guest Raw Video or Audio filenames in place. kind: video|audio|both."""
    actions: list[str] = []
    pairs: list[tuple[str, str]] = []
    if kind in ("video", "both"):
        pairs.append((HOST_RAW_VIDEO, GUEST_RAW_VIDEO))
    if kind in ("audio", "both"):
        pairs.append((HOST_RAW_AUDIO, GUEST_RAW_AUDIO))
    for a_name, b_name in pairs:
        a = raw_dir / a_name
        b = raw_dir / b_name
        if not a.is_file() or not b.is_file():
            raise FileNotFoundError(f"Cannot swap; missing {a.name} or {b.name} in {raw_dir}")
        tmp = raw_dir / f".piab-swap-tmp-{a_name}"
        if tmp.exists():
            tmp.unlink()
        a.rename(tmp)
        b.rename(a)
        tmp.rename(b)
        actions.append(f"swapped {a_name} <-> {b_name}")
    return actions


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2))
