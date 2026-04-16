"""Emit nerst_full_episode.dsl from Nerst Detail Transcript_simplified.json. Run from repo root."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TRANS = REPO / "John_Nerst" / "Nerst Detail Transcript_simplified.json"
OUT = REPO / "John_Nerst" / "nerst_full_episode.dsl"


def main() -> None:
    t = json.loads(TRANS.read_text(encoding="utf-8"))
    lines = [
        "// Full episode: all sentence-level rows (consecutive ids; zero-length lines use min duration in JSON)",
    ]
    for k in sorted(t.keys(), key=int):
        e = t[k]
        text = (e.get("text") or "").strip().replace("\n", " ")
        sn = e.get("speaker_name")
        if sn:
            lines.append(f"$segment4/{k} // {sn}: {text}")
        else:
            lines.append(f"$segment4/{k} // {text}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines) - 1} segment lines to {OUT}")


if __name__ == "__main__":
    main()
