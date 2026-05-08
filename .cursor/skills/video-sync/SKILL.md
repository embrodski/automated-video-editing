---
name: video-sync
description: >-
  For each of 1-4 MP4s under a Working Folder, cross-correlates the video's
  embedded audio against one shared cleaned WAV and muxes the video with that
  aligned audio via scripts/sync_video_wav_replace.py. When two or more videos
  are listed, multicam waveform alignment runs by default (scripts/multicam_align_trim.py
  with --prepped-names) unless the user passes --no-align, then runs
  scripts/extract_mp4_audio_wav.py to write the anchor (Video 1) final audio as
  <audio-stem>-prepped.wav in the same folder as the final MP4 deliverables
  (e.g. Input when -synced/-prepped MP4s are written there). Use when the user says
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

- **`--no-align`** (optional): skip the multicam step entirely. Final outputs for the user are the **`-synced`** MP4s only.
- If **`--no-align`** is **not** given and there are **two or more** videos, run multicam alignment **by default** after all per-video syncs (see below).

## Locate files

- Resolve **Working Folder** to an absolute path when helpful (Windows).
- For **Audio File** and each **Video N** basename, find the file under the Working Folder using, in order:
  1. `Working Folder / <filename>`
  2. `Working Folder / Raw / <filename>`
  3. If still missing, search under the Working Folder for a file with that exact basename (e.g. shallow `rglob`; if multiple hits, prefer the match under `Raw`, then the shortest path).
- Common subfolder names include **Raw** and **Input**; do not assume files are only at the root.

## Per-video processing (mandatory)

For **each** listed video, **one at a time**, in order (Video 1, then Video 2, ...):

1. Run **`scripts/sync_video_wav_replace.py`** from the **repository root** (`automated-video-editing`) with that video's resolved path, the resolved **Audio File** path, and `-o` set to the **intermediate** output path computed below (`*-synced.mp4`).
2. **Recalculate offset every time** - do **not** reuse lag/offset from a previous video in the list; each run performs its own cross-correlation for that file's embedded audio vs the same cleaned WAV.

Optional: `--json-report "<output-without-.mp4> report.json"` for alignment metadata.

## Intermediate output filename (`-synced`)

- Start from the input video's **stem** (filename without `.mp4`).
- If the stem **includes the word `raw`** as a whole word (case-insensitive; treat spaces, hyphens, and underscores as word separators), **remove that word** and any extra spaces left behind (collapse whitespace; trim).
- Append the suffix **`-synced`** before the extension.
- Extension: **`.mp4`**.

Examples:

- `Intro Guest vid raw.mp4` -> `Intro Guest vid-synced.mp4`
- `Intro Ben vid raw.mp4` -> `Intro Ben vid-synced.mp4`

## Output folder (sync step)

- If the **source video** path sits in a subfolder named **`Raw`** (parent directory name is exactly `Raw`), choose the output folder in this order:
  1. If `Working Folder / Input` exists as a directory, write the **`-synced`** MP4 to **`Working Folder / Input / <intermediate filename>`**.
  2. Else, check for a **parallel** `Input` folder next to `Raw`: i.e. if the source video is under `<Parent>/Raw/...`, check whether `<Parent>/Input` exists as a directory. If it exists, write the **`-synced`** MP4 to **`<Parent>/Input / <intermediate filename>`**.
  3. Else write the **`-synced`** MP4 to the **same directory as the source video**.
- If the source video is **not** under a `Raw` folder, write the **`-synced`** MP4 to the **same directory as the source video**.

## Command template (sync only)

From the repository root:

```bash
python scripts/sync_video_wav_replace.py "<resolved-video-path>" "<resolved-audio-path>" -o "<resolved-synced-output-path>"
```

## Multicam alignment (default when 2+ videos)

When there are **two or more** videos **and** the user did **not** pass **`--no-align`**:

