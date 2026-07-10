---
name: inkhaven-episode-harness
description: >-
  Orchestrates the full Inkhaven Presents episode workflow from a folder of raw
  source files through Complete Episode.mp4. Tracks progress in
  <name>-episode.json at the episode root. Chains existing repo skills and
  scripts only; does not reimplement rendering or DSL logic. Use when the user
  says "inkhaven-episode-harness", "episode harness", "run the harness", or
  starts a new Inkhaven episode from raw files in an episode folder.
---

# Inkhaven Episode Harness

## Episode state file

- **Path:** `<episode_folder>/<name>-episode.json`
- **`<name>`:** guest name parsed from the episode folder basename — the part after **`Inkhaven `** (e.g. `E:\Inkhaven Viv` → **`Viv`** → **`Viv-episode.json`**).
- **Update rule:** after every harness step completes (or fails), update the matching `steps[...]` entry (`pending` / `in_progress` / `completed` / `failed`) and set **`updated_at`**.

## Folder layout (episode root)

After prep, the episode root contains siblings:

| Subfolder | Role |
|-----------|------|
| **Raw** | Source files moved in at launch |
| **Input** | Prepped/synced media + transcripts (later steps) |
| **Output** | Final `.mp4` deliverables only |
| **Temp** | Pipeline JSON, DSL, ffmpeg scratch |

All downstream skills use these four paths for the rest of the harness.

---

## Hard rule: no overwrite without user verification

**Never replace an existing file** without first checking with the user and getting explicit approval.

This applies to **every harness step**, **every subordinate skill** the harness chains (podcast autocut, reading autocut, stitch, human transcript, conversation-sync, video prep, etc.), and **any** direct `python -m podcast_dsl` / stitch / converter run the agent performs on behalf of the user.

**Before any write that would overwrite:**

1. **List** which paths already exist and would be replaced (Output deliverables, Temp DSL/JSON, user DaVinci exports, transcripts, test renders, `Complete Episode.mp4`, etc.).
2. **Stop and ask** the user — even when fixing bugs, re-running after a code change, or the user said “redo the render” without naming the output file.
3. **After approval only:** pass **`--allow-overwrite`** on harness render/stitch/transcript commands, **or** write to a **new filename** if the user wants to keep the previous file.

**Routine exceptions** (no approval needed): updating **`<name>-episode.json`** step metadata; ephemeral ffmpeg scratch under **Temp** (not named deliverables).

Harness scripts that write deliverable outputs **exit with code 2** if the target already exists unless **`--allow-overwrite`** is passed.

---

## Launch — Steps 1–3

### Step 1 — Launch

**Trigger:** user runs **`inkhaven-episode-harness`**.

**Input:** folder path (episode working folder).

If no folder path was given, ask:

> Please provide the episode folder path before we continue.

**Actions:**

1. Resolve the folder to an absolute path.
2. Identify guest **`<name>`** from the folder basename: text after **`Inkhaven `** (case-insensitive prefix match on the folder name).
3. Run initialization (creates/updates **`<name>-episode.json`** and performs Step 2):

```powershell
Set-Location "<repo>"
python scripts/init_inkhaven_episode.py "<episode_folder>"
```

Use **`--dry-run`** only when debugging folder prep without moving files.

**On script failure (exit code 1):** report the error and stop.

**On script exit code 2:** Step 2 ran but reported non-fatal issues (e.g. duplicate filenames in Raw); summarize **`steps.02_prep_folders.errors`** and address with the user before continuing.

Mark **`steps.01_launch`** **`completed`** in **`<name>-episode.json`** (the init script does this when run without `--dry-run`).

### Step 2 — Prep folders and raw files

**Informational — expected raw source files**

In the episode folder there are typically **8–13** files, each containing the word **`raw`** in the filename (anywhere in the name, case-insensitive). **`Ben`** may appear as **`Host`**; **`Guest`** may be a person's name; **`Main`** may be absent; **`raw`** may be in the middle of the name rather than at the end.

**8 files:**

- Main Ben audio raw.wav
- Main Ben vid raw.mp4
- Main Guest audio raw.wav
- Main Guest vid raw.mp4
- Main Wide vid raw.mp4
- Reading audio raw.wav
- Reading front raw.mp4
- Reading side raw.mp4

**13 files** (adds five intro files):

- Intro Ben audio raw.wav
- Intro Ben vid raw.mp4
- Intro Guest audio raw.wav
- Intro Guest vid raw.mp4
- Intro Wide vid raw.mp4

**Actions** (performed by `scripts/init_inkhaven_episode.py`):

