"""Tests for harness delivery prompt helpers."""

from __future__ import annotations

import unittest

from harness_delivery_prompt import (
    confirm_delivery_email,
    delivery_already_confirmed,
    delivery_disabled,
    delivery_from_cli,
    is_valid_email,
    prompt_delivery_opt_in,
)


class DeliveryPromptTests(unittest.TestCase):
    def test_is_valid_email(self) -> None:
        self.assertTrue(is_valid_email("User@Example.com"))
        self.assertFalse(is_valid_email("not-an-email"))

    def test_delivery_from_cli_requires_confirm(self) -> None:
        with self.assertRaises(ValueError):
            delivery_from_cli(email="user@example.com", confirm=False)

    def test_confirm_abort_returns_none(self) -> None:
        result = confirm_delivery_email(
            "user@example.com",
            input_fn=lambda _prompt: "a",
            print_fn=lambda _msg: None,
        )
        self.assertIsNone(result)

    def test_confirm_yes_returns_enabled_block(self) -> None:
        result = confirm_delivery_email(
            "user@example.com",
            input_fn=lambda _prompt: "y",
            print_fn=lambda _msg: None,
        )
        self.assertTrue(result["enabled"])
        self.assertEqual(result["email"], "user@example.com")

    def test_confirm_no_reprompts(self) -> None:
        answers = iter(["n", "y"])
        emails = iter(["bad@", "good@example.com"])

        def fake_input(prompt: str) -> str:
            if prompt.startswith("Recipient"):
                return next(emails)
            return next(answers)

        result = confirm_delivery_email(
            "bad@",
            input_fn=fake_input,
            print_fn=lambda _msg: None,
        )
        self.assertEqual(result["email"], "good@example.com")

    def test_prompt_opt_in_disabled(self) -> None:
        result = prompt_delivery_opt_in(
            input_fn=lambda prompt: "n" if "Email the finished" in prompt else "",
            print_fn=lambda _msg: None,
        )
        self.assertEqual(result, delivery_disabled())

    def test_delivery_already_confirmed(self) -> None:
        state = {
            "delivery": {
                "enabled": True,
                "email": "user@example.com",
                "email_confirmed_at": "2026-01-01T00:00:00+00:00",
            }
        }
        self.assertTrue(delivery_already_confirmed(state))


if __name__ == "__main__":
    unittest.main()
