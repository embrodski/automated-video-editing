---
name: inkhaven-human-transcript-clean
description: Cleans a human transcript text file containing many SRT-style timestamp/speaker marker lines like "00:00:00,780 --> 00:00:12,590 [Speaker 0]". Deletes those lines, replaces speaker changes with "Host:" (Speaker 0) or "Guest:" (Speaker 1), removes repeated attributions for consecutive same-speaker sections by concatenating them, and writes a new file named "Host-Guest Transcript.txt". Use when the user asks for "Inkhaven-Human-Transcript-Clean", "clean transcript", "remove timestamp lines", or wants Speaker 0/1 replaced with Host/Guest names.
---

# Inkhaven Human Transcript Clean

## Inputs to collect

- **Transcript file path** (the text file to clean; often `.txt` or `.srt`-like)
- **Host name** (maps to **Speaker 0**)
- **Guest name** (maps to **Speaker 1**)
- **Output folder** (optional; default is the transcript’s folder)

## Transformation rules (must apply)

- **Detect speaker marker lines** that look like:
  - `00:00:00,780 --> 00:00:12,590 [Speaker 0]`
- **Delete** those marker lines and replace them with a speaker attribution line:
  - Speaker 0 → `<Host>:`
  - Speaker 1 → `<Guest>:`
- **Concatenate consecutive same-speaker sections**:
  - If multiple marker lines in a row refer to the same speaker (with text in between), do **not** repeat the attribution; keep a single attribution and merge the content into one block.
- **Output filename**:
  - Write a new file named exactly: `<Host>-<Guest> Transcript.txt`

## Command (default)

From the repo root, run:

```bash
python scripts/clean_human_transcript.py "<transcript file path>" --host "<Host>" --guest "<Guest>"
```

If the user wants a specific output folder:

```bash
python scripts/clean_human_transcript.py "<transcript file path>" --host "<Host>" --guest "<Guest>" --output-dir "<output folder>"
```

## Example

Inputs:
- Host = `Ben`
- Guest = `Nicholas`
- Transcript line: `00:00:00,780 --> 00:00:12,590 [Speaker 0]`

Output attribution line:
- `Ben:`

