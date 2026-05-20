#!/usr/bin/env python3
"""Regression tests for reading DSL row selection."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_reading_dsl import (
    ArticleSentence,
    RowMatch,
    TranscriptRow,
    align_rows,
    build_sanity_report,
    is_visual_callout_sentence,
    normalize,
    select_kept,
)


def _article(idx: int, text: str) -> ArticleSentence:
    return ArticleSentence(idx=idx, text=text, norm=normalize(text), paragraph_idx=0)


def _row(idx: int, text: str) -> TranscriptRow:
    return TranscriptRow(
        idx=idx,
        start=float(idx),
        end=float(idx) + 0.5,
        text=text,
        norm=normalize(text),
        speaker_id=1,
        words=[],
    )


def _match(row_idx: int, text: str, a_start: int, a_end: int, similarity: float = 1.0) -> RowMatch:
    return RowMatch(
        row=_row(row_idx, text),
        a_start=a_start,
        a_end=a_end,
        similarity=similarity,
        off_script=False,
    )


class ReadingSelectionTests(unittest.TestCase):
    def test_keeps_split_chunk_across_adjacent_rows(self) -> None:
        article = [
            _article(
                0,
                "if other workers have a lot of skill, i will also try to get educated, "
                "but if other agents do not get much education, then i will not either",
            ),
            _article(1, "these multiple equilibria exist"),
        ]
        matches = [
            _match(70, "if other workers have a lot of skill, i will also try to get educated", 0, 0, 0.66),
            _match(71, "but if other workers do not get much education, then i will not either", 0, 0, 0.63),
            _match(72, "these multiple equilibria exist", 1, 1, 1.0),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)

        self.assertEqual([m.row.idx for m in kept], [70, 71, 72])
        self.assertTrue(any("row 70" in note for note in notes))

    def test_still_drops_duplicate_reread_same_chunk(self) -> None:
        article = [_article(0, "the o ring theory is influential")]
        matches = [
            _match(10, "the o ring theory is influential", 0, 0, 1.0),
            _match(11, "the o ring theory is influential", 0, 0, 1.0),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)

        self.assertEqual([m.row.idx for m in kept], [11])
        self.assertEqual(notes, [])

    def test_normalize_maps_curly_apostrophe_for_substring_match(self) -> None:
        article_line = "If you are alone, that\u2019s okay\u2014four is ideal."
        spoken = "If you are alone, that's okay."
        self.assertIn(normalize(spoken), normalize(article_line))

    def test_prefix_chunk_pair_rescues_lead_in_row(self) -> None:
        article = [
            _article(
                0,
                "If you are alone, that\u2019s okay\u2014four is ideal, but as few as two can do in a pinch.",
            ),
        ]
        prefix = _match(63, "If you are alone, that's okay.", 75, 75, 0.51)
        prefix.off_script = True
        matches = [
            _match(62, "each of you only needs to recruit one other person.", 58, 58, 0.60),
            prefix,
            _match(64, "Four is ideal, but as few as two can do in a pinch.", 0, 0, 0.90),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)

        self.assertIn(63, {m.row.idx for m in kept})
        self.assertTrue(any("prefix chunk" in note and "row 63" in note for note in notes))

    def test_weak_late_header_match_does_not_drop_middle_paragraphs(self) -> None:
        """Regression: Viv-style flub matched only the section header must not erase rows 42-49."""
        article = [
            _article(41, "what upstanding members of the public should do about bluetooth speaker people"),
            _article(42, "despite the weakness of the foregoing arguments"),
            _article(43, "perhaps you give the bluetooth speaker person a dirty look"),
            _article(49, "probably it is because they too are very disagreeable"),
            _article(50, "therefore i think that when upstanding members encounter a bluetooth speaker person they should seize"),
        ]
        matches = [
            _match(42, "finally what upstanding members of the public should do", 41, 41, 0.95),
            _match(43, "despite the weakness of the foregoing arguments", 42, 42, 1.0),
            _match(44, "perhaps you give the bluetooth speaker person a dirty look", 43, 43, 1.0),
            _match(53, "probably it is because they too are very disagreeable", 49, 49, 1.0),
            _match(
                54,
                "therefore i think that upstanding members should be able to do what they want",
                41,
                41,
                0.58,
            ),
            _match(
                55,
                "therefore i think that when upstanding members encounter a bluetooth speaker person they should seize",
                50,
                50,
                1.0,
            ),
        ]

        kept, _notes = select_kept(matches, force_keep=set(), article=article)

        self.assertEqual([m.row.idx for m in kept], [42, 43, 44, 53, 55])
        self.assertNotIn(54, {m.row.idx for m in kept})

    def test_sanity_report_flags_internal_missing_but_allows_trailing_missing(self) -> None:
        article = [
            _article(0, "title"),
            _article(1, "body one"),
            _article(2, "body two"),
            _article(3, "tail one"),
            _article(4, "tail two"),
        ]
        kept = [
            _match(10, "title", 0, 0),
            _match(11, "body two", 2, 2),
        ]

        report = build_sanity_report(
            article=article,
            kept=kept,
            selection_notes=[],
            article_path=Path("reading_article.txt"),
            transcript_path=Path("reading_transcript_simplified.json"),
        )

        self.assertEqual(report["summary"]["internal_missing_count"], 1)
        self.assertEqual(report["summary"]["trailing_missing_count"], 2)
        self.assertEqual(report["blocking_issues"], [])
        self.assertEqual(sorted(w["idx"] for w in report["warnings"]), [1, 3, 4])

    def test_keeps_split_chunk_when_first_half_is_below_threshold(self) -> None:
        article = [
            _article(
                0,
                "the story is less plausible when it concerns janitors surely interfirm equity "
                "issues of some kind provide a better explanation but the theory is clever nonetheless",
            ),
            _article(1, "kremer further considers sequential production"),
        ]
        first = _match(43, "the story is less plausible when it concerns janitor", 0, 0, 0.48)
        first.off_script = True
        matches = [
            first,
            _match(
                44,
                "surely inter firm equity issues of some kind provide a better explanation but the theory is clever nonetheless",
                0,
                0,
                0.80,
            ),
            _match(45, "kremer further considers sequential production", 1, 1, 1.0),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)

        self.assertEqual([m.row.idx for m in kept], [43, 44, 45])
        self.assertTrue(any("row 43" in note for note in notes))

    def test_keeps_split_chunk_when_second_half_is_below_threshold(self) -> None:
        article = [
            _article(
                0,
                "the discrimination argument relies heavily on the fact that errors on education "
                "and on test scores are normally distributed hence no matter what the true quality "
                "test scores have full support",
            ),
            _article(1, "if this werent the case"),
        ]
        second = _match(101, "hence no matter what the true quality test scores have full support", 0, 0, 0.52)
        second.off_script = True
        matches = [
            _match(
                100,
                "the discrimination argument relies heavily on the fact that errors on education and on test score are normally distributed",
                0,
                0,
                0.77,
            ),
            second,
            _match(102, "if this werent the case", 1, 1, 1.0),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)

        self.assertEqual([m.row.idx for m in kept], [100, 101, 102])
        self.assertTrue(any("row 101" in note for note in notes))

    def test_section_header_callouts_are_keep_anyway_rows(self) -> None:
        examples = [
            "This section is called Middle Income Traps.",
            "Section 3 is about wage polarization.",
            "The next section is called policy implications.",
            "The section title is Further Reading.",
        ]

        for idx, text in enumerate(examples, start=1):
            with self.subTest(text=text):
                self.assertTrue(is_visual_callout_sentence(text))

                matches = align_rows(
                    rows=[_row(idx, text)],
                    article=[_article(0, "the article begins here")],
                    threshold=0.55,
                    max_span=6,
                    force_keep=set(),
                    force_drop=set(),
                    reader_speaker_id=1,
                )

                self.assertEqual(len(matches), 1)
                self.assertTrue(matches[0].keep_anyway)
                self.assertFalse(matches[0].off_script)


if __name__ == "__main__":
    unittest.main()
