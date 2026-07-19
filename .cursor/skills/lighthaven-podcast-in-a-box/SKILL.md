---
name: lighthaven-podcast-in-a-box
description: >-
  Walk-in podcast pipeline: scan MultiCorder dumps in E:\PodcastRoom, label
  Host/Guest/Wide video and Host/Guest audio, then run conversation-sync,
  Combined-as-Clean (DeRoom placeholder), video-sync, ElevenLabs transcribe,
  podcast autocut 1-min approval, and full interview render. Use when the user
  says "Lighthaven Podcast In A Box", "podcast in a box", "PIAB", or wants a
  stripped-down interview-only edit from fresh MultiCorder files.
---

# Lighthaven Podcast In A Box

Cursor-guided skill (no GUI). Reuses harness Interview tools; skips reading, intro, stitch, hand-edit, and real DeRoom.

**State file:** `<working_folder>/podcast-in-a-box.json`  
**Default scan root:** `E:\PodcastRoom`

## Hard rules

- **No overwrite** without listing paths and getting explicit approval; then pass `--allow-overwrite`.
- **No long renders** (>~30s) without user confirmation (prep chain and full render both count).
- After rename/move: give **Estimate A**, wait for OK before prep.
- After 1-min approval: give **Estimate B**, wait for OK before full render.
- Stop at the **1-min approval gate**; do not auto-start the full render.
- **Use 5-minute completion checks for long jobs.** After launching prep or full render in the background: confirm it started once and report the estimate. Do **not** busy-wait with sub-minute polling. While the job is running, **check status about every 5 minutes** until completion or failure, then notify the user immediately (short progress notes on intermediate checks are fine). This is agent monitoring, not part of the render pipeline or future standalone app. See project **`AGENTS.md`**.

### Revealing folders / files to the user

Whenever you ask the user to look at a folder (previews, Raw, Output, etc.) or open a deliverable folder:

1. **Open it in File Explorer** with:
   ```powershell
   explorer.exe "<absolute Windows path>"
   ```
2. In the chat message, always give **both**:
   - Plain full path for copy-paste: `E:\PodcastRoom\<name>\Temp\piab-previews`
   - Optional markdown link: `[Open folder](file:///E:/PodcastRoom/<name>/Temp/piab-previews)`  
     (use forward slashes in the `file:///` URL)
3. Do **not** rely on clickable `file://` links alone — Cursor’s chat webview often fails them silently.

## Standard Raw names (after labeling)

| Role | Filename |
|------|----------|
| Host video | `Host Raw Video.mp4` |
| Guest video | `Guest Raw Video.mp4` |
| Wide video | `Wide Raw Video.mp4` |
| Host audio | `Host Raw Audio.wav` |
| Guest audio | `Guest Raw Audio.wav` |

MultiCorder sources (top-level only under scan root):

- Video: `MultiCorder[n] - DeckLink Quad HDMI Recorder ... .MP4`
- Audio: `MultiCorder[n] - Output [m] ... .WAV`

---

## Step 1 — Scan and confirm

```powershell
Set-Location "<repo>"
python scripts/piab_scan_session.py --root "E:\PodcastRoom"
```

Show the user: file list, typical mtime, typical duration, counts. Ask: **Are these the files from this session?** and **What should the working folder be named?**

On confirm:

```powershell
python scripts/piab_init_session.py --name "<UserChosenName>" --root "E:\PodcastRoom"
```

Creates `E:\PodcastRoom\<UserChosenName>\` with `Raw`, `Input`, `Output`, `Temp`, and `podcast-in-a-box.json`.

---

## Step 2 — Label videos

```powershell
python scripts/piab_extract_video_previews.py "E:\PodcastRoom\<name>"
```

The script names the previews `Camera 1.jpg`, `Camera 2.jpg`, etc. Before asking
for labels, **open the preview folder** (`explorer.exe`) and give the plain path
plus optional `file:///` link (see **Revealing folders** above).

For each preview JPG: **Read the image**, identify it by the matching `Camera X`
filename, and ask the user to label **Host**, **Guest**, **Wide**, or
**do not use**.

Rules: exactly one Host, one Guest, one Wide; all others do not use.

Show a confirmation table. Offer **Accept**, **Re-label**, or **Swap Host ↔ Guest** (before move).

---

## Step 3 — Label audio

```powershell
python scripts/piab_extract_audio_previews.py "E:\PodcastRoom\<name>"
```

