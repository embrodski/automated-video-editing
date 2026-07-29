"""Camera and microphone setup confirmation for PIAB."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent

CAMERA_SETUP_MESSAGE = (
    "Please ensure the cameras are positioned correctly and the microphone volume "
    "is turned up high enough (~80% full). It is recommended to have the speaker "
    "close-ups slightly off-center, looking towards the center of frame, with their "
    "eyes at the level of the top horizontal line in the view finder (see picture).\n"
    "Confirm when ready to continue."
)

DEFAULT_CAMERA_IMAGES: tuple[tuple[str, Path], ...] = (
    ("Left Camera", REPO_ROOT / "assets" / "piab-camera-left.jpg"),
    ("Right Camera", REPO_ROOT / "assets" / "piab-camera-right.jpg"),
    ("Wide", REPO_ROOT / "assets" / "piab-camera-wide.jpg"),
)

# Future standalone PIAB app: set True (or PIAB_USE_CONTINUE_BUTTON=1) to replace the
# stdin prompt with a UI Continue button wired to ``continue_event``.
PIAB_USE_CONTINUE_BUTTON = False

_READY_REPLIES = frozenset(
    {
        "",
        "ready",
        "y",
        "yes",
        "continue",
        "ok",
        "done",
    }
)


@dataclass(frozen=True)
class CameraSetupResult:
    status: str
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"confirmed", "skipped"}


def use_continue_button() -> bool:
    env = str(os.environ.get("PIAB_USE_CONTINUE_BUTTON") or "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        return True
    return PIAB_USE_CONTINUE_BUTTON


def _default_open_image(image_path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(image_path))  # noqa: S606
        return
    subprocess.run(["xdg-open", str(image_path)], check=False)


def show_camera_setup_images(
    images: tuple[tuple[str, Path], ...] = DEFAULT_CAMERA_IMAGES,
    *,
    open_fn: Callable[[Path], None] | None = None,
    print_fn: Callable[[str], None] = print,
) -> list[Path]:
    opener = open_fn or _default_open_image
    opened: list[Path] = []
    for label, path in images:
        if not path.is_file():
            print_fn(f"WARNING: Missing camera setup image ({label}): {path}")
            continue
        opener(path)
        opened.append(path)
        print_fn(f"Opened {label}: {path}")
    return opened


def wait_for_camera_setup_confirmation(
    *,
    use_continue_button_flag: bool | None = None,
    continue_event: threading.Event | None = None,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> bool:
    enabled = use_continue_button() if use_continue_button_flag is None else use_continue_button_flag
    if enabled:
        if continue_event is None:
            raise RuntimeError(
                "PIAB_USE_CONTINUE_BUTTON is enabled but no continue_event was provided."
            )
        print_fn("Waiting for Continue button...")
        continue_event.wait()
        return True

    while True:
        answer = input_fn("Type 'ready' when set up to continue: ").strip().lower()
        if answer in _READY_REPLIES:
            return True
        print_fn("Please type 'ready' (or y/yes/continue) when you are set up.")


def confirm_camera_setup(
    *,
    skip: bool = False,
    auto_confirm: bool = False,
    images: tuple[tuple[str, Path], ...] = DEFAULT_CAMERA_IMAGES,
    use_continue_button_flag: bool | None = None,
    continue_event: threading.Event | None = None,
    open_fn: Callable[[Path], None] | None = None,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> CameraSetupResult:
    if skip:
        return CameraSetupResult(status="skipped")

    print_fn(CAMERA_SETUP_MESSAGE)
    print_fn("")
    opened = show_camera_setup_images(images, open_fn=open_fn, print_fn=print_fn)
    if not opened:
        return CameraSetupResult(
            status="failed",
            message="No camera setup reference images were found.",
        )

    if auto_confirm:
        return CameraSetupResult(status="confirmed")

    if wait_for_camera_setup_confirmation(
        use_continue_button_flag=use_continue_button_flag,
        continue_event=continue_event,
        input_fn=input_fn,
        print_fn=print_fn,
    ):
        return CameraSetupResult(status="confirmed")

    return CameraSetupResult(status="failed", message="Camera setup was not confirmed.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Confirm PIAB camera and microphone setup.",
    )
    parser.add_argument(
        "--skip",
        action="store_true",
        help="Skip camera setup confirmation (automation/CI).",
    )
    parser.add_argument(
        "--confirm-ready",
        action="store_true",
        help="Non-interactive: proceed without waiting for user input.",
    )
    args = parser.parse_args()

    result = confirm_camera_setup(skip=args.skip, auto_confirm=args.confirm_ready)
    if result.message:
        print(result.message, file=sys.stderr)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
