---
name: conversation-sync
description: >-
  Syncs two stereo WAV recordings of the same conversation (each file has one
  speaker close-mic and the other faint), mixes them into one stereo WAV with
  reduced echo, and writes "{FirstWord} Combined Audio.wav" (first word of WAV
  file 1's basename) into the Working Folder unless -o overrides. Use when the user says "Conversation-Sync", "sync conversation WAVs",
  "combine two recorder WAVs", or provides a folder plus two WAV filenames to
  merge after alignment.
---

# Conversation-Sync

## Inputs to collect

- **Working Folder** — directory that contains both WAVs (use absolute path on Windows when helpful).
- **WAV file 1** and **WAV file 2** — filenames only or paths relative to that folder (same conversation, slightly out of sync).

## Output

- Default output: **`{FirstWord} Combined Audio.wav`** in the **Working Folder** (same folder as the sources), where **`{FirstWord}`** is the first whitespace-separated token of **WAV file 1**'s basename (e.g. `Intro Ben audio raw.wav` → **`Intro Combined Audio.wav`**). Override with **`-o`** if needed.

## Command

From the **repository root** (`automated-video-editing`):

```bash
python scripts/sync_conversation_wavs.py "<Working Folder>/<WAV 1>" "<Working Folder>/<WAV 2>"
```

Optional explicit output: `-o "<Working Folder>/Intro Combined Audio.wav"` (or any path).

Optional: `--analyze-seconds 600` if the first five minutes are silence or unrelated and offset detection needs a longer window.

**Piecewise alignment is the default**: it first applies the **same leading trim** as global mode from the full-file lag estimate (so negative lag trims the reference WAV’s start), then **residual** sliding-window lag estimates, median smoothing, and one delay per segment between **knots**. Knots start on a nominal grid (`--segment-seconds`, default 22) but **shift up to ±8 s** to the quietest nearby moment on **both** tracks (low short-term energy on each, then the minimum of the two). Segment joins use **adaptive-length** cosine crossfades (wider when the delay step is larger, capped in software) and **cubic** resampling when reading the second file. Use **`--no-piecewise`** for a single global offset and start-trim only (no per-segment warp). Tunables: `--segment-seconds` (default 22), `--corr-window-seconds` (default 15), `--corr-hop-seconds` (default 7.5), `--crossfade-ms` (baseline join width, default 25), `--lag-median-size` (default 3).

Optional: `--json-report "<Working Folder>/Intro Combined Audio sync report.json"` (match the output basename if you like) for machine-readable lag/trim metadata (includes `piecewise_segments` unless you pass `--no-piecewise`).

## Dependencies

The script needs **NumPy** and **SciPy** (`pip install numpy scipy`).

## After running

Tell the user briefly:

- Which file is the **reference timeline** (`reference_file`) and which was **aligned** (`shifted_file`): default piecewise mode time-warps `shifted_file` with segment delays; **`--no-piecewise`** trims the start of `shifted_file` for a single global offset only.
- Estimated offset in **milliseconds** (`lag_ms` / `lag_ms_initial` in JSON or console).
- Whether peak limiting ran (console mentions pre-mix peak).
- Any **drift_warning** (global only) or **drift_note** / large `drift_estimate_ms` from the JSON/console.

---
name: conversation-sync
description: >-
  Syncs two stereo WAV recordings of the same conversation (each file has one
  speaker close-mic and the other faint), mixes them into one stereo WAV with
  reduced echo, and writes "{FirstWord} Combined Audio.wav" (first word of WAV
  file 1's basename) into the Working Folder unless -o overrides. Use when the user says "Conversation-Sync", "sync conversation WAVs",
  "combine two recorder WAVs", or provides a folder plus two WAV filenames to
  merge after alignment.
---

# Conversation-Sync

## Inputs to collect

- **Working Folder** — directory that contains both WAVs (use absolute path on Windows when helpful).
- **WAV file 1** and **WAV file 2** — filenames only or paths relative to that folder (same conversation, slightly out of sync).

## Output

- Default output: **`{FirstWord} Combined Audio.wav`** in the **Working Folder** (same folder as the sources), where **`{FirstWord}`** is the first whitespace-separated token of **WAV file 1**'s basename (e.g. `Intro Ben audio raw.wav` → **`Intro Combined Audio.wav`**). Override with **`-o`** if needed.

## Command

From the **repository root** (`automated-video-editing`):

```bash
python scripts/sync_conversation_wavs.py "<Working Folder>/<WAV 1>" "<Working Folder>/<WAV 2>"
```

Optional explicit output: `-o "<Working Folder>/Intro Combined Audio.wav"` (or any path).

Optional: `--analyze-seconds 600` if the first five minutes are silence or unrelated and offset detection needs a longer window.

**Piecewise alignment is the default**: it first applies the **same leading trim** as global mode from the full-file lag estimate (so negative lag trims the reference WAV’s start), then **residual** sliding-window lag estimates, median smoothing, and one delay per segment between **knots**. Knots start on a nominal grid (`--segment-seconds`, default 22) but **shift up to ±8 s** to the quietest nearby moment on **both** tracks (low short-term energy on each, then the minimum of the two). Segment joins use **adaptive-length** cosine crossfades (wider when the delay step is larger, capped in software) and **cubic** resampling when reading the second file. Use **`--no-piecewise`** for a single global offset and start-trim only (no per-segment warp). Tunables: `--segment-seconds` (default 22), `--corr-window-seconds` (default 15), `--corr-hop-seconds` (default 7.5), `--crossfade-ms` (baseline join width, default 25), `--lag-median-size` (default 3).

Optional **`--echo-suppress 0.5`** (0..1): after alignment, bidirectional least-squares subtraction of each track from the other to attenuate shared doubled content; start low (e.g. 0.3–0.6) and check by ear—high values can sound thin if correlation is weak.

Optional: `--json-report "<Working Folder>/Intro Combined Audio sync report.json"` (match the output basename if you like) for machine-readable lag/trim metadata (includes `piecewise_segments` unless you pass `--no-piecewise`).

## Dependencies

The script needs **NumPy** and **SciPy** (`pip install numpy scipy`).

## After running

Tell the user briefly:

- Which file is the **reference timeline** (`reference_file`) and which was **aligned** (`shifted_file`): default piecewise mode time-warps `shifted_file` with segment delays; **`--no-piecewise`** trims the start of `shifted_file` for a single global offset only.
- Estimated offset in **milliseconds** (`lag_ms` / `lag_ms_initial` in JSON or console).
- Whether peak limiting ran (console mentions pre-mix peak).
- Any **drift_warning** (global only) or **drift_note** / large `drift_estimate_ms` from the JSON/console.
