#!/usr/bin/env python3
"""Interactive Gmail SMTP setup for PIAB delivery (writes repo-root .env)."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_delivery_prompt import is_valid_email, normalize_email
from harness_env import DEFAULT_ENV_PATH, merge_env_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure Gmail SMTP for harness video delivery."
    )
    parser.add_argument(
        "--email",
        help="Gmail address (default: prompt).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_PATH,
        help=f"Dotenv file to write (default: {DEFAULT_ENV_PATH}).",
    )
    args = parser.parse_args()

    print("Gmail SMTP setup for Podcast In A Box delivery")
    print()
    print("You need a Google App Password (not your normal Gmail password):")
    print("  1. Enable 2-Step Verification on your Google account")
    print("  2. Google Account → Security → App passwords")
    print("  3. Create an app password for Mail / Other (e.g. PIAB)")
    print()

    email = normalize_email(args.email or input("Gmail address: ").strip())
    while not is_valid_email(email):
        print("That does not look like a valid email address.")
        email = normalize_email(input("Gmail address: ").strip())

    app_password = getpass.getpass("Gmail App Password (16 chars, spaces optional): ").strip()
    app_password = app_password.replace(" ", "")
    if len(app_password) < 8:
        print("ERROR: App password looks too short.", file=sys.stderr)
        return 1

    merge_env_file(
        args.env_file,
        {
            "HARNESS_SMTP_HOST": "smtp.gmail.com",
            "HARNESS_SMTP_PORT": "587",
            "HARNESS_SMTP_USER": email,
            "HARNESS_SMTP_PASSWORD": app_password,
            "HARNESS_SMTP_FROM": email,
            "HARNESS_SMTP_USE_TLS": "true",
        },
    )

    print()
    print(f"Wrote Gmail SMTP settings to {args.env_file.resolve()}")
    print("This file is gitignored — do not commit it.")
    print()
    print("Test with:")
    print(f'  python scripts/harness_smtp_test.py --to "{email}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
