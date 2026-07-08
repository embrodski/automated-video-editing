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
    normalize_had,
    normalize_pair,
    select_kept,
)


def _article(idx: int, text: str) -> ArticleSentence:
    norm, norm_had = normalize_pair(text)
    return ArticleSentence(
        idx=idx, text=text, norm=norm, norm_had=norm_had, paragraph_idx=0,
    )


def _row(idx: int, text: str) -> TranscriptRow:
    norm, norm_had = normalize_pair(text)
    return TranscriptRow(
        idx=idx,
        start=float(idx),
        end=float(idx) + 0.5,
        text=text,
        norm=norm,
        norm_had=norm_had,
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

    def test_contraction_expansion_bidirectional(self) -> None:
        contracted = normalize("You'd be working from the office full-time.")
        expanded = normalize("You would be working from the office full-time.")
        self.assertEqual(contracted, expanded)
        self.assertIn(contracted, normalize(
            "It was a toss-up; you would be working from the office full-time, and if not."
        ))

    def test_contraction_had_matches_i_d_to_i_had(self) -> None:
        spoken = normalize_had("I'd already left when you arrived.")
        written = normalize_had("I had already left when you arrived.")
        self.assertEqual(spoken, written)
        self.assertNotEqual(normalize("I'd already left."), normalize_had("I'd already left."))

    def test_normalize_expands_digits_and_ordinals_for_spoken_match(self) -> None:
        self.assertEqual(normalize("2026"), normalize("twenty twenty-six"))
        self.assertEqual(normalize("2025"), normalize("twenty twenty-five"))
        self.assertEqual(normalize("9th"), normalize("ninth"))
        self.assertEqual(normalize("17th"), normalize("seventeenth"))
        self.assertEqual(normalize("20th"), normalize("twentieth"))
        self.assertEqual(normalize("100th"), normalize("hundredth"))
        self.assertEqual(
            normalize("released on the 9th of April 2026"),
            normalize("released on the ninth of April, twenty twenty-six"),
        )

    def test_align_rows_keeps_middle_clause_after_you_would_expansion(self) -> None:
        tossup = (
            "It was a toss-up between two people in the end, and I picked you – "
            "you would be working from the office full-time, and if you weren't a good fit "
            "then at least we wouldn't see much of you."
        )
        article = [
            _article(7, "You'd come over from New Zealand for a job."),
            _article(8, tossup),
            _article(9, "That turned out to be a fateful choice."),
        ]
        rows = [
            _row(16, "It was a toss-up between two people in the end, and I picked you."),
            _row(17, "You'd be working from the office full-time,"),
            _row(18, "and if you weren't a good fit, then at least we wouldn't see much of you."),
        ]
        matches = align_rows(
            rows=rows,
            article=article,
            threshold=0.55,
            max_span=6,
            force_keep=set(),
            force_drop=set(),
            reader_speaker_id=1,
        )
        by_idx = {m.row.idx: m for m in matches}
        self.assertFalse(by_idx[17].off_script, msg=f"row 17 score={by_idx[17].similarity} span={by_idx[17].a_start}:{by_idx[17].a_end}")
        self.assertEqual(by_idx[17].a_start, 1)
        self.assertEqual(by_idx[17].a_end, 1)
        self.assertGreaterEqual(by_idx[17].similarity, 0.55)

        kept, _notes = select_kept(matches, force_keep=set(), article=article)
        self.assertEqual([m.row.idx for m in kept], [16, 17, 18])

    def test_prefix_chunk_pair_rescues_lead_in_row(self) -> None:
        article = [
            _article(
                0,
                "If you are alone, that\u2019s okay\u2014four is ideal, but as few as two can do in a pinch.",
            ),
        ]
        prefix = _match(63, "If you are alone, that's okay.", 0, 0, 0.51)
        prefix.off_script = True
        matches = [
            _match(62, "each of you only needs to recruit one other person.", 0, 0, 0.60),
            prefix,
            _match(64, "Four is ideal, but as few as two can do in a pinch.", 0, 0, 0.90),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)

        self.assertIn(63, {m.row.idx for m in kept})
        self.assertTrue(
            any(
                ("prefix chunk" in note or "stitch" in note.lower()) and "row 63" in note
                for note in notes
            )
        )

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
            _match(42, "finally what upstanding members of the public should do", 0, 0, 0.95),
            _match(43, "despite the weakness of the foregoing arguments", 1, 1, 1.0),
            _match(44, "perhaps you give the bluetooth speaker person a dirty look", 2, 2, 1.0),
            _match(53, "probably it is because they too are very disagreeable", 3, 3, 1.0),
            _match(
                54,
                "therefore i think that upstanding members should be able to do what they want",
                0,
                0,
                0.58,
            ),
            _match(
                55,
                "therefore i think that when upstanding members encounter a bluetooth speaker person they should seize",
                4,
                4,
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

    def test_keeps_stumbled_prefix_before_suffix_clause(self) -> None:
        sentence = (
            "Detecting when the model is emotionally distressed served as a potential signal "
            "for harmful behaviours such as reward hacking."
        )
        article = [_article(0, sentence)]
        stumble = _match(10, "Detecting when the model w-- is emotionally distressed", 0, 0, 0.84)
        suffix = _match(11, "served as a potential signal for harmful behaviours such as reward hacking.", 0, 0, 0.90)

        kept, notes = select_kept([stumble, suffix], force_keep=set(), article=article)

        self.assertEqual([m.row.idx for m in kept], [10, 11])
        self.assertTrue(any("stitch" in note.lower() or "gap-fill" in note.lower() for note in notes))

    def test_gap_fill_keeps_middle_quotes_between_takes(self) -> None:
        paragraph = (
            "In an episode in which the model exploited the creation of another agent to escalate privileges, "
            "AV explanations on code used to cover its tracks showed cleanup to avoid detection, "
            "and the malicious config explicitly mirrors the original core section to avoid detection. "
            "In a separate episode where the model had been leaked the ground truth answers, "
            "AVs surfaced additional scheming."
        )
        article = [_article(0, paragraph)]
        matches = [
            _match(24, "In an episode in which the model exploited the creation of another agent to escalate privileges,", 0, 0, 0.90),
            _match(25, "AV explanations on code used to cover its tracks showed cleanup to avoid detection,", 0, 0, 0.90),
            _match(26, "and the malicious config explicitly mirrors the original core section", 0, 0, 0.90),
            _match(27, "to avoid detection.", 0, 0, 0.90),
            _match(28, "In a separate episode where the model had been leaked the ground truth answers,", 0, 0, 0.90),
            _match(29, "AVs surfaced additional scheming.", 0, 0, 0.90),
        ]

        kept, notes = select_kept(matches, force_keep=set(), article=article)
        kept_ids = {m.row.idx for m in kept}

        self.assertIn(25, kept_ids)
        self.assertIn(26, kept_ids)
        self.assertTrue(any("gap-fill" in note.lower() for note in notes))
        self.assertGreater(len(kept_ids & {24, 25, 26, 27, 28, 29}), 3)

    def test_stitches_tail_with_earlier_prefix_on_same_span(self) -> None:
        opening = (
            "With the release of Claude Mythos, it feels like we are approaching the end-game "
            "of AI safety, where the number of parties that can make a real impact shrinks down "
            "to the handful of labs at the frontier, a few companies too critical to exclude "
            "from the conversation, and the governments of China and the US."
        )
        article = [_article(5, opening), _article(6, "Given this, it feels hard.")]
        matches = [
            _match(2, "With the release of Claude Mythos, it feels like we're approaching some kind of endgame", 0, 0, 0.46),
            _match(3, "of AI safety, where the number of parties that can make a real impact", 0, 0, 0.40),
            _match(4, "shrinks down to the handful of labs at the frontier,", 0, 0, 0.90),
            _match(5, "a few companies too critical to exclude from the conversation", 0, 0, 0.42),
            _match(6, "conversation, and the governments of China and the US.", 0, 0, 0.90),
            _match(7, "Given this, it feels hard.", 1, 1, 1.0),
        ]
        matches[0].off_script = True
        matches[1].off_script = True
        matches[3].off_script = True

        kept, notes = select_kept(matches, force_keep=set(), article=article)
        kept_ids = {m.row.idx for m in kept}

        self.assertIn(4, kept_ids)
        self.assertIn(6, kept_ids)
        self.assertTrue(
            any("stitch" in note.lower() or "split chunk" in note for note in notes)
        )

    def test_sanity_report_flags_partial_coverage(self) -> None:
        opening = (
            "With the release of Claude Mythos, it feels like we are approaching the end-game "
            "of AI safety, where the number of parties that can make a real impact shrinks down "
            "to the handful of labs at the frontier, a few companies too critical to exclude "
            "from the conversation, and the governments of China and the US."
        )
        article = [_article(0, opening)]
        kept = [_match(1, "conversation, and the governments of China and the US.", 0, 0, 0.90)]

        report = build_sanity_report(
            article=article,
            kept=kept,
            selection_notes=[],
            article_path=Path("reading_article.txt"),
            transcript_path=Path("reading_transcript_simplified.json"),
        )

        self.assertEqual(report["summary"]["partial_coverage_count"], 1)
        self.assertEqual(report["partial_coverage_chunks"][0]["idx"], 0)
        self.assertLess(report["partial_coverage_chunks"][0]["coverage"], 0.55)

    def test_prunes_spurious_short_suffix_match(self) -> None:
        article = [
            _article(6, "Given this, it feels hard to make a difference."),
            _article(61, "Comment"),
        ]
        spurious = _match(48, "content.", 1, 1, 0.71)
        good = _match(49, "Given this, it feels hard to make a difference.", 0, 0, 1.0)

        kept, notes = select_kept([spurious, good], force_keep=set(), article=article)

        self.assertNotIn(48, {m.row.idx for m in kept})
        self.assertTrue(any("Pruned spurious" in note for note in notes))

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
