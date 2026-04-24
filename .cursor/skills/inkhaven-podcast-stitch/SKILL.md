---
name: inkhaven-podcast-stitch
description: Stitch final episode from four rendered parts in the Output folder. Validates required files, applies 0.5s fade-in/out to each clip, inserts 0.25s black between clips, concatenates in order, and writes Complete Episode.mp4. Aborts with a clear error if any required file is missing.
---

# Inkhaven Podcast Stitch

## Load / kickoff behavior (when user says “Load Inkhaven-Podcast-Stitch”)

When the user asks to load this skill, do the following:

1) Scan the repo briefly to understand expected folder conventions (where renders usually land, typical folder names like `outputs/Output`, etc.).
2) Read and internalize this skill file.
3) Reply with a **single-paragraph summary** of what this skill can do and what inputs it expects.
4) **Stop and wait** for the user to provide the **path to the working directory** (the folder that contains the four rendered MP4 inputs and will receive `Complete Episode.mp4`). Do **not** attempt to run the stitch step until that path is provided.

## Purpose

Create `Complete Episode.mp4` by stitching four already-rendered MP4s in the **Output folder**:

1) `Intro.mp4`  
2) `Reading.mp4`  
3) `Edited Interview.mp4`  
4) `Closing.mp4`

For **each clip**:

- Add **0.5s fade-in** at the start
- Add **0.5s fade-out** at the end

Between clips:

- Insert **0.25s of black** (with silence)

Final output:

- `Complete Episode.mp4` in the Output folder

If any required input file is missing, **abort** and report which file(s) were not found.

## Inputs to collect

- **Output folder**: contains the four MP4s and will receive `Complete Episode.mp4`
- **Temp folder**: same temp folder used previously (Windows: set `TEMP`/`TMP` before running)
- **Encoder preference**: by default, let the stitch step use a working hardware H.264 encoder if available; otherwise it should fall back to `libx264`. Only override this if the user explicitly asks for a specific encoder.

## Run (PowerShell)

```powershell
Set-Location "<repo>"

$env:TEMP = "<temp folder>"
$env:TMP  = "<temp folder>"

python .\stitch_episode.py --output-dir "<output folder>"
```

Notes:
- Run this directly in your PowerShell session (avoid wrapping it in another `powershell -Command "..."`), to prevent quoting/variable-expansion issues.
- The stitch step can take several minutes for long interviews. You should see `ffmpeg` progress output while it runs.
- The script now defaults to encoder auto-selection: working hardware H.264 if available, otherwise `libx264`. If the user explicitly asks for software-only or a specific encoder, add `--video-encoder <encoder>`.

## Expected outputs

- `<output folder>\Complete Episode.mp4` exists and is non-trivial size.
- After a successful stitch, the script prints **four lines** to stdout: each clip’s fade-in start in the final timeline as `mm:ss` plus one word — `Intro`, `Reading`, `Interview`, `Sponsor` (closing). Times come from each source file’s duration plus **0.25s** black between clips (first line is always `00:00 Intro`).

### Reporting timecodes to the user

When summarizing a successful stitch, paste the four timecodes **exactly** like this: **plaintext only**, one line per entry, **no** markdown tables, bullets, or other wrapping. Use the real values from the script output; the example below shows the shape only:

```
00:00 Intro
06:18 Reading
15:35 Interview
62:46 Sponsor
```