1. Create subfolders **`Raw`**, **`Input`**, **`Output`**, **`Temp`** under the episode folder.
2. Move every file in the episode root whose name contains **`raw`** (case-insensitive) into **`Raw`**.
3. Look in the **parent** of the episode folder for **`Closing.mp4`**. If it exists, move it to **`Output`**.

Mark **`steps.02_prep_folders`** when done (the init script sets **`completed`** or **`failed`**).

### Step 3 — Check-in and reading link

If Step 2 had errors, summarize them and work with the user to resolve before asking for the reading link.

Otherwise say exactly:

> The folders are ready. Please input the link to the Reading source.

**Stop and wait** for the user's reading URL or for them to say there will be **no reading at this time**. Do not run Step 4 until they reply.

Terminology: the user's article URL is **`<reading-link>`** in all harness instructions below.

---

## Step 4 — Verify `<reading-link>`

Confirm the page is an accessible article or blog post. If you cannot access it, tell the user and prompt for a working **`<reading-link>`** until one works.

Alternatively, if the user says there will be **no reading at this time**, set **`skip_reading`: true** and **skip all harness steps tagged READING** (mark those steps **`skipped`** in **`<name>-episode.json`** as they are encountered).

**Agent check (preferred):** use **WebFetch** on **`<reading-link>`** and confirm substantial article text (not a sign-in wall or empty page). If fetch fails or content is not article-like, report that to the user and wait for a new link.

**Record state** (from repo root):

```powershell
Set-Location "<repo>"
python scripts/harness_set_reading_link.py "<episode_folder>" --reading-link "<reading-link>"
```

If the agent already verified the URL in Cursor and the script fetch might differ, add **`--skip-verify`**.

**No reading:**

```powershell
python scripts/harness_set_reading_link.py "<episode_folder>" --no-reading
```

On verification failure the script exits **1**, leaves **`steps.04_verify_reading_link`** as **`failed`**, and does not advance.

---

## Step 5 — Main conversation-sync

Run **conversation-sync** (existing skill / `scripts/sync_conversation_wavs.py`):

- **Working folder:** **`Raw`** (`<episode_folder>/Raw`)
- **WAV file 1:** main Ben/Host audio raw (e.g. `Main Ben audio raw.wav` — resolve actual basename in Raw)
- **WAV file 2:** main Guest audio raw (guest name may replace the word Guest)

The script **`harness_run_conversation_sync.py`** discovers the correct pair by filename patterns (Ben/Host vs non-Ben, not Intro, not Reading).

**Output:** **Main Combined Audio** file in **Raw** — `{FirstWord} Combined Audio.wav` where `{FirstWord}` is the first token of WAV 1's basename (e.g. **`Main Combined Audio.wav`**). Stored in **`<name>-episode.json`** as **`main_combined_audio`**.

---

## Step 6 — Intro conversation-sync (conditional)

If there is **no** intro audio raw pair in **Raw**, **skip** this step.

If intro files exist, run the same sync with:

- **WAV file 1:** Intro Ben/Host audio raw
- **WAV file 2:** Intro Guest audio raw

**Output:** **Intro Combined Audio** file in **Raw** (e.g. **`Intro Combined Audio.wav`**). Stored as **`intro_combined_audio`** when present.

**Run steps 5 and 6 together:**

```powershell
Set-Location "<repo>"
python scripts/harness_run_conversation_sync.py "<episode_folder>"
```

Requires Step 4 **`completed`** or **`skipped`**. On failure, exit **1** and report stderr.

---

## Step 7 — Audacity DeRoom (user gate)

After Step 5/6 succeed, tell the user:

1. The combined audio file(s) are ready — **list each combined WAV** (full paths or basenames under **Raw**).
2. Run **DeRoom** on them in **Audacity**.
3. Export the DeRoomed files with the word **`Clean`** in the filename(s) (e.g. `Main Clean Audio.wav`).

**Stop and wait** until the user confirms they have processed the files on their end. Do not run the next harness step until they say so.

When the user confirms Audacity export is done:

```powershell
python scripts/harness_complete_audacity_deroom.py "<episode_folder>"
python scripts/harness_identify_clean_audio.py "<episode_folder>"
```

Step **8** must succeed before steps **9–15**. If Step 8 cannot find clean WAVs, ask the user to export DeRoomed files into **Raw** with **`Clean`** in the filename (newer than the combined audio from steps 5–6).

---

## Step 8 — Identify clean audio

Find user-exported DeRoom WAVs in **Raw**:

