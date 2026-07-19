#!/usr/bin/env python3
"""Regression tests for interview DSL generation."""

from pathlib import Path
import sys
import tempfile
import unittest
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_full_dsl import (
    Row,
    WordToken,
    _apply_end_phrase,
    _apply_start_phrase,
    _find_wide_spans,
    _intended_camera,
    _row_segment_line,
)


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
            window_sec=3.0,
            min_wide_sec=3.0,
        )

        self.assertEqual(spans, [(1, 3)])


def _words(*pairs: tuple[str, float, float]) -> tuple[WordToken, ...]:
    return tuple(WordToken(text=t, start=s, end=e) for t, s, e in pairs)


class StartEndPhraseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            Row(
                idx=0,
                start=0.0,
                end=5.0,
                text="Setup chatter before we begin.",
                speaker_id=0,
                speaker_name="Host",
                words=_words(
                    ("Setup", 0.0, 0.4),
                    ("chatter", 0.5, 1.0),
                    ("before", 1.1, 1.4),
                    ("we", 1.5, 1.6),
                    ("begin.", 1.7, 2.1),
                ),
            ),
            Row(
                idx=1,
                start=10.0,
                end=14.0,
                text="Hut of brown, now sit down. Jolly!",
                speaker_id=0,
                speaker_name="Host",
                words=_words(
                    ("Hut", 10.0, 10.2),
                    ("of", 10.3, 10.4),
                    ("brown,", 10.5, 10.8),
                    ("now", 11.0, 11.2),
                    ("sit", 11.3, 11.5),
                    ("down.", 11.6, 12.0),
                    ("Jolly!", 12.5, 13.0),
                ),
            ),
            Row(
                idx=2,
                start=20.0,
                end=24.0,
                text="That was fun. Hut of brown, now stand up. Goodbye.",
                speaker_id=1,
                speaker_name="Guest",
                words=_words(
                    ("That", 20.0, 20.3),
                    ("was", 20.4, 20.6),
                    ("fun.", 20.7, 21.0),
                    ("Hut", 21.2, 21.4),
                    ("of", 21.5, 21.6),
                    ("brown,", 21.7, 22.0),
                    ("now", 22.1, 22.3),
                    ("stand", 22.4, 22.7),
                    ("up.", 22.8, 23.0),
                    ("Goodbye.", 23.2, 23.8),
                ),
            ),
        ]

    def test_start_phrase_cuts_one_second_before_next_word(self) -> None:
        cut = _apply_start_phrase(
            self.rows,
            "Hut of brown, now sit down.",
            preroll_sec=1.0,
        )
        self.assertEqual([r.idx for r in cut.rows], [1, 2])
        self.assertEqual(cut.next_word_text, "jolly")
        self.assertAlmostEqual(cut.content_start_abs, 12.5)
        # Jolly starts 2.5s into row 1 -> slice_start 2.5; !opening supplies the 1s preroll.
        self.assertAlmostEqual(cut.first_slice_start or -1.0, 2.5)

    def test_start_phrase_ignores_case_and_punctuation(self) -> None:
        cut = _apply_start_phrase(
            self.rows,
            "hut of brown now sit down",
            preroll_sec=1.0,
        )
        self.assertEqual(cut.next_word_text, "jolly")
        self.assertEqual(cut.host_speaker_id, 0)

    def test_start_phrase_speaker_becomes_host_camera(self) -> None:
        from generate_full_dsl import _cam_by_speaker_with_host, _main_impl
        import sys as _sys

        self.assertEqual(
            _cam_by_speaker_with_host(1, {0: "speaker_0", 1: "speaker_1"}),
            {0: "speaker_1", 1: "speaker_0"},
        )
        self.assertEqual(
            _cam_by_speaker_with_host(0, {0: "speaker_0", 1: "speaker_1"}),
            {0: "speaker_0", 1: "speaker_1"},
        )

        # Speaker 1 says the start phrase → their lines should use !camera speaker_0.
        transcript = {
            "0": {
                "start": 10.0,
                "end": 14.0,
                "text": "Hut of brown, now sit down. Jolly!",
                "speaker_id": 1,
                "speaker_name": "Host",
                "words": [
                    {"text": "Hut", "start": 10.0, "end": 10.2},
                    {"text": "of", "start": 10.3, "end": 10.4},
                    {"text": "brown,", "start": 10.5, "end": 10.8},
                    {"text": "now", "start": 11.0, "end": 11.2},
                    {"text": "sit", "start": 11.3, "end": 11.5},
                    {"text": "down.", "start": 11.6, "end": 12.0},
                    {"text": "Jolly!", "start": 12.5, "end": 13.0},
                ],
            },
            "1": {
                "start": 20.0,
                "end": 21.0,
                "text": "Hello there.",
                "speaker_id": 0,
                "speaker_name": "Guest",
                "words": [
                    {"text": "Hello", "start": 20.0, "end": 20.4},
                    {"text": "there.", "start": 20.5, "end": 21.0},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "t.json"
            out = Path(td) / "out.dsl"
            src.write_text(json.dumps(transcript), encoding="utf-8")
            argv = [
                "generate_full_dsl.py",
                str(src),
                "--segment",
                "main",
                "--output",
                str(out),
                "--start-phrase",
                "Hut of brown, now sit down.",
                "--no-camera-switch-offset",
                "--open-ben-sec",
                "0",
                "--tail-ben-sec",
                "0",
            ]
            old = _sys.argv
            try:
                _sys.argv = argv
                rc = _main_impl()
            finally:
                _sys.argv = old
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("Host = transcript speaker_id 1 -> speaker_0", text)
            self.assertIn("Speaker 1 -> speaker_0", text)
            self.assertIn("Speaker 0 -> speaker_1", text)
            # After the start cut, first kept content is still speaker_id 1 ("Jolly").
            self.assertRegex(text, r"!camera speaker_0\s*\n\$segmentmain/0")

    def test_end_phrase_keeps_one_second_after_prior_word(self) -> None:
        # First apply start so end phrase matches the later occurrence contextually.
        started = _apply_start_phrase(
            self.rows,
            "Hut of brown, now sit down.",
            preroll_sec=1.0,
        )
        cut = _apply_end_phrase(
            started.rows,
            "Hut of brown, now stand up.",
            postroll_sec=1.0,
        )
        self.assertEqual([r.idx for r in cut.rows], [1, 2])
        self.assertEqual(cut.last_word_text, "fun")
        # fun ends at 21.0; +1s postroll = 22.0; relative to row start 20.0 => 2.0
        self.assertAlmostEqual(cut.content_end_abs, 22.0)
        self.assertAlmostEqual(cut.last_slice_end or -1.0, 2.0)

    def test_missing_start_phrase_errors(self) -> None:
        with self.assertRaises(ValueError):
            _apply_start_phrase(self.rows, "this phrase does not exist", preroll_sec=1.0)

    def test_cli_emits_opening_and_slice(self) -> None:
        transcript = {
            "0": {
                "start": 10.0,
                "end": 14.0,
                "text": "Hut of brown, now sit down. Jolly!",
                "speaker_id": 0,
                "speaker_name": "Host",
                "words": [
                    {"text": "Hut", "start": 10.0, "end": 10.2},
                    {"text": "of", "start": 10.3, "end": 10.4},
                    {"text": "brown,", "start": 10.5, "end": 10.8},
                    {"text": "now", "start": 11.0, "end": 11.2},
                    {"text": "sit", "start": 11.3, "end": 11.5},
                    {"text": "down.", "start": 11.6, "end": 12.0},
                    {"text": "Jolly!", "start": 12.5, "end": 13.0},
                ],
            },
            "1": {
                "start": 20.0,
                "end": 21.0,
                "text": "Hello there.",
                "speaker_id": 1,
                "speaker_name": "Guest",
                "words": [
                    {"text": "Hello", "start": 20.0, "end": 20.4},
                    {"text": "there.", "start": 20.5, "end": 21.0},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "t.json"
            out = Path(td) / "out.dsl"
            src.write_text(json.dumps(transcript), encoding="utf-8")
            from generate_full_dsl import _main_impl
            import sys as _sys

            argv = [
                "generate_full_dsl.py",
                str(src),
                "--segment",
                "main",
                "--output",
                str(out),
                "--start-phrase",
                "Hut of brown, now sit down.",
                "--no-camera-switch-offset",
                "--open-ben-sec",
                "0",
                "--tail-ben-sec",
                "0",
            ]
            old = _sys.argv
            try:
                _sys.argv = argv
                rc = _main_impl()
            finally:
                _sys.argv = old
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            self.assertIn("!opening 1000", text)
            self.assertIn("slice(2.500:", text)


class PauseUnpauseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            Row(
                idx=0,
                start=0.0,
                end=5.0,
                text="Hello there friend.",
                speaker_id=0,
                speaker_name="Host",
                words=_words(
                    ("Hello", 0.0, 0.4),
                    ("there", 0.5, 0.8),
                    ("friend.", 0.9, 1.3),
                ),
            ),
            Row(
                idx=1,
                start=5.0,
                end=12.0,
                text="Computer Freeze Program. Secret stuff here.",
                speaker_id=0,
                speaker_name="Host",
                words=_words(
                    ("Computer", 5.0, 5.4),
                    ("Freeze", 5.5, 5.9),
                    ("Program.", 6.0, 6.5),
                    ("Secret", 7.0, 7.4),
                    ("stuff", 7.5, 7.9),
                    ("here.", 8.0, 8.4),
                ),
            ),
            Row(
                idx=2,
                start=12.0,
                end=20.0,
                text="Computer Resume Program. Welcome back everyone.",
                speaker_id=1,
                speaker_name="Guest",
                words=_words(
                    ("Computer", 12.0, 12.4),
                    ("Resume", 12.5, 12.9),
                    ("Program.", 13.0, 13.5),
                    ("Welcome", 14.0, 14.4),
                    ("back", 14.5, 14.8),
                    ("everyone.", 14.9, 15.5),
                ),
            ),
        ]

    def test_matched_pair_removes_middle_and_marks_seam(self) -> None:
        from generate_full_dsl import _apply_pause_unpause_to_pieces

        pieces, notes = _apply_pause_unpause_to_pieces(
            self.rows,
            pause_phrase="Computer Freeze Program.",
            unpause_phrases=["Computer Resume Program", "Computer Unfreeze Program"],
            preroll_sec=0.25,
            postroll_sec=0.7,
            first_slice_start=None,
            last_slice_end=None,
        )
        self.assertTrue(any("Pause" in n for n in notes))
        # Should keep intro + resume content; drop secret stuff.
        texts = " ".join(p.row.text for p in pieces)
        self.assertIn("Hello", texts)
        self.assertIn("Welcome", texts)
        # Seam piece is the resume side.
        self.assertTrue(any(p.seam_after_pause for p in pieces))

    def test_unmatched_pause_left_in(self) -> None:
        from generate_full_dsl import _apply_pause_unpause_to_pieces

        rows = self.rows[:2]  # no unpause
        pieces, _notes = _apply_pause_unpause_to_pieces(
            rows,
            pause_phrase="Computer Freeze Program.",
            unpause_phrases=["Computer Resume Program"],
            preroll_sec=0.25,
            postroll_sec=0.7,
            first_slice_start=None,
            last_slice_end=None,
        )
        self.assertEqual(len(pieces), 2)
        self.assertFalse(any(p.seam_after_pause for p in pieces))

    def test_abort_disables_pause(self) -> None:
        from generate_full_dsl import _phrase_exists, _main_impl
        import sys as _sys

        rows = self.rows + [
            Row(
                idx=3,
                start=30.0,
                end=35.0,
                text="Emergency override - Eject the warp core",
                speaker_id=0,
                speaker_name="Host",
                words=_words(
                    ("Emergency", 30.0, 30.5),
                    ("override", 30.6, 31.1),
                    ("Eject", 31.5, 31.9),
                    ("the", 32.0, 32.1),
                    ("warp", 32.2, 32.5),
                    ("core", 32.6, 33.0),
                ),
            )
        ]
        self.assertTrue(
            _phrase_exists(rows, "Emergency override - Eject the warp core")
        )

        transcript = {
            str(r.idx): {
                "start": r.start,
                "end": r.end,
                "text": r.text,
                "speaker_id": r.speaker_id,
                "speaker_name": r.speaker_name,
                "words": [
                    {"text": w.text, "start": w.start, "end": w.end} for w in r.words
                ],
            }
            for r in rows
        }
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "t.json"
            out = Path(td) / "out.dsl"
            src.write_text(json.dumps(transcript), encoding="utf-8")
            argv = [
                "generate_full_dsl.py",
                str(src),
                "--segment",
                "main",
                "--output",
                str(out),
                "--pause-phrase",
                "Computer Freeze Program.",
                "--unpause-phrase",
                "Computer Resume Program",
                "--unpause-phrase",
                "Computer Unfreeze Program",
                "--abort-phrase",
                "Emergency override - Eject the warp core",
                "--no-cameras",
                "--no-camera-switch-offset",
            ]
            old = _sys.argv
            try:
                _sys.argv = argv
                rc = _main_impl()
            finally:
                _sys.argv = old
            self.assertEqual(rc, 0)
            text = out.read_text(encoding="utf-8")
            # Abort keeps the paused middle content in the cut.
            self.assertIn("Secret", text)


if __name__ == "__main__":
    unittest.main()
