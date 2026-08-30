#!/usr/bin/env python3
"""Tests for Windows console-hiding subprocess helpers."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from podcast_dsl.hidden_subprocess import (
    CREATE_NO_WINDOW,
    apply_hidden_kwargs,
    hidden_popen_kwargs,
    run as hidden_run,
)


class HiddenSubprocessTests(unittest.TestCase):
    def test_non_windows_kwargs_are_empty(self) -> None:
        self.assertEqual(hidden_popen_kwargs(platform="linux"), {})
        self.assertEqual(apply_hidden_kwargs({"check": True}, platform="linux"), {"check": True})

    def test_windows_kwargs_set_create_no_window(self) -> None:
        kwargs = hidden_popen_kwargs(platform="win32")
        self.assertEqual(kwargs["creationflags"] & CREATE_NO_WINDOW, CREATE_NO_WINDOW)

    def test_windows_kwargs_preserve_existing_creationflags(self) -> None:
        merged = apply_hidden_kwargs({"creationflags": 0x1, "text": True}, platform="win32")
        self.assertEqual(merged["creationflags"] & 0x1, 0x1)
        self.assertEqual(merged["creationflags"] & CREATE_NO_WINDOW, CREATE_NO_WINDOW)
        self.assertTrue(merged["text"])

    def test_hidden_run_forwards_create_no_window_on_windows(self) -> None:
        captured: dict = {}

        def fake_run(*_args, **kwargs):
            captured.update(kwargs)
            return subprocess.CompletedProcess(args=["ffmpeg"], returncode=0)

        with mock.patch("podcast_dsl.hidden_subprocess._orig_run", fake_run):
            with mock.patch("podcast_dsl.hidden_subprocess.sys.platform", "win32"):
                hidden_run(["ffmpeg", "-version"], capture_output=True)

        self.assertEqual(captured.get("creationflags", 0) & CREATE_NO_WINDOW, CREATE_NO_WINDOW)
        self.assertTrue(captured.get("capture_output"))


if __name__ == "__main__":
    unittest.main()
