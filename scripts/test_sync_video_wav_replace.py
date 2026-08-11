"""Tests for sync_video_wav_replace alignment fallback."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sync_video_wav_replace import (
    DEFAULT_MIN_CORRELATION_STRENGTH,
    _align_external_to_reference,
)


class SyncVideoWavReplaceTests(unittest.TestCase):
    def test_weak_correlation_uses_start_aligned_mux(self) -> None:
        sr = 48000
        n = sr * 2
        rng = np.random.default_rng(0)
        ref_mono = rng.normal(0, 0.2, n).astype(np.float32)
        external = rng.normal(0, 0.2, (n, 2)).astype(np.float32)

        aligned, report = _align_external_to_reference(
            ref_mono,
            sr,
            external,
            sr,
            analyze_seconds=1.0,
            min_correlation_strength=DEFAULT_MIN_CORRELATION_STRENGTH,
        )

        self.assertTrue(report["start_aligned"])
        self.assertTrue(report["start_aligned_fallback"])
        self.assertEqual(report["lag_samples_external_delayed_vs_video_audio"], 0)
        self.assertLess(report["correlation_peak_strength"], DEFAULT_MIN_CORRELATION_STRENGTH)
        np.testing.assert_array_equal(aligned, external[:n])

    def test_strong_correlation_applies_detected_lag(self) -> None:
        sr = 48000
        n = sr * 2
        t = np.arange(n, dtype=np.float32) / sr
        ref_mono = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        external = np.stack([ref_mono, ref_mono * 0.8], axis=1)

        aligned, report = _align_external_to_reference(
            ref_mono,
            sr,
            external,
            sr,
            analyze_seconds=1.0,
            min_correlation_strength=DEFAULT_MIN_CORRELATION_STRENGTH,
        )

        self.assertFalse(report["start_aligned"])
        self.assertGreater(report["correlation_peak_strength"], 0.9)
        self.assertEqual(report["lag_samples_external_delayed_vs_video_audio"], 0)
        np.testing.assert_allclose(aligned[:, 0], ref_mono, atol=0.01)

    def test_assume_start_aligned_skips_lag_even_with_strong_signal(self) -> None:
        sr = 48000
        n = sr * 2
        t = np.arange(n, dtype=np.float32) / sr
        ref_mono = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        delay = sr // 10
        delayed = np.zeros(n, dtype=np.float32)
        delayed[delay:] = ref_mono[: n - delay]
        external = np.stack([delayed, delayed * 0.8], axis=1)

        aligned, report = _align_external_to_reference(
            ref_mono,
            sr,
            external,
            sr,
            analyze_seconds=1.0,
            assume_start_aligned=True,
        )

        self.assertTrue(report["start_aligned"])
        self.assertEqual(report["lag_samples_external_delayed_vs_video_audio"], 0)
        np.testing.assert_array_equal(aligned, external[:n])

    def test_force_detected_lag_applies_offset_despite_weak_correlation(self) -> None:
        sr = 48000
        n = sr * 2
        rng = np.random.default_rng(0)
        ref_mono = rng.normal(0, 0.2, n).astype(np.float32)
        external = rng.normal(0, 0.2, (n, 2)).astype(np.float32)

        aligned_weak, report_weak = _align_external_to_reference(
            ref_mono,
            sr,
            external,
            sr,
            analyze_seconds=1.0,
            min_correlation_strength=DEFAULT_MIN_CORRELATION_STRENGTH,
        )
        aligned_forced, report_forced = _align_external_to_reference(
            ref_mono,
            sr,
            external,
            sr,
            analyze_seconds=1.0,
            min_correlation_strength=DEFAULT_MIN_CORRELATION_STRENGTH,
            force_detected_lag=True,
        )

        self.assertTrue(report_weak["start_aligned"])
        self.assertFalse(report_forced["start_aligned"])
        self.assertTrue(report_forced.get("force_detected_lag"))


if __name__ == "__main__":
    unittest.main()
