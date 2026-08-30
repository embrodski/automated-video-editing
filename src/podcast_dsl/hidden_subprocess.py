"""Hide console windows when spawning ffmpeg/ffprobe on Windows.

Podcast in a Box launches as a GUI (often via pythonw), so it has no console.
ffmpeg.exe and ffprobe.exe are console-subsystem binaries. Windows then
allocates a new visible console for every spawn, steals foreground focus,
and leaves the window up for the life of the process.

Short autocut probes flicker; long encodes sit on top for minutes.
CREATE_NO_WINDOW (plus SW_HIDE) keeps those tools in the background.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

# Win32 process/creation flags. subprocess exposes these on Windows only.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
STARTF_USESHOWWINDOW = getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
SW_HIDE = getattr(subprocess, "SW_HIDE", 0)

_installed = False
_orig_run = subprocess.run
_orig_popen = subprocess.Popen


def hidden_popen_kwargs(*, platform: str | None = None) -> dict[str, Any]:
    """Return extra subprocess kwargs that suppress a console on Windows."""
    plat = sys.platform if platform is None else platform
    if plat != "win32":
        return {}
    kwargs: dict[str, Any] = {"creationflags": CREATE_NO_WINDOW}
    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_cls is not None:
        info = startupinfo_cls()
        info.dwFlags |= STARTF_USESHOWWINDOW
        info.wShowWindow = SW_HIDE
        kwargs["startupinfo"] = info
    return kwargs


def apply_hidden_kwargs(
    kwargs: dict[str, Any],
    *,
    platform: str | None = None,
) -> dict[str, Any]:
    """Merge no-console flags into an existing subprocess kwargs dict."""
    extra = hidden_popen_kwargs(platform=platform)
    if not extra:
        return kwargs
    merged = dict(kwargs)
    merged["creationflags"] = int(merged.get("creationflags") or 0) | int(
        extra["creationflags"]
    )
    if "startupinfo" not in merged and "startupinfo" in extra:
        merged["startupinfo"] = extra["startupinfo"]
    return merged


def run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
    """subprocess.run that never flashes a console on Windows."""
    return _orig_run(*args, **apply_hidden_kwargs(kwargs))


def popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
    """subprocess.Popen that never flashes a console on Windows."""
    return _orig_popen(*args, **apply_hidden_kwargs(kwargs))


def install() -> None:
    """Patch subprocess.run / Popen so later callers inherit hidden consoles.

    Safe to call more than once. On non-Windows hosts this is a no-op.
    """
    global _installed
    if _installed:
        return
    if sys.platform != "win32":
        _installed = True
        return

    def _run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return _orig_run(*args, **apply_hidden_kwargs(kwargs))

    class _Popen(_orig_popen):  # type: ignore[misc,valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **apply_hidden_kwargs(kwargs))

    subprocess.run = _run  # type: ignore[assignment]
    subprocess.Popen = _Popen  # type: ignore[misc,assignment]
    _installed = True


install()
