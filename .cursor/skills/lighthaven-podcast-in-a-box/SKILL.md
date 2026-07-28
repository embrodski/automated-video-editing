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

**Immediate failure alerts:** `piab_run_prep.py` and `piab_run_full_render.py` write **`Temp/harness-FAILURE.json`** and show a **Windows toast** (with sound) when a step fails (e.g. ElevenLabs billing). If you launched prep in the background, also check for that marker file or a non-zero exit — do not wait for the next 5-minute poll to report failures.

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

## Step 1 — Where are the source files?

**Email delivery (optional):** When starting a **new** session (not resume), ask whether to email `Full Interview.mp4` when the full render completes. If yes, collect the recipient email, read it back, and confirm with **“Is this correct? [Y/N or A to abort]”**. Abort = continue without delivery. On **resume**, do not re-prompt if `podcast-in-a-box.json` already has a confirmed delivery email for this session.

Interactive launcher (`piab_start_session.py`) handles this after init. Agent-driven starts should call the same flow or use:

```powershell
python scripts/piab_init_session.py --working-folder "<folder>" --delivery-email "user@example.com" --confirm-delivery-email
```

Secrets: copy `delivery-config.example.env` and set Frame.io + Gmail SMTP env vars before full render delivery runs. For Gmail, run:

```powershell
python scripts/harness_setup_smtp.py
python scripts/harness_smtp_test.py --to "you@gmail.com"
```

This writes a gitignored repo-root `.env` loaded automatically by `piab_run_full_render.py`.

**Frame.io (Native App OAuth):** on Windows, register the Adobe `adobe+://` redirect handler once, then browser login and ID discovery:

```powershell
python scripts/harness_frameio_oauth.py register-protocol
python scripts/harness_frameio_oauth.py login
python scripts/harness_frameio_discover.py --write-env
```

After Adobe sign-in, allow the browser prompt to **Open** the PIAB OAuth handler. App Builder projects often do not expose Redirect URI editing; this path uses the existing Native App credential without changing Adobe Console.

Tokens live in `.frameio-oauth.json` (gitignored) and refresh automatically.

**First ask the user:**

> Are the MultiCorder files in the **default folder** (`E:\PodcastRoom`), or in a **special folder** you already created (e.g. `E:\Bayeswatch\Jessiah`)?

### Default folder (previous behavior)

Sources sit at the top level of `E:\PodcastRoom`. PIAB creates a **new working subfolder** there.

```powershell
Set-Location "<repo>"
python scripts/piab_scan_session.py --root "E:\PodcastRoom"
```

Show the user: file list, typical mtime, typical duration, counts, and any **`requirements.missing`** lines. Ask: **Are these the files from this session?** and **What should the working folder be named?**

On confirm:

```powershell
python scripts/piab_init_session.py --name "<UserChosenName>" --root "E:\PodcastRoom"
```

Creates `E:\PodcastRoom\<UserChosenName>\` with `Raw`, `Input`, `Output`, `Temp`, and `podcast-in-a-box.json`. Init scans **`E:\PodcastRoom`** (not the empty new subfolder).

### Special folder (sources already in place)

The user gives a **single folder path** that **is** the working folder and already contains the MultiCorder files (often alongside future `Raw` / `Output` subfolders).

```powershell
python scripts/piab_scan_session.py --root "<SpecialFolderPath>" --strict
```

If **`requirements.ok`** is false, **stop and tell the user** what is missing (need ≥3 camera MP4s and ≥2 Output WAVs). Do not init until the folder is complete or the user explicitly accepts incomplete files.

On confirm:

```powershell
python scripts/piab_init_session.py --working-folder "<SpecialFolderPath>"
```

Init scans **that folder only**. Do **not** pass `--root` + `--name` for special folders.

### Interactive launcher (optional)

For a terminal-only flow without the agent:

```powershell
python scripts/piab_start_session.py
```

Prompts default vs special, scans, validates, then calls init.

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

The script names the previews `Mic 1 A.wav`, `Mic 1 B.wav`, etc. (two **5 s**
clips from different parts of each track). Before asking for labels, **open the
preview folder** (`explorer.exe`) and give the plain path plus optional
`file:///` link (see **Revealing folders** above).

Silent or empty Output WAVs are skipped automatically (not shown for labeling).

Play each preview clip and label **Host**, **Guest**, or **do not use** per
**mic** (both A and B clips for a mic share the same source file).

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

To **resume** after a failure (e.g. ElevenLabs billing) without redoing video-sync:

```powershell
python scripts/piab_resume_prep.py "E:\PodcastRoom\<name>"
python scripts/piab_run_prep.py "E:\PodcastRoom\<name>" --resume
```

`--resume` skips steps whose outputs already exist on disk (conversation-sync → clean audio → prepped Input files → transcript → 1 Min Test). Optional `--from-step transcribe` (aliases: `video_sync`, `one_min`, `06`–`10`) forces a start point. On failure, `Temp/harness-FAILURE.json` records the step; the next `--resume` starts there.

Interactive launcher option **2 = resume existing session** runs the same path.

Does: conversation-sync → copy Combined→Clean (**DeRoom placeholder**) → video-sync → `elevenlabs_transcribe_wav.py` → podcast autocut **1 Min Test.mp4**.

Optional phrase gates live in **`podcast-phrase-gates.json`** at the repo root (created automatically with walk-in defaults). Start/end/pause are **always attempted**; if a phrase is missing from the transcript, that gate is skipped. Override the file with `piab_set_phrase_gates.py` or per-episode fields on `podcast-in-a-box.json`.

Default gates (editable in `podcast-phrase-gates.json`):
- **Start:** `I solemnly swear I'm up to no good, in five four three two` / preroll 1.0s — `in` before the countdown is optional; countdown numbers may be skipped; optional trailing `one` / `zero` are removed when spoken; skipped if not in transcript
- **End:** `Be excellent to each other and party on dudes` (alternate: `Hut of brown, now sit down`) / postroll 1.0s — latest match among end phrases wins; skipped if none match
- **Pause:** `Computer Freeze Program.`
- **Unpause:** `Computer Resume Program` / `Computer Unfreeze Program`
- **Abort:** `Emergency override - Eject the warp core`
- Start speaker → Host camera (`speaker_0`)

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
python scripts/piab_run_full_render.py "E:\PodcastRoom\<name>" --allow-overwrite
```

If delivery was enabled at session start, this also uploads `Full Interview.mp4` to Frame.io, creates a **public** no-expiration share, emails the `short_url` to the confirmed recipient, and writes:

- `Output/Full Interview.delivery.json` — `file_id`, `share_id`, `short_url`, recipient
- `Output/Full Interview Transcript.json` — copy of the main transcript
- `Temp/delivery-summary.json` — machine-readable summary

Delivery failure does **not** fail the render; the user gets a failure email with the **local file path**. Validate config without uploading: `--delivery-dry-run`.

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
| `06_conversation_sync` … `10_one_min_test` | Run `piab_run_prep.py --resume` (or `piab_start_session.py` → resume) |
| `11_one_min_approval` | Review 1 Min Test |
| `12_estimate_full` | Show Estimate B; on OK full render |
| `14_done` | Finished |

---

## Out of scope (v1)

- GUI
- Real DeRoom (placeholder only)
- Reading / intro / stitch / hand-edit
- 5-minute test gate
