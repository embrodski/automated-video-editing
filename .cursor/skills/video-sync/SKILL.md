---
name: video-sync
description: >-
  For each of 1-4 MP4s under a Working Folder, cross-correlates the video's
  embedded audio against one shared cleaned WAV and muxes the video with that
  aligned audio via scripts/sync_video_wav_replace.py. Resolves output folders
  INPUT_DIR and TEMP_DIR (see skill body): when Working Folder is named Raw,
  prefers sibling Input/temp under the parent when those directories exist;
  otherwise matches prior episode-root rules. When multicam will produce
  *-prepped.mp4 (2+ videos, no --no-align), *-synced.mp4 and per-clip sync JSON
  go under TEMP_DIR; multicam writes *-prepped.mp4 to INPUT_DIR. If only *-synced
  is produced (--no-align or one video), *-synced and sync JSON go under INPUT_DIR.
  extract_mp4_audio_wav.py writes <sanitized-audio-stem>-prepped.wav under INPUT_DIR
  (same whole-word raw removal as synced MP4 stems). Multicam re-encode defaults to
  1080p downscale (--downscale-1080p); user may say "downscale off".
  Use when the user says
  "video-sync", "Video-Sync",
  "--no-align", or provides Working Folder + Audio File + Video 1 (and optional Video 2-4)
  in the format below.
disable-model-invocation: true
---

# Video-Sync

## Inputs (verbatim format)

The user provides:

```
Working Folder: PATH
Audio File: CLEANED-AUDIO-FILE-NAME.wav
Video 1: VIDEO1-FILE.mp4
Video 2: VIDEO2-FILE.mp4
Video 3: VIDEO3-FILE.mp4
```

There will be **between 1 and 4** videos (`Video 1` ... `Video 4` as given). `PATH` is the Working Folder.

