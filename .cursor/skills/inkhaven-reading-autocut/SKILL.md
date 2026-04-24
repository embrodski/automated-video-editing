---
name: inkhaven-reading-autocut
description: Automates the Inkhaven single-speaker reading workflow: given front/side camera files, master audio, a detail transcript JSON, and the article URL being read, convert the transcript to per-sentence simplified JSON (with word timestamps), create a canonical article text file, register a new segment in src/podcast_dsl/config.py using the next unused integer key in SEGMENT_CONFIG (same as podcast autocut; front=speaker_0, side=speaker_1, optional wide=wide only when color correction is explicitly requested), generate reading.dsl using generate_reading_dsl.py (re-read/rewind handling + side-disfavored rule + gap-only lead-in + last-line-on-front + no cut padding), then render a 1-minute test MP4 and pause to ask before longer renders. Default to no color correction; enable it only if the user's initial request explicitly says "Use Color Correct", "Run Color Correct", or similar. Use when the user says “reading autocut”, “Inkhaven-Reading-Autocut”, “generate reading DSL”, or provides reading inputs (Front/Side plus optional Wide + Reading Audio + Reading Transcript + article link).
---

# Inkhaven Reading Autocut

## Inputs to collect

- **Working folder path**
  - Input folder: `<working folder>/Input` (source files live here)
  - Output folder: `<working folder>/Output` (generated transcript/article/DSL + renders go here)
  - Temp folder: `<working folder>/Temp` (temporary working files; on Windows redirect `TEMP`/`TMP` here before rendering)
- **Edit aggressiveness**:
  - Default: **hard edit** (more aggressive pause splitting; better at separating false starts + restarts)
  - If the user explicitly requests **soft edit**: use less aggressive pause splitting (more conservative)
- **Files**
  - **Front camera video** (maps to `speaker_0`)
  - **Side camera video** (maps to `speaker_1`)
  - **Master audio** (WAV preferred)
  - **Detail transcript JSON** (must have top-level `segments` array; ideally includes `words`)
- **Wide video**: collect only if the user's initial request explicitly asks for color correction. If provided, map it to `wide` and use it as a reference only; never show it in the edit.
- **Color correction request**: treat color correction as **off by default**. Only enable it if the user's initial run request explicitly says `Use Color Correct`, `Run Color Correct`, or equivalent phrasing.
- **Encoder preference**: by default, let `podcast_dsl` use a working hardware H.264 encoder if available; otherwise it should fall back to `libx264`. Only override this if the user explicitly asks for a specific encoder.
- **Downscale request**: if the user's initial run request says `Downscale 4K to 1080p` or equivalent phrasing, add `--downscale-4k-to-1080p` to the render command.
- **Original article URL** (the canonical script being read)
- **Optional overrides**
  - Per-camera offsets (seconds; default 0)
  - Transcript rows to force-keep / force-drop (for rare picture/graph description exception cases)

## Core rules (must apply)

### Camera mapping
- **Front = `speaker_0`**
- **Side = `speaker_1`**
- **Wide = `wide`** only when color correction is explicitly requested (reference only; do not use for shots)

### Content rules
- Keep only sentences that belong to the original article (URL), in order.
- Handle flubs / re-reads / rewinds: keep only the final contiguous correct reading.
- No article sentence should appear more than once unless it appears more than once in the source.

### Cut rules (Reading-specific)
- Start on **Front** for the title and first kept span.
- **User-driven cuts** (dropped transcript rows between kept rows) flip cameras.
- **Side is disfavored**: if a side-camera run lasts >12s, switch to Front at the next comma / sentence end / row boundary (use word timestamps to avoid mid-word cuts).
- **Gap-only lead-in**: if a camera change crosses discarded time (a transcript time gap), start the incoming clip up to 0.25s early; never shorten outgoing clips; if there is no gap, do not shift times.
- **Last transcript row** in the final edit must be **Front**.
- **No padding between cuts**: emit `!cut 0 0` so the renderer does not add pre/post padding that could cause tiny audio overlaps at camera switches.

## Workflow

### 1) List the input files
Confirm the exact filenames for front/side/wide/audio/transcript in `<working folder>/Input`.

### 2) Convert detail transcript → simplified per-sentence JSON (with words)
Run (default = **hard edit**):

```bash
python convert_transcript_json.py "<working folder>/Input/<detail transcript filename>" -o "<working folder>/Output/reading_transcript_simplified.json" --pause-split-gap-sec 0.60 --pause-split-min-words 4
```

