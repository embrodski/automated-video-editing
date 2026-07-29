"""Tests for PIAB camera setup confirmation."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from piab_confirm_camera_setup import (
    CAMERA_SETUP_MESSAGE,
    confirm_camera_setup,
    wait_for_camera_setup_confirmation,
)


class PiabConfirmCameraSetupTests(unittest.TestCase):
    def test_confirm_shows_message_and_opens_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = []
            for label in ("Left Camera", "Right Camera", "Wide"):
                path = root / f"{label}.jpg"
                path.write_text("img", encoding="utf-8")
                images.append((label, path))
            opened: list[Path] = []
            messages: list[str] = []

            result = confirm_camera_setup(
                images=tuple(images),
                auto_confirm=True,
                open_fn=lambda path: opened.append(path),
                print_fn=messages.append,
            )

        self.assertTrue(result.ok)
        self.assertEqual(len(opened), 3)
        self.assertIn(CAMERA_SETUP_MESSAGE, messages[0])

    def test_wait_for_confirmation_accepts_ready(self) -> None:
        confirmed = wait_for_camera_setup_confirmation(
            use_continue_button_flag=False,
            input_fn=lambda _prompt: "ready",
            print_fn=lambda *_args, **_kwargs: None,
        )
        self.assertTrue(confirmed)

    def test_continue_button_flag_waits_for_event(self) -> None:
        event = threading.Event()
        event.set()
        confirmed = wait_for_camera_setup_confirmation(
            use_continue_button_flag=True,
            continue_event=event,
            print_fn=lambda *_args, **_kwargs: None,
        )
        self.assertTrue(confirmed)


if __name__ == "__main__":
    unittest.main()
