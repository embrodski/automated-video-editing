"""Refuse harness writes that would replace existing files without --allow-overwrite."""

from __future__ import annotations

import sys
from pathlib import Path

OVERWRITE_EXIT_CODE = 2


class HarnessOverwriteError(Exception):
    """Raised when a harness script would overwrite an existing file without approval."""


def refuse_overwrite(path: Path, *, allow_overwrite: bool, label: str | None = None) -> None:
    """
    Raise :class:`HarnessOverwriteError` if ``path`` exists and overwrite is not allowed.

    Harness agents must get explicit user approval before passing ``allow_overwrite=True``.
    Callers should catch :class:`HarnessOverwriteError` and exit with :data:`OVERWRITE_EXIT_CODE`.
    """
    if allow_overwrite or not path.exists():
        return
    kind = label or path.name
    print(
        f"ERROR: Refusing to overwrite existing {kind}:\n  {path}\n\n"
        "Harness rule: list affected files and get explicit user approval first, then either:\n"
        "  - re-run with --allow-overwrite, or\n"
        "  - write to a new filename.\n",
        file=sys.stderr,
    )
    raise HarnessOverwriteError(f"Refusing to overwrite existing {kind}: {path}")
