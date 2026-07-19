"""Tests for episode-only reading spoken expansions (not shared normalizer)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_episode_lib import (
    apply_episode_reading_spoken_expansions,
    apply_spoken_text_expansions,
    reading_spoken_expansions,
)


class ReadingSpokenExpansionsTests(unittest.TestCase):
    def test_reads_expansions_from_episode_notes(self) -> None:
        state = {
            "reading_dsl_notes": {
                "normalize_expansions": {"<": "less than", "pp": "percentage points"}
            }
        }
        self.assertEqual(
            reading_spoken_expansions(state),
            {"<": "less than", "pp": "percentage points"},
        )
        self.assertEqual(reading_spoken_expansions({}), {})

    def test_expands_less_than_and_standalone_pp(self) -> None:
        expansions = {"<": "less than", "pp": "percentage points"}
        self.assertEqual(
            apply_spoken_text_expansions("p < 0.05", expansions),
            "p less than 0.05",
        )
        self.assertEqual(
            apply_spoken_text_expansions("+0.3 pp", expansions),
            "+0.3 percentage points",
        )
        self.assertEqual(
            apply_spoken_text_expansions("the app store", expansions),
            "the app store",
        )
        self.assertNotIn(
            "percentage points",
            apply_spoken_text_expansions("opportunity", expansions),
        )

    def test_rewrites_article_and_simplified_transcript(self) -> None:
        expansions = {"<": "less than", "pp": "percentage points"}
        state = {"reading_dsl_notes": {"normalize_expansions": expansions}}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            article = root / "reading_article.txt"
            simplified = root / "reading_transcript_simplified.json"
            article.write_text("Rise by +0.3 pp (p < 0.05).\n", encoding="utf-8")
            simplified.write_text(
                json.dumps(
                    {
                        "1": {
                            "text": "Rise by +0.3 pp (p < 0.05).",
                            "words": [{"text": "pp"}, {"text": "app"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            rewritten = apply_episode_reading_spoken_expansions(
                state,
                article_txt=article,
                simplified_json=simplified,
            )
            self.assertEqual(len(rewritten), 2)
            self.assertIn("percentage points", article.read_text(encoding="utf-8"))
            self.assertIn("less than", article.read_text(encoding="utf-8"))
            data = json.loads(simplified.read_text(encoding="utf-8"))
            self.assertIn("percentage points", data["1"]["text"])
            self.assertEqual(data["1"]["words"][0]["text"].strip(), "percentage points")
            self.assertEqual(data["1"]["words"][1]["text"], "app")


if __name__ == "__main__":
    unittest.main()
