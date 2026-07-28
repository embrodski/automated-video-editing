"""Shared podcast phrase gates (start/end/pause) for PIAB and harness autocut."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from harness_episode_lib import REPO_ROOT

PHRASE_GATES_FILENAME = "podcast-phrase-gates.json"

EMBEDDED_DEFAULTS: dict[str, Any] = {
    "start_phrase": (
        "I solemnly swear I'm up to no good, in five four three two"
    ),
    "start_phrase_countdown_tokens": ["five", "four", "three", "two"],
    "start_phrase_countdown_suffix": ["one", "zero"],
    "end_phrases": [
        "Be excellent to each other and party on dudes",
        "Hut of brown, now sit down",
    ],
    "start_preroll_sec": 1.0,
    "end_postroll_sec": 1.0,
    "pause_phrase": "Computer Freeze Program.",
    "unpause_phrases": [
        "Computer Resume Program",
        "Computer Unfreeze Program",
    ],
    "abort_phrase": "Emergency override - Eject the warp core",
    "pause_preroll_sec": 0.25,
    "pause_postroll_sec": 0.7,
    "flag_phrases": [
        "Computer Drop Flag",
        "Computer Raise Flag",
        "Computer Timestamp",
        "Computer Drop Timestamp",
    ],
}

_STATE_OVERRIDE_KEYS = (
    "start_phrase",
    "start_phrase_countdown_tokens",
    "start_phrase_countdown_suffix",
    "end_phrase",
    "end_phrases",
    "start_preroll_sec",
    "end_postroll_sec",
    "pause_phrase",
    "unpause_phrases",
    "unpause_phrase",
    "abort_phrase",
    "pause_preroll_sec",
    "pause_postroll_sec",
    "flag_phrases",
    "flag_phrase",
)


def flag_phrases_from_gates(gates: dict[str, Any]) -> list[str]:
    """Return configured flag phrases (primary + alternates), in order."""
    if gates.get("flag_phrases"):
        return [str(p) for p in gates["flag_phrases"] if str(p).strip()]
    if gates.get("flag_phrase"):
        return [str(gates["flag_phrase"])]
    return []


def end_phrases_from_gates(gates: dict[str, Any]) -> list[str]:
    """Return configured end phrases (primary + alternates), in order."""
    if gates.get("end_phrases"):
        return [str(p) for p in gates["end_phrases"] if str(p).strip()]
    if gates.get("end_phrase"):
        return [str(gates["end_phrase"])]
    return []


def phrase_gates_path(repo_root: Path | None = None) -> Path:
    root = (repo_root or REPO_ROOT).resolve()
    return root / PHRASE_GATES_FILENAME


def _normalize_gates(raw: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(EMBEDDED_DEFAULTS)
    for key in _STATE_OVERRIDE_KEYS:
        if key not in raw or raw[key] is None:
            continue
        out[key] = raw[key]
    unpause = out.get("unpause_phrases") or out.get("unpause_phrase")
    if isinstance(unpause, str):
        out["unpause_phrases"] = [unpause]
    elif isinstance(unpause, list):
        out["unpause_phrases"] = [str(p) for p in unpause if str(p).strip()]
    out.pop("unpause_phrase", None)

    end_phrases: list[str] = []
    if raw.get("end_phrases"):
        end_phrases.extend(str(p) for p in raw["end_phrases"] if str(p).strip())
    elif out.get("end_phrases"):
        end_phrases.extend(str(p) for p in out["end_phrases"] if str(p).strip())
    if raw.get("end_phrase") and str(raw["end_phrase"]).strip():
        primary = str(raw["end_phrase"]).strip()
        if primary not in end_phrases:
            end_phrases.insert(0, primary)
    if end_phrases:
        out["end_phrases"] = end_phrases
    out.pop("end_phrase", None)

    flag_phrases: list[str] = []
    if raw.get("flag_phrases"):
        flag_phrases.extend(str(p) for p in raw["flag_phrases"] if str(p).strip())
    elif out.get("flag_phrases"):
        flag_phrases.extend(str(p) for p in out["flag_phrases"] if str(p).strip())
    if raw.get("flag_phrase") and str(raw["flag_phrase"]).strip():
        primary = str(raw["flag_phrase"]).strip()
        if primary not in flag_phrases:
            flag_phrases.insert(0, primary)
    if flag_phrases:
        out["flag_phrases"] = flag_phrases
    out.pop("flag_phrase", None)
    return out


def load_phrase_gates(
    *,
    repo_root: Path | None = None,
    state_overrides: dict | None = None,
    create_file_if_missing: bool = True,
) -> dict[str, Any]:
    """
    Load phrase gates: embedded defaults <- JSON file <- optional state overrides.

    When ``create_file_if_missing`` and the JSON file is absent, write
    ``podcast-phrase-gates.json`` with embedded defaults.
    """
    path = phrase_gates_path(repo_root)
    merged = deepcopy(EMBEDDED_DEFAULTS)
    if path.is_file():
        file_data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(file_data, dict):
            raise ValueError(f"{path} must contain a JSON object.")
        merged = _normalize_gates({**merged, **file_data})
    elif create_file_if_missing:
        save_phrase_gates(merged, repo_root=repo_root)

    if state_overrides:
        patch = {
            key: state_overrides[key]
            for key in _STATE_OVERRIDE_KEYS
            if key in state_overrides and state_overrides[key] is not None
        }
        if patch:
            merged = _normalize_gates({**merged, **patch})
    return merged


def save_phrase_gates(
    updates: dict[str, Any],
    *,
    repo_root: Path | None = None,
) -> Path:
    """Merge ``updates`` into the on-disk phrase gates file and save."""
    path = phrase_gates_path(repo_root)
    current = load_phrase_gates(
        repo_root=repo_root,
        create_file_if_missing=False,
    )
    merged = _normalize_gates({**current, **updates})
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return path


def podcast_phrase_cli_args(state: dict | None = None) -> list[str]:
    """CLI args for ``generate_full_dsl.py`` from shared gates (+ optional state)."""
    gates = load_phrase_gates(state_overrides=state or {})
    out: list[str] = []

    start_phrase = gates.get("start_phrase")
    if start_phrase:
        out.extend(["--start-phrase", str(start_phrase)])
        if gates.get("start_preroll_sec") is not None:
            out.extend(["--start-preroll-sec", str(gates["start_preroll_sec"])])
        countdown = gates.get("start_phrase_countdown_tokens") or []
        if countdown:
            out.extend(["--start-phrase-countdown", *[str(t) for t in countdown]])
        suffix = gates.get("start_phrase_countdown_suffix") or []
        if suffix:
            out.extend(
                ["--start-phrase-countdown-suffix", *[str(t) for t in suffix]]
            )

    end_phrases = end_phrases_from_gates(gates)
    for phrase in end_phrases:
        out.extend(["--end-phrase", phrase])
    if end_phrases and gates.get("end_postroll_sec") is not None:
        out.extend(["--end-postroll-sec", str(gates["end_postroll_sec"])])

    pause_phrase = gates.get("pause_phrase")
    if pause_phrase:
        out.extend(["--pause-phrase", str(pause_phrase)])
        for phrase in gates.get("unpause_phrases") or []:
            out.extend(["--unpause-phrase", str(phrase)])
        if gates.get("pause_preroll_sec") is not None:
            out.extend(["--pause-preroll-sec", str(gates["pause_preroll_sec"])])
        if gates.get("pause_postroll_sec") is not None:
            out.extend(["--pause-postroll-sec", str(gates["pause_postroll_sec"])])

    abort_phrase = gates.get("abort_phrase")
    if abort_phrase:
        out.extend(["--abort-phrase", str(abort_phrase)])

    return out


def apply_namespace_phrase_defaults(args: Any) -> Any:
    """
    Fill missing ``generate_full_dsl.py`` phrase args from shared gates.

    Explicit CLI values on ``args`` win over the file.
    """
    gates = load_phrase_gates()
    if getattr(args, "start_phrase", None) in (None, ""):
        args.start_phrase = gates.get("start_phrase")
    if getattr(args, "start_phrase_countdown", None) is None:
        args.start_phrase_countdown = list(
            gates.get("start_phrase_countdown_tokens") or []
        )
    if getattr(args, "start_phrase_countdown_suffix", None) is None:
        args.start_phrase_countdown_suffix = list(
            gates.get("start_phrase_countdown_suffix") or []
        )
    if not getattr(args, "end_phrase", None):
        args.end_phrase = end_phrases_from_gates(gates)
    if getattr(args, "pause_phrase", None) in (None, ""):
        args.pause_phrase = gates.get("pause_phrase")
    if not getattr(args, "unpause_phrase", None):
        args.unpause_phrase = list(gates.get("unpause_phrases") or [])
    if getattr(args, "abort_phrase", None) in (None, ""):
        args.abort_phrase = gates.get("abort_phrase")
    if getattr(args, "start_preroll_sec", None) is None:
        args.start_preroll_sec = float(gates.get("start_preroll_sec", 1.0))
    if getattr(args, "end_postroll_sec", None) is None:
        args.end_postroll_sec = float(gates.get("end_postroll_sec", 1.0))
    if getattr(args, "pause_preroll_sec", None) is None:
        args.pause_preroll_sec = float(gates.get("pause_preroll_sec", 0.25))
    if getattr(args, "pause_postroll_sec", None) is None:
        args.pause_postroll_sec = float(gates.get("pause_postroll_sec", 0.7))
    return args
