"""Tests for Frame.io OAuth helpers."""

from __future__ import annotations

import unittest

from frameio_oauth import build_authorization_request, parse_authorization_response


class FrameioOAuthTests(unittest.TestCase):
    def test_build_authorization_request_contains_pkce(self) -> None:
        req = build_authorization_request(
            client_id="abc",
            redirect_uri="adobe+callback://adobeid/abc",
        )
        self.assertIn("code_challenge=", req.url)
        self.assertIn("client_id=abc", req.url)
        self.assertTrue(req.code_verifier)
        self.assertTrue(req.state)

    def test_parse_authorization_response_from_full_url(self) -> None:
        code, state = parse_authorization_response(
            "adobe+callback://adobeid/abc?code=XYZ123&state=abc"
        )
        self.assertEqual(code, "XYZ123")
        self.assertEqual(state, "abc")

    def test_parse_authorization_response_from_code_only(self) -> None:
        code, state = parse_authorization_response("XYZ123")
        self.assertEqual(code, "XYZ123")
        self.assertIsNone(state)


if __name__ == "__main__":
    unittest.main()
