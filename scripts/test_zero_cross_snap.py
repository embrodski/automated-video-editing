#!/usr/bin/env python3
"""Tests for podcast_dsl.zero_cross_snap."""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from podcast_dsl.zero_cross_snap import (
    pick_best_zero_crossing,
    snap_boundary_group_time,
    snap_interior_boundaries,
)


class ZeroCrossSnapTests(unittest.TestCase):
    def test_pick_best_zero_crossing_finds_center_crossing(self) -> None:
        sr = 1000
        half = 0.2
        center = 1.0
        window_start = 0.8
        samples = []
        for i in range(int(0.4 * sr) + 1):
            t = window_start + i / sr
            samples.append(math.sin(2 * math.pi * 5 * (t - center)))
        found = pick_best_zero_crossing(samples, window_start, sr, center, half)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found, center, delta=0.02)

    def test_snap_interior_boundaries_monotonic(self) -> None:
        clip_infos = [
            {
                "clip_info": {
                    "video_file": "a.mp4",
                    "video_start": 0.0,
                    "audio_start": 0.0,
                },
            },
            {
                "clip_info": {
                    "video_file": "b.mp4",
                    "video_start": 10.0,
                    "audio_start": 10.0,
                },
            },
        ]
        bounds = [0.0, 10.0, 20.0]
        # No ffmpeg / files: snap is a no-op but must stay ordered.
        snap_interior_boundaries(bounds, clip_infos, half_window_sec=0.2)
        self.assertEqual(bounds, [0.0, 10.0, 20.0])

    def test_snap_boundary_without_files_returns_nominal(self) -> None:
        out = {
            "video_file": "/nonexistent/front.mp4",
            "video_start": 0.0,
            "audio_start": 0.0,
        }
        inc = {
            "video_file": "/nonexistent/side.mp4",
            "video_start": 5.0,
            "audio_start": 5.0,
        }
        self.assertEqual(
            snap_boundary_group_time(5.0, out, inc, half_window_sec=0.2),
            5.0,
        )


if __name__ == "__main__":
    unittest.main()
