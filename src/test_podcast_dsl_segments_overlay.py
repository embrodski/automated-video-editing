"""Unit tests for podcast_dsl segment overlay loading."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from podcast_dsl.config import (
    clear_segments_overlay,
    get_segment_config,
    has_segment_config,
    load_segments_overlay,
)


class SegmentOverlayTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_segments_overlay()

    def test_overlay_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "segments.json"
            entry = {
                "main": {
                    "audio_file": str(path.parent / "audio.wav"),
                    "audio_offset": 0,
                    "enable_color_match": False,
                    "video_files": {
                        "speaker_0": {"file": str(path.parent / "ben.mp4"), "offset": 0},
                    },
                    "transcript_file": str(path.parent / "t.json"),
                }
            }
            path.write_text(json.dumps(entry), encoding="utf-8")
            load_segments_overlay(path)
            self.assertTrue(has_segment_config("main"))
            cfg = get_segment_config("main")
            self.assertEqual(cfg["audio_offset"], 0)
            self.assertTrue(str(cfg["audio_file"]).endswith("audio.wav"))

    def test_legacy_fallback(self) -> None:
        clear_segments_overlay()
        self.assertTrue(has_segment_config("1"))
        cfg = get_segment_config("1")
        self.assertIn("video_files", cfg)


if __name__ == "__main__":
    unittest.main()