This must produce a JSON dict keyed by row id strings with `start`, `end`, `text`, `speaker_id`, and **`words`** (word-level timestamps) so the reading DSL can snap cuts to true word boundaries.

If the user explicitly requests a **soft edit**, use:

```bash
python convert_transcript_json.py "<working folder>/Input/<detail transcript filename>" -o "<working folder>/Output/reading_transcript_simplified.json" --pause-split-gap-sec 0.65 --pause-split-min-words 6
```

### 3) Create canonical article text file in output folder
Run the fetcher utility to create:

- `<working folder>/Output/reading_article.txt`

Command template:

```bash
python fetch_article_to_reading_article.py --url "<article url>" --output-dir "<working folder>/Output"
```

Equivalent (explicit path):

```bash
python fetch_article_to_reading_article.py --url "<article url>" --output "<working folder>/Output/reading_article.txt"
```

Notes:
- Output is one sentence-like chunk per line with blank lines between paragraphs.
- If the auto-chunking doesn’t align well with how the speaker read (rare), manually edit the output file (split/join a couple lines) and rerun DSL generation.

### 4) Register a new segment in `src/podcast_dsl/config.py`
Add a new segment entry with:

**Segment number policy**: choose the **next unused integer** segment key in `SEGMENT_CONFIG` (e.g. if `10` exists, use `11`).

- `audio_file`: master audio absolute path
- `enable_color_match`: `True` only if the user's initial request explicitly asked for color correction; otherwise `False`
- `video_files`:
  - `speaker_0`: front file absolute path (+ optional offset)
  - `speaker_1`: side file absolute path (+ optional offset)
  - `wide`: wide file absolute path (+ optional offset) only when color correction is enabled
- `transcript_file`: `<working folder>/Output/reading_transcript_simplified.json` absolute path

### 5) Generate `reading.dsl`
Run:

```bash
python generate_reading_dsl.py "<working folder>/Output/reading_transcript_simplified.json" "<working folder>/Output/reading_article.txt" --segment <SEGMENT_NUM> --output "<working folder>/Output/reading.dsl"
```

Optional:
- Run `--verbose` or inspect `<working folder>/Output/reading.dsl.alignment.txt` if alignment is suspicious.
- If you want to change the final hold, pass `--final-shot-tail-sec 2.0` (default is 2 seconds).

### 6) Render ONLY the 1-minute test first (always redirect TEMP/TMP)
PowerShell-friendly template (do not use `&&`):

By default, `python -m podcast_dsl` now auto-selects a working hardware H.264 encoder if available and falls back to `libx264` otherwise. If the user explicitly asks for software-only or a specific encoder, add `--video-encoder <encoder>`.
If the user explicitly asks to downscale 4K footage, add `--downscale-4k-to-1080p`.

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<working folder>\\Temp"
$env:TMP  = "<working folder>\\Temp"

python -m podcast_dsl "<working folder>\\Output\\reading.dsl" -o "<working folder>\\Output\\1 Min Test Reading.mp4" --workers 6 --max-seconds 60
```

After the 1-minute render finishes, **pause and ask** whether to render longer tests or the full episode.

### 7) Optional: render 5-minute test and/or full MP4 (only if user agrees)

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<working folder>\\Temp"
$env:TMP  = "<working folder>\\Temp"

python -m podcast_dsl "<working folder>\\Output\\reading.dsl" -o "<working folder>\\Output\\5 Min Test Reading.mp4" --workers 6 --max-seconds 300
python -m podcast_dsl "<working folder>\\Output\\reading.dsl" -o "<working folder>\\Output\\Full Reading.mp4" --workers 6
```

### 8) After render
No thumbnail-text generation step is included in this pipeline.

## Usage example (what the user will paste)

User: “Load Inkhaven-Reading-Autocut.
Front camera: `Reading Front.mp4`
Side camera: `Reading Side.mp4`
Master audio: `Reading Audio.wav`
Transcript JSON: `Reading Transcript.json`
Article: `<url>`
Working folder: `D:\...\Inkhaven Alice`”

Assistant:
- Converts transcript to `reading_transcript_simplified.json`
- Creates `reading_article.txt` from the URL
- Registers a new segment in `src/podcast_dsl/config.py` using the **next unused integer** key in `SEGMENT_CONFIG` (same rule as Inkhaven-Podcast-Autocut), with `enable_color_match: False` unless the initial request explicitly asked for color correction
- Generates `reading.dsl`
- Renders `1 Min Test Reading.mp4` only, then asks before longer renders

