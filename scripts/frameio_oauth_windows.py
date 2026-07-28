"""Windows custom-scheme handler for Frame.io Native App OAuth."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CAPTURE_PATH = REPO_ROOT / ".frameio-oauth-capture.json"
HANDLER_SCRIPT = Path(__file__).resolve().parent / "harness_frameio_oauth.py"


def scheme_from_redirect_uri(redirect_uri: str) -> str:
    parsed = redirect_uri.split("://", 1)
    if len(parsed) != 2 or not parsed[0]:
        raise ValueError(f"Invalid redirect URI: {redirect_uri}")
    return parsed[0]


def protocol_handler_command(*, python_exe: str | None = None) -> str:
    py = python_exe or sys.executable
    return f"\"{py}\" \"{HANDLER_SCRIPT}\" capture \"%1\""


def register_protocol_handler(*, scheme: str, python_exe: str | None = None) -> None:
    if sys.platform != "win32":
        raise OSError("Protocol registration is only supported on Windows.")

    import winreg

    command = protocol_handler_command(python_exe=python_exe)
    base = f"Software\\Classes\\{scheme}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValue(key, "", winreg.REG_SZ, f"URL:{scheme}")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        f"{base}\\shell\\open\\command",
    ) as key:
        winreg.SetValue(key, "", winreg.REG_SZ, command)


def unregister_protocol_handler(*, scheme: str) -> None:
    if sys.platform != "win32":
        raise OSError("Protocol registration is only supported on Windows.")

    import winreg

    base = f"Software\\Classes\\{scheme}"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{base}\\shell\\open\\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{base}\\shell\\open")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{base}\\shell")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, base)
    except FileNotFoundError:
        pass


def clear_capture(path: Path = DEFAULT_CAPTURE_PATH) -> None:
    if path.is_file():
        path.unlink()


def write_capture(
    *,
    code: str,
    state: str | None,
    raw: str,
    path: Path = DEFAULT_CAPTURE_PATH,
) -> None:
    payload = {
        "code": code,
        "state": state,
        "raw": raw,
        "captured_at": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def wait_for_capture(
    *,
    timeout_sec: float,
    path: Path = DEFAULT_CAPTURE_PATH,
    poll_sec: float = 0.25,
) -> dict[str, str | None]:
    end = time.time() + timeout_sec
    while time.time() < end:
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            path.unlink()
            code = str(payload.get("code") or "").strip()
            if not code:
                raise ValueError("Capture file did not contain an authorization code.")
            state = payload.get("state")
            return {"code": code, "state": str(state).strip() if state else None}
        time.sleep(poll_sec)
    raise TimeoutError(
        "Timed out waiting for Adobe to open the PIAB OAuth handler. "
        "After sign-in, allow the browser to open the app when prompted."
    )
