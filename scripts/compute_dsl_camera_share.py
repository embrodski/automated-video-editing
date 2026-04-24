#!/usr/bin/env python3
"""Sum transcript clip durations per active !camera in a DSL file."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("dsl_path", type=Path)
    p.add_argument("transcript_json", type=Path)
    args = p.parse_args()

    dsl_text = args.dsl_path.read_text(encoding="utf-8")
    data = json.loads(args.transcript_json.read_text(encoding="utf-8"))

    cam_pat = re.compile(r"^!camera\s+(speaker_0|speaker_1|wide)\s*$")
    clip_pat = re.compile(r"^\$segment\d+/(\d+)")
    totals = {"speaker_0": 0.0, "speaker_1": 0.0, "wide": 0.0}
    current: str | None = None
    missing: list[str] = []

    for raw in dsl_text.splitlines():
        s = raw.strip()
        m = cam_pat.match(s)
        if m:
            current = m.group(1)
            continue
        m = clip_pat.match(s)
        if not m:
            continue
        if current is None:
            print("error: clip line before first !camera", file=sys.stderr)
            return 2
        idx = m.group(1)
        row = data.get(idx)
        if not row:
            missing.append(idx)
            continue
        d = float(row["end"]) - float(row["start"])
        totals[current] += d

    if missing:
        print(f"warning: {len(missing)} missing transcript keys (first 10): {missing[:10]}", file=sys.stderr)

    clip_total = sum(float(r["end"]) - float(r["start"]) for r in data.values())
    attributed = sum(totals.values())

    print(f"DSL: {args.dsl_path}")
    print(f"Transcript: {args.transcript_json}")
    print()
    for k in ("speaker_0", "speaker_1", "wide"):
        sec = totals[k]
        print(f"{k:12}  {sec:12.2f} s   {sec/60:10.2f} min   {100*sec/attributed:6.2f}% of attributed")
    print()
    print(f"Sum (attributed clips): {attributed:.2f} s  ({attributed/60:.2f} min)")
    print(f"Sum (all JSON rows):    {clip_total:.2f} s  ({clip_total/60:.2f} min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
