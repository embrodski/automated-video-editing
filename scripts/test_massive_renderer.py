#!/usr/bin/env python3
"""Regression tests for massive single-camera variant selection."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from massive_renderer import force_single_camera_dsl_text, is_reading_dsl, variant_specs_for_dsl


class MassiveRendererTests(unittest.TestCase):
    def test_reading_dsl_gets_front_and_side_variants(self) -> None:
        dsl = "\n".join(
            [
                "// Generated reading DSL (segment 20)",
                "// Cameras: speaker_0 (front, starting) / speaker_1 (side, alternate)",
                "!camera speaker_0",
                "$segment20/1 // first line",
                "!camera speaker_1",
                "$segment20/2 // second line",
            ]
        )

        self.assertTrue(is_reading_dsl(dsl))
        specs = variant_specs_for_dsl(dsl)

        self.assertEqual(
            [(spec.name, spec.camera) for spec in specs],
            [("Front Render", "speaker_0"), ("Side Render", "speaker_1")],
        )

    def test_interview_dsl_keeps_existing_ben_guest_wide_variants(self) -> None:
        dsl = "\n".join(
            [
                "// Generated full interview DSL",
                "!camera speaker_0",
                "$segment22/1 // Ben",
                "!camera wide",
                "$segment22/2 // wide",
            ]
        )

        self.assertFalse(is_reading_dsl(dsl))
        specs = variant_specs_for_dsl(dsl)

        self.assertEqual(
            [(spec.name, spec.camera) for spec in specs],
            [
                ("Ben Render", "speaker_0"),
                ("Guest Render", "speaker_1"),
                ("Wide Render", "wide"),
            ],
        )

    def test_forced_camera_dsl_replaces_camera_commands_once(self) -> None:
        dsl = "\n".join(
            [
                "// Generated reading DSL (segment 20)",
                "!camera speaker_0",
                "$segment20/1 // first line",
                "!camera speaker_1",
                "$segment20/2 // second line",
            ]
        )

        forced = force_single_camera_dsl_text(dsl, "speaker_1")

        self.assertIn("!camera speaker_1\n$segment20/1", forced)
        self.assertEqual(forced.count("!camera "), 1)


if __name__ == "__main__":
    unittest.main()
