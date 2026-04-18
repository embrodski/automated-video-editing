#!/usr/bin/env python3
"""Regression tests for interview DSL generation."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_full_dsl import Row, _find_wide_spans, _intended_camera, _row_segment_line


class GenerateFullDslTests(unittest.TestCase):
    def test_final_row_gets_default_two_second_tail(self) -> None:
        row = Row(
            idx=12,
            start=10.0,
            end=11.5,
            text="Closing line",
            speaker_id=1,
            speaker_name="Guest",
        )

        line = _row_segment_line(
            row,
            "17",
            include_fallback_speaker=True,
            is_last=True,
            final_shot_tail_sec=2.0,
        )

        self.assertEqual(
            line,
            "$segment17/12 slice(:3.500) // Guest: Closing line",
        )

    def test_non_final_row_is_unmodified(self) -> None:
        row = Row(
            idx=11,
            start=8.0,
            end=9.0,
            text="Penultimate line",
            speaker_id=0,
            speaker_name="",
        )

        line = _row_segment_line(
            row,
            "17",
            include_fallback_speaker=True,
            is_last=False,
            final_shot_tail_sec=2.0,
        )

        self.assertEqual(line, "$segment17/11 // Speaker 0: Penultimate line")

    def test_dense_cut_wide_rule_still_applies_with_final_tail_change(self) -> None:
        rows = [
            Row(idx=0, start=0.0, end=1.0, text="a", speaker_id=0, speaker_name=""),
            Row(idx=1, start=1.0, end=2.0, text="b", speaker_id=1, speaker_name=""),
            Row(idx=2, start=2.0, end=3.0, text="c", speaker_id=0, speaker_name=""),
            Row(idx=3, start=7.5, end=8.5, text="d", speaker_id=1, speaker_name=""),
        ]

        spans = _find_wide_spans(
            rows,
            _intended_camera(rows),
            window_sec=5.0,
            min_wide_sec=5.0,
        )

        self.assertEqual(spans, [(1, 3)])


if __name__ == "__main__":
    unittest.main()
