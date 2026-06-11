"""Refuse harness writes that would replace existing files without --allow-overwrite."""

from __future__ import annotations

import sys
from pathlib import Path


def refuse_overwrite(path: Path, *, allow_overwrite: bool, label: str | None = None) -> None:
    """
    Exit with a clear error if ``path`` already exists and overwrite is not allowed.

    Harness agents must get explicit user approval before passing ``allow_overwrite=True``.
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
    raise SystemExit(2)