- Filename contains **`clean`** (case-insensitive)
- Modification time **after** the matching combined audio from step 5 (main) or step 6 (intro)
- **Main** clean: not Intro, not Reading
- **Intro** clean: Intro in name (only if step 6 ran)

Stored as **`main_clean_audio`** and optional **`intro_clean_audio`** in **`<name>-episode.json`**.

---

## Step 9 — Intro video prep

**Skip** if step 6 was skipped (no intro conversation-sync).

Otherwise run **video-sync** (see **video-sync** skill) via:

```powershell
python scripts/harness_run_video_sync_scope.py "<episode_folder>" --scope intro
```

- **Working folder:** **Raw**
- **Audio:** **`intro_clean_audio`** from step 8
- **Videos:** Intro Ben/Host, Intro Guest, Intro Wide raw MP4s (resolved automatically)

Report: **Intro files are ready.** Continue to step 10.

---

## Step 10 — Reading video prep (READING)

**Skip** when **`skip_reading`** is true.

```powershell
python scripts/harness_run_video_sync_scope.py "<episode_folder>" --scope reading
```

- **Audio:** **Reading audio raw.wav** (or equivalent in Raw) — reading uses the **raw** reading WAV, not a clean combined mix
- **Videos:** Reading front + Reading side raw MP4s

**Deliverables in Input:** `*-prepped.mp4` and **`Reading audio-prepped.wav`** (raw removed from stem). Record paths under **`reading_prepped`** in episode JSON.

---

## Step 11 — Reading transcript (READING)

**Skip** when **`skip_reading`** is true.

Uses **`scripts/elevenlabs_transcribe_wav.py`** on the **Reading `*-prepped.wav`** from step **10** (not intro prepped audio).

```powershell
python scripts/harness_transcribe_prepped.py "<episode_folder>" --scope reading
```

**Output in Input:** `{stem} Transcript.json` — recorded as **`reading_transcript_json`**.

---

## Step 12 — Main video prep

```powershell
python scripts/harness_run_video_sync_scope.py "<episode_folder>" --scope main
```

- **Audio:** **`main_clean_audio`** from step 8
- **Videos:** Main Ben/Host, Main Guest, Main Wide raw MP4s

**Deliverables in Input:** main `*-prepped.mp4` and main `*-prepped.wav`. Record under **`main_prepped`**.

---

## Step 13 — Main transcript

Uses **`elevenlabs_transcribe_wav.py`** on the **main `*-prepped.wav`** from step **12**.

```powershell
python scripts/harness_transcribe_prepped.py "<episode_folder>" --scope main
```

**Output in Input:** main `{stem} Transcript.json` — recorded as **`main_transcript_json`**.

---

## Step 14 — Reading autocut 1-minute test (READING)

**Skip** when **`skip_reading`** is true.

Chains **Inkhaven-Reading-Autocut** (convert transcript, fetch **`<reading-link>`**, register segment, `reading.dsl`, **Shorten**, 1-minute render):

```powershell
python scripts/harness_reading_autocut_test.py "<episode_folder>"
```

- **Working folder for renders:** episode **Input** path is used in `SEGMENT_CONFIG`; DSL/JSON under **Temp**
- **Output:** **`<output>/1 Min Test Reading.mp4`**

Tell the user: **Reading 1 Min Test File is ready for review** (`1 Min Test Reading.mp4`). Continue to step 15.

---

## Step 15 — Podcast autocut 1-minute test

Chains **Inkhaven-Podcast-Autocut** (convert transcript, register segment, `interview.dsl`, 1-minute render):

```powershell
python scripts/harness_podcast_autocut_test.py "<episode_folder>"
```

- **Output:** **`<output>/1 Min Test.mp4`**

Tell the user: **Main Interview 1 Min Test File is ready for review** (`1 Min Test.mp4`). Then enter **Step 16** (reading approval) unless **`skip_reading`**.

After step **15**, **`resume_at`** is **`16_reading_test_approval`** when reading is enabled, else **`18_interview_test_approval`**.

---

## Step 16 — Reading 1-minute test approval (READING)

**Skip** when **`skip_reading`** is true (mark **`skipped`**, go to step **18**).

**Gate:** **`steps.16_reading_test_approval`** is **`awaiting_user`** after step **14**.

Review **`1 Min Test Reading.mp4`** with the user. Troubleshoot using **Inkhaven-Reading-Autocut** parameters from step **14** (same segment, **`reading.dsl`**, Shorten, **`<reading-link>`**).

**Never re-render without explicit user approval** for that render. If the target file already exists, list it and ask before overwriting; pass **`--allow-overwrite`** only after approval.

