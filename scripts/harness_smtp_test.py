#!/usr/bin/env python3
"""Send a test email using harness SMTP configuration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_email import SmtpConfig, send_email
from harness_env import load_harness_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Test harness Gmail/SMTP delivery.")
    parser.add_argument(
        "--to",
        required=True,
        help="Recipient email address for the test message.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional dotenv file (default: repo .env).",
    )
    args = parser.parse_args()

    loaded = load_harness_env(args.env_file)
    if loaded is None:
        print(
            "ERROR: No .env file found. Run: python scripts/harness_setup_smtp.py",
            file=sys.stderr,
        )
        return 1

    try:
        config = SmtpConfig.from_env()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    send_email(
        config,
        to_addr=args.to.strip(),
        subject="PIAB SMTP test",
        body=(
            "This is a test message from the Podcast In A Box delivery harness.\n\n"
            "If you received this, Gmail SMTP is configured correctly."
        ),
    )
    print(f"Test email sent to {args.to.strip()} via {config.host}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