- **`--no-align`** (optional): skip the multicam step entirely. Final MP4s for the session are the **`-synced`** files under **`INPUT_DIR`** (see [Sync output directory](#sync-output-directory-temp-vs-input)).
- If **`--no-align`** is **not** given and there are **two or more** videos, run multicam alignment **by default** after all per-video syncs (see below).
- **Downscale (multicam re-encode):** by default, **`multicam_align_trim.py`** downscales to max width **1920** when re-encoding **`-prepped`** outputs (`--downscale-1080p` is on by default). If the initial request includes **`downscale off`** (case-insensitive; e.g. `Downscale off`, `no downscale`), pass **`--no-downscale-1080p`**. Downscale does not apply to **`--stream-copy`** or when a clip is copied with **no head trim** (no re-encode).

## Locate files

- Resolve **Working Folder** to an absolute path when helpful (Windows).
- For **Audio File** and each **Video N** basename, find the file under the Working Folder using, in order:
  1. `Working Folder / <filename>`
  2. `Working Folder / Raw / <filename>`
  3. If still missing, search under the Working Folder for a file with that exact basename (e.g. shallow `rglob`; if multiple hits, prefer the match under `Raw`, then the shortest path).
- Common subfolder names include **Raw** and **Input**; do not assume files are only at the root.

## Episode root `R` (for output folder resolution)

Compute **`R`** once after resolving **Working Folder** and the **Video 1** path (use the resolved path from **Locate files**):

1. If the **Working Folder**'s last path segment equals **`raw`** (case-insensitive), set **`R = parent(Working Folder)`** (the directory above the folder the user passed).
2. Else, if **Video 1**'s immediate parent directory's name equals **`raw`** (case-insensitive), set **`R = parent(that Raw directory)`** — i.e. the folder that contains **`Raw`**, same as the legacy “parallel `Input` next to `Raw`” episode root.
3. Else set **`R = Working Folder`**.

If **`parent(...)`** is not meaningful (e.g. drive root), treat **`R`** as **Working Folder** for the steps below.

## Session folders (`INPUT_DIR` and `TEMP_DIR`)

These are the **only** directories used for **`-synced`**, **`-prepped`**, sync **`.json`** reports (per clip and multicam), and the anchor **`*-prepped.wav`** (basename stem follows [Whole-word `raw` in output stems](#whole-word-raw-in-output-stems)). Always resolve them to absolute paths when running commands.

Let **`WF_RAW`** be true iff the **Working Folder**'s last path segment equals **`raw`** (case-insensitive).

### **`temp` directory existence (case-insensitive)**

When testing whether **`temp`** already exists under a candidate path, treat **`temp`** and **`Temp`** as the same name on case-insensitive filesystems (e.g. Windows): if either exists as a directory, that directory is **`TEMP_DIR`** for that candidate.

### **`INPUT_DIR`**

- **If `WF_RAW` is true** (user passed **`.../Raw`** as Working Folder): use the **parent-first** rule the user requested:
  1. If **`R / Input`** exists as a directory → **`INPUT_DIR = R / Input`**
  2. Else **`INPUT_DIR = Working Folder / Input`** (create with `mkdir -p` semantics if missing).
- **Else** (legacy committed priority when Working Folder is the episode root or anything else):
  1. If **`Working Folder / Input`** exists as a directory → **`INPUT_DIR = Working Folder / Input`**
  2. Else if **`R / Input`** exists as a directory → **`INPUT_DIR = R / Input`**
  3. Else **`INPUT_DIR = Working Folder / Input`** (create with `mkdir -p` semantics if missing).

### **`TEMP_DIR`**

- **If `WF_RAW` is true**:
  1. If **`R / temp`** (case-insensitive; see above) exists as a directory → **`TEMP_DIR`** is that directory.
  2. Else **`TEMP_DIR = Working Folder / temp`** (create with `mkdir -p` semantics if missing).
- **Else**:
  1. If **`Working Folder / temp`** (case-insensitive) exists as a directory → **`TEMP_DIR`** is that directory.
  2. Else if **`R / temp`** (case-insensitive) exists as a directory → **`TEMP_DIR`** is that directory.
  3. Else **`TEMP_DIR = Working Folder / temp`** (create with `mkdir -p` semantics if missing).

### Sync output directory (`temp` vs `Input`)

Define whether this session will produce **`*-prepped.mp4`** via multicam:

- **Prepped path** — **Two or more** listed videos **and** the user did **not** pass **`--no-align`**. After sync, multicam runs and writes **`*-prepped.mp4`** to **`INPUT_DIR`**.
- **Synced-only path** — **One** video only, **or** **`--no-align`**. No **`-prepped`** MP4s; session deliverables are **`-synced`** only.

Then set **`SYNC_DIR`** for this run:

| Session | **`SYNC_DIR`** | Also ensure exists |
|------|----------------|-------------|
| Prepped path | **`TEMP_DIR`** | **`TEMP_DIR`** (if you created it above, done) |
| Synced-only path | **`INPUT_DIR`** | **`INPUT_DIR`** (already ensured) |

Write every **`*-synced.mp4`** and each per-clip sync **`--json-report`** under **`SYNC_DIR`**. When multicam runs, write its **`--json-report`** under **`TEMP_DIR`** (same folder as the **`-synced`** inputs to multicam on the prepped path).

## Per-video processing (mandatory)

For **each** listed video, **one at a time**, in order (Video 1, then Video 2, ...):

1. Run **`scripts/sync_video_wav_replace.py`** from the **repository root** (`automated-video-editing`) with that video's resolved path, the resolved **Audio File** path, and `-o` set to the **intermediate** output path computed below (`*-synced.mp4`).
2. **Recalculate offset every time** - do **not** reuse lag/offset from a previous video in the list; each run performs its own cross-correlation for that file's embedded audio vs the same cleaned WAV.

Always pass **`--json-report`** with a path in **`SYNC_DIR`**, beside that clip's **`-synced`** file (e.g. same basename as the **`-synced`** output with extension **`.json`**).

## Whole-word `raw` in output stems

For **video** **`-synced`** / **`-prepped`** basenames and the **anchor `*-prepped.wav`**, first take the relevant **source stem**:

- **Video outputs:** the input clip's filename **without** `.mp4`.
- **Anchor WAV output:** the **Audio File** basename **without** its extension (e.g. `.wav`).

Then:

- If that stem **includes the word `raw`** as a whole word (case-insensitive; treat spaces, hyphens, and underscores as word separators), **remove that word** and any extra spaces left behind (collapse whitespace; trim).
- Use this **sanitized stem** wherever the sections below build a **`-synced`**, **`-prepped`**, or **`-prepped.wav`** basename. **`-prepped` MP4s** from multicam still come from replacing **`-synced`** with **`-prepped`** in the **already-sanitized** **`-synced`** basename, so they inherit the same rule.

Examples:

- `Intro Guest vid raw.mp4` → sanitized `Intro Guest vid` → `Intro Guest vid-synced.mp4` / `Intro Guest vid-prepped.mp4`
- `Reading audio raw.wav` → sanitized `Reading audio` → `Reading audio-prepped.wav`

## Intermediate output filename (`-synced`)

- Start from the input video's **stem** (filename without `.mp4`), then apply [Whole-word `raw` in output stems](#whole-word-raw-in-output-stems) to get the basename stem used in the output.
- Append the suffix **`-synced`** before the extension.
- Extension: **`.mp4`**.

Examples:

- `Intro Guest vid raw.mp4` -> `Intro Guest vid-synced.mp4`
- `Intro Ben vid raw.mp4` -> `Intro Ben vid-synced.mp4`

## Output folder (sync step)

Write every **`-synced`** MP4 to **`SYNC_DIR / <intermediate filename>`** ([Sync output directory](#sync-output-directory-temp-vs-input)). Ignore whether the source lives under `Raw` or elsewhere for this path; **`SYNC_DIR`** already accounts for **`INPUT_DIR`** / **`TEMP_DIR`**.

## Command template (sync only)

From the repository root (use the resolved **`SYNC_DIR`** for this session):

```bash
python scripts/sync_video_wav_replace.py "<resolved-video-path>" "<resolved-audio-path>" -o "<SYNC_DIR>/<intermediate-filename>.mp4" --json-report "<SYNC_DIR>/<intermediate-filename>.json"
```

When the video's embedded audio does not correlate with the external WAV (common with
MultiCorder when HDMI embed differs from Output WAV recorders), the script **automatically
muxes at sample 0** if peak strength is below **0.35**. The JSON report records both
the detected (unused) lag and `start_aligned_fallback: true`. Force that behavior with
`--assume-start-aligned`; tune the threshold with `--min-correlation-strength`.

## Multicam alignment (default when 2+ videos)

When there are **two or more** videos **and** the user did **not** pass **`--no-align`**:

1. **After** every `sync_video_wav_replace.py` run for that session has finished, resolve each **`-synced`** MP4 path under **`SYNC_DIR`** (on the prepped path, **`SYNC_DIR`** is **`TEMP_DIR`**).
2. From the **repository root**, run **`scripts/multicam_align_trim.py`** once with:
   - Arguments in **Video 1, Video 2, ...** order (Video 1 = correlation anchor only).
   - **`--prepped-names`** so final outputs are named by replacing **`-synced`** with **`-prepped`** in the stem (e.g. `Play Wide vid-synced.mp4` -> `Play Wide vid-prepped.mp4`). Do **not** use the default `-multicamaligned` suffix for this skill.
   - **`--out-dir`** set to **`INPUT_DIR`** so **`*-prepped.mp4`** files are written there; **`-synced`** inputs stay under **`TEMP_DIR`** on the prepped path.
3. Default **`--align-to earliest`** on the multicam script. Add **`--align-to latest`** only if the user asks for the "slowest camera wins" rule.
4. **Downscale:** default **on** (`multicam_align_trim.py` applies **`--downscale-1080p`** automatically). If the user said **`downscale off`**, add **`--no-downscale-1080p`**.
5. **`--json-report`** under **`TEMP_DIR`** (e.g. `video-sync-multicam.json`). Optional: `--dry-run` on the multicam step if the user wants trims printed only; **`--stream-copy`** only if the user explicitly accepts keyframe-approximate trims (default is re-encode).

```bash
python scripts/multicam_align_trim.py --prepped-names --out-dir "<input-dir>" --json-report "<temp-dir>/video-sync-multicam.json" "<synced-video-1-under-temp>" "<synced-video-2-under-temp>"
```

If the user said **`downscale off`**:

```bash
python scripts/multicam_align_trim.py --prepped-names --no-downscale-1080p --out-dir "<input-dir>" --json-report "<temp-dir>/video-sync-multicam.json" "<synced-video-1-under-temp>" "<synced-video-2-under-temp>"
```

Use **`INPUT_DIR`** for **`<input-dir>`** and **`TEMP_DIR`** for **`<temp-dir>`** (absolute paths).

If only **one** video was listed, **skip** multicam (nothing to align across angles).

## Anchor audio WAV (mandatory last step)

After **all** video steps for Video 1 are finished (multicam when applicable, otherwise sync-only), extract the **muxed audio** from **Video 1's final MP4** (the anchor) to a WAV under **`INPUT_DIR`**.

- **Output path:** **`INPUT_DIR / {audio-output-stem}-prepped.wav`** where **`{audio-output-stem}`** is the **Audio File** basename **without** its extension, then sanitized with the same **whole-word `raw` removal** as in [Whole-word `raw` in output stems](#whole-word-raw-in-output-stems) (e.g. `Intro Audio clean.wav` → `Intro Audio clean-prepped.wav`; `Reading audio raw.wav` → `Reading audio-prepped.wav` relative to **`INPUT_DIR`**). Do **not** place this WAV next to the cleaned source WAV unless that folder is also **`INPUT_DIR`**.
- **Source MP4 (anchor, Video 1):**
  - If multicam ran (2+ videos and no **`--no-align`**): **`INPUT_DIR /`** basename = Video 1's **`-synced`** basename with **`-synced`** replaced by **`-prepped`**.
  - If multicam was skipped (**`--no-align`** or only **one** video): Video 1's **`-synced`** MP4 under **`SYNC_DIR`** (on the synced-only path, **`SYNC_DIR`** is **`INPUT_DIR`**).

From the **repository root**:

```bash
python scripts/extract_mp4_audio_wav.py "<anchor-final-mp4-path>" "<input-dir>/<audio-output-stem>-prepped.wav"
```

This WAV is the anchor's audio **after** the same head trims as its final video (sync + optional multicam). It is **not** a remaster of the original input WAV; it is a decode of the anchor MP4's audio track.

## Final deliverable naming

- With multicam (default, 2+ clips): **`INPUT_DIR / *.mp4`** whose stem ends in **`-prepped`** (from `--prepped-names` + `--out-dir` to **`INPUT_DIR`**; replaces **`-synced`**, not stacked with `-multicamaligned`). Intermediate **`-synced`** (and per-clip sync JSON) stay under **`TEMP_DIR`**.
- With **`--no-align`** or a **single** video: the session's MP4 deliverable(s) are the **`-synced`** file(s) under **`INPUT_DIR`** (Video 1 anchor for extraction); per-clip sync JSON is beside them in **`INPUT_DIR`**.

The **`-synced`** files under **`TEMP_DIR`** may remain on disk after multicam; delete them only if the user asks. The anchor **`*-prepped.wav`** under **`INPUT_DIR`** (sanitized **Audio File** stem + **`-prepped.wav`**) is written whenever video-sync completes successfully for Video 1.

## Dependencies

**ffmpeg** / **ffprobe** on `PATH`, **NumPy**, **SciPy** (same as other sync scripts in this repo).

## After running

For each **sync** output, briefly report: path, lag in **ms**, correlation **peak strength**, any **drift** / caveats.

If multicam ran, also report: **`--align-to` mode**, **reference clip** (no head trim on that file), **lag vs Video 1** and **head trim ms** per file, each **`-prepped`** path, and whether **1080p downscale** was applied (default yes unless **`--no-downscale-1080p`**). Note re-encode unless **`--stream-copy`** was used.

Always report the **anchor `*-prepped.wav`** path from **`extract_mp4_audio_wav.py`**.

If a video file cannot be found or sync fails, stop that step with a clear error and continue only if the user wants the remaining videos attempted. If Video 1 never reached a final MP4, **skip** the anchor WAV extract and explain why.