The script names the previews `Mic 1.wav`, `Mic 2.wav`, etc. Before asking
for labels, **open the preview folder** (`explorer.exe`) and give the plain path
plus optional `file:///` link (see **Revealing folders** above).

Each preview is a ~4s loud clip past the quarter-point. Ask the user to play
each `Mic X.wav` and label **Host**, **Guest**, or **do not use**.

Rules: exactly one Host, one Guest; rest do not use. Confirm / re-label / swap Host ↔ Guest before applying.

---

## Step 4 — Apply labels + Estimate A

Build JSON maps of absolute source path → role, then:

```powershell
python scripts/piab_apply_labels.py "E:\PodcastRoom\<name>" --video-labels-json "<json>" --audio-labels-json "<json>"
```

Script moves files into `Raw` and prints **Estimate A** (prep through 1-min test).

**Open `Raw`** (`explorer.exe`), give plain path + optional link, tell the user
the estimate, then **wait for confirmation** before prep.

### Swap / re-label after move

```powershell
# Swap Host/Guest files in Raw (clears downstream prep state)
python scripts/piab_swap.py "E:\PodcastRoom\<name>" --files video   # or audio | both

# If wrong files were labeled and sources still exist: re-run extract + apply
# (may need --allow-overwrite after user approval)
```

---

## Step 5 — Prep through 1-min test

Long job — only after Estimate A approval:

```powershell
python scripts/piab_run_prep.py "E:\PodcastRoom\<name>"
```

Does: conversation-sync → copy Combined→Clean (**DeRoom placeholder**) → video-sync → `elevenlabs_transcribe_wav.py` → podcast autocut **1 Min Test.mp4**.

Optional phrase gates (persist on `podcast-in-a-box.json` before DSL generation):
- `start_phrase` / optional `start_preroll_sec` (default 1.0)
  - When set, the speaker who says the start phrase is Host for camera mapping (`speaker_0`)
- `end_phrase` / optional `end_postroll_sec` (default 2.0)
- `pause_phrase` / `unpause_phrases` (list) / optional `pause_preroll_sec` (0.25) / `pause_postroll_sec` (0.7)
- `abort_phrase` (anywhere in full transcript disables Pause/Unpause)

BayesVishal / walk-in defaults when set on state:
- Pause: `Computer Freeze Program.`
- Unpause (either): `Computer Resume Program` / `Computer Unfreeze Program`
- Abort: `Emergency override - Eject the warp core`

Then **open `Output`** (`explorer.exe`), give plain path + optional link, and tell
the user:

> 1 Min Test is ready for review: `E:\PodcastRoom\<name>\Output\1 Min Test.mp4`

**Stop and wait.**

### 1-min approval loop

| User intent | Action |
|-------------|--------|
| Looks good | Go to Estimate B |
| Host/Guest cameras feel swapped | `python scripts/piab_swap.py "<folder>" --speaker-ids toggle` then `python scripts/piab_rerun_one_min.py "<folder>" --allow-overwrite` (after overwrite approval) |
| Wrong Raw Host/Guest files | `piab_swap.py --files video` and/or `--files audio`, then re-run **full prep** (`piab_run_prep.py --allow-overwrite` after approval) |
| Other fixes | Adjust and re-run 1-min only when possible |

---

## Step 6 — Estimate B + full render

```powershell
python scripts/piab_estimate.py "E:\PodcastRoom\<name>" --which full --mark-awaiting
```

Show the estimate. **Wait for confirmation.** Then:

```powershell
python scripts/piab_run_full_render.py "E:\PodcastRoom\<name>"
```

When done, **open `Output`** (`explorer.exe`), give plain path + optional link, and
say exactly:

> Full render is complete: `E:\PodcastRoom\<name>\Output\Full Interview.mp4`

Filename: **`Full Interview.mp4`** under the session **Output** folder. Stop.

---

## Resume

Read `podcast-in-a-box.json` → `resume_at` and `steps`.

| `resume_at` | Next action |
|-------------|-------------|
| `03_label_videos` | Video previews / labels |
| `04_label_audio` | Audio previews / labels |
| `05_estimate_prep` | Show Estimate A; on OK run prep |
| `11_one_min_approval` | Review 1 Min Test |
| `12_estimate_full` | Show Estimate B; on OK full render |
| `14_done` | Finished |

---

## Out of scope (v1)

- GUI
- Real DeRoom (placeholder only)
- Reading / intro / stitch / hand-edit
- 5-minute test gate
