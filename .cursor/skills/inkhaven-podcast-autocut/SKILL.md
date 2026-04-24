---
name: inkhaven-podcast-autocut
description: Automates the Inkhaven multi-cam podcast workflow: convert a detail transcript JSON into per-sentence simplified JSON, register a new segment in src/podcast_dsl/config.py using provided input media paths, generate a full DSL with speaker-based camera cuts plus the dense-cuts→wide rule, then render ONLY the 1-minute test MP4 and pause to ask whether to continue (5-minute + full render are opt-in). If the user's initial request includes "massive" or `--massive`, after the agreed full-episode render add `--massive` to `python -m podcast_dsl` so the same folder also gets Ben Render, Guest Render, and Wide Render (single-camera variants, encoded sequentially: Ben, then Guest, then Wide). Default to no color correction; enable it only if the user's initial request explicitly says "Use Color Correct", "Run Color Correct", or similar. Use when the user says “Inkhaven”, “podcast autocut”, “generate DSL”, “render interview”, or provides input/output folders with Ben/Guest/Wide videos + WAV + transcript JSON.
---

# Inkhaven Podcast Autocut

## Inputs to collect

- **Working folder path**
  - Input folder: `<working folder>/Input` (source media + transcript live here)
  - Output folder: `<working folder>/Output` (simplified transcript JSON, DSL(s), MP4(s) written here)
  - Temp folder: `<working folder>/Temp` (temporary working files; on Windows redirect `TEMP`/`TMP` here before rendering)
- **Files**:
  - **Ben close video** (`speaker_0`)
  - **Guest close video** (`speaker_1`)
  - **Wide video** (`wide`)
  - **Master audio** (WAV preferred)
  - **Detail transcript** JSON (must have top-level `segments` array with `start_time`/`end_time` and ideally `words`)
  - Optional: **simplified transcript HTML** (reference only; not required)
- **Filename variations**: any alternate spellings/case/spaces.
- **Offsets** (optional): per-camera offsets in seconds (default 0 for all).
- **Temp folder free space**: if `<working folder>/Temp` is on a cramped drive, choose a different working folder (rendering writes large temp files; keep it off a nearly-full C: drive).
- **Color correction request**: treat color correction as **off by default**. Only enable it if the user's initial run request explicitly says `Use Color Correct`, `Run Color Correct`, or equivalent phrasing.
- **Encoder preference**: by default, let `podcast_dsl` use a working hardware H.264 encoder if available; otherwise it should fall back to `libx264`. Only override this if the user explicitly asks for a specific encoder.
- **Downscale request**: if the user's initial run request says `Downscale 4K to 1080p` or equivalent phrasing, add `--downscale-4k-to-1080p` to the render command.
- **Massive renders**: if the user's initial run request includes `massive`, `--massive`, or equivalent (e.g. “run massive”, “massive test”), then when they agree to the **full episode** render, append **`--massive`** to that `python -m podcast_dsl` command (same flags otherwise). That produces **in the same folder as `-o`**: `Ben Render.mp4`, `Guest Render.mp4`, and `Wide Render.mp4` (plus matching `.dsl` files), each the same timeline as `interview.dsl` but forced to `speaker_0`, `speaker_1`, or `wide` respectively; `massive_renderer.py` runs those three encodes **one after another** (Ben, then Guest, then Wide) to avoid overloading the machine. Do **not** add `--massive` to 1-minute or 5-minute test commands (`--max-seconds` is incompatible with `--massive`).

## Core rules (must apply)

### Speaker mapping

- **Speaker 0 = Ben = `speaker_0`**
- **Speaker 1 = Guest = `speaker_1`**
- Wide camera is `wide`

### Open and close on Ben (`generate_full_dsl.py`)

These apply when generating **`interview.dsl`** (before rendering):

- **First five seconds:** the timeline interval **[0s, 5s)** stays on **`speaker_0` (Ben)**. Every transcript row whose time range **overlaps** `[0, 5)` is forced to Ben, so there is **no cut off Ben** during that window (sentence-row aligned; a long row that crosses 5s is one clip, so Ben may extend past 5s for that row).
- **Last four seconds:** the timeline from **`T − 4s` through `T`** stays on **`speaker_0`**, where **`T`** is the end of the last transcript row plus the generator’s **final-shot tail** (same `--final-shot-tail-sec` as `generate_full_dsl.py`, default 2s). Every transcript row that **overlaps** that tail window is forced to Ben. If there is no row boundary exactly at `T − 4s`, the first row that intersects the tail window is forced to Ben for its whole clip (Ben may start slightly before `T − 4s`).
- **CLI:** `--open-ben-sec` and `--tail-ben-sec` default to **5** and **4**; set to **0** to disable either lock.

Forced-wide spans from the dense-cut rule are **trimmed** so **`!camera wide`** never covers the open-Ben or tail-Ben windows.

### Dense cuts → force wide

Treat a **cut** as a **camera change** only (`speaker_0 ↔ speaker_1`), not sentence boundaries.

Whenever there would be **more than one cut in any rolling window** (default **3 seconds**, see `generate_full_dsl.py` `--cut-window-sec`), switch to a single **`!camera wide`** for that period:

