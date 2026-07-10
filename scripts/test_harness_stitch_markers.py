"""Unit tests for harness stitch timecode marker parsing."""

from __future__ import annotations

import unittest

from harness_episode_lib import STITCH_TIMECODE_MARKER_RE


class StitchTimecodeMarkerTests(unittest.TestCase):
    def test_standard_mmss(self) -> None:
        self.assertTrue(STITCH_TIMECODE_MARKER_RE.match("00:00 Intro"))
        self.assertTrue(STITCH_TIMECODE_MARKER_RE.match("12:34 Reading"))

    def test_unpadded_minutes_over_100(self) -> None:
        self.assertTrue(STITCH_TIMECODE_MARKER_RE.match("105:30 Sponsor"))

    def test_rejects_non_markers(self) -> None:
        self.assertIsNone(STITCH_TIMECODE_MARKER_RE.match("Done! Output: Complete Episode.mp4"))
        self.assertIsNone(STITCH_TIMECODE_MARKER_RE.match("not a marker"))


if __name__ == "__main__":
    unittest.main()
