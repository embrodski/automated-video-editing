#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from clean_human_transcript import clean_transcript_text


def _is_generated_output(name: str, host: str) -> bool:
    # Matches: Ben-Anything Transcript.txt
    return re.fullmatch(rf"{re.escape(host)}-.+ Transcript\.txt", name) is not None


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Batch-clean all .txt transcripts in a folder. Guest name is inferred as the "
            "first word of each filename (stem). Writes '<Host>-<Guest> Transcript.txt' "
            "beside the inputs."
        )
    )
    p.add_argument("folder", type=Path, help="Folder containing input .txt transcript files")
    p.add_argument("--host", required=True, help="Host name (Speaker 0)")
    p.add_argument(
        "--skip",
        action="append",
        default=[],
        help="Exact filename to skip (can be repeated)",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="If set, do not overwrite existing '<Host>-<Guest> Transcript.txt' outputs",
    )
    args = p.parse_args()

    folder: Path = args.folder
    host: str = args.host
    skip: set[str] = set(args.skip)

    if not folder.exists():
        raise FileNotFoundError(str(folder))
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))

    inputs: list[Path] = []
    for pth in folder.glob("*.txt"):
        if pth.name in skip:
            continue
        if _is_generated_output(pth.name, host=host):
            continue
        inputs.append(pth)

    inputs.sort(key=lambda pth: pth.name.lower())

    wrote: list[Path] = []
    skipped_existing: list[Path] = []

    for in_path in inputs:
        guest = in_path.stem.split()[0]
        out_path = folder / f"{host}-{guest} Transcript.txt"
        if args.skip_existing and out_path.exists():
            skipped_existing.append(out_path)
            continue

        cleaned = clean_transcript_text(in_path.read_text(encoding="utf-8"), host=host, guest=guest)
        out_path.write_text(cleaned, encoding="utf-8")
        wrote.append(out_path)

    print(f"Processed inputs: {len(inputs)}")
    print(f"Wrote outputs:   {len(wrote)}")
    if skipped_existing:
        print(f"Skipped existing outputs: {len(skipped_existing)}")
    for pth in wrote:
        print(f"Wrote: {pth}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

