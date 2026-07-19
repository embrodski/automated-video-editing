# Agent directives (project-wide)

## No overwrite without user verification (Inkhaven harness)

When running the **inkhaven-episode-harness** or any step it chains, **never replace an existing file** (Output deliverables, Temp DSL/JSON, user exports, etc.) without **listing what would be overwritten** and getting **explicit user approval** first. After approval only: pass **`--allow-overwrite`** on harness scripts or write to a **new filename**. See **`.cursor/skills/inkhaven-episode-harness/SKILL.md`** (hard rule section).

## Primary directive: avoid long renders during debugging

When doing **debugging**, **error-correction**, or **investigation**, do **not** start any **long-running video render / re-encode / multicam / ffmpeg** job (anything likely to take more than ~30 seconds, create multi-GB outputs, or lock files) **without explicitly asking the user first**.

If a long job seems necessary, first propose the smallest safe alternative (e.g. `--dry-run`, `ffprobe` checks, short clip, `-t` sample render, or reporting-only mode), then wait for approval before launching the full run.

## Long jobs: 5-minute completion checks

After the user approves and you **start** a long prep/render/video-sync job in the background: confirm it started once and report that it is running plus the estimate. Do **not** poll every few seconds.

**While any harness rendering-class task is running** (video-sync / multicam prep, `podcast_dsl` / reading renders, stitch, PIAB prep or full render, or a chained prep→1-min-test pipeline): **check status about every 5 minutes** until the job completes or fails, then notify the user immediately. Prefer a short progress note on each check (current step / newest outputs) when useful; always notify on completion or failure.

Do not busy-wait with sub-minute polling. Five minutes is the default cadence for these jobs unless the user asks for a different interval.

## Crash dumps (this machine)

For post-mortem debugging of BSODs / kernel bugchecks, newer kernel dumps on this machine are kept under **`D:\Crash Report`** (user-configured location). When investigating a render-time crash, check that folder for `.dmp` files and timestamps that match the incident.

