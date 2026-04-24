#!/usr/bin/env python3
"""
Render one corrected file per target video by matching each target to a reference video.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from podcast_dsl.color_match import (
    build_color_match_vf,
    ffmpeg_cmd_base,
    probe_mean_signalstats_multi,
)
from podcast_dsl.video_renderer import _map_encoder_preset


COLOR_MATCH_SAMPLE_OFFSETS = (0.0, 1 / 3, 2 / 3)
DEFAULT_COLOR_MATCH_STRENGTH = 2.1
DEFAULT_VIDEO_ENCODER = 'auto'
# Match podcast_dsl clip-stage rendering: ultrafast + quality 23 (CRF/CQ/QVBR level).
DEFAULT_VIDEO_PRESET = 'ultrafast'
DEFAULT_VIDEO_QUALITY = 23
FOUR_K_WIDTH = 3840
FOUR_K_HEIGHT = 2160
DOWNSCALE_WIDTH_1080P = 1920
DOWNSCALE_HEIGHT_1080P = 1080
STANDALONE_MATCH_LIMITS = {
    'max_abs_d': 0.45,
    'gamma_scale': 1.1,
    'brightness_scale': 1.3,
    'gamma_min': 0.93,
    'gamma_max': 1.18,
    'brightness_min': -0.05,
    'brightness_max': 0.08,
    'saturation_scale': 1.0,
    'saturation_min': 0.93,
    'saturation_max': 1.24,
    'vibrance_scale': 0.72,
    'vibrance_max': 0.55,
    'chroma_strength': 2.3,
    'chroma_scale': 1.25,
    'chroma_midtone_max': 0.10,
}

VIDEO_ENCODER_CHOICES = ('auto', 'libx264', 'h264_nvenc', 'h264_qsv', 'h264_amf')
AUTO_HARDWARE_ENCODERS = ('h264_nvenc', 'h264_qsv', 'h264_amf')
ENCODER_TEST_WIDTH = 1280
ENCODER_TEST_HEIGHT = 720
# Equal temporal splits for optional parallel chunk renders.
MAX_TIME_CHUNKS = 32
MIN_CHUNK_DURATION_SEC = 1.0
CONCAT_DURATION_TOLERANCE_SEC = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render color-matched outputs for up to four target videos using one "
            "reference video as the analysis source."
        )
    )
    parser.add_argument(
        "--reference",
        required=True,
        help="Reference video file used only for analysis",
    )
    parser.add_argument(
        "--target",
        dest="targets",
        action="append",
        required=True,
        help="Target video to render; repeat up to four times",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        required=True,
        help="Directory where corrected output files will be written",
    )
    parser.add_argument(
        "--suffix",
        default="-colorcorr",
        help='Suffix inserted before the file extension (default: "-colorcorr")',
    )
    parser.add_argument(
        "--sample-seconds",
        type=float,
        default=8.0,
        help="Seconds to sample from the start of each file for analysis (default: 8.0)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=240,
        help="Maximum frames to analyze per file (default: 240)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print computed filter info without rendering outputs",
    )
    parser.add_argument(
        "--strength",
        type=float,
        default=DEFAULT_COLOR_MATCH_STRENGTH,
        help=(
            "Scale the correction intensity for standalone renders "
            f"(default: {DEFAULT_COLOR_MATCH_STRENGTH})"
        ),
    )
    parser.add_argument(
        "--video-encoder",
        choices=VIDEO_ENCODER_CHOICES,
        default=DEFAULT_VIDEO_ENCODER,
        help=(
            "Video encoder for filtered renders. Hardware encoders require local "
            f"FFmpeg/driver support (default: {DEFAULT_VIDEO_ENCODER})"
        ),
    )
    parser.add_argument(
        "--video-preset",
        default=DEFAULT_VIDEO_PRESET,
        help=(
            "Preset for the selected video encoder. For libx264 this is the x264 "
            f"preset (default: {DEFAULT_VIDEO_PRESET}). "
            "Hardware encoders map this name the same way as podcast_dsl."
        ),
    )
    parser.add_argument(
        "--video-quality",
        type=int,
        default=DEFAULT_VIDEO_QUALITY,
        metavar="N",
        help=(
            "Quality level for the video encoder: libx264 CRF, NVENC CQ, QSV "
            f"global_quality, AMF qvbr_quality_level (default: {DEFAULT_VIDEO_QUALITY}; "
            "matches podcast_dsl clip renders)."
        ),
    )
    parser.add_argument(
        "--downscale-4k-to-1080p",
        action="store_true",
        help="Downscale 4K targets to 1920x1080 before encoding",
    )
    parser.add_argument(
        "--downscale-target",
        dest="downscale_targets",
        action="append",
        default=[],
        help=(
            "Explicitly downscale this target to 1920x1080. Repeat as needed; "
            "accepts either the target path or filename."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Run up to N targets in parallel (separate probe/analysis and ffmpeg "
            "renders per target). Default: number of --target files (all targets in "
            "parallel). Effective concurrency is capped at the number of --target files."
        ),
    )
    parser.add_argument(
        "--time-chunks",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Split each filtered render into N equal-duration time segments, encode "
            "segments in parallel (see --chunk-workers), then concat. Default: 1 "
            "(disabled). Requires a non-empty color filter (not passthrough copy). "
            "Uses accurate post-input seeking, AAC per chunk, concat copy with "
            "re-encode fallback + validation."
        ),
    )
    parser.add_argument(
        "--chunk-workers",
        type=int,
        default=4,
        metavar="N",
        help=(
            "Max parallel segment encodes per target when --time-chunks > 1. "
            "Capped at --time-chunks. Default: 4."
        ),
    )
    return parser.parse_args()


def build_output_path(target_file: Path, output_dir: Path, suffix: str) -> Path:
    return output_dir / f"{target_file.stem}{suffix}{target_file.suffix}"


def validate_inputs(reference: Path, targets: list[Path], output_dir: Path) -> None:
    if not reference.is_file():
        raise FileNotFoundError(f"Reference file not found: {reference}")
    if not targets:
        raise ValueError("At least one --target must be provided")
    if len(targets) > 4:
        raise ValueError("A maximum of four --target files is supported")
    for target in targets:
        if not target.is_file():
            raise FileNotFoundError(f"Target file not found: {target}")
    output_dir.mkdir(parents=True, exist_ok=True)


def _summarize_stderr(stderr_text: str, max_lines: int = 20) -> str:
    lines = [line.rstrip() for line in (stderr_text or "").splitlines() if line.strip()]
    if not lines:
        return "(no stderr output)"
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines] + ["...", f"[truncated {len(lines) - max_lines} more lines]"])


def _validate_video_output(output_path: Path) -> None:
    if not output_path.exists():
        raise RuntimeError(f"Expected output file was not created: {output_path}")
    if output_path.stat().st_size <= 0:
        raise RuntimeError(f"Output file is empty: {output_path}")

    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,pix_fmt,width,height",
        "-of",
        "json",
        str(output_path),
    ]
    probe_result = subprocess.run(probe_cmd, check=False, text=True, capture_output=True)
    if probe_result.returncode != 0:
        raise RuntimeError(
            f"ffprobe could not inspect video stream for {output_path}:\n"
            f"{_summarize_stderr(probe_result.stderr)}"
        )

    info = json.loads(probe_result.stdout or "{}")
    streams = info.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {output_path}")

    pix_fmt = str(streams[0].get("pix_fmt") or "").strip().lower()
    if not pix_fmt or pix_fmt == "unknown":
        raise RuntimeError(
            f"Video stream in {output_path} has an invalid pixel format: {streams[0].get('pix_fmt')!r}"
        )

    decode_cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(output_path),
        "-map",
        "0:v:0",
        "-frames:v",
        "1",
        "-f",
        "null",
        "-",
    ]
    decode_result = subprocess.run(decode_cmd, check=False, text=True, capture_output=True)
    if decode_result.returncode != 0:
        raise RuntimeError(
            f"Video stream decode validation failed for {output_path}:\n"
            f"{_summarize_stderr(decode_result.stderr)}"
        )


def _probe_format_duration_seconds(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe could not read duration for {path}:\n{_summarize_stderr(result.stderr)}"
        )
    raw = (result.stdout or "").strip()
    if not raw or raw == "N/A":
        raise RuntimeError(f"ffprobe returned no duration for {path}")
    try:
        duration = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid duration from ffprobe for {path}: {raw!r}") from exc
    if duration <= 0:
        raise RuntimeError(f"Non-positive duration for {path}: {duration}")
    return duration


def _even_time_chunk_spans(total_seconds: float, num_chunks: int) -> list[tuple[float, float]]:
    """Return (start, duration) for each chunk; covers [0, total_seconds) without gaps."""
    if num_chunks < 1:
        raise ValueError("num_chunks must be >= 1")
    spans: list[tuple[float, float]] = []
    for i in range(num_chunks):
        start = total_seconds * i / num_chunks
        if i == num_chunks - 1:
            duration = max(0.0, total_seconds - start)
        else:
            end = total_seconds * (i + 1) / num_chunks
            duration = max(0.0, end - start)
        spans.append((start, duration))
    return spans


def _path_for_concat_demuxer_line(path: Path) -> str:
    """Single-quoted path for ffconcat `file` directive (POSIX slashes, escape quotes)."""
    posix = path.resolve().as_posix()
    return posix.replace("'", "'\\''")


def _write_concat_demuxer_list(chunk_paths: list[Path], *, output_dir: Path) -> Path:
    fd, raw_name = tempfile.mkstemp(
        suffix=".ffconcat",
        prefix="color_match_concat_",
        dir=str(output_dir),
    )
    list_path = Path(raw_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("ffconcat version 1.0\n")
            for chunk in chunk_paths:
                handle.write(f"file '{_path_for_concat_demuxer_line(chunk)}'\n")
    except Exception:
        list_path.unlink(missing_ok=True)
        raise
    return list_path


def _ffmpeg_concat_stream_copy(list_path: Path, out_path: Path) -> subprocess.CompletedProcess:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(out_path),
    ]
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def _ffmpeg_concat_reencode(
    list_path: Path,
    out_path: Path,
    *,
    video_encoder: str,
    video_preset: str,
    video_quality: int,
) -> subprocess.CompletedProcess:
    cmd = ffmpeg_cmd_base() + [
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:a",
        "aac",
        "-b:a",
        "320k",
        "-aac_coder",
        "twoloop",
        "-movflags",
        "+faststart",
    ]
    _append_encoder_args(cmd, video_encoder, video_preset, video_quality)
    cmd.extend(
        [
            "-pix_fmt",
            "yuv420p",
            "-profile:v",
            "high",
            str(out_path),
        ]
    )
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def _duration_close_enough(actual: float, expected: float, tol: float) -> bool:
    return abs(actual - expected) <= tol


def _render_target_time_chunked(
    target: Path,
    output_path: Path,
    vf: str,
    video_settings: dict,
    *,
    video_encoder: str,
    video_preset: str,
    video_quality: int,
    apply_1080p_downscale: bool,
    time_chunks: int,
    chunk_workers: int,
) -> None:
    if not vf:
        raise ValueError(
            "Time-chunked rendering requires a non-empty color filter. "
            "Use a single pass (default) for passthrough copy."
        )

    total_duration = _probe_format_duration_seconds(target)
    spans = _even_time_chunk_spans(total_duration, time_chunks)
    if any(duration < MIN_CHUNK_DURATION_SEC for _, duration in spans):
        raise ValueError(
            f"Each time chunk must be at least {MIN_CHUNK_DURATION_SEC}s "
            f"(file ~{total_duration:.2f}s with {time_chunks} chunks). "
            "Lower --time-chunks."
        )

    output_filter = _build_output_filter(
        vf,
        video_settings,
        apply_1080p_downscale=apply_1080p_downscale,
    )

    chunk_paths = [
        output_path.with_name(f"{output_path.stem}._chunk{i:02d}.part{output_path.suffix}")
        for i in range(time_chunks)
    ]
    for path in chunk_paths:
        path.unlink(missing_ok=True)

    def encode_chunk(args: tuple[int, float, float, Path]) -> None:
        index, start_sec, duration_sec, chunk_out = args
        cmd = ffmpeg_cmd_base() + ["-i", str(target)]
        # Accurate trim: -ss after -i (slower than fast seek but aligns chunk boundaries).
        if start_sec > 0.0:
            cmd.extend(["-ss", f"{start_sec:.6f}"])
        cmd.extend(["-t", f"{duration_sec:.6f}"])
        cmd.extend(
            [
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-map_metadata",
                "0",
                "-fps_mode",
                "passthrough",
                "-vf",
                output_filter,
            ]
        )
        _append_encoder_args(cmd, video_encoder, video_preset, video_quality)
        cmd.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-profile:v",
                "high",
                "-movflags",
                "+faststart",
                # Fresh AAC per chunk avoids concat demuxer issues with stream-copy splits.
                "-c:a",
                "aac",
                "-b:a",
                "320k",
                "-aac_coder",
                "twoloop",
            ]
        )
        for ffmpeg_key, probe_key in (
            ("-color_range", "color_range"),
            ("-colorspace", "color_space"),
            ("-color_trc", "color_transfer"),
            ("-color_primaries", "color_primaries"),
        ):
            value = video_settings.get(probe_key)
            if value and value != "unknown":
                cmd.extend([ffmpeg_key, value])
        cmd.append(str(chunk_out))

        result = subprocess.run(cmd, check=False, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed for time chunk {index + 1}/{time_chunks} of {target}:\n"
                f"{result.stderr.strip()}"
            )
        _validate_video_output(chunk_out)

    pool = max(1, min(chunk_workers, time_chunks))
    chunk_errors: list[tuple[int, Exception]] = []
    concat_tmp = output_path.with_name(f"{output_path.stem}._concattmp{output_path.suffix}")
    concat_tmp.unlink(missing_ok=True)
    list_path: Path | None = None
    try:
        with ThreadPoolExecutor(max_workers=pool) as executor:
            future_to_index = {
                executor.submit(
                    encode_chunk,
                    (idx, start_sec, duration_sec, chunk_paths[idx]),
                ): idx
                for idx, (start_sec, duration_sec) in enumerate(spans)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    future.result()
                except Exception as exc:
                    chunk_errors.append((idx, exc))

        if chunk_errors:
            chunk_errors.sort(key=lambda item: item[0])
            lines = "\n".join(
                f"  chunk #{idx + 1}: {exc}" for idx, exc in chunk_errors
            )
            raise RuntimeError(
                f"Time-chunk encode failed for {target}:\n{lines}"
            ) from chunk_errors[0][1]

        list_path = _write_concat_demuxer_list(chunk_paths, output_dir=output_path.parent)

        try:
            copy_result = _ffmpeg_concat_stream_copy(list_path, concat_tmp)
            copy_ok = (
                copy_result.returncode == 0
                and concat_tmp.exists()
                and concat_tmp.stat().st_size > 0
            )
            if copy_ok:
                try:
                    _validate_video_output(concat_tmp)
                    out_dur = _probe_format_duration_seconds(concat_tmp)
                    if not _duration_close_enough(
                        out_dur,
                        total_duration,
                        CONCAT_DURATION_TOLERANCE_SEC,
                    ):
                        copy_ok = False
                except Exception:
                    copy_ok = False
            if not copy_ok:
                if concat_tmp.exists():
                    concat_tmp.unlink(missing_ok=True)
                reenc = _ffmpeg_concat_reencode(
                    list_path,
                    concat_tmp,
                    video_encoder=video_encoder,
                    video_preset=video_preset,
                    video_quality=video_quality,
                )
                if reenc.returncode != 0:
                    raise RuntimeError(
                        "Concat re-encode failed after stream-copy concat was not usable:\n"
                        f"{reenc.stderr.strip()}"
                    )
                _validate_video_output(concat_tmp)
                out_dur = _probe_format_duration_seconds(concat_tmp)
                if not _duration_close_enough(
                    out_dur,
                    total_duration,
                    CONCAT_DURATION_TOLERANCE_SEC,
                ):
                    raise RuntimeError(
                        f"Concat output duration {out_dur:.3f}s differs from source "
                        f"{total_duration:.3f}s beyond {CONCAT_DURATION_TOLERANCE_SEC}s tolerance."
                    )

            if output_path.exists():
                output_path.unlink()
            concat_tmp.replace(output_path)
        finally:
            if list_path is not None:
                list_path.unlink(missing_ok=True)
    finally:
        for path in chunk_paths:
            path.unlink(missing_ok=True)
        if concat_tmp.exists():
            concat_tmp.unlink(missing_ok=True)


def _normalized_selector(value: str) -> str:
    return value.strip().lower()


def _target_matches_selector(target: Path, selector: str) -> bool:
    normalized = _normalized_selector(selector)
    return normalized in {
        str(target).lower(),
        target.name.lower(),
    }


def validate_downscale_targets(targets: list[Path], downscale_targets: list[str]) -> None:
    unmatched = [
        selector
        for selector in downscale_targets
        if not any(_target_matches_selector(target, selector) for target in targets)
    ]
    if unmatched:
        quoted = ", ".join(unmatched)
        raise ValueError(
            "Each --downscale-target must match one of the provided targets "
            f"by full path or filename. Unmatched: {quoted}"
        )


def probe_video_settings(target: Path) -> dict:
    """Read the primary video-stream settings we want to preserve where safe."""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries',
        (
            'stream=codec_name,profile,pix_fmt,width,height,avg_frame_rate,'
            'sample_aspect_ratio,color_range,color_space,color_transfer,color_primaries'
        ),
        '-of', 'json',
        str(target),
    ]
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    info = json.loads(result.stdout)
    streams = info.get('streams', [])
    if not streams:
        raise RuntimeError(f"No video stream found in {target}")
    return streams[0]


def _format_frame_rate(frame_rate: str) -> str:
    if not frame_rate or frame_rate in {'0/0', 'N/A'}:
        return 'unknown fps'
    num_str, den_str = frame_rate.split('/', 1)
    num = float(num_str)
    den = float(den_str)
    if den == 0:
        return 'unknown fps'
    return f"{num / den:.3f} fps"


def _is_4k_or_higher(video_settings: dict) -> bool:
    width = int(video_settings.get('width', 0) or 0)
    height = int(video_settings.get('height', 0) or 0)
    return width >= FOUR_K_WIDTH or height >= FOUR_K_HEIGHT


def _is_above_1080p(video_settings: dict) -> bool:
    width = int(video_settings.get('width', 0) or 0)
    height = int(video_settings.get('height', 0) or 0)
    return width > DOWNSCALE_WIDTH_1080P or height > DOWNSCALE_HEIGHT_1080P


def _should_downscale_target(
    target: Path,
    video_settings: dict,
    *,
    auto_downscale_4k_to_1080p: bool,
    explicit_downscale_targets: list[str],
) -> bool:
    if not _is_above_1080p(video_settings):
        return False
    if any(_target_matches_selector(target, selector) for selector in explicit_downscale_targets):
        return True
    return auto_downscale_4k_to_1080p and _is_4k_or_higher(video_settings)


def _scale_pad_1080p_vf() -> str:
    """Scale + pad + setsar=1 for 1080p deliverable (shared by analysis prefix and render)."""
    return (
        f"scale={DOWNSCALE_WIDTH_1080P}:{DOWNSCALE_HEIGHT_1080P}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={DOWNSCALE_WIDTH_1080P}:{DOWNSCALE_HEIGHT_1080P}:(ow-iw)/2:(oh-ih)/2:black,"
        "setsar=1"
    )


def _build_output_filter(vf: str, video_settings: dict, *, apply_1080p_downscale: bool) -> str:
    # Downscale first, then color correction, so filter work runs at 1080p when enabled.
    filters: list[str] = []
    if apply_1080p_downscale:
        filters.append(_scale_pad_1080p_vf())
    filters.append(vf)
    if not apply_1080p_downscale:
        sar = video_settings.get('sample_aspect_ratio')
        if sar and sar not in {'0:1', '1:1', 'N/A'}:
            filters.append(f"setsar={sar.replace(':', '/')}")
    return ",".join(filters)


def _append_encoder_args(
    cmd: list[str],
    video_encoder: str,
    video_preset: str,
    video_quality: int,
) -> None:
    mapped_preset = _map_encoder_preset(video_encoder, video_preset)
    q = str(int(video_quality))

    if video_encoder == 'libx264':
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', mapped_preset,
            '-crf', q,
        ])
        return

    if video_encoder == 'h264_nvenc':
        cmd.extend([
            '-c:v', 'h264_nvenc',
            '-preset', mapped_preset,
            '-tune', 'hq',
            '-rc', 'vbr',
            '-cq', q,
            '-b:v', '0',
        ])
        return

    if video_encoder == 'h264_qsv':
        cmd.extend([
            '-c:v', 'h264_qsv',
            '-preset', mapped_preset,
            '-global_quality', q,
        ])
        return

    if video_encoder == 'h264_amf':
        cmd.extend([
            '-c:v', 'h264_amf',
            '-preset', mapped_preset,
            '-rc', 'qvbr',
            '-qvbr_quality_level', q,
        ])
        return

    raise ValueError(f"Unsupported video encoder: {video_encoder}")


def _encoder_test_command(
    output_path: str,
    video_encoder: str,
    video_preset: str,
    video_quality: int,
) -> list[str]:
    cmd = ffmpeg_cmd_base() + [
        '-f', 'lavfi',
        '-i', f'color=c=black:s={ENCODER_TEST_WIDTH}x{ENCODER_TEST_HEIGHT}:r=24000/1001:d=0.1',
        '-frames:v', '1',
    ]
    _append_encoder_args(cmd, video_encoder, video_preset, video_quality)
    cmd.extend([
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'high',
        '-an',
        output_path,
    ])
    return cmd


def _encoder_is_usable(video_encoder: str, video_preset: str, video_quality: int) -> bool:
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        temp_path = tmp.name
    try:
        Path(temp_path).unlink(missing_ok=True)
        cmd = _encoder_test_command(temp_path, video_encoder, video_preset, video_quality)
        result = subprocess.run(cmd, check=False, text=True, capture_output=True)
        return result.returncode == 0 and Path(temp_path).exists() and Path(temp_path).stat().st_size > 0
    finally:
        Path(temp_path).unlink(missing_ok=True)


def resolve_video_encoder(
    video_encoder: str,
    video_preset: str,
    video_quality: int,
) -> str:
    if video_encoder != 'auto':
        return video_encoder

    for candidate in AUTO_HARDWARE_ENCODERS:
        if _encoder_is_usable(candidate, video_preset, video_quality):
            return candidate
    return 'libx264'


@dataclass(frozen=True)
class TargetRenderPlan:
    """Per-target probe, analysis, and paths (used for parallel prep + render)."""

    index: int
    total: int
    target: Path
    output_path: Path
    video_settings: dict
    apply_1080p_downscale: bool
    reference_stats: tuple[float, float, float]
    target_stats: tuple[float, float, float]
    vf: str


def _prepare_target_job(
    index: int,
    total: int,
    target: Path,
    reference: Path,
    output_dir: Path,
    suffix: str,
    *,
    auto_downscale_4k_to_1080p: bool,
    explicit_downscale_targets: list[str],
    sample_seconds: float,
    max_frames: int,
    strength: float,
) -> TargetRenderPlan:
    output_path = build_output_path(target, output_dir, suffix)
    video_settings = probe_video_settings(target)
    apply_1080p_downscale = _should_downscale_target(
        target,
        video_settings,
        auto_downscale_4k_to_1080p=auto_downscale_4k_to_1080p,
        explicit_downscale_targets=explicit_downscale_targets,
    )
    analysis_vf_prefix = _scale_pad_1080p_vf() if apply_1080p_downscale else ""
    reference_stats, target_stats, vf = print_analysis(
        reference,
        target,
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        strength=strength,
        analysis_vf_prefix=analysis_vf_prefix,
    )
    return TargetRenderPlan(
        index=index,
        total=total,
        target=target,
        output_path=output_path,
        video_settings=video_settings,
        apply_1080p_downscale=apply_1080p_downscale,
        reference_stats=reference_stats,
        target_stats=target_stats,
        vf=vf,
    )


def _print_target_plan(plan: TargetRenderPlan) -> None:
    reference_yavg, reference_uavg, reference_vavg = plan.reference_stats
    target_yavg, target_uavg, target_vavg = plan.target_stats
    print(f"[{plan.index}/{plan.total}] Target: {plan.target}")
    print(f"  Output: {plan.output_path}")
    print(
        "  Source video: "
        f"{plan.video_settings.get('width')}x{plan.video_settings.get('height')}, "
        f"{_format_frame_rate(plan.video_settings.get('avg_frame_rate', ''))}, "
        f"{plan.video_settings.get('codec_name')} / {plan.video_settings.get('pix_fmt')}"
    )
    print(f"  Reference YAVG: {reference_yavg:.4f}")
    print(f"  Target YAVG:    {target_yavg:.4f}")
    print(f"  Reference U/V:  {reference_uavg:.4f} / {reference_vavg:.4f}")
    print(f"  Target U/V:     {target_uavg:.4f} / {target_vavg:.4f}")
    if plan.apply_1080p_downscale:
        print("  Downscale:      1920x1080")
    else:
        print("  Downscale:      no")
    print(f"  Filter: {plan.vf or '<none; passthrough copy>'}")


def _render_plan(
    plan: TargetRenderPlan,
    *,
    video_encoder: str,
    video_preset: str,
    video_quality: int,
    time_chunks: int,
    chunk_workers: int,
) -> None:
    render_target(
        plan.target,
        plan.output_path,
        plan.vf,
        plan.video_settings,
        video_encoder=video_encoder,
        video_preset=video_preset,
        video_quality=video_quality,
        apply_1080p_downscale=plan.apply_1080p_downscale,
        time_chunks=time_chunks,
        chunk_workers=chunk_workers,
    )


def print_analysis(
    reference: Path,
    target: Path,
    *,
    sample_seconds: float,
    max_frames: int,
    strength: float,
    analysis_vf_prefix: str = "",
) -> tuple[tuple[float, float, float], tuple[float, float, float], str]:
    reference_stats = probe_mean_signalstats_multi(
        str(reference),
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        sample_offsets=COLOR_MATCH_SAMPLE_OFFSETS,
        vf_prefix=analysis_vf_prefix,
    )
    target_stats = probe_mean_signalstats_multi(
        str(target),
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        sample_offsets=COLOR_MATCH_SAMPLE_OFFSETS,
        vf_prefix=analysis_vf_prefix,
    )
    vf = build_color_match_vf(
        str(reference),
        str(target),
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        sample_offsets=COLOR_MATCH_SAMPLE_OFFSETS,
        analysis_vf_prefix=analysis_vf_prefix,
        strength=strength,
        **STANDALONE_MATCH_LIMITS,
    )
    return reference_stats, target_stats, vf


def render_target(
    target: Path,
    output_path: Path,
    vf: str,
    video_settings: dict,
    *,
    video_encoder: str,
    video_preset: str,
    video_quality: int,
    apply_1080p_downscale: bool,
    time_chunks: int = 1,
    chunk_workers: int = 4,
) -> None:
    if time_chunks > 1:
        if not vf:
            raise ValueError(
                "Time-chunked rendering requires a non-empty color filter. "
                "Use --time-chunks 1 for passthrough copy, or adjust inputs."
            )
        _render_target_time_chunked(
            target,
            output_path,
            vf,
            video_settings,
            video_encoder=video_encoder,
            video_preset=video_preset,
            video_quality=video_quality,
            apply_1080p_downscale=apply_1080p_downscale,
            time_chunks=time_chunks,
            chunk_workers=chunk_workers,
        )
        return

    temp_output_path = output_path.with_name(f"{output_path.stem}._tmp{output_path.suffix}")
    if temp_output_path.exists():
        temp_output_path.unlink()

    cmd = ffmpeg_cmd_base() + ['-i', str(target)]
    if vf:
        output_filter = _build_output_filter(
            vf,
            video_settings,
            apply_1080p_downscale=apply_1080p_downscale,
        )
        cmd.extend([
            '-map', '0:v:0',
            '-map', '0:a?',
            '-map_metadata', '0',
            '-fps_mode', 'passthrough',
            '-vf', output_filter,
        ])
        _append_encoder_args(cmd, video_encoder, video_preset, video_quality)
        # Force a playback-friendly H.264 output; filtered inputs can otherwise
        # land in yuv444p / High 4:4:4 Predictive, which many Windows apps reject.
        cmd.extend([
            '-pix_fmt', 'yuv420p',
            '-profile:v', 'high',
            '-movflags', '+faststart',
            '-c:a', 'copy',
        ])
        for ffmpeg_key, probe_key in (
            ('-color_range', 'color_range'),
            ('-colorspace', 'color_space'),
            ('-color_trc', 'color_transfer'),
            ('-color_primaries', 'color_primaries'),
        ):
            value = video_settings.get(probe_key)
            if value and value != 'unknown':
                cmd.extend([ffmpeg_key, value])
        cmd.append(str(temp_output_path))
    else:
        cmd.extend([
            '-map', '0:v:0',
            '-map', '0:a?',
            '-c', 'copy',
            str(temp_output_path),
        ])

    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {target} -> {output_path}:\n{result.stderr.strip()}"
        )

    try:
        _validate_video_output(temp_output_path)
        if output_path.exists():
            output_path.unlink()
        temp_output_path.replace(output_path)
    finally:
        if temp_output_path.exists():
            temp_output_path.unlink()


def main() -> None:
    args = parse_args()

    reference = Path(args.reference).expanduser().resolve()
    targets = [Path(p).expanduser().resolve() for p in args.targets]
    output_dir = Path(args.output_dir).expanduser().resolve()
    resolved_video_encoder = resolve_video_encoder(
        args.video_encoder,
        args.video_preset,
        args.video_quality,
    )

    try:
        validate_inputs(reference, targets, output_dir)
        validate_downscale_targets(targets, args.downscale_targets)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"Reference: {reference}")
    print(f"Targets: {len(targets)}")
    print(f"Output directory: {output_dir}")
    print(f"Sample window: {args.sample_seconds:.2f}s, max frames: {args.max_frames}")
    print(f"Video encoder: {args.video_encoder}")
    if args.video_encoder == 'auto':
        print(f"Resolved encoder: {resolved_video_encoder}")
    print(f"Video preset: {args.video_preset}")
    print(f"Video quality: {args.video_quality}")
    if args.downscale_4k_to_1080p:
        print("Downscale: 4K targets will be rendered at 1920x1080")
    if args.downscale_targets:
        print(
            "Explicit downscale targets: "
            + ", ".join(args.downscale_targets)
        )
    print(
        "Sample positions: "
        + ", ".join(f"{offset * 100:.0f}%" for offset in COLOR_MATCH_SAMPLE_OFFSETS)
    )
    print(f"Correction strength: {args.strength:.2f}")
    print()

    if args.workers is None:
        args.workers = len(targets)
    if args.workers < 1:
        print("Error: --workers must be >= 1", file=sys.stderr)
        raise SystemExit(1)
    if args.time_chunks < 1 or args.time_chunks > MAX_TIME_CHUNKS:
        print(
            f"Error: --time-chunks must be between 1 and {MAX_TIME_CHUNKS} (got {args.time_chunks})",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if args.chunk_workers < 1:
        print("Error: --chunk-workers must be >= 1", file=sys.stderr)
        raise SystemExit(1)

    effective_workers = min(args.workers, len(targets))
    effective_chunk_workers = max(1, min(args.chunk_workers, args.time_chunks))
    print(f"Parallel workers (effective): {effective_workers}")
    if args.time_chunks > 1:
        print(
            f"Time-chunked render: {args.time_chunks} equal segments per target, "
            f"up to {effective_chunk_workers} parallel segment encodes per target"
        )
        if effective_workers > 1:
            print(
                "Warning: multiple targets (--workers > 1) and time-chunking both "
                "spawn ffmpeg jobs; reduce --workers and/or --chunk-workers if the "
                "machine or disk struggles.",
                file=sys.stderr,
            )
    print()

    plans_by_index: dict[int, TargetRenderPlan] = {}
    prepare_errors: list[tuple[int, Exception]] = []

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        future_to_index = {
            executor.submit(
                _prepare_target_job,
                index,
                len(targets),
                target,
                reference,
                output_dir,
                args.suffix,
                auto_downscale_4k_to_1080p=args.downscale_4k_to_1080p,
                explicit_downscale_targets=args.downscale_targets,
                sample_seconds=args.sample_seconds,
                max_frames=args.max_frames,
                strength=args.strength,
            ): index
            for index, target in enumerate(targets, start=1)
        }
        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                plans_by_index[idx] = future.result()
            except Exception as exc:
                prepare_errors.append((idx, exc))

    if prepare_errors:
        prepare_errors.sort(key=lambda item: item[0])
        lines = "\n".join(
            f"  #{idx} ({targets[idx - 1]}): {exc}" for idx, exc in prepare_errors
        )
        print(
            f"Error: probe/analysis failed for {len(prepare_errors)} target(s):\n{lines}",
            file=sys.stderr,
        )
        raise SystemExit(1) from prepare_errors[0][1]

    if args.time_chunks > 1:
        for index in range(1, len(targets) + 1):
            if not plans_by_index[index].vf:
                print(
                    "Error: --time-chunks > 1 requires a color filter on every target, "
                    f"but target #{index} would use passthrough copy. Use --time-chunks 1 "
                    "or change inputs.",
                    file=sys.stderr,
                )
                raise SystemExit(1)

    for index in range(1, len(targets) + 1):
        _print_target_plan(plans_by_index[index])
        print()

    if not args.dry_run:
        render_errors: list[tuple[int, Exception]] = []
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_index = {
                executor.submit(
                    _render_plan,
                    plans_by_index[index],
                    video_encoder=resolved_video_encoder,
                    video_preset=args.video_preset,
                    video_quality=args.video_quality,
                    time_chunks=args.time_chunks,
                    chunk_workers=effective_chunk_workers,
                ): index
                for index in range(1, len(targets) + 1)
            }
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    future.result()
                except Exception as exc:
                    render_errors.append((idx, exc))

        if render_errors:
            render_errors.sort(key=lambda item: item[0])
            lines = "\n".join(
                f"  #{idx} ({targets[idx - 1]}): {exc}" for idx, exc in render_errors
            )
            print(
                f"Error: render failed for {len(render_errors)} target(s):\n{lines}",
                file=sys.stderr,
            )
            raise SystemExit(1) from render_errors[0][1]

        for index in range(1, len(targets) + 1):
            print(f"  [{index}/{len(targets)}] Rendered successfully.")
            print()


if __name__ == "__main__":
    main()