1. **After** every `sync_video_wav_replace.py` run for that session has finished, resolve each **`-synced`** MP4 path (same rules: `Input` vs same folder as source).
2. From the **repository root**, run **`scripts/multicam_align_trim.py`** once with:
   - Arguments in **Video 1, Video 2, ...** order (Video 1 = correlation anchor only).
   - **`--prepped-names`** so final outputs are named by replacing **`-synced`** with **`-prepped`** in the stem (e.g. `Play Wide vid-synced.mp4` -> `Play Wide vid-prepped.mp4`). Do **not** use the default `-multicamaligned` suffix for this skill.
3. Default **`--align-to earliest`** on the multicam script. Add **`--align-to latest`** only if the user asks for the "slowest camera wins" rule.
4. Optional: `--dry-run` on the multicam step if the user wants trims printed only; `--json-report` on the multicam step; **`--stream-copy`** only if the user explicitly accepts keyframe-approximate trims (default is re-encode).

```bash
python scripts/multicam_align_trim.py --prepped-names "<synced-video-1-path>" "<synced-video-2-path>" "<synced-video-3-path>"
```

If only **one** video was listed, **skip** multicam (nothing to align across angles).

## Anchor audio WAV (mandatory last step)

After **all** video steps for Video 1 are finished (multicam when applicable, otherwise sync-only), extract the **muxed audio** from **Video 1's final MP4** (the anchor) to a WAV in the **same directory as that final MP4**—i.e. the same folder where the session's **`-prepped`** (or **`--no-align`** / single-video **`-synced`**) deliverables live, which may be **`Working Folder / Input`** when the sync step wrote there, or the source video's folder otherwise.

- **Output path:** **`{parent-of-anchor-final-mp4}/{stem}-prepped.wav`** where **`{stem}`** is the **Audio File** basename **without** its extension (e.g. `Intro Audio clean.wav` → `Intro Audio clean-prepped.wav`). Do **not** place this WAV next to the cleaned audio file unless that folder is also where the final MP4s were written.
- **Source MP4 (anchor, Video 1):**
  - If multicam ran (2+ videos and no **`--no-align`**): the **`-prepped`** file for Video 1 (same path rules as for `*-prepped.mp4`: take Video 1's **`-synced`** path, then replace **`-synced`** with **`-prepped`** in the basename).
  - If multicam was skipped (**`--no-align`** or only **one** video): Video 1's **`-synced`** MP4 path.

From the **repository root**:

```bash
python scripts/extract_mp4_audio_wav.py "<anchor-final-mp4-path>" "<same-dir-as-that-mp4>/<audio-stem>-prepped.wav>"
```

This WAV is the anchor's audio **after** the same head trims as its final video (sync + optional multicam). It is **not** a remaster of the original input WAV; it is a decode of the anchor MP4's audio track.

## Final deliverable naming

- With multicam (default, 2+ clips): **`*.mp4`** whose stem ends in **`-prepped`** (from `--prepped-names`; replaces **`-synced`**, not stacked with `-multicamaligned`).
- With **`--no-align`** or a **single** video: final deliverable is the **`-synced`** file only (Video 1 anchor for extraction).

The **`-synced`** intermediates may remain on disk alongside **`-prepped`**; delete them only if the user asks. The **`-prepped.wav`** anchor extract is an additional final artifact whenever video-sync completes successfully for Video 1.

## Dependencies

**ffmpeg** / **ffprobe** on `PATH`, **NumPy**, **SciPy** (same as other sync scripts in this repo).

## After running

For each **sync** output, briefly report: path, lag in **ms**, correlation **peak strength**, any **drift** / caveats.

If multicam ran, also report: **`--align-to` mode**, **reference clip** (no head trim on that file), **lag vs Video 1** and **head trim ms** per file, and each **`-prepped`** path. Note re-encode unless **`--stream-copy`** was used.

Always report the **anchor `*-prepped.wav`** path from **`extract_mp4_audio_wav.py`**.

If a video file cannot be found or sync fails, stop that step with a clear error and continue only if the user wants the remaining videos attempted. If Video 1 never reached a final MP4, **skip** the anchor WAV extract and explain why.
