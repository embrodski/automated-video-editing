"""Tests for harness failure notification helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from harness_notify_failure import (
    FAILURE_JSON_NAME,
    summarize_error,
    write_failure_artifacts,
)


class SummarizeErrorTests(unittest.TestCase):
    def test_elevenlabs_payment(self) -> None:
        exc = RuntimeError(
            'ElevenLabs API HTTP 401: {"detail":{"type":"payment_required",'
            '"message":"Complete the latest invoice"}}'
        )
        summary = summarize_error(exc)
        self.assertIn("billing/payment", summary.lower())
        self.assertIn("ElevenLabs", summary)

    def test_generic_runtime_error(self) -> None:
        summary = summarize_error(RuntimeError("ffmpeg audio clip failed"))
        self.assertIn("ffmpeg", summary)


class FailureArtifactTests(unittest.TestCase):
    def test_writes_json_and_txt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            json_path, txt_path = write_failure_artifacts(
                temp,
                pipeline="piab_prep",
                step_id="09_transcribe",
                step_title="Transcribe prepped WAV",
                error_summary="Test failure",
                error_detail="detail here",
                working_folder=Path("E:/Demo"),
            )
            self.assertEqual(json_path.name, FAILURE_JSON_NAME)
            self.assertTrue(txt_path.is_file())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["notify_immediately"])
            self.assertEqual(payload["step_id"], "09_transcribe")
            self.assertIn("Test failure", txt_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
