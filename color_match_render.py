#!/usr/bin/env python3
"""
Render one corrected file per target video by matching each target to a reference video.
"""

import argparse
import json
import subprocess
import sys
import tempfile
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


COLOR_MATCH_SAMPLE_OFFSETS = (0.0, 1 / 3, 2 / 3)
DEFAULT_COLOR_MATCH_STRENGTH = 2.1
DEFAULT_VIDEO_ENCODER = 'auto'
DEFAULT_VIDEO_PRESET = 'fast'
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
            f"preset (default: {DEFAULT_VIDEO_PRESET})"
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


def _build_output_filter(vf: str, video_settings: dict, *, apply_1080p_downscale: bool) -> str:
    filters = [vf]
    if apply_1080p_downscale:
        filters.append(
            f"scale={DOWNSCALE_WIDTH_1080P}:{DOWNSCALE_HEIGHT_1080P}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={DOWNSCALE_WIDTH_1080P}:{DOWNSCALE_HEIGHT_1080P}:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1"
        )
    sar = video_settings.get('sample_aspect_ratio')
    if sar and sar not in {'0:1', '1:1', 'N/A'}:
        filters.append(f"setsar={sar.replace(':', '/')}")
    return ",".join(filters)


def _append_encoder_args(cmd: list[str], video_encoder: str, video_preset: str) -> None:
    if video_encoder == 'libx264':
        cmd.extend([
            '-c:v', 'libx264',
            '-preset', video_preset,
            '-crf', '18',
        ])
        return

    if video_encoder == 'h264_nvenc':
        cmd.extend([
            '-c:v', 'h264_nvenc',
            '-preset', video_preset,
            '-tune', 'hq',
            '-rc', 'vbr',
            '-cq', '18',
            '-b:v', '0',
        ])
        return

    if video_encoder == 'h264_qsv':
        cmd.extend([
            '-c:v', 'h264_qsv',
            '-preset', video_preset,
            '-global_quality', '18',
        ])
        return

    if video_encoder == 'h264_amf':
        amf_preset = {
            'ultrafast': 'speed',
            'superfast': 'speed',
            'veryfast': 'speed',
            'faster': 'speed',
            'fast': 'speed',
            'medium': 'balanced',
            'slow': 'quality',
            'slower': 'quality',
            'veryslow': 'quality',
        }.get(video_preset, video_preset)
        cmd.extend([
            '-c:v', 'h264_amf',
            '-preset', amf_preset,
            '-rc', 'qvbr',
            '-qvbr_quality_level', '18',
        ])
        return

    raise ValueError(f"Unsupported video encoder: {video_encoder}")


def _encoder_test_command(output_path: str, video_encoder: str, video_preset: str) -> list[str]:
    cmd = ffmpeg_cmd_base() + [
        '-f', 'lavfi',
        '-i', f'color=c=black:s={ENCODER_TEST_WIDTH}x{ENCODER_TEST_HEIGHT}:r=24000/1001:d=0.1',
        '-frames:v', '1',
    ]
    _append_encoder_args(cmd, video_encoder, video_preset)
    cmd.extend([
        '-pix_fmt', 'yuv420p',
        '-profile:v', 'high',
        '-an',
        output_path,
    ])
    return cmd


def _encoder_is_usable(video_encoder: str, video_preset: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        temp_path = tmp.name
    try:
        Path(temp_path).unlink(missing_ok=True)
        cmd = _encoder_test_command(temp_path, video_encoder, video_preset)
        result = subprocess.run(cmd, check=False, text=True, capture_output=True)
        return result.returncode == 0 and Path(temp_path).exists() and Path(temp_path).stat().st_size > 0
    finally:
        Path(temp_path).unlink(missing_ok=True)


def resolve_video_encoder(video_encoder: str, video_preset: str) -> str:
    if video_encoder != 'auto':
        return video_encoder

    for candidate in AUTO_HARDWARE_ENCODERS:
        if _encoder_is_usable(candidate, video_preset):
            return candidate
    return 'libx264'


def print_analysis(
    reference: Path,
    target: Path,
    *,
    sample_seconds: float,
    max_frames: int,
    strength: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float], str]:
    reference_stats = probe_mean_signalstats_multi(
        str(reference),
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        sample_offsets=COLOR_MATCH_SAMPLE_OFFSETS,
    )
    target_stats = probe_mean_signalstats_multi(
        str(target),
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        sample_offsets=COLOR_MATCH_SAMPLE_OFFSETS,
    )
    vf = build_color_match_vf(
        str(reference),
        str(target),
        sample_seconds=sample_seconds,
        max_frames=max_frames,
        sample_offsets=COLOR_MATCH_SAMPLE_OFFSETS,
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
    apply_1080p_downscale: bool,
) -> None:
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
        _append_encoder_args(cmd, video_encoder, video_preset)
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
        cmd.append(str(output_path))
    else:
        cmd.extend([
            '-map', '0:v:0',
            '-map', '0:a?',
            '-c', 'copy',
            str(output_path),
        ])

    result = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed for {target} -> {output_path}:\n{result.stderr.strip()}"
        )


def main() -> None:
    args = parse_args()

    reference = Path(args.reference).expanduser().resolve()
    targets = [Path(p).expanduser().resolve() for p in args.targets]
    output_dir = Path(args.output_dir).expanduser().resolve()
    resolved_video_encoder = resolve_video_encoder(args.video_encoder, args.video_preset)

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

    for index, target in enumerate(targets, start=1):
        output_path = build_output_path(target, output_dir, args.suffix)
        video_settings = probe_video_settings(target)
        apply_1080p_downscale = _should_downscale_target(
            target,
            video_settings,
            auto_downscale_4k_to_1080p=args.downscale_4k_to_1080p,
            explicit_downscale_targets=args.downscale_targets,
        )
        reference_stats, target_stats, vf = print_analysis(
            reference,
            target,
            sample_seconds=args.sample_seconds,
            max_frames=args.max_frames,
            strength=args.strength,
        )
        reference_yavg, reference_uavg, reference_vavg = reference_stats
        target_yavg, target_uavg, target_vavg = target_stats
        print(f"[{index}/{len(targets)}] Target: {target}")
        print(f"  Output: {output_path}")
        print(
            "  Source video: "
            f"{video_settings.get('width')}x{video_settings.get('height')}, "
            f"{_format_frame_rate(video_settings.get('avg_frame_rate', ''))}, "
            f"{video_settings.get('codec_name')} / {video_settings.get('pix_fmt')}"
        )
        print(f"  Reference YAVG: {reference_yavg:.4f}")
        print(f"  Target YAVG:    {target_yavg:.4f}")
        print(f"  Reference U/V:  {reference_uavg:.4f} / {reference_vavg:.4f}")
        print(f"  Target U/V:     {target_uavg:.4f} / {target_vavg:.4f}")
        if apply_1080p_downscale:
            print("  Downscale:      1920x1080")
        else:
            print("  Downscale:      no")
        print(f"  Filter: {vf or '<none; passthrough copy>'}")

        if not args.dry_run:
            render_target(
                target,
                output_path,
                vf,
                video_settings,
                video_encoder=resolved_video_encoder,
                video_preset=args.video_preset,
                apply_1080p_downscale=apply_1080p_downscale,
            )
            print("  Rendered successfully.")
        print()


if __name__ == "__main__":
    main()
