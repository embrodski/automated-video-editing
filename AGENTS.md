# Agent directives (project-wide)

## No overwrite without user verification (Inkhaven harness)

When running the **inkhaven-episode-harness** or any step it chains, **never replace an existing file** (Output deliverables, Temp DSL/JSON, user exports, etc.) without **listing what would be overwritten** and getting **explicit user approval** first. After approval only: pass **`--allow-overwrite`** on harness scripts or write to a **new filename**. See **`.cursor/skills/inkhaven-episode-harness/SKILL.md`** (hard rule section).

## Primary directive: avoid long renders during debugging

When doing **debugging**, **error-correction**, or **investigation**, do **not** start any **long-running video render / re-encode / multicam / ffmpeg** job (anything likely to take more than ~30 seconds, create multi-GB outputs, or lock files) **without explicitly asking the user first**.

If a long job seems necessary, first propose the smallest safe alternative (e.g. `--dry-run`, `ffprobe` checks, short clip, `-t` sample render, or reporting-only mode), then wait for approval before launching the full run.

## Crash dumps (this machine)

For post-mortem debugging of BSODs / kernel bugchecks, newer kernel dumps on this machine are kept under **`D:\Crash Report`** (user-configured location). When investigating a render-time crash, check that folder for `.dmp` files and timestamps that match the incident.