| User intent | Action |
|-------------|--------|
| Adjustments (DSL/transcript/article) | Confirm, then rebuild + re-render 1-min test |
| Satisfied → full reading render | Mark step 16 **`completed`**, run step **17** |
| Skip reading entirely → interview only | Mark 16–17 **`skipped`**, go to step **18** |
| No reading changes, wants interview full only | Mark 16 **`completed`**, skip 17, go to **18** or **20** per user |

**Re-render 1-minute reading test** (only after user confirms):

```powershell
python scripts/harness_reading_autocut_render.py "<episode_folder>" --mode test [--rebuild-dsl] [--allow-overwrite]
```

**Mark step complete / skip:**

```powershell
python scripts/harness_step_status.py "<episode_folder>" --step 16_reading_test_approval --status completed --resume-at 17_reading_full_render
python scripts/harness_step_status.py "<episode_folder>" --skip-reading-chain --resume-at 18_interview_test_approval
```

---

## Step 17 — Reading full render & approval (READING)

**Skip** when **`skip_reading`** is true.

**Full render** (long job — confirm with user first; if `Full Reading.mp4` exists, ask before overwriting):

```powershell
python scripts/harness_reading_autocut_render.py "<episode_folder>" --mode full [--rebuild-dsl] [--allow-overwrite]
```

**Output:** **`<output>/Full Reading.mp4`**. Record as **`reading_final_mp4`**.

When render finishes, tell the user the file is ready. Troubleshoot with the same reading-autocut levers; **do not re-render without approval**.

When satisfied, mark **`17_reading_full_approval`** **`completed`** and set **`resume_at`** to **`18_interview_test_approval`**:

```powershell
python scripts/harness_step_status.py "<episode_folder>" --step 17_reading_full_approval --status completed --resume-at 18_interview_test_approval
```

---

## Step 18 — Interview 1-minute test approval

**Gate:** **`steps.18_interview_test_approval`** is **`awaiting_user`** after step **15**.

Review **`1 Min Test.mp4`**. Troubleshoot using **Inkhaven-Podcast-Autocut** parameters from step **15** (**`interview.dsl`**, segment **`main_segment_id`**).

**Never re-render without explicit user approval.** If the target file already exists, list it and ask before overwriting; pass **`--allow-overwrite`** only after approval.

| User intent | Action |
|-------------|--------|
| Adjustments | Confirm, then rebuild + re-render 1-min test |
| Satisfied → 5-minute test | Mark 18 **`completed`**, run step **19** |
| Satisfied → full interview | Mark 18 **`completed`**, run step **20** |
| No changes, jump to full | Mark 18 **`completed`**, run step **20** |

**Re-render 1-minute interview test:**

```powershell
python scripts/harness_podcast_autocut_render.py "<episode_folder>" --mode test [--rebuild-dsl] [--allow-overwrite]
```

```powershell
python scripts/harness_step_status.py "<episode_folder>" --step 18_interview_test_approval --status completed --resume-at 19_interview_five_min_approval
python scripts/harness_step_status.py "<episode_folder>" --step 18_interview_test_approval --status completed --resume-at 20_full_interview_render
```

---

## Step 19 — Interview 5-minute test approval

Optional; only when the user requests a 5-minute test after step **18**.

**Render** (confirm with user first):

```powershell
python scripts/harness_podcast_autocut_render.py "<episode_folder>" --mode five_min [--rebuild-dsl] [--allow-overwrite]
```

**Output:** **`<output>/5 Min Test.mp4`**.

Troubleshoot like step **18**; **no re-render without approval**. When satisfied, mark **`19_interview_five_min_approval`** **`completed`** and proceed to step **20**.

```powershell
python scripts/harness_step_status.py "<episode_folder>" --step 19_interview_five_min_approval --status completed --resume-at 20_full_interview_render
```

---

## Step 20 — Full interview render

**Render** (long job — confirm with user first; see **no overwrite** hard rule):

```powershell
python scripts/harness_podcast_autocut_render.py "<episode_folder>" --mode full [--rebuild-dsl] [--allow-overwrite]
```

**Output:** **`<output>/Full Interview.mp4`**.

When complete, tell the user exactly:

> Full render is complete: **`<absolute path to Full Interview.mp4>`**

**Stop and wait** for further user input before any later harness steps (hand edits, stitch, publish).

After step **20**, **`21_hand_edit_approval`** is **`awaiting_user`**. The user hand-edits in DaVinci and exports **`Intro.mp4`**, **`Edited Reading.mp4`**, and **`Edited Interview.mp4`** into **Output** ( **`Closing.mp4`** should already be there from launch).

