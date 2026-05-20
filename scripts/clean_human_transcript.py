#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


SPEAKER_LINE_RE = re.compile(
    r"^\s*(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\[Speaker\s+(\d+)\]\s*$"
)


@dataclass
class Block:
    label: str
    parts: list[str]


def _normalize_part(s: str) -> str:
    # Keep internal spaces but strip leading/trailing whitespace.
    return s.strip()


def clean_transcript_text(text: str, host: str, guest: str) -> str:
    speaker_to_label = {
        "0": f"{host}:",
        "1": f"{guest}:",
    }

    blocks: list[Block] = []
    current_label: str | None = None

    for raw in text.splitlines():
        m = SPEAKER_LINE_RE.match(raw)
        if m:
            speaker_id = m.group(3)
            label = speaker_to_label.get(speaker_id, f"Speaker {speaker_id}:")
            if current_label != label:
                blocks.append(Block(label=label, parts=[]))
                current_label = label
            # If the label is unchanged, we intentionally drop this attribution line.
            continue

        if not blocks:
            # Ignore any preamble before the first speaker marker.
            if raw.strip() == "":
                continue
            # If transcript starts with text, treat it as Host by default.
            blocks.append(Block(label=f"{host}:", parts=[]))
            current_label = blocks[-1].label

        s = _normalize_part(raw)
        if s == "":
            # Preserve paragraph breaks within a speaker block.
            blocks[-1].parts.append("\n")
        else:
            blocks[-1].parts.append(s)

    out_lines: list[str] = []
    for b in blocks:
        # Merge consecutive sections by design: each block is one speaker run.
        out_lines.append(b.label)

        # Join text parts: treat "\n" markers as paragraph breaks.
        paragraphs: list[str] = []
        cur: list[str] = []
        for p in b.parts:
            if p == "\n":
                if cur:
                    paragraphs.append(" ".join(cur).strip())
                    cur = []
            else:
                cur.append(p)
        if cur:
            paragraphs.append(" ".join(cur).strip())

        if paragraphs:
            out_lines.extend(paragraphs)

        out_lines.append("")  # blank line between speaker blocks

    # Drop trailing blank lines
    while out_lines and out_lines[-1] == "":
        out_lines.pop()

    return "\n".join(out_lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Clean human-readable transcripts containing SRT-style timestamp lines like "
            "'00:00:00,780 --> 00:00:12,590 [Speaker 0]'. Replaces them with Host:/Guest:, "
            "merges consecutive same-speaker sections, and writes 'Host-Guest Transcript.txt' "
            "(or a custom output name/path if provided)."
        )
    )
    p.add_argument("input", type=Path, help="Input transcript .txt/.srt-like file")
    p.add_argument("--host", required=True, help="Host name (Speaker 0)")
    p.add_argument("--guest", required=True, help="Guest name (Speaker 1)")
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write output file into (default: same folder as input)",
    )
    p.add_argument(
        "--output-name",
        default=None,
        help=(
            "Output filename (e.g. 'Scott Intro Transcript.txt'). "
            "If omitted, defaults to '<Host>-<Guest> Transcript.txt'."
        ),
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Full output path. If provided, overrides --output-dir and --output-name."
        ),
    )
    args = p.parse_args()

    in_path: Path = args.input
    if not in_path.exists():
        raise FileNotFoundError(str(in_path))

    if args.output is not None:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = args.output_dir if args.output_dir is not None else in_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_name = args.output_name if args.output_name is not None else f"{args.host}-{args.guest} Transcript.txt"
        out_path = out_dir / out_name

    cleaned = clean_transcript_text(in_path.read_text(encoding="utf-8"), host=args.host, guest=args.guest)
    out_path.write_text(cleaned, encoding="utf-8")

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

