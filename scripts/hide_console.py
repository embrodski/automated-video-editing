"""Re-export hidden subprocess helpers for scripts/ entry points."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from podcast_dsl.hidden_subprocess import (  # noqa: F401
    CREATE_NO_WINDOW,
    apply_hidden_kwargs,
    hidden_popen_kwargs,
    install,
    popen,
    run,
)

install()