---

## Step 21 — Hand-edit approval (DaVinci)

**Gate:** user confirms DaVinci hand edits are finished.

Troubleshoot **`Edited Interview.mp4`** (and reading/intro exports) if the user reports problems — same iterative pattern as steps **18–19**; **no re-export or re-render without explicit approval**.

| User message | Action |
|--------------|--------|
| Problems / help requested | Work with user until exports are acceptable |
| Acknowledgement only (edits complete, no issues) | Mark step **21** **`completed`**, continue to step **22** |

```powershell
python scripts/harness_step_status.py "<episode_folder>" --step 21_hand_edit_approval --status completed --resume-at 22_podcast_stitch
```

**Required in Output before stitch:** `Intro.mp4`, `Edited Reading.mp4`, `Edited Interview.mp4`, `Closing.mp4`. Harness step 22 resolves loosely named exports (e.g. stems containing `intro`, `edited`, `reading`) and passes those paths to `stitch_episode.py`; canonical names are preferred.

---

## Step 22 — Podcast stitch

```powershell
Set-Location "<repo>"
$env:TEMP = "<temp folder>"
$env:TMP  = "<temp folder>"
python scripts/harness_run_stitch.py "<episode_folder>" [--allow-overwrite]
```

Wraps **`stitch_episode.py`** → **`<output>/Complete Episode.mp4`**.

On success, report stitch **timecodes** from script output (plaintext, four lines):

```
00:00 Intro
… Reading
… Interview
… Sponsor
```

Step **23** is marked **`skipped`** automatically (placeholder).

---

## Step 23 — Teaser line (placeholder)

**Skip** — reserved for a future Teaser Line skill. Do not run any command.

---

## Step 24 — Human transcript

```powershell
python scripts/harness_run_human_transcript.py "<episode_folder>" [--allow-overwrite]
```

Chains **create-human-transcript**:

- **Path:** **Output** folder
- **Video 1:** `Intro.mp4` (or equivalent)
- **Video 2:** `Edited Interview.mp4` (or equivalent)
- **Host:** `Ben`
- **Guest:** **`<name>`** from step 1 (episode JSON **`name`** field)

**Output in Output:** **`Ben-<name> Transcript.txt`** (e.g. `Ben-Henry Test Transcript.txt`). Intermediate WAV/JSON live in **Temp**.

---

## Step 25 — Final deliverables alert

```powershell
python scripts/harness_finalize_deliverables.py "<episode_folder>"
```

Tell the user:

1. **Complete episode is ready:** absolute path to **`Complete Episode.mp4`**
2. **Human-readable transcript is ready:** absolute path to **`Ben-<name> Transcript.txt`**
3. Paste stitch **timecodes** (if not already shared from step 22)

**Stop and wait** for further user input (publish steps are out of harness scope for now).

---

## Progress / resume

- **`resume_at`** in **`<name>-episode.json`** is the next harness step id after the last completed action.
- **`steps.*.status`:** `pending` | `completed` | `skipped` | `failed` | `awaiting_user`
- To see status: read **`<name>-episode.json`** or ask the agent to summarize **`steps`**.

Example resume after a successful test through step 7:

```json
"resume_at": "08_identify_clean_audio",
"steps": { "07_audacity_deroom": { "status": "awaiting_user" } }
```

---

## READING-tagged steps

When **`skip_reading`** is **true**, skip all READING-tagged steps (mark **`skipped`**): **10, 11, 14, 16, 17**.

| Step | READING |
|------|---------|
| 10 Reading video prep | Yes |
| 11 Reading transcript | Yes |
| 14 Reading autocut 1-min test | Yes |
| 16 Reading 1-min approval | Yes |
| 17 Reading full render/approval | Yes |

---

## Downstream steps

Harness steps after **25** (Riverside/YouTube/SubStack publish, thumbnail, etc.) may be added later.

## Human gates (always)

- **No overwrite without user verification** (see hard rule above and **`AGENTS.md`**). Harness scripts exit unless **`--allow-overwrite`** is passed after the user approves.
- Do not start long renders (> ~30 s) during debugging without user approval (see **`AGENTS.md`**).
- Steps **16–20** require explicit user approval before every re-render (`harness_*_autocut_render.py`).
- Full reading (**step 17**), full interview (**step 20**), and **stitch** (**step 22**) are long jobs — confirm before running.
- Step **21** requires user confirmation that DaVinci exports in **Output** are final before stitch.
