#!/usr/bin/env python3
"""
Interactive Podcast In A Box session start.

Ask whether sources are in the default dump folder (E:\\PodcastRoom) or a special
folder that already contains the MultiCorder files, then scan and init — or
resume an interrupted prep run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_episode_lib import PIAB_STATE_FILENAME
from harness_delivery_prompt import (
    delivery_already_confirmed,
    delivery_from_cli,
    merge_delivery_into_state,
    prompt_delivery_opt_in,
)
from piab_lib import DEFAULT_SCAN_ROOT, collect_session_scan, load_piab_state, print_json, save_piab_state
from piab_resume import is_prep_resumable, plan_to_json
from piab_resume import build_prep_resume_plan


def _prompt_choice(prompt: str, *, choices: dict[str, str]) -> str:
    labels = ", ".join(f"{key}={label}" for key, label in choices.items())
    while True:
        answer = input(f"{prompt} [{labels}]: ").strip().lower()
        if answer in choices:
            return answer
        print(f"Please enter one of: {', '.join(choices)}")


def _prompt_yes_no(prompt: str, *, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{prompt} [{suffix}]: ").strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please enter y or n.")


def _run_init(repo: Path, argv: list[str]) -> int:
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts" / "piab_init_session.py"), *argv],
        cwd=str(repo),
    )
    return proc.returncode


def _maybe_configure_delivery(working: Path, *, delivery_email: str | None, confirm: bool) -> None:
    state = load_piab_state(working)
    if delivery_already_confirmed(state):
        return
    if delivery_email:
        delivery = delivery_from_cli(email=delivery_email, confirm=confirm)
    else:
        delivery = prompt_delivery_opt_in()
    merge_delivery_into_state(state, delivery)
    save_piab_state(working, state)


def _init_argv_with_delivery(base: list[str], args: argparse.Namespace) -> list[str]:
    argv = list(base)
    if args.delivery_email:
        argv.extend(["--delivery-email", args.delivery_email])
        if args.confirm_delivery_email:
            argv.append("--confirm-delivery-email")
    return argv


def _run_prep(repo: Path, working: Path, *, resume: bool) -> int:
    argv = [sys.executable, str(repo / "scripts" / "piab_run_prep.py"), str(working)]
    if resume:
        argv.append("--resume")
    proc = subprocess.run(argv, cwd=str(repo))
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive PIAB session start.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root (default: parent of scripts/).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Require --default-name or --working-folder; do not prompt.",
    )
    parser.add_argument(
        "--default-name",
        help="Default mode: working subfolder name under E:\\PodcastRoom.",
    )
    parser.add_argument(
        "--working-folder",
        type=Path,
        help="Special mode: folder that already contains MultiCorder sources.",
    )
    parser.add_argument(
        "--delivery-email",
        help="Non-interactive: recipient email for finished-video delivery.",
    )
    parser.add_argument(
        "--confirm-delivery-email",
        action="store_true",
        help="Required with --delivery-email for non-interactive delivery opt-in.",
    )
    args = parser.parse_args()
    repo = args.repo.resolve()

    if args.non_interactive:
        if args.working_folder is not None:
            rc = _run_init(
                repo,
                _init_argv_with_delivery(
                    ["--working-folder", str(args.working_folder.resolve())],
                    args,
                ),
            )
            if rc == 0 and args.delivery_email:
                _maybe_configure_delivery(
                    args.working_folder.resolve(),
                    delivery_email=args.delivery_email,
                    confirm=args.confirm_delivery_email,
                )
            return rc
        if args.default_name:
            working = DEFAULT_SCAN_ROOT / args.default_name
            rc = _run_init(
                repo,
                _init_argv_with_delivery(
                    ["--name", args.default_name, "--root", str(DEFAULT_SCAN_ROOT)],
                    args,
                ),
            )
            if rc == 0 and args.delivery_email:
                _maybe_configure_delivery(
                    working,
                    delivery_email=args.delivery_email,
                    confirm=args.confirm_delivery_email,
                )
            return rc
        print(
            "ERROR: --non-interactive requires --working-folder or --default-name.",
            file=sys.stderr,
        )
        return 1

    print("Podcast In A Box")
    print()
    action = _prompt_choice(
        "What would you like to do?",
        choices={
            "1": "new session",
            "2": "resume existing session",
        },
    )

    if action == "2":
        while True:
            raw = input("Enter working folder path (contains podcast-in-a-box.json): ").strip().strip('"')
            if not raw:
                print("Path is required.")
                continue
            working = Path(raw)
            state_path = working / PIAB_STATE_FILENAME
            if not state_path.is_file():
                print(f"No PIAB state file: {state_path}")
                continue
            try:
                state = load_piab_state(working)
                plan = build_prep_resume_plan(state, working, resume=True)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                print(f"ERROR: {exc}")
                continue

            print_json(plan_to_json(plan))
            if plan.ready_for_approval:
                print("\n1 Min Test is already done. Open Output and continue approval in the app/agent.")
                return 0
            if not is_prep_resumable(state, working) and not plan.skipped_steps:
                print("\nNothing to resume yet — complete labeling and run prep first.")
                continue
            if not _prompt_yes_no("Run prep with --resume from the step above?", default=True):
                continue
            return _run_prep(repo, working, resume=True)

    print()
    mode = _prompt_choice(
        "Where are the MultiCorder source files?",
        choices={
            "1": f"default folder ({DEFAULT_SCAN_ROOT})",
            "2": "special folder (files already in a dedicated folder)",
        },
    )

    if mode == "2":
        while True:
            raw = input("Enter full path to the special folder: ").strip().strip('"')
            if not raw:
                print("Path is required.")
                continue
            working = Path(raw)
            if not working.is_dir():
                print(f"Folder not found: {working}")
                continue
            try:
                payload = collect_session_scan(working)
            except (FileNotFoundError, RuntimeError) as exc:
                print(f"ERROR: {exc}")
                continue

            print_json(payload)
            requirements = payload["requirements"]
            if not requirements["ok"]:
                print("\nThis folder is missing required files for Podcast In A Box:")
                for line in requirements["missing"]:
                    print(f"  - {line}")
                for line in requirements["warnings"]:
                    print(f"  - {line}")
                if requirements.get("unrecognized_media"):
                    print("  Unrecognized media files:")
                    for name in requirements["unrecognized_media"]:
                        print(f"    - {name}")
                if not _prompt_yes_no("Continue anyway?", default=False):
                    continue

            if not _prompt_yes_no(
                f"Use {working} as the working folder and start labeling?",
                default=True,
            ):
                continue
            rc = _run_init(
                repo,
                _init_argv_with_delivery(
                    ["--working-folder", str(working.resolve())],
                    args,
                ),
            )
            if rc == 0:
                _maybe_configure_delivery(
                    working.resolve(),
                    delivery_email=args.delivery_email,
                    confirm=args.confirm_delivery_email,
                )
            return rc

    try:
        payload = collect_session_scan(DEFAULT_SCAN_ROOT)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_json(payload)
    requirements = payload["requirements"]
    if not requirements["ok"]:
        print("\nWARNING: Latest default-folder cluster is incomplete:")
        for line in requirements["missing"]:
            print(f"  - {line}")

    if not _prompt_yes_no("Are these the files from this session?", default=True):
        print("Aborted. Move or copy sources into the default folder and re-run.")
        return 1

    while True:
        name = input("Working folder name to create under PodcastRoom: ").strip()
        if name and "/" not in name and "\\" not in name:
            break
        print("Enter a single folder name (no path separators).")

    rc = _run_init(
        repo,
        _init_argv_with_delivery(
            ["--name", name, "--root", str(DEFAULT_SCAN_ROOT)],
            args,
        ),
    )
    if rc == 0:
        _maybe_configure_delivery(
            DEFAULT_SCAN_ROOT / name,
            delivery_email=args.delivery_email,
            confirm=args.confirm_delivery_email,
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
