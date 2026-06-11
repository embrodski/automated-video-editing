#!/usr/bin/env python3
"""
Align two stereo WAV recordings of the same conversation (different close-mic
balance), then mix into one stereo WAV with minimal echo.

Default mode applies the same initial start trim as single-offset alignment
(from the full-file lag estimate), then sliding-window residual lag estimates,
median smoothing, one delay per segment between knot boundaries. Knots start on
a nominal grid but move up to ±8 s to the quietest nearby moment on both
tracks; joins use adaptive-length cosine crossfades and cubic resampling when
reading the second file.

Use --no-piecewise for a single global offset (cross-correlation on downsampled
mono, then trim the start of one file and mix).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile
from scipy.ndimage import map_coordinates, median_filter, uniform_filter1d


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Load WAV as float32 in [-1, 1], shape (n_frames, n_channels)."""
    rate, data = wavfile.read(str(path))
    if data.ndim == 1:
        data = data[:, np.newaxis]
    if np.issubdtype(data.dtype, np.floating):
        y = np.clip(data.astype(np.float32), -1.0, 1.0)
    else:
        maxv = np.iinfo(data.dtype).max
        y = (data.astype(np.float32) / float(maxv)).clip(-1.0, 1.0)
    return y, int(rate)


def _write_wav(path: Path, y: np.ndarray, rate: int) -> None:
    y = np.clip(y, -1.0, 1.0)
    pcm = np.round(y * 32767.0).astype(np.int16)
    wavfile.write(str(path), rate, pcm)


def _default_combined_output_path(wav_a: Path) -> Path:
    """Same directory as wav_a: '{first word of stem} Combined Audio.wav'."""
    parts = wav_a.stem.split()
    prefix = parts[0] if parts else (wav_a.stem or "Combined")
    return wav_a.parent / f"{prefix} Combined Audio.wav"


def _find_child_dir_case_insensitive(parent: Path, name: str) -> Path | None:
    if not parent.is_dir():
        return None
    target = name.lower()
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == target:
            return child
    return None


def _resolve_temp_dir(wav_a: Path) -> Path:
    """Temp folder parallel to Raw when sources live under Raw; else beside sources."""
    sources = wav_a.resolve().parent
    if sources.name.lower() == "raw":
        episode_root = sources.parent
        if episode_root.name:
            existing = _find_child_dir_case_insensitive(episode_root, "temp")
            return existing if existing is not None else episode_root / "Temp"
    existing = _find_child_dir_case_insensitive(sources, "temp")
    if existing is not None:
        return existing
    return sources / "Temp"


def _default_json_report_path(output_wav: Path, wav_a: Path) -> Path:
    return _resolve_temp_dir(wav_a) / f"{output_wav.stem} sync report.json"


def _to_mono(y: np.ndarray) -> np.ndarray:
    if y.ndim == 1:
        return y.astype(np.float32)
    return np.mean(y.astype(np.float32), axis=1)


