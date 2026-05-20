---
name: inkhaven-reading-autocut
description: Automates the Inkhaven single-speaker reading workflow: given front/side camera files, master audio, a detail transcript JSON, and the article URL being read, convert the transcript to per-sentence simplified JSON (with word timestamps), create a canonical article text file, register a new segment in src/podcast_dsl/config.py using the next unused integer key in SEGMENT_CONFIG (same as podcast autocut; front=speaker_0, side=speaker_1, use_video_embedded_audio True, optional wide=wide only when color correction is explicitly requested), generate reading.dsl using generate_reading_dsl.py (re-read/rewind handling + side-disfavored rule + gap-only lead-in + last-line-on-front + no cut padding). All .dsl/.json/.txt artifacts go under episode Temp (parallel to Input/Output); only final .mp4 renders go to Output. If the user's initial directions include **Shorten**, post-process the DSL with shorten_reading_dsl_silences.py before any render. Then render a 1-minute test MP4 and pause to ask before longer renders (multicam full render only; no default Front/Side single-camera variants). Default to no color correction; enable it only if the user's initial request explicitly says "Use Color Correct", "Run Color Correct", or similar. Use when the user says “reading autocut”, “Inkhaven-Reading-Autocut”, “generate reading DSL”, or provides reading inputs (Front/Side plus optional Wide + Reading Audio + Reading Transcript + article link).
---

# Inkhaven Reading Autocut

## Permanent safety rule (must apply)

- **Do not re-render any video without first asking the user for permission.**
  - This includes re-rendering the 1-minute test (it typically overwrites the same output filename).
  - If a fix requires a re-render, stop after generating/updating `reading.dsl` and ask.

## Working folder resolution

Resolve episode folders **before** listing files or building command paths. Let **`P`** be the absolute path the user gave. Let **`WF_INPUT`** be true iff **`P`**'s last path segment equals **`Input`** (case-insensitive).

- **If `WF_INPUT` is true**: let **`R = parent(P)`**. If **`R / Output`** exists as a directory **and** **`R`** has a sibling **`temp`** directory (case-insensitive; e.g. `Temp` or `temp` on Windows), treat **`R`** as the **working folder** (same as if the user had passed the parent):
  - **Input folder** = **`P`** (the path they passed; normally **`R / Input`**)
  - **Output folder** = **`R / Output`**
  - **Temp folder** = that existing **`R / temp`** sibling (do not create a second temp folder under **`P`**)
- **Else**: **working folder** = **`P`**, with the usual layout:
  - **Input folder** = **`P / Input`**
  - **Output folder** = **`P / Output`**
  - **Temp folder** = existing **`P / temp`** sibling if present, else **`P / Temp`** (case-insensitive; create if missing when needed)

If **`parent(P)`** is not meaningful (e.g. drive root), do not promote; use **`P`** as the working folder.

When promotion applies, say so once (e.g. “Using `E:\Inkhaven Viv` as the working folder because you passed `...\Input`”). Use the resolved **Input**, **Output**, and **Temp** paths in every step below—not **`P / Input`** when **`P`** was already the Input folder.

In all commands below, substitute **`<input folder>`**, **`<output folder>`**, and **`<temp folder>`** with those resolved absolute paths.

## Artifact layout (Temp vs Output)

Keep episode **Input** and **Output** clean:

| Location | What goes here |
|----------|----------------|
| **`<input folder>`** | Source media only (camera MP4s, master WAV, detail transcript JSON from ElevenLabs, etc.). Do not write pipeline artifacts here. |
| **`<temp folder>`** | All non-deliverable working files: simplified transcript JSON, `reading_article.txt`, `reading.dsl`, `reading.dsl.alignment.txt`, `reading.dsl.sanity.json`, ffmpeg scratch, and any other **`.dsl` / `.json` / `.txt`** produced by this pipeline. Create **`Temp`** if missing. |
| **`<output folder>`** | **Final `.mp4` renders only** (e.g. `1 Min Test Reading.mp4`, `5 Min Test Reading.mp4`, `Full Reading.mp4`, and optional massive variant MP4s if the user requested `--massive`). No `.dsl`, `.json`, or `.txt` in Output. |

