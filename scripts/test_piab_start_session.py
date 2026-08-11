"""Unit tests for PIAB session start prompts."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from piab_start_session import _prompt_session_folder_name


class PromptSessionFolderNameTests(unittest.TestCase):
    def test_returns_cli_default_name(self) -> None:
        self.assertEqual(_prompt_session_folder_name("Jessiah"), "Jessiah")

    @patch("piab_start_session._prompt_custom_folder_name", return_value="Bayeswatch")
    @patch("piab_start_session._prompt_choice", return_value="1")
    def test_custom_name_choice(self, _choice, custom) -> None:
        self.assertEqual(_prompt_session_folder_name(None), "Bayeswatch")
        custom.assert_called_once_with()

    @patch(
        "piab_start_session.default_session_folder_name",
        return_value="2026-07-29 22-00-15",
    )
    @patch("piab_start_session._prompt_choice", return_value="2")
    def test_default_datetime_choice(self, _choice, default_name) -> None:
        self.assertEqual(_prompt_session_folder_name(None), "2026-07-29 22-00-15")
        default_name.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
