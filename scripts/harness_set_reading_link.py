#!/usr/bin/env python3
"""Harness step 4: verify reading link or mark episode as no-reading."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from harness_episode_lib import (
    load_episode_state,
    save_episode_state,
    step_state,
)


MIN_ARTICLE_TEXT_CHARS = 300
SIGN_IN_RE = re.compile(r"sign\s+in\s+to\s+continue", re.IGNORECASE)


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def verify_reading_url(url: str, *, timeout_sec: float = 30.0) -> tuple[bool, str, int]:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; InkhavenEpisodeHarness/1.0; +article-check)"
            )
        },
    )
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
    except HTTPError as exc:
        return False, f"HTTP {exc.code} fetching URL.", 0
    except URLError as exc:
        return False, f"Could not fetch URL: {exc.reason}", 0

    text = _html_to_text(body)
    if SIGN_IN_RE.search(text):
        return False, "Page appears to require sign-in (not a readable article).", len(text)
    if len(text) < MIN_ARTICLE_TEXT_CHARS:
        return (
            False,
            f"Page has too little readable text ({len(text)} chars) to be an article or blog post.",
            len(text),
        )
    return True, "Readable article-like content detected.", len(text)


def apply_reading_link(
    episode_folder: Path,
    *,
    reading_link: str | None,
    no_reading: bool,
    skip_verify: bool,
) -> dict:
    state = load_episode_state(episode_folder)
    steps = state.setdefault("steps", {})

    if no_reading:
        state["reading_link"] = None
        state["skip_reading"] = True
        steps["03_reading_link"] = step_state(
            steps,
            "03_reading_link",
            title="Reading source link",
            status="completed",
            user_input="no reading at this time",
        )
        steps["04_verify_reading_link"] = step_state(
            steps,
            "04_verify_reading_link",
            title="Verify reading link",
            status="skipped",
            reason="User indicated no reading for this episode.",
        )
        save_episode_state(episode_folder, state)
        return state

    if not reading_link or not reading_link.strip():
        raise ValueError("Provide --reading-link or --no-reading.")

    url = reading_link.strip()
    verify_note = "skipped (--skip-verify)"
    text_chars = None
    if not skip_verify:
        ok, verify_note, text_chars = verify_reading_url(url)
        if not ok:
            steps["04_verify_reading_link"] = step_state(
                steps,
                "04_verify_reading_link",
                title="Verify reading link",
                status="failed",
                url=url,
                error=verify_note,
                text_chars=text_chars,
            )
            state["reading_link"] = url
            state["skip_reading"] = False
            save_episode_state(episode_folder, state)
            raise ValueError(verify_note)

    state["reading_link"] = url
    state["skip_reading"] = False
    steps["03_reading_link"] = step_state(
        steps,
        "03_reading_link",
        title="Reading source link",
        status="completed",
        user_input=url,
    )
    steps["04_verify_reading_link"] = step_state(
        steps,
        "04_verify_reading_link",
        title="Verify reading link",
        status="completed",
        url=url,
        verify_note=verify_note,
        text_chars=text_chars,
    )
    save_episode_state(episode_folder, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness step 4: reading link.")
    parser.add_argument("episode_folder", type=Path)
    parser.add_argument("--reading-link", help="Article or blog post URL (<reading-link>).")
    parser.add_argument(
        "--no-reading",
        action="store_true",
        help="User chose no reading; skip future READING-tagged harness steps.",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Record link without fetching (agent already verified in Cursor).",
    )
    args = parser.parse_args()

    try:
        state = apply_reading_link(
            args.episode_folder,
            reading_link=args.reading_link,
            no_reading=args.no_reading,
            skip_verify=args.skip_verify,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