Register `transcript_file` in `SEGMENT_CONFIG` pointing at **`<temp folder>/reading_transcript_simplified.json`**, not Output.

## Inputs to collect

- **Working folder path** (after [Working folder resolution](#working-folder-resolution))
  - Input folder: resolved **Input folder** (source files live here)
  - Output folder: resolved **Output folder** (**`.mp4` deliverables only**)
  - Temp folder: resolved **Temp folder** (all **`.dsl` / `.json` / `.txt`** artifacts; on Windows also redirect process **`TEMP`/`TMP`** here before rendering)
- **Edit aggressiveness**:
  - Default: **hard edit** (more aggressive pause splitting; better at separating false starts + restarts)
  - If the user explicitly requests **soft edit**: use less aggressive pause splitting (more conservative)
- **Files**
  - **Front camera video** (maps to `speaker_0`)
  - **Side camera video** (maps to `speaker_1`)
  - **Master audio** (WAV preferred) — used for **ElevenLabs / transcript timing only**; renders take **AAC embedded in each camera MP4** by default (see step 4)
  - **Detail transcript JSON** (must have top-level `segments` array; ideally includes `words`)
- **Wide video**: collect only if the user's initial request explicitly asks for color correction. If provided, map it to `wide` and use it as a reference only; never show it in the edit.
- **Color correction request**: treat color correction as **off by default**. Only enable it if the user's initial run request explicitly says `Use Color Correct`, `Run Color Correct`, or equivalent phrasing.
- **Encoder preference**: by default, let `podcast_dsl` use a working hardware H.264 encoder if available; otherwise it should fall back to `libx264`. Only override this if the user explicitly asks for a specific encoder.
- **Downscale request**: if the user's initial run request says `Downscale 4K to 1080p` or equivalent phrasing, add `--downscale-4k-to-1080p` to the render command.
- **Original article URL** (the canonical script being read)
- **Shorten**: if the user's initial directions include the word **Shorten** (e.g. “reading autocut, Shorten”), after `reading.dsl` is generated you must run the silence post-pass (see workflow step 6) **before** any `python -m podcast_dsl` render.
- **Optional overrides**
  - Per-camera offsets (seconds; default 0)
  - Transcript rows to force-keep / force-drop (for rare visual or section-header callout exception cases)

## Core rules (must apply)

### Camera mapping
- **Front = `speaker_0`**
- **Side = `speaker_1`**
- **Wide = `wide`** only when color correction is explicitly requested (reference only; do not use for shots)

### Content rules
- Keep only sentences that belong to the original article (URL), in order.
- Keep reader callouts for visuals or section headers even when they are not in the canonical article text, including phrases like “here is a graph”, “here is a picture”, “this section is called”, “section 2”, “the next section is called”, or “the section title is”.
- Handle flubs / re-reads / rewinds: keep only the final contiguous correct reading.
- No article sentence should appear more than once unless it appears more than once in the source.

### Cut rules (Reading-specific)
- Start on **Front** for the title and first kept span.
- **User-driven cuts** (dropped transcript rows between kept rows) flip cameras.
- **Side is disfavored**: if a side-camera run lasts >12s, switch to Front at the next comma / sentence end / row boundary (use word timestamps to avoid mid-word cuts).
- **Gap-only lead-in**: if a camera change crosses discarded time (a transcript time gap), start the incoming clip up to 0.25s early; never shorten outgoing clips; if there is no gap, do not shift times.
- **Last transcript row** in the final edit must be **Front**.
- **No padding between cuts**: emit `!cut 0 0` so the renderer does not add pre/post padding that could cause tiny audio overlaps at camera switches.

### Shorten (silence removal) — only when the user includes **Shorten**
- Run **after** `generate_reading_dsl.py` has written `<temp folder>/reading.dsl`, and **before** any render.
- Detect consecutive spoken tokens using **word** timestamps from the simplified transcript (rows without `words` use the whole clip interval as a single token).
- Where the gap from **end of previous word** to **start of next word** is **greater than 1.5 seconds**:
  - End the outgoing clip at **1.25 seconds after** the previous word’s end.
  - Start the incoming clip at **0.25 seconds before** the next word’s start.
- **Every** such edit is a cut and must include a **camera change** (front ↔ side).
- If that cut puts the incoming segment on the **side** camera, re-apply the usual **side-disfavored** behavior (same logic as `generate_reading_dsl.py`: cap side runs at 12s with comma / sentence end / row-boundary flips to front, and the last transcript row stays on front). The repo script `shorten_reading_dsl_silences.py` performs the trim, forces the camera flip at each shortened gap, then runs `enforce_side_max_durations` per span and `ensure_last_sentence_on_front`.

## Workflow

### 1) List the input files
Confirm the exact filenames for front/side/wide/audio/transcript in `<input folder>`.

### 2) Convert detail transcript → simplified per-sentence JSON (with words)
Run (default = **hard edit**):

```bash
python convert_transcript_json.py "<input folder>/<detail transcript filename>" -o "<temp folder>/reading_transcript_simplified.json" --pause-split-gap-sec 0.60 --pause-split-min-words 4
```

This must produce a JSON dict keyed by row id strings with `start`, `end`, `text`, `speaker_id`, and **`words`** (word-level timestamps) so the reading DSL can snap cuts to true word boundaries.

If the user explicitly requests a **soft edit**, use:

```bash
python convert_transcript_json.py "<input folder>/<detail transcript filename>" -o "<temp folder>/reading_transcript_simplified.json" --pause-split-gap-sec 0.65 --pause-split-min-words 6
```

### 3) Create canonical article text file in Temp
Run the fetcher utility to create:

- `<temp folder>/reading_article.txt`

Command template:

```bash
python fetch_article_to_reading_article.py --url "<article url>" --output-dir "<temp folder>"
```

Equivalent (explicit path):

```bash
python fetch_article_to_reading_article.py --url "<article url>" --output "<temp folder>/reading_article.txt"
```

Notes:
- Output is one sentence-like chunk per line with blank lines between paragraphs.
- If the auto-chunking doesn’t align well with how the speaker read (rare), manually edit the output file (split/join a couple lines) and rerun DSL generation.

### 4) Register a new segment in `src/podcast_dsl/config.py`
Add a new segment entry with:

**Segment number policy**: choose the **next unused integer** segment key in `SEGMENT_CONFIG` (e.g. if `10` exists, use `11`).

- `audio_file`: master audio absolute path (transcript alignment reference; **not** muxed into the final reading MP4 unless you explicitly disable embedded audio)
- `use_video_embedded_audio`: **`True`** (required for all reading segments — lip-sync uses each camera file's embedded track so output does not drift vs a separate WAV)
- `enable_color_match`: `True` only if the user's initial request explicitly asked for color correction; otherwise `False`
- `video_files`:
  - `speaker_0`: front file absolute path (+ optional offset)
  - `speaker_1`: side file absolute path (+ optional offset)
  - `wide`: wide file absolute path (+ optional offset) only when color correction is enabled
- `transcript_file`: `<temp folder>/reading_transcript_simplified.json` absolute path

### 5) Generate `reading.dsl`
Run:

```bash
python generate_reading_dsl.py "<temp folder>/reading_transcript_simplified.json" "<temp folder>/reading_article.txt" --segment <SEGMENT_NUM> --output "<temp folder>/reading.dsl"
```

Optional:
- Run `--verbose` or inspect `<temp folder>/reading.dsl.alignment.txt` if alignment is suspicious.
- If ElevenLabs diarized the **read** on `speaker_1` and setup on `speaker_0`, add **`--reader-speaker-id 1`** (default is `0`).
- If you want to change the final hold, pass `--final-shot-tail-sec 2.0` (default is 2 seconds).

### 6) Shorten long pauses in `reading.dsl` (only when user includes **Shorten**)
Skip this step entirely if **Shorten** was not in the user’s initial directions.

From the **repository root** (same folder as `shorten_reading_dsl_silences.py`):

```bash
python shorten_reading_dsl_silences.py "<temp folder>/reading.dsl" --segment <SEGMENT_NUM>
```

This overwrites `reading.dsl` in place by default (add `--output` if you want a separate file). It uses `SEGMENT_CONFIG[<SEGMENT_NUM>]['transcript_file']` unless you pass `--transcript`. Defaults match the skill: `--min-silence-sec 1.5`, `--tail-sec 1.25`, `--lead-sec 0.25`, `--side-shot-max-sec 12`.

Do **not** start the 1-minute render until this step has finished when Shorten is requested.

### Render audio source (default)
`python -m podcast_dsl` **must** use **embedded audio from the front/side MP4s** for reading projects. That is the default when:
- the segment has `'use_video_embedded_audio': True` in `SEGMENT_CONFIG`, and/or
- the DSL header is `// Generated reading DSL` (renderer infers embedded audio even if the flag was omitted).

Do **not** turn this off for reading unless the user explicitly asks to debug master-WAV muxing.

Final concat of segment MP4s uses **concat demuxer + re-encode** (each segment stays muxed; never separate video/audio concat chains) with **CFR 23.976** (`fps` filter + `fps_mode cfr` + `aresample=async=1`) so DaVinci Resolve and other NLEs get one continuous timeline without progressive A/V drift.

Per-segment cuts from camera MP4s use **accurate seek** (`-i` then `-ss`, not fast seek before `-i`) so embedded audio stays aligned at each cut (slower than interview autocut, NLE-safe).

Multi-camera groups snap cuts to the output frame grid; each span export uses **`-frames:v`** plus **`-shortest`** so embedded audio cannot run past the last video frame before concat (avoids ~3 frames of previous-camera audio under the new shot).

### 7) Render ONLY the 1-minute test first (always redirect TEMP/TMP)
PowerShell-friendly template (do not use `&&`):

By default, `python -m podcast_dsl` now auto-selects a working hardware H.264 encoder if available and falls back to `libx264` otherwise. If the user explicitly asks for software-only or a specific encoder, add `--video-encoder <encoder>`.
If the user explicitly asks to downscale 4K footage, add `--downscale-4k-to-1080p`.

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<temp folder>"
$env:TMP  = "<temp folder>"

python -m podcast_dsl "<temp folder>\\reading.dsl" -o "<output folder>\\1 Min Test Reading.mp4" --workers 6 --max-seconds 60
```

After the 1-minute render finishes, **pause and ask** whether to render longer tests or the full episode.

### 8) Optional: render 5-minute test and/or full MP4 (only if user agrees)

```powershell
Set-Location "<repo>\\src"
$env:TEMP = "<temp folder>"
$env:TMP  = "<temp folder>"

python -m podcast_dsl "<temp folder>\\reading.dsl" -o "<output folder>\\5 Min Test Reading.mp4" --workers 6 --max-seconds 300
python -m podcast_dsl "<temp folder>\\reading.dsl" -o "<output folder>\\Full Reading.mp4" --workers 6
```

Do **not** append **`--massive`** unless the user explicitly asks for single-camera **Front Render** / **Side Render** variants (same timeline forced to one camera each; incompatible with `--max-seconds`). Massive variant **`.mp4`** files still go under **`<output folder>`**; any sidecar **`.dsl`** from that step should be moved or regenerated under **`<temp folder>`** if the tool writes them beside the MP4.

### 9) After render
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
- Writes `reading_transcript_simplified.json`, `reading_article.txt`, `reading.dsl`, and reports under **Temp**
- Registers a new segment in `src/podcast_dsl/config.py` using the **next unused integer** key in `SEGMENT_CONFIG` (same rule as Inkhaven-Podcast-Autocut), with `use_video_embedded_audio: True` and `enable_color_match: False` unless the initial request explicitly asked for color correction; `transcript_file` under **Temp**
- If the user included **Shorten**, runs `shorten_reading_dsl_silences.py` on `reading.dsl` in **Temp** before rendering
- Renders `1 Min Test Reading.mp4` to **Output** only, then asks before longer renders (full render is multicam only unless the user explicitly requests `--massive`)

