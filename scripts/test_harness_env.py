"""Tests for harness dotenv loader."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from harness_env import load_harness_env, merge_env_file, parse_dotenv


class HarnessEnvTests(unittest.TestCase):
    def test_parse_dotenv_ignores_comments(self) -> None:
        values = parse_dotenv(
            "# comment\nHARNESS_SMTP_HOST=smtp.gmail.com\n\nHARNESS_SMTP_PORT=587\n"
        )
        self.assertEqual(values["HARNESS_SMTP_HOST"], "smtp.gmail.com")
        self.assertEqual(values["HARNESS_SMTP_PORT"], "587")

    def test_load_harness_env_does_not_override_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("HARNESS_SMTP_USER=from-file@gmail.com\n", encoding="utf-8")
            prior = os.environ.get("HARNESS_SMTP_USER")
            os.environ["HARNESS_SMTP_USER"] = "already-set@gmail.com"
            try:
                load_harness_env(path)
                self.assertEqual(os.environ["HARNESS_SMTP_USER"], "already-set@gmail.com")
            finally:
                if prior is None:
                    os.environ.pop("HARNESS_SMTP_USER", None)
                else:
                    os.environ["HARNESS_SMTP_USER"] = prior

    def test_merge_env_file_updates_existing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# SMTP\nHARNESS_SMTP_USER=old@gmail.com\nFRAMEIO_ACCESS_TOKEN=keep\n",
                encoding="utf-8",
            )
            merge_env_file(path, {"HARNESS_SMTP_USER": "new@gmail.com"})
            text = path.read_text(encoding="utf-8")
            self.assertIn("HARNESS_SMTP_USER=new@gmail.com", text)
            self.assertIn("FRAMEIO_ACCESS_TOKEN=keep", text)


if __name__ == "__main__":
    unittest.main()
