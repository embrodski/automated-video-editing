---
name: create-human-transcript
description: Creates a human transcript from up to three video files by extracting and concatenating their audio into "Human Transcript.wav", then transcribes with ElevenLabs into "Text Transcript.txt" using the API key in "ElevenLabs 100k Key.txt", then runs Inkhaven-Human-Transcript-Clean (scripts/clean_human_transcript.py) when the user supplies Host and Guest names. Use when the user says "Create Human Transcript" or asks to extract/concat audio from multiple videos for ElevenLabs transcription and a cleaned Host/Guest transcript.
disable-model-invocation: true
---

# Create Human Transcript

## Inputs (verbatim format)

The user provides:

```
PATH: <working folder path>
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

## What to do

1. Extract audio from each video and concatenate in order.
2. Write a WAV named exactly: `Human Transcript.wav` (in `PATH`).
3. Read the ElevenLabs API key from the repo-root file: `ElevenLabs 100k Key.txt`.
4. Run `scripts/elevenlabs_transcribe_wav.py` against `Human Transcript.wav` and capture the SRT-style transcript text (timestamps + `[Speaker N]`).
5. Write the transcript text to a file named exactly: `Text Transcript.txt` (in `PATH`).
6. Using **Host** and **Guest** from the user, run **Inkhaven-Human-Transcript-Clean**: `scripts/clean_human_transcript.py` on `PATH/Text Transcript.txt` with `--host` and `--guest`. Default output is `<Host>-<Guest> Transcript.txt` in the same folder as the input (unless the user asks for `--output-dir` / `--output-name` / `--output`).

## Commands

From the repository root (`automated-video-editing`):

**Step 1 — WAV + ElevenLabs text**

```bash
python scripts/create_human_transcript.py "<PATH>" "<Video 1>" "<Video 2>" "<Video 3>"
```

If only 1 or 2 videos were provided, omit the missing trailing arguments.

**Step 2 — Clean transcript (after `Text Transcript.txt` exists)**

```bash
python scripts/clean_human_transcript.py "<PATH>/Text Transcript.txt" --host "<name1>" --guest "<name2>"
```

Use the exact **Host** and **Guest** strings from the user's `Host:` / `Guest:` lines (strip brackets if the user wrote `[name]` literally; otherwise use the name as given).

## Output

In `PATH`:
- `Human Transcript.wav`
- `Text Transcript.txt`
- `<Host>-<Guest> Transcript.txt` (from `clean_human_transcript.py`, default naming)

Also next to the WAV: ElevenLabs artifacts from `elevenlabs_transcribe_wav.py` (e.g. `Human Transcript Text.txt`, JSON) unless the user asks to remove them.

## After running

Briefly confirm paths for `Human Transcript.wav`, `Text Transcript.txt`, and the cleaned `<Host>-<Guest> Transcript.txt`.