- **Sentence-aligned** start/end (only at sentence boundaries)
- **Wide lasts at least** `--min-wide-sec` (default **3 seconds**)
- **Return** to the intended camera for the **first sentence after** the wide span
- **Extension exception**: if another cut would happen within the **same window** of the wide span ending, extend the wide span until that cut boundary (repeat until no such cut exists)

## Workflow

### 1) List the input files

Confirm the exact filenames in `<working folder>/Input` and identify which map to:
`speaker_0`, `speaker_1`, `wide`, `audio`, `detail transcript`.

### 2) Convert detail transcript → simplified per-sentence JSON

Run the repo converter to create a simplified transcript JSON in `<working folder>/Output`.

- **Default**: split into one row per sentence from word timings (critical for sentence-boundary edits).
- Output format must be a JSON dict keyed by row id strings; each row has `start`, `end`, `text`, `speaker_id`, `speaker_name`.

Command template:

```bash
python convert_transcript_json.py "<working folder>/Input/<detail transcript filename>" -o "<working folder>/Output/interview_transcript_simplified.json"
```

### 3) Register a new segment in `src/podcast_dsl/config.py`

Add a new segment entry with:

- `audio_file`: absolute path to the master audio
- `audio_offset`: 0
- `enable_color_match`: `True` only if the user's initial request explicitly asked for color correction; otherwise `False`
- `video_files`: `speaker_0`, `speaker_1`, `wide` each with absolute `file` path and `offset` (default 0 unless user provided overrides)
- `transcript_file`: `<working folder>/Output/interview_transcript_simplified.json` absolute path

**Segment number policy**: choose the **next unused integer** segment key in `SEGMENT_CONFIG` (e.g. if `10` exists, use `11`).

### 4) Generate the full DSL (camera + wide rule)

Use `generate_full_dsl.py` (now includes camera switching + wide rule by default) to generate:

- Full DSL: `<working folder>/Output/interview.dsl`

Command template:

```bash
python generate_full_dsl.py "<working folder>/Output/interview_transcript_simplified.json" --segment <SEGMENT_NUM> --output "<working folder>/Output/interview.dsl"
```

### 5) Render ONLY the 1-minute test from the full DSL (always redirect TEMP/TMP on Windows)

Rendering writes large temp files. On Windows, **always** set `TEMP` and `TMP` to `<working folder>/Temp` before rendering.

By default, `python -m podcast_dsl` now auto-selects a working hardware H.264 encoder if available and falls back to `libx264` otherwise. If the user explicitly asks for software-only or a specific encoder, add `--video-encoder <encoder>`.
If the user explicitly asks to downscale 4K footage, add `--downscale-4k-to-1080p`.

Render template (PowerShell-friendly; do not use `&&`):

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<working folder>\\Temp"
$env:TMP  = "<working folder>\\Temp"

python -m podcast_dsl "<working folder>\\Output\\interview.dsl" -o "<working folder>\\Output\\1 Min Test.mp4" --workers 6 --max-seconds 60
```

After the 1-minute render completes, **pause** and ask:

- “Do you want to continue with the 5-minute test render?”
- “Do you want to render the full episode MP4?”

### 6) Optional: render 5-minute test and/or full episode (only if user agrees)

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<working folder>\\Temp"
$env:TMP  = "<working folder>\\Temp"

python -m podcast_dsl "<working folder>\\Output\\interview.dsl" -o "<working folder>\\Output\\5 Min Test.mp4" --workers 6 --max-seconds 300
python -m podcast_dsl "<working folder>\\Output\\interview.dsl" -o "<working folder>\\Output\\Full Interview.mp4" --workers 6
```

If the user asked for **massive** on the full episode, use the same command with **`--massive`** appended (and keep any `--downscale-4k-to-1080p` / `--video-encoder` flags they requested):

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<working folder>\\Temp"
$env:TMP  = "<working folder>\\Temp"

python -m podcast_dsl "<working folder>\\Output\\interview.dsl" -o "<working folder>\\Output\\Full Interview.mp4" --workers 6 --massive
```

After it finishes, confirm **`Ben Render.mp4`**, **`Guest Render.mp4`**, **`Wide Render.mp4`** (and optional `.dsl` siblings) exist beside **`Full Interview.mp4`**.

### 7) Validate outputs

- Confirm the output MP4 files exist and are non-trivial size.
- Optional: run `--dry-run` on the DSL to confirm total duration before a long render.
- If **massive** was used: also confirm the three single-camera outputs are non-trivial size.

## Usage example

User: “Load Inkhaven-Podcast-Autocut. Working folder is `D:\\Project`. Ben close is `Ben Close.mp4`, guest is `Guest Close.mp4`, wide is `Interview Wide.mp4`, audio is `interview audio.wav`, transcript is `interview transcript detail.json`.”

Assistant (following this skill):

- Uses `D:\Project\Input` for inputs, writes outputs to `D:\Project\Output`, and redirects `TEMP/TMP` to `D:\Project\Temp`
- Convert transcript to `D:\Project\Output\interview_transcript_simplified.json`
- Add a new `SEGMENT_CONFIG['<next>']` entry pointing to the provided files, with `enable_color_match: False` unless the initial request explicitly asked for color correction
- Generate `D:\Project\Output\interview.dsl` (with dense-cuts→wide)
- Render ONLY `1 Min Test.mp4` into the output folder with `TEMP/TMP` redirected to `D:\Project\Temp`
- Pause and ask whether to continue with the 5-minute test and/or full render

