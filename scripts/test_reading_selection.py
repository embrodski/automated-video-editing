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
    build_sanity_report,
    select_kept,
)


def _article(idx: int, text: str) -> ArticleSentence:
    return ArticleSentence(idx=idx, text=text, norm=text.lower(), paragraph_idx=0)


def _row(idx: int, text: str) -> TranscriptRow:
    return TranscriptRow(
        idx=idx,
        start=float(idx),
        end=float(idx) + 0.5,
        text=text,
        norm=text.lower(),
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
        self.assertEqual(report["blocking_issues"][0]["idx"], 1)
        self.assertEqual([w["idx"] for w in report["warnings"]], [3, 4])

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


if __name__ == "__main__":
    unittest.main()
