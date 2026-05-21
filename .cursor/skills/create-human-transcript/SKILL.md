---
name: create-human-transcript
description: Creates a human transcript from up to three video files by extracting and concatenating their audio, transcribing with ElevenLabs, and writing a cleaned Host/Guest transcript. Intermediate artifacts (WAV, raw text, ElevenLabs JSON) go in the episode Temp folder (parent of PATH + Temp sibling); only `<Host>-<Guest> Transcript.txt` stays in PATH. Use when the user says "Create Human Transcript" or asks to extract/concat audio from multiple videos for ElevenLabs transcription and a cleaned Host/Guest transcript.
disable-model-invocation: true
---

# Create Human Transcript

## Inputs (verbatim format)

The user provides:

```
PATH: <deliverable folder path> (e.g. episode Output)
Video 1: <video file path or filename>
Video 2: <video file path or filename> (optional)
Video 3: <video file path or filename> (optional)
Host: [name1]
Guest: [name2]
```

Notes:
- If a video is a filename (not an absolute path), treat it as relative to `PATH`.
- Process videos in the order given (Video 1 then Video 2 then Video 3).
- **Speaker 0** maps to **Host**; **Speaker 1** maps to **Guest** (same rules as Inkhaven-Human-Transcript-Clean).

## Temp folder resolution

Let **`PATH`** be the deliverable folder the user gave (typically **Output**). **Temp** is the sibling folder under the same episode root:

- **`R = parent(PATH)`**
- **Temp folder** = first existing child of **`R`** whose name is **`Temp`** (case-insensitive), or create **`R / Temp`** if missing.

Example: `PATH = E:\Inkhaven Nancy\Output` → Temp = `E:\Inkhaven Nancy\Temp`.

## What to do

1. Extract audio from each video and concatenate in order.
2. Write **`Human Transcript.wav`** in **Temp** (not in `PATH`).
3. Read the ElevenLabs API key from the repo-root file: `ElevenLabs 100k Key.txt`.
4. Run `scripts/elevenlabs_transcribe_wav.py` against the Temp WAV (ElevenLabs sidecars land in **Temp** too).
5. Write **`Text Transcript.txt`** in **Temp** (SRT-style timestamps + `[Speaker N]`).
6. Run **Inkhaven-Human-Transcript-Clean** on `Temp/Text Transcript.txt` with **Host** and **Guest**; write **only** `<Host>-<Guest> Transcript.txt` into **`PATH`**.

## Command (single step)

From the repository root (`automated-video-editing`):

```bash
python scripts/create_human_transcript.py "<PATH>" "<Video 1>" "<Video 2>" "<Video 3>" --host "<name1>" --guest "<name2>"
```

If only 1 or 2 videos were provided, omit the missing trailing video arguments.

Use the exact **Host** and **Guest** strings from the user's `Host:` / `Guest:` lines (strip brackets if the user wrote `[name]` literally; otherwise use the name as given).

### Optional two-step split

If you already have `Temp/Text Transcript.txt` and only need the clean file in `PATH`:

```bash
python scripts/clean_human_transcript.py "<Temp>/Text Transcript.txt" --host "<name1>" --guest "<name2>" --output-dir "<PATH>"
```

## Output

In **`PATH`** (deliverable folder only):

- `<Host>-<Guest> Transcript.txt`

In **Temp**:

- `Human Transcript.wav`
- `Text Transcript.txt`
- ElevenLabs artifacts (e.g. `Human Transcript Text.txt`, `Human Transcript Transcript.json`, `Human Transcript Transcription ID.txt`)

## After running

Briefly confirm:

- Cleaned transcript path in **`PATH`**
- Temp folder path and that intermediate files are there, not in **`PATH`**
