---
name: inkhaven-color-match
description: Color-match up to four target videos to a reference source video using the repo's standalone renderer. Use when the user says "Inkhaven-Color-Match", "color match", "match these videos to a source", or provides a working folder with target files plus a source/reference video.
---

# Inkhaven Color Match

## Inputs to collect

- **Working folder path**: contains the reference video, target videos, outputs, and any temp files if needed.
- **Source file**: the reference video used for analysis only.
- **Target files**: 1 to 4 video files to render against the source.
- Optional:
  - `sample_seconds` override (default `8.0`)
  - `max_frames` override (default `240`)
  - whether to do a `--dry-run` first
  - whether to **downscale 4K to 1080p**
  - **`--workers N`**: render up to **N targets** in parallel (probe/analysis, then encode). Default `1`. Capped at the number of `--target` files.
  - **`--time-chunks N`**: split each **filtered** (non-passthrough) target encode into **N equal-duration** segments, encode segments in parallel, then **concat** with validation. Default **`1`** (**off**). Only add if the user asks for faster / chunked rendering or explicitly agrees after you explain tradeoffs.
  - **`--chunk-workers M`**: max parallel **segment** encodes per target when `--time-chunks` > 1. Default `4`, capped at `--time-chunks`.
  - **`--video-preset`** / **`--video-quality`**: override defaults (**`ultrafast`** + **23**, aligned with podcast clip renders).

## Core rules

- The source/reference file is **analysis only**. Do not render it as an output.
- Render **one corrected file per target** into the **same working folder**.
- Output filenames must append **`-colorcorr`** before the original extension.
- Preserve the **target video's audio**.
- Do not change the target video's timeline length or audio content.
- Accept **up to four** target files.
- By default, let the renderer use **hardware H.264 encoding if available**; otherwise it should fall back to `libx264`. Only override this if the user explicitly asks for a specific encoder.
- Default encode tuning matches podcast clip renders: **`ultrafast`** + **quality 23** (overridable with `--video-preset` / `--video-quality`).
- **`--time-chunks` > 1** is invalid for targets that would **passthrough-copy** (empty filter). In that case use `--time-chunks 1` or adjust inputs. If **`--workers` > 1** and **`--time-chunks` > 1**, many `ffmpeg` processes may run at once; warn the user they can lower **`--workers`** and/or **`--chunk-workers`** if disk or GPU struggles.
- If the user's initial request says `Downscale 4K to 1080p` or equivalent phrasing, add `--downscale-4k-to-1080p` so true 4K targets are rendered at `1920x1080`.
- When 1080p downscale applies, the renderer uses **downscale → color correction → encode** on the target: the **same** scale/pad chain is applied **before** signalstats probes and `build_color_match_vf` on **both** reference and target, so analysis matches output geometry.
- If any provided target is **not** 4K, first ask the user whether that specific file should also be rendered at `1920x1080` or left at its native resolution. Use `--downscale-target "<filename>"` only for the non-4K targets the user explicitly approves.
- If the computed filter is empty, the renderer may passthrough-copy the file instead of re-encoding.

## Workflow

### Listing folder contents (when the user asks)

When the user asks for a **list of files in a folder** (or you list a folder for them to pick source/targets):

- Collect **only** files whose extension is **`.mp4`** (case-insensitive).
- **Order** `.mp4` files for display: split into names **without** `Wide` vs **with** `Wide` (match the **basename** case-insensitively). Sort each group by **filename** (lexicographic). List **non-`Wide` first**, then **`Wide`** (so e.g. `Ben Wide.mp4` is always last among `.mp4` when present). If several names contain `Wide`, sort that tail by filename too.
- Assign **1-based** indices **in that final order**: **1**, **2**, **3**, …
- In the reply, show **each `.mp4` on its own line** with the **number before** the filename, e.g. `1. Alice Video.mp4` or `1) Alice Video.mp4` (pick one style and use it consistently in that message).
- List **non-`.mp4`** files after the numbered block (no index). Use the same **`Wide` last** rule there: names **without** `Wide` first (sorted), then names **with** `Wide` (sorted).
- **End** that reply with this sentence (final line is fine): **You may list the target files by number rather than name.**
- **Interactive follow-up (same turn, after that footer):** ask exactly **What are the targets to be color-corrected?** Do **not** ask for the source yet—**only** after the user answers targets may you ask about the source.
- **Numbered `.mp4` block (reuse):** Whenever the skill calls for the **full set of `.mp4` files** in the working folder, use **this section’s ordering and numbering** (non-`Wide` group sorted, then `Wide` group sorted; one line per file with **1-based** index before the name). Apply the same style you used earlier in the thread (e.g. `1.` vs `1)`).

### Selection flow after listing (numbers or names)

Use this when the user is driving the job **after** you showed a **numbered `.mp4` list** for a folder (same rules as **Listing folder contents**). Keep the **folder path** in context as the working folder.