def _resample_poly(y: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return y.astype(np.float32)
    g = math.gcd(sr_in, sr_out)
    up = sr_out // g
    down = sr_in // g
    return signal.resample_poly(y.astype(np.float64), up, down).astype(np.float32)


def _estimate_lag_samples(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    sr: int,
    analyze_seconds: float,
    analyze_start_seconds: float = 0.0,
) -> tuple[int, float]:
    """
    Return lag (samples) where positive means b is delayed vs a.
    """
    start = int(max(0.0, analyze_start_seconds) * sr)
    avail = int(min(len(mono_a), len(mono_b)) - start)
    max_samples = int(min(avail, analyze_seconds * sr))
    if max_samples < sr // 2:
        raise ValueError("Not enough audio to analyze (need at least ~0.5s).")

    target_sr = min(8000, sr)
    a_ds = _resample_poly(mono_a[start : start + max_samples], sr, target_sr)
    b_ds = _resample_poly(mono_b[start : start + max_samples], sr, target_sr)
    a_ds -= np.mean(a_ds)
    b_ds -= np.mean(b_ds)
    if float(np.std(a_ds) * np.std(b_ds)) < 1e-12:
        raise ValueError("Audio appears silent in the analyzed window.")

    corr = signal.correlate(a_ds, b_ds, mode="full", method="fft")
    peak = int(np.argmax(corr))
    lag_ds = peak - (len(b_ds) - 1)
    lag_samples = -int(round(lag_ds * (sr / float(target_sr))))
    peak_strength = float(
        corr[peak] / (np.linalg.norm(a_ds) * np.linalg.norm(b_ds) + 1e-12)
    )
    return lag_samples, peak_strength


def _estimate_lag_at_window(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    sr: int,
    start: int,
    length: int,
) -> int:
    """Return lag for a window; positive means b delayed vs a."""
    end = start + length
    sa = mono_a[start:end]
    sb = mono_b[start:end]
    if len(sa) < length // 2 or len(sb) < length // 2:
        return 0

    target_sr = min(8000, sr)
    a_ds = _resample_poly(sa, sr, target_sr)
    b_ds = _resample_poly(sb, sr, target_sr)
    a_ds -= np.mean(a_ds)
    b_ds -= np.mean(b_ds)
    if float(np.std(a_ds) * np.std(b_ds)) < 1e-12:
        return 0

    corr = signal.correlate(a_ds, b_ds, mode="full", method="fft")
    peak = int(np.argmax(corr))
    lag_ds = peak - (len(b_ds) - 1)
    return -int(round(lag_ds * (sr / float(target_sr))))


def _lags_sliding_windows(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    sr: int,
    *,
    window_samples: int,
    hop_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (center_sample, lag_samples) per analysis window."""
    n = min(len(mono_a), len(mono_b))
    if n < window_samples:
        lag = _estimate_lag_at_window(mono_a, mono_b, sr, 0, n)
        return np.array([n // 2], dtype=np.int64), np.array([lag], dtype=np.int64)

    centers: list[int] = []
    lags: list[int] = []

    start = 0
    while start + window_samples <= n:
        lag = _estimate_lag_at_window(mono_a, mono_b, sr, start, window_samples)
        centers.append(start + window_samples // 2)
        lags.append(lag)
        start += hop_samples

    last_start = max(0, n - window_samples)
    last_center = last_start + window_samples // 2
    if not centers or int(centers[-1]) != int(last_center):
        lag = _estimate_lag_at_window(mono_a, mono_b, sr, last_start, window_samples)
        centers.append(last_center)
        lags.append(lag)

    return np.asarray(centers, dtype=np.int64), np.asarray(lags, dtype=np.int64)


def _smooth_lags_median(lags: np.ndarray, size: int) -> np.ndarray:
    if size <= 1 or len(lags) < 3:
        return lags.astype(np.float64)
    k = size if size % 2 == 1 else size + 1
    return median_filter(lags.astype(np.float64), size=k, mode="nearest")


def _mix_peak_limited(a_use: np.ndarray, b_use: np.ndarray) -> tuple[np.ndarray, dict]:
    mix = 0.5 * (a_use.astype(np.float32) + b_use.astype(np.float32))
    peak = float(np.max(np.abs(mix)))
    meta: dict = {}
    if peak > 0.99:
        mix *= 0.99 / peak
        meta["gain_reduction"] = peak / 0.99
    else:
        meta["gain_reduction"] = 1.0
    meta["output_frames"] = int(mix.shape[0])
    return mix, meta


def _apply_initial_lag_trim(
    a: np.ndarray, b: np.ndarray, lag_ab: int
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """
    Same leading discard as global alignment before mixing or piecewise warp.
    Positive lag_ab: B delayed vs A — trim start of B. Negative: trim start of A.
    """
    trim_a = trim_b = 0
    if lag_ab >= 0:
        trim_b = lag_ab
        b_adj = b[trim_b:]
        a_adj = a[: len(b_adj)]
    else:
        trim_a = -lag_ab
        a_adj = a[trim_a:]
        b_adj = b[: len(a_adj)]
    n = min(len(a_adj), len(b_adj))
    return a_adj[:n].astype(np.float32), b_adj[:n].astype(np.float32), trim_a, trim_b


def _align_and_mix(a: np.ndarray, b: np.ndarray, lag_ab: int) -> tuple[np.ndarray, dict]:
    """
    lag_ab: positive means the second track (b) is delayed vs (a); trim start
    of b. Negative means (a) is delayed vs (b); trim start of a.
    """
    meta: dict = {"lag_samples_b_relative_to_a": lag_ab}
    a_adj, b_adj, trim_a, trim_b = _apply_initial_lag_trim(a, b, lag_ab)
    mix, mm = _mix_peak_limited(a_adj, b_adj)
    meta.update(mm)
    meta["trim_start_samples_a"] = trim_a
    meta["trim_start_samples_b"] = trim_b
    return mix, meta


def sync_pair(
    path_a: Path,
    path_b: Path,
    *,
    analyze_seconds: float = 300.0,
    analyze_start_seconds: float = 0.0,
    check_drift: bool = True,
    piecewise: bool = True,
    segment_seconds: float = 22.0,
    corr_window_seconds: float = 15.0,
    corr_hop_seconds: float = 7.5,
    crossfade_ms: float = 25.0,
    lag_median_size: int = 3,
) -> tuple[np.ndarray, int, dict]:
    report: dict = {}
    a, sr_a = _read_wav(path_a)
    b, sr_b = _read_wav(path_b)

    if a.shape[1] != b.shape[1]:
        raise ValueError(
            f"Channel count mismatch: {path_a.name} has {a.shape[1]}, "
            f"{path_b.name} has {b.shape[1]}."
        )

    if sr_b != sr_a:
        chans = []
        for c in range(b.shape[1]):
            chans.append(_resample_poly(b[:, c].astype(np.float64), sr_b, sr_a))
        b = np.stack(chans, axis=1).astype(np.float32)
        report["resampled_b_to_hz"] = sr_a

    mono_a = _to_mono(a)
    mono_b = _to_mono(b)
    lag, strength = _estimate_lag_samples(
        mono_a,
        mono_b,
        sr_a,
        analyze_seconds,
        analyze_start_seconds=analyze_start_seconds,
    )
    report["correlation_peak_strength"] = strength
    report["analyze_start_seconds"] = float(analyze_start_seconds)
    report["lag_ms_initial"] = lag / float(sr_a) * 1000.0

    mono_a_full = mono_a
    mono_b_full = mono_b
    n_out = min(len(a), len(b))

    if piecewise:
        a_pw, b_pw, trim_a, trim_b = _apply_initial_lag_trim(a, b, lag)
        mono_a = _to_mono(a_pw)
        mono_b = _to_mono(b_pw)
        n_out = len(mono_a)
        win = int(min(corr_window_seconds * sr_a, n_out))
        win = max(win, sr_a // 2)
        hop = int(max(256, min(corr_hop_seconds * sr_a, max(win // 2, 256))))
        if win < sr_a // 2 or n_out < win:
            raise ValueError(
                "Piecewise mode needs at least ~0.5s of audio and a correlation window "
                "that fits the file length."
            )

        centers, lags = _lags_sliding_windows(
            mono_a, mono_b, sr_a, window_samples=win, hop_samples=hop
        )
        lags_f = _smooth_lags_median(lags, lag_median_size)

        seg_samples = int(max(256, segment_seconds * sr_a))
        cf = int(max(2, crossfade_ms * 1e-3 * sr_a))
        if cf >= seg_samples:
            cf = max(256, seg_samples // 4)

        min_seg_sec = max(10.0, corr_window_seconds * 0.75)
        boundaries, nominal_b = _relocate_piecewise_knots(
            mono_a,
            mono_b,
            n_out,
            seg_samples,
            sr_a,
            min_segment_min_seconds=min_seg_sec,
        )
        d_seg, piece_rows = _segment_delay_table_knots(
            n_out, centers, lags_f, boundaries, sr_a
        )
        d_seg = _clamp_segment_delays_knots(d_seg, boundaries, len(b_pw))
        b_w = _warp_b_piecewise_knots(
            b_pw,
            n_out,
            d_seg,
            boundaries,
            cf,
            sr_a,
        )
        a_use = a_pw.astype(np.float32)
        mix, meta = _mix_peak_limited(a_use, b_w)

        report["piecewise"] = True
        report["lag_ms"] = float(d_seg[0] * 1000.0 / sr_a)
        report["lag_samples_b_relative_to_a"] = int(d_seg[0])
        report["shifted_file"] = path_b.name
        report["reference_file"] = path_a.name
        report["trim_start_samples_a"] = trim_a
        report["trim_start_samples_b"] = trim_b
        report["piecewise_segments"] = piece_rows
        report["piecewise_delay_spread_ms"] = float(
            (int(np.max(d_seg)) - int(np.min(d_seg))) * 1000.0 / sr_a
        )
        report["piecewise_crossfade_samples"] = cf
        report["piecewise_crossfade_samples_base"] = cf
        report["piecewise_crossfade_max_ms"] = 120.0
        report["piecewise_adaptive_ms_per_lag_sample"] = 0.14
        report["piecewise_correlation_window_samples"] = win
        report["piecewise_hop_samples"] = hop
        report["piecewise_knot_nominal_samples"] = [int(x) for x in nominal_b.tolist()]
        report["piecewise_knot_adjusted_samples"] = [int(x) for x in boundaries.tolist()]
        report["piecewise_knot_shift_samples"] = [
            int(boundaries[j] - nominal_b[j]) for j in range(1, len(boundaries) - 1)
        ]
        report.update(meta)
    else:
        report["lag_ms"] = report["lag_ms_initial"]
        if lag >= 0:
            report["shifted_file"] = path_b.name
            report["reference_file"] = path_a.name
        else:
            report["shifted_file"] = path_a.name
            report["reference_file"] = path_b.name

        mix, meta = _align_and_mix(a, b, lag)
        report.update(meta)

    if check_drift and len(mono_a_full) > int(2.5 * analyze_seconds * sr_a):
        w = int(min(analyze_seconds * sr_a, len(mono_a_full) * 0.25))
        start2 = max(0, len(mono_a_full) - w)
        lag2 = _estimate_lag_at_window(mono_a_full, mono_b_full, sr_a, start2, w)
        drift_ms = abs(lag2 - lag) / float(sr_a) * 1000.0
        report["drift_check_end_lag_ms"] = lag2 / float(sr_a) * 1000.0
        report["drift_estimate_ms"] = drift_ms
        if drift_ms > 25.0 and not piecewise:
            report["drift_warning"] = (
                "Offset differs noticeably between start and end windows; "
                "a single global shift may leave residual echo. "
                "Per-segment alignment is the default; omit --no-piecewise or tune "
                "--segment-seconds / --corr-hop-seconds."
            )
        elif drift_ms > 25.0 and piecewise:
            report["drift_note"] = (
                "Start vs end window offset still differs; piecewise segments should "
                "reduce but not eliminate all residual misalignment."
            )

    return mix, sr_a, report


def _enforce_monotonic_knots(b: np.ndarray, n_out: int, min_seg: int) -> np.ndarray:
    b = b.astype(np.int64).copy()
    b[0] = 0
    b[-1] = n_out
    for j in range(1, len(b) - 1):
        b[j] = max(b[j], b[j - 1] + min_seg)
    for j in range(len(b) - 2, 0, -1):
        b[j] = min(b[j], b[j + 1] - min_seg)
    return b


def _relocate_piecewise_knots(
    mono_a: np.ndarray,
    mono_b: np.ndarray,
    n_out: int,
    seg_nominal_samples: int,
    sr: int,
    *,
    search_seconds: float = 8.0,
    min_segment_min_seconds: float,
    rms_window_ms: float = 40.0,
    hop_samples: int = 240,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Place interior knots near low-energy regions (min of both tracks' short RMS).
    Returns (adjusted_boundaries, nominal_boundaries), each shape (k_seg+1,).
    """
    k_seg = int(math.ceil(n_out / float(seg_nominal_samples)))
    nominal = np.array(
        [min(j * seg_nominal_samples, n_out) for j in range(k_seg + 1)],
        dtype=np.int64,
    )
    min_seg = int(max(256, min_segment_min_seconds * sr))
    search_half = int(search_seconds * sr)
    win = max(32, int(rms_window_ms * 1e-3 * sr))
    ea = uniform_filter1d(mono_a.astype(np.float64) ** 2, size=win, mode="nearest")
    eb = uniform_filter1d(mono_b.astype(np.float64) ** 2, size=win, mode="nearest")
    quiet = np.minimum(ea, eb)
    boundaries = nominal.copy()
    for j in range(1, k_seg):
        nom = int(nominal[j])
        lo = max(int(boundaries[j - 1]) + min_seg, nom - search_half)
        next_nom = min((j + 1) * seg_nominal_samples, n_out)
        hi = min(next_nom - min_seg, nom + search_half)
        if hi < lo + hop_samples:
            boundaries[j] = nom
            continue
        idxs = np.arange(lo, hi, hop_samples, dtype=np.int64)
        scores = quiet[idxs]
        boundaries[j] = int(idxs[int(np.argmin(scores))])
    boundaries = _enforce_monotonic_knots(boundaries, n_out, min_seg)
    return boundaries, nominal


def _segment_delay_table_knots(
    n_output: int,
    centers: np.ndarray,
    lags_smoothed: np.ndarray,
    boundaries: np.ndarray,
    sr: int,
) -> tuple[np.ndarray, list[dict]]:
    """One integer delay per segment between consecutive knot boundaries."""
    k_seg = len(boundaries) - 1
    d_seg = np.zeros(k_seg, dtype=np.int64)
    meta_rows: list[dict] = []

    for k in range(k_seg):
        s = int(boundaries[k])
        e = int(boundaries[k + 1])
        if e <= s:
            dk = 0
        else:
            mask = (centers >= s) & (centers < e)
            if np.any(mask):
                d = float(np.median(lags_smoothed[mask]))
            else:
                j = int(np.argmin(np.abs(centers - (s + e) // 2)))
                d = float(lags_smoothed[j])
            dk = int(round(d))
        d_seg[k] = dk
        meta_rows.append(
            {
                "segment_index": k,
                "start_sample": s,
                "end_sample": e,
                "lag_samples": dk,
                "lag_ms": float(dk * 1000.0 / sr),
            }
        )

    return d_seg, meta_rows


def _clamp_segment_delays_knots(
    d_seg: np.ndarray,
    boundaries: np.ndarray,
    len_b: int,
) -> np.ndarray:
    """Ensure 0 <= t + d_k < len_b for all t in each segment."""
    out = d_seg.copy()
    for k in range(len(out)):
        s = int(boundaries[k])
        e = int(boundaries[k + 1])
        lo = -s
        hi = len_b - e
        if hi < lo:
            out[k] = lo
        else:
            out[k] = int(np.clip(out[k], lo, hi))
    return out


def _warp_b_piecewise_knots(
    b: np.ndarray,
    n_out: int,
    d_seg: np.ndarray,
    boundaries: np.ndarray,
    cf_base_samples: int,
    sr: int,
    *,
    crossfade_max_ms: float = 120.0,
    adaptive_ms_per_lag_sample: float = 0.14,
) -> np.ndarray:
    """
    Piecewise delay with knots at irregular boundaries, adaptive cosine crossfades
    at each join, and cubic-spline resampling (order=3) for fractional reads.
    """
    n_ch = b.shape[1]
    len_b = b.shape[0]
    idx = np.arange(n_out, dtype=np.float64)
    seg_ix = np.searchsorted(boundaries, idx, side="right") - 1
    seg_ix = np.clip(seg_ix, 0, len(d_seg) - 1).astype(np.int64)
    d_base = d_seg[seg_ix].astype(np.float64)
    idx_read = idx + d_base

    cf_max_s = max(cf_base_samples, int(crossfade_max_ms * 1e-3 * sr))
    scale = float(adaptive_ms_per_lag_sample) * float(sr) / 1000.0
    k_seg = len(d_seg)
    for j in range(1, k_seg):
        t_bound = int(boundaries[j])
        if t_bound <= 0 or t_bound >= n_out:
            continue
        delta = abs(float(d_seg[j]) - float(d_seg[j - 1]))
        w = int(round(cf_base_samples + delta * scale))
        w = max(cf_base_samples, min(cf_max_s, w))
        left = int(boundaries[j] - boundaries[j - 1])
        right = int(boundaries[j + 1] - boundaries[j])
        max_half = max(32, min(left, right) // 2 - 8)
        w = min(w, max(4, 2 * max_half))
        half = w // 2
        lo = max(0, t_bound - half)
        hi = min(n_out, t_bound + half)
        if hi - lo < 2:
            continue
        t_span = np.arange(lo, hi, dtype=np.float64)
        span = float(max(hi - lo - 1, 1))
        alpha = (t_span - float(lo)) / span
        sm = 0.5 - 0.5 * np.cos(math.pi * np.clip(alpha, 0.0, 1.0))
        d0 = float(d_seg[j - 1])
        d1 = float(d_seg[j])
        idx_read[lo:hi] = t_span + (1.0 - sm) * d0 + sm * d1

    idx_read = np.clip(idx_read, 0.0, float(len_b - 1))
    out = np.empty((n_out, n_ch), dtype=np.float32)
    for c in range(n_ch):
        col = b[:, c].astype(np.float64)
        out[:, c] = map_coordinates(
            col, [idx_read], order=3, mode="nearest", prefilter=True
        ).astype(np.float32)
    return out


def _echo_suppress_bidirectional(
    a: np.ndarray,
    b: np.ndarray,
    strength: float,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Per channel, k_ab = argmin_k ||a - k b||^2 on zero-mean slices; subtract
    strength * k_ab * b from a (and symmetric for b). strength in [0, 1].
    """
    if strength <= 0.0:
        return a.astype(np.float32), b.astype(np.float32), {}
    s = float(np.clip(strength, 0.0, 1.0))
    a_f = a.astype(np.float64)
    b_f = b.astype(np.float64)
    n_ch = a_f.shape[1]
    k_ab: list[float] = []
    k_ba: list[float] = []
    a_out = np.empty_like(a_f)
    b_out = np.empty_like(b_f)
    for c in range(n_ch):
        ac = a_f[:, c] - np.mean(a_f[:, c])
        bc = b_f[:, c] - np.mean(b_f[:, c])
        bb = float(np.dot(bc, bc) + 1e-12)
        aa = float(np.dot(ac, ac) + 1e-12)
        kab = float(np.clip(np.dot(ac, bc) / bb, -2.0, 2.0))
        kba = float(np.clip(np.dot(bc, ac) / aa, -2.0, 2.0))
        k_ab.append(kab)
        k_ba.append(kba)
        a_out[:, c] = a_f[:, c] - s * kab * b_f[:, c]
        b_out[:, c] = b_f[:, c] - s * kba * a_f[:, c]

    meta = {
        "echo_suppress_strength": s,
        "echo_suppress_k_ab": k_ab,
        "echo_suppress_k_ba": k_ba,
    }
    return a_out.astype(np.float32), b_out.astype(np.float32), meta


def _mix_peak_limited(a_use: np.ndarray, b_use: np.ndarray) -> tuple[np.ndarray, dict]:
    mix = 0.5 * (a_use.astype(np.float32) + b_use.astype(np.float32))
    peak = float(np.max(np.abs(mix)))
    meta: dict = {}
    if peak > 0.99:
        mix *= 0.99 / peak
        meta["gain_reduction"] = peak / 0.99
    else:
        meta["gain_reduction"] = 1.0
    meta["output_frames"] = int(mix.shape[0])
    return mix, meta


def _track_rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))


def _rms_match_boost(
    a: np.ndarray,
    b: np.ndarray,
    *,
    max_gain: float = 20.0,
    min_rms: float = 1e-6,
    fraction: float = 0.9,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Boost the quieter track toward the louder's RMS (never attenuate).

    fraction in [0, 1]: 1.0 = full RMS match; 0.9 = apply 90% of the gain correction.
    Applied as gain = 1 + fraction * (full_gain - 1).
    """
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError("rms_match fraction must be between 0 and 1.")

    rms_a = _track_rms(a)
    rms_b = _track_rms(b)
    meta: dict = {
        "rms_match": True,
        "rms_match_fraction": fraction,
        "rms_match_pre_a": rms_a,
        "rms_match_pre_b": rms_b,
        "rms_match_gain_a": 1.0,
        "rms_match_gain_b": 1.0,
    }
    if rms_a < min_rms or rms_b < min_rms:
        meta["rms_match_skipped"] = "source too quiet to match safely"
        return a, b, meta
    target = max(rms_a, rms_b)
    if abs(rms_a - rms_b) / target < 0.01:
        meta["rms_match_skipped"] = "already within 1%"
        return a, b, meta

    def _apply_boost(track: np.ndarray, rms: float, label: str) -> tuple[np.ndarray, float]:
        full_gain = target / rms
        gain = 1.0 + fraction * (full_gain - 1.0)
        gain = min(gain, max_gain)
        meta[f"rms_match_full_gain_{label}"] = full_gain
        meta[f"rms_match_gain_{label}"] = gain
        meta["rms_match_boosted"] = label
        return (track * gain).astype(np.float32), gain

    if rms_a < rms_b:
        a_out, _ = _apply_boost(a, rms_a, "a")
        return a_out, b, meta
    if rms_b < rms_a:
        b_out, _ = _apply_boost(b, rms_b, "b")
        return a, b_out, meta
    return a, b, meta


def _align_and_mix(
    a: np.ndarray,
    b: np.ndarray,
    lag_ab: int,
    *,
    echo_suppress: float = 0.0,
    rms_match: bool = True,
    rms_match_max_gain: float = 20.0,
    rms_match_fraction: float = 0.9,
) -> tuple[np.ndarray, dict]:
    """
    lag_ab: positive means the second track (b) is delayed vs (a); trim start
    of b. Negative means (a) is delayed vs (b); trim start of a.
    """
    meta: dict = {"lag_samples_b_relative_to_a": lag_ab}
    a_adj, b_adj, trim_a, trim_b = _apply_initial_lag_trim(a, b, lag_ab)

    if echo_suppress > 0.0:
        a_adj, b_adj, es_meta = _echo_suppress_bidirectional(a_adj, b_adj, echo_suppress)
        meta.update(es_meta)

    if rms_match:
        a_adj, b_adj, lm_meta = _rms_match_boost(
            a_adj,
            b_adj,
            max_gain=rms_match_max_gain,
            fraction=rms_match_fraction,
        )
        meta.update(lm_meta)
    else:
        meta["rms_match"] = False

    mix, mm = _mix_peak_limited(a_adj, b_adj)
    meta.update(mm)
    meta["trim_start_samples_a"] = trim_a
    meta["trim_start_samples_b"] = trim_b
    return mix, meta


def sync_pair(
    path_a: Path,
    path_b: Path,
    *,
    analyze_seconds: float = 300.0,
    analyze_start_seconds: float = 0.0,
    check_drift: bool = True,
    piecewise: bool = True,
    segment_seconds: float = 22.0,
    corr_window_seconds: float = 15.0,
    corr_hop_seconds: float = 7.5,
    crossfade_ms: float = 25.0,
    lag_median_size: int = 3,
    echo_suppress: float = 0.0,
    rms_match: bool = True,
    rms_match_max_gain: float = 20.0,
    rms_match_fraction: float = 0.9,
) -> tuple[np.ndarray, int, dict]:
    """
    Load WAVs, resample B to A's rate if needed, estimate lag, mix.

    Piecewise mode (default): applies the same initial start trim as global mode
    from the full-file lag estimate, then estimates residual lag in sliding
    windows, assigns a delay per segment on the reference timeline, reads B with
    fractional delay and cosine crossfades at segment boundaries.

    Global mode (--no-piecewise): positive lag (second file delayed) trims the
    start of the second file; negative lag trims the first file.

    echo_suppress in [0, 1]: bidirectional linear suppression of shared content
    after alignment (see module docstring).

    rms_match: after alignment, boost the quieter track toward the louder's RMS
    before the 50/50 mix (never attenuate the louder source). rms_match_fraction
    (default 0.9) applies that fraction of the full corrective gain.
    """
    if echo_suppress < 0.0 or echo_suppress > 1.0:
        raise ValueError("echo_suppress must be between 0 and 1.")

    report: dict = {}
    a, sr_a = _read_wav(path_a)
    b, sr_b = _read_wav(path_b)

    if a.shape[1] != b.shape[1]:
        raise ValueError(
            f"Channel count mismatch: {path_a.name} has {a.shape[1]}, "
            f"{path_b.name} has {b.shape[1]}."
        )

    if sr_b != sr_a:
        chans = []
        for c in range(b.shape[1]):
            chans.append(_resample_poly(b[:, c].astype(np.float64), sr_b, sr_a))
        b = np.stack(chans, axis=1).astype(np.float32)
        report["resampled_b_to_hz"] = sr_a

    mono_a = _to_mono(a)
    mono_b = _to_mono(b)
    lag, strength = _estimate_lag_samples(
        mono_a,
        mono_b,
        sr_a,
        analyze_seconds,
        analyze_start_seconds=analyze_start_seconds,
    )
    report["correlation_peak_strength"] = strength
    report["analyze_start_seconds"] = float(analyze_start_seconds)
    report["lag_ms_initial"] = lag / float(sr_a) * 1000.0

    mono_a_full = mono_a
    mono_b_full = mono_b
    n_out = min(len(a), len(b))

    if piecewise:
        a_pw, b_pw, trim_a, trim_b = _apply_initial_lag_trim(a, b, lag)
        mono_a = _to_mono(a_pw)
        mono_b = _to_mono(b_pw)
        n_out = len(mono_a)
        win = int(min(corr_window_seconds * sr_a, n_out))
        win = max(win, sr_a // 2)
        hop = int(max(256, min(corr_hop_seconds * sr_a, max(win // 2, 256))))
        if win < sr_a // 2 or n_out < win:
            raise ValueError(
                "Piecewise mode needs at least ~0.5s of audio and a correlation window "
                "that fits the file length."
            )
        centers, lags = _lags_sliding_windows(
            mono_a, mono_b, sr_a, window_samples=win, hop_samples=hop
        )
        lags_f = _smooth_lags_median(lags, lag_median_size)
        seg_samples = int(max(256, segment_seconds * sr_a))
        cf = int(max(2, crossfade_ms * 1e-3 * sr_a))
        if cf >= seg_samples:
            cf = max(256, seg_samples // 4)

        min_seg_sec = max(10.0, corr_window_seconds * 0.75)
        boundaries, nominal_b = _relocate_piecewise_knots(
            mono_a,
            mono_b,
            n_out,
            seg_samples,
            sr_a,
            min_segment_min_seconds=min_seg_sec,
        )
        d_seg, piece_rows = _segment_delay_table_knots(
            n_out, centers, lags_f, boundaries, sr_a
        )
        d_seg = _clamp_segment_delays_knots(d_seg, boundaries, len(b_pw))
        b_w = _warp_b_piecewise_knots(
            b_pw,
            n_out,
            d_seg,
            boundaries,
            cf,
            sr_a,
        )
        a_use = a_pw.astype(np.float32)
        if echo_suppress > 0.0:
            a_use, b_w, es_meta = _echo_suppress_bidirectional(a_use, b_w, echo_suppress)
            report.update(es_meta)
        if rms_match:
            a_use, b_w, lm_meta = _rms_match_boost(
                a_use,
                b_w,
                max_gain=rms_match_max_gain,
                fraction=rms_match_fraction,
            )
            report.update(lm_meta)
        else:
            report["rms_match"] = False
        mix, meta = _mix_peak_limited(a_use, b_w)

        report["piecewise"] = True
        report["lag_ms"] = float(d_seg[0] * 1000.0 / sr_a)
        report["lag_samples_b_relative_to_a"] = int(d_seg[0])
        report["shifted_file"] = path_b.name
        report["reference_file"] = path_a.name
        report["trim_start_samples_a"] = trim_a
        report["trim_start_samples_b"] = trim_b
        report["piecewise_segments"] = piece_rows
        report["piecewise_delay_spread_ms"] = float(
            (int(np.max(d_seg)) - int(np.min(d_seg))) * 1000.0 / sr_a
        )
        report["piecewise_crossfade_samples"] = cf
        report["piecewise_crossfade_samples_base"] = cf
        report["piecewise_crossfade_max_ms"] = 120.0
        report["piecewise_adaptive_ms_per_lag_sample"] = 0.14
        report["piecewise_correlation_window_samples"] = win
        report["piecewise_hop_samples"] = hop
        report["piecewise_knot_nominal_samples"] = [int(x) for x in nominal_b.tolist()]
        report["piecewise_knot_adjusted_samples"] = [int(x) for x in boundaries.tolist()]
        report["piecewise_knot_shift_samples"] = [
            int(boundaries[j] - nominal_b[j]) for j in range(1, len(boundaries) - 1)
        ]
        report.update(meta)
    else:
        report["lag_ms"] = report["lag_ms_initial"]
        if lag >= 0:
            report["shifted_file"] = path_b.name
            report["reference_file"] = path_a.name
        else:
            report["shifted_file"] = path_a.name
            report["reference_file"] = path_b.name

        mix, meta = _align_and_mix(
            a,
            b,
            lag,
            echo_suppress=echo_suppress,
            rms_match=rms_match,
            rms_match_max_gain=rms_match_max_gain,
            rms_match_fraction=rms_match_fraction,
        )
        report.update(meta)

    if check_drift and len(mono_a_full) > int(2.5 * analyze_seconds * sr_a):
        win = int(min(analyze_seconds * sr_a, len(mono_a_full) * 0.25))
        start2 = max(0, len(mono_a_full) - win)
        lag2 = _estimate_lag_at_window(mono_a_full, mono_b_full, sr_a, start2, win)
        drift_ms = abs(lag2 - lag) / float(sr_a) * 1000.0
        report["drift_check_end_lag_ms"] = lag2 / float(sr_a) * 1000.0
        report["drift_estimate_ms"] = drift_ms
        if drift_ms > 25.0 and not piecewise:
            report["drift_warning"] = (
                "Offset differs noticeably between start and end windows; "
                "a single global shift may leave residual echo. "
                "Per-segment alignment is the default; omit --no-piecewise or tune "
                "--segment-seconds / --corr-hop-seconds."
            )
        elif drift_ms > 25.0 and piecewise:
            report["drift_note"] = (
                "Start vs end window offset still differs; piecewise segments should "
                "reduce but not eliminate all residual misalignment."
            )

    return mix, sr_a, report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "wav_a",
        type=Path,
        help="First WAV (its sample rate is used for the output; order affects lag sign reporting).",
    )
    p.add_argument("wav_b", type=Path, help="Second WAV (aligned to the first by trimming starts).")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help='Output WAV path. Default: beside wav_a, "{first word of its basename} Combined Audio.wav".',
    )
    p.add_argument(
        "--analyze-seconds",
        type=float,
        default=300.0,
        help="Max duration used for offset detection (default: 300).",
    )
    p.add_argument(
        "--analyze-start-seconds",
        type=float,
        default=0.0,
        help="Skip this many seconds from the start before offset detection "
        "(default: 0). Use when early audio differs between recorders.",
    )
    p.add_argument(
        "--no-drift-check",
        action="store_true",
        help="Skip comparing offset at end of file vs start.",
    )
    p.add_argument(
        "--piecewise",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Per-segment delay of B vs A with cosine crossfades at segment joins (default: on). "
        "Use --no-piecewise for a single global offset and start trim only.",
    )
    p.add_argument(
        "--segment-seconds",
        type=float,
        default=22.0,
        help="Piecewise segment length on the reference timeline (default: 22).",
    )
    p.add_argument(
        "--corr-window-seconds",
        type=float,
        default=15.0,
        help="Correlation window length for each lag estimate (default: 15).",
    )
    p.add_argument(
        "--corr-hop-seconds",
        type=float,
        default=7.5,
        help="Hop between correlation windows (default: 7.5).",
    )
    p.add_argument(
        "--crossfade-ms",
        type=float,
        default=25.0,
        help="Crossfade duration at each segment boundary in ms (default: 25).",
    )
    p.add_argument(
        "--lag-median-size",
        type=int,
        default=3,
        help="Median filter kernel size (odd) applied to per-window lags (default: 3).",
    )
    p.add_argument(
        "--echo-suppress",
        type=float,
        default=0.0,
        metavar="STRENGTH",
        help="0..1 bidirectional linear echo reduction after alignment (default: 0 = off).",
    )
    p.add_argument(
        "--rms-match",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Boost the quieter aligned track so its RMS matches the louder before mixing "
        "(default: on). Use --no-rms-match to keep raw recorder levels.",
    )
    p.add_argument(
        "--rms-match-max-gain",
        type=float,
        default=20.0,
        help="Maximum linear gain applied when RMS-matching (default: 20).",
    )
    p.add_argument(
        "--rms-match-fraction",
        type=float,
        default=0.9,
        help="Fraction of full RMS corrective gain to apply, 0..1 (default: 0.9). "
        "1.0 = full match; 0.9 = boost 90%% of the way from unity to a perfect match.",
    )
    p.add_argument(
        "--no-json-report",
        action="store_true",
        help="Do not write alignment metadata JSON.",
    )
    p.add_argument(
        "--json-report",
        type=Path,
        default=None,
        help="Write alignment metadata JSON (default: Temp folder parallel to Raw, "
        '"{output stem} sync report.json").',
    )
    args = p.parse_args()

    if args.output is None:
        args.output = _default_combined_output_path(args.wav_a.resolve())

    if not args.no_json_report and args.json_report is None:
        args.json_report = _default_json_report_path(
            args.output.resolve(), args.wav_a.resolve()
        )

    if not args.wav_a.is_file() or not args.wav_b.is_file():
        print("Both input paths must exist.", file=sys.stderr)
        return 2

    try:
        mix, sr, report = sync_pair(
            args.wav_a.resolve(),
            args.wav_b.resolve(),
            analyze_seconds=args.analyze_seconds,
            analyze_start_seconds=args.analyze_start_seconds,
            check_drift=not args.no_drift_check,
            piecewise=args.piecewise,
            segment_seconds=args.segment_seconds,
            corr_window_seconds=args.corr_window_seconds,
            corr_hop_seconds=args.corr_hop_seconds,
            crossfade_ms=args.crossfade_ms,
            lag_median_size=args.lag_median_size,
            echo_suppress=args.echo_suppress,
            rms_match=args.rms_match,
            rms_match_max_gain=args.rms_match_max_gain,
            rms_match_fraction=args.rms_match_fraction,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(args.output.resolve(), mix, sr)

    print(f"Wrote {args.output}")
    print(f"  Reference:         {report['reference_file']}")
    print(f"  Aligned / warped:  {report['shifted_file']}")
    if report.get("piecewise"):
        print(f"  Mode:              piecewise ({len(report.get('piecewise_segments', []))} segments)")
        print(f"  Lag first segment: {report['lag_ms']:.2f} ms (initial global: {report['lag_ms_initial']:.2f} ms)")
        print(f"  Delay spread:      {report.get('piecewise_delay_spread_ms', 0.0):.2f} ms across segments")
    else:
        print("  Mode:              global (single offset, start trim)")
        print(f"  Lag (B vs A):      {report['lag_ms']:.2f} ms")
    print(f"  Correlation peak:  {report['correlation_peak_strength']:.4f}")
    if "drift_estimate_ms" in report:
        print(f"  Drift estimate:    {report['drift_estimate_ms']:.2f} ms (start vs end window)")
    if report.get("echo_suppress_strength"):
        print(f"  Echo suppress:     {report['echo_suppress_strength']:.2f} (k_ab={report.get('echo_suppress_k_ab')}, k_ba={report.get('echo_suppress_k_ba')})")
    if report.get("rms_match") and not report.get("rms_match_skipped"):
        boosted = report.get("rms_match_boosted", "?")
        ga = report.get("rms_match_gain_a", 1.0)
        gb = report.get("rms_match_gain_b", 1.0)
        ra = report.get("rms_match_pre_a", 0.0)
        rb = report.get("rms_match_pre_b", 0.0)
        frac = report.get("rms_match_fraction", 1.0)
        print(
            f"  RMS match:         boosted track {boosted!r} at {frac:.0%} correction "
            f"(pre RMS {ra:.5f} / {rb:.5f}, gains {ga:.3f}x / {gb:.3f}x)"
        )
    elif report.get("rms_match_skipped"):
        print(f"  RMS match:         skipped ({report['rms_match_skipped']})")
    elif report.get("rms_match") is False:
        print("  RMS match:         off")
    if report.get("gain_reduction", 1.0) > 1.01:
        print(f"  Peak limiting:     applied (pre-mix peak > 0.99)")
    if "drift_warning" in report:
        print(f"  Caveat: {report['drift_warning']}")
    if "drift_note" in report:
        print(f"  Note: {report['drift_note']}")

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        out = {**report, "output_path": str(args.output.resolve())}
        args.json_report.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"  JSON report:       {args.json_report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