- **Targets first**: When the user answers **What are the targets to be color-corrected?**, accept **either** basenames **or** **1-based indices** referring to that list’s **`.mp4` order only** (non-`.mp4` files are never numbered). Resolve numbers to full paths under the working folder. Enforce **up to four** targets; if unclear, ask.
- **Only after targets are settled**, in **one** reply: output the **numbered `.mp4` block** again for the **working folder**—**all** **`.mp4`** files currently present (re-read the directory when possible so the list is not stale). Use the **Numbered `.mp4` block** rules from **Listing folder contents**. You do **not** need to repeat the non-`.mp4` list on this turn unless it helps the user. Then ask exactly: **What is the source?**
- **Source**: Accept **filename** or **number** indexing **the `.mp4` list you just showed in that message** (if the folder unchanged, indices match the earlier listing). Resolve to a single reference path. The source remains **analysis only** (not an output).
- Ask exactly: **Begin color match process? Please list any optional flags here as well.**
- If the user confirms (**Yes** / clear affirmative), run **Inkhaven Color Match** from the repo root: `python color_match_render.py` with `--reference`, one `--target` per resolved file, `-o` set to the **working folder**, plus any optional flags they named—map their wording to the script’s flags (e.g. `--dry-run`, `--downscale-4k-to-1080p`, `--downscale-target`, `--workers`, `--time-chunks`, `--chunk-workers`, `--video-preset`, `--video-quality`, `--sample-seconds`, `--max-frames`, `--strength`, `--video-encoder`, `--suffix`). If they confirm but give **no** flags, use script defaults. If they decline or hedge, clarify before running.
- If the user uses numbers **without** a recent list in the thread, ask them to **re-list the folder** or give **full filenames** so indices are unambiguous.

### 1) Confirm files in the working folder

List the files in the working folder and confirm:

- which **1 to 4** files are targets
- which file is the **source/reference**

When you show that inventory to the user, use the same **numbered `.mp4` listing** rules as in **Listing folder contents** above, and end with: **You may list the target files by number rather than name.** If you are walking the user through choices interactively, ask **What are the targets to be color-corrected?** first; **What is the source?** only after they answer—and **immediately before** **What is the source?**, show the **full numbered `.mp4` list** for the folder again (see **Selection flow after listing**).

If any provided file is missing, stop and ask the user to clarify.

### 2) Run dry-run first when useful

Use dry-run when:

- the user asks for verification first
- filenames look suspicious
- you want to confirm the computed filters before a full render

Before the dry-run or final render, probe each target's resolution with `ffprobe`.

- If the user asked to downscale 4K footage, apply `--downscale-4k-to-1080p` for true 4K targets.
- If any target is not 4K, stop and ask the user for that file specifically:
  - `Downscale to 1080p`
  - `Leave as is`
- If the user chooses `Downscale to 1080p` for a non-4K target, add `--downscale-target "<target filename>"`.

Command template:

```powershell
python "color_match_render.py" --reference "<folder>\<source file>" --target "<folder>\<target 1>" --target "<folder>\<target 2>" -o "<folder>" --dry-run
```

Add more `--target` flags as needed, up to four.

### 3) Run the actual render

Command template:

```powershell
python "color_match_render.py" --reference "<folder>\<source file>" --target "<folder>\<target 1>" --target "<folder>\<target 2>" -o "<folder>"
```

Notes:

- Run from the repo root so `color_match_render.py` can import the package code.
- Keep the output folder the same as the working folder unless the user explicitly asks otherwise.
- The script already uses the correct default suffix: `-colorcorr`.
- The script now defaults to encoder auto-selection: working hardware H.264 if available, otherwise `libx264`.
- If the user explicitly asks to downscale 4K footage, add `--downscale-4k-to-1080p`.
- For any non-4K target that the user explicitly approves for 1080p output, add `--downscale-target "<target filename>"`.
- **Parallel targets** (optional): add `--workers <N>` when the user wants multiple targets processed concurrently (same cap as number of targets).
- **Time-chunked encode** (optional, **default off**): only when the user asks for it. Add `--time-chunks <N>` (e.g. `4`) and optionally `--chunk-workers <M>`. The script uses post-input **`-ss`** for accurate cuts, **AAC per chunk**, **concat copy** with **re-encode fallback** and **duration validation**. Do **not** enable unless every target will get a **non-empty** color filter.

Example with parallelism and time-chunking (user-requested):

```powershell
python "color_match_render.py" --reference "<folder>\<source file>" --target "<folder>\<target 1>" --target "<folder>\<target 2>" -o "<folder>" --workers 2 --time-chunks 4 --chunk-workers 4
```

### 4) Validate outputs

Confirm that each expected output exists in the working folder:

- `<target stem>-colorcorr<original extension>`

Also confirm the files are non-trivial in size.

## Example request

User:

```text
Run Inkhhaven-Color-Match
Target files:
File1.mp4
File2.mp4
File3.mp4
File4.mp4
Source file:
Source.mp4
Folder:
D:\Project\ColorMatch
```

Assistant:

- Verify those files exist in `D:\Project\ColorMatch`
- Run:

```powershell
python "color_match_render.py" --reference "D:\Project\ColorMatch\Source.mp4" --target "D:\Project\ColorMatch\File1.mp4" --target "D:\Project\ColorMatch\File2.mp4" --target "D:\Project\ColorMatch\File3.mp4" --target "D:\Project\ColorMatch\File4.mp4" -o "D:\Project\ColorMatch"
```

- Confirm outputs:
  - `File1-colorcorr.mp4`
  - `File2-colorcorr.mp4`
  - `File3-colorcorr.mp4`
  - `File4-colorcorr.mp4`
