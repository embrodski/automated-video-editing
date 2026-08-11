# A/V sync confidence fallback

When `sync_video_wav_replace.py` aligns clean/combined audio to each camera’s embedded
program audio, it cross-correlates the two signals. If peak strength is below **0.35**
(default `--min-correlation-strength`), the tool **does not** apply the detected lag and
instead muxes at sample 0 (“start-aligned fallback”).

That protects against bad offsets when correlation is untrustworthy, but on some sessions
(weak match between combined clean mix and embedded MP4 audio) it leaves a small lip-sync
error (~50–150 ms) that users notice.

This document describes the **confidence-fallback workflow** added for Inkhaven harness
and planned for PIAB forks.

---

## Artifacts


| Path                                        | Purpose                                                    |
| ------------------------------------------- | ---------------------------------------------------------- |
| `Temp/failed-sync-confidence.json`          | Flag + summary of weak-correlation sync reports            |
| `Temp/av-sync/forced-offset/`               | Forced-offset prepped media (sync + multicam + anchor WAV) |
| `Output/1 Min Test no offset.mp4`           | 1-min test using start-aligned prep (`Input/`)             |
| `Output/1 Min Test forced audio offset.mp4` | 1-min test using `--force-detected-lag` prep               |
| `Output/full video with audio offset.mp4`   | Full render when user chooses forced offset                |
| `Output/Full Interview.mp4`                 | Full render when user chooses start-aligned (or no flag)   |


Episode JSON fields (Cursor CLI uses `cursor-podcast-in-a-box.json`; GUI app uses `podcast-in-a-box.json`):

- `sync_confidence_failed` (bool)
- `sync_offset_choice_pending` (bool)
- `sync_offset_choice`: `"start_aligned"`  `"forced_offset"`  null
- `main_prepped` — start-aligned prep (normal `Input/`)
- `main_prepped_forced_offset` — forced-offset prep under `Temp/av-sync/forced-offset/`

Harness steps:

- **18a_sync_offset_approval** — awaiting user A/B choice (only when flag set)
- **18_interview_test_approval** — general 1-min approval after offset choice

---

## Pipeline (still runs on every episode)

1. **Conversation-sync** → combined clean in `Raw/`
2. **Video-sync (step 12 / PIAB 08)** — for each camera MP4:
  - `sync_video_wav_replace.py` correlates **clean audio** vs **embedded video audio**
  - Writes `Temp/*-synced.json` reports
  - Multicam align → `Input/*-prepped.mp4`
  - Extract anchor WAV → `Input/*-prepped.wav` (used for transcribe + render master)
3. **Transcribe** on prepped WAV
4. **Podcast autocut** — DSL + render

Sync is **not removed**; the question is whether to trust the detected lag.

---

## When confidence fails

After main video-sync, if **any** camera report has `start_aligned_fallback` due to
“below threshold”:

1. Write `Temp/failed-sync-confidence.json`
2. Set `sync_confidence_failed: true` on episode state
3. Build forced-offset prep (`Temp/av-sync/forced-offset/`) with `--force-detected-lag`
4. Render **both** 1-minute tests:
  - `1 Min Test no offset.mp4` — existing start-aligned `Input/` prep
  - `1 Min Test forced audio offset.mp4` — forced-offset prep
5. Set step **18a_sync_offset_approval** → `awaiting_user`
6. **Stop** and ask the user which offset version they prefer

### Agent prompts (in order)

1. **Sync offset choice** (only if flag exists):
  > Review `1 Min Test no offset.mp4` and `1 Min Test forced audio offset.mp4`.
  > Which do you prefer — **no offset** (start-aligned) or **forced audio offset**?
  >  Record choice:
2. **General 1-min approval** (step 18):
  > Review the chosen 1-min test. Is it OK otherwise, or do other changes need to be made
  > (e.g. speaker swap, DSL tweaks)?
3. **Full render** uses active prep from the recorded choice:
  - `forced_offset` → `full video with audio offset.mp4` (or standard name if overridden)
  - `start_aligned` → `Full Interview.mp4`

---

## Speaker swap + failed confidence

If the user fixes **speaker-ID mapping** (`piab_fix_audio_speaker_swap.py` / harness
equivalent) **and** `failed-sync-confidence.json` still exists:

1. Reconvert transcript + regenerate DSL (speaker swap only — no video re-prep)
2. **Re-run the A/B 1-min pair** (same offset variants, new speaker mapping)
3. Return to **18a_sync_offset_approval** — user must confirm offset choice again
4. Then **18_interview_test_approval**

Raw files and video prep are unchanged; only transcript/DSL and both 1-min renders refresh.

---

## Implementation map


| Component                                      | Role                                                           |
| ---------------------------------------------- | -------------------------------------------------------------- |
| `scripts/sync_video_wav_replace.py`            | Core align; `--force-detected-lag` flag                        |
| `scripts/harness_av_sync_lib.py`               | Shared flag, dual prep, A/B renders, choice apply              |
| `scripts/harness_run_video_sync_scope.py`      | Writes flag after main sync (harness)                          |
| `scripts/harness_podcast_autocut_test.py`      | A/B 1-min when flag set                                        |
| `scripts/harness_record_sync_offset_choice.py` | CLI to record user choice                                      |
| `scripts/harness_podcast_autocut_render.py`    | Full render respects `sync_offset_choice`                      |
| `scripts/piab_run_prep.py`                     | Same flag + A/B in 1-min step (PIAB)                           |
| `scripts/piab_fix_audio_speaker_swap.py`       | Re-A/B when flag present                                       |
| `scripts/harness_av_sync_experiment.py`        | Sandbox (host-only / forced); superseded by lib for production |


---

## PIAB port checklist (later)

- After `08_video_sync`, call `maybe_write_sync_confidence_flag`
- Replace single `1 Min Test.mp4` with A/B pair when flag set
- Add PIAB step / approval gate for offset choice (mirror 18a)
- `piab_run_full_render.py` — honor `sync_offset_choice` and output filename
- `piab_fix_audio_speaker_swap.py` — re-A/B when flag exists (implemented in repo)
- Update `.cursor/skills/lighthaven-podcast-in-a-box/SKILL.md` agent prompts
- Optional: host-only sync reference as third fallback (experiment only today)

---

## CLI reference

```powershell
# Record user offset choice (harness)
python scripts/harness_record_sync_offset_choice.py "E:\...\Episode" --choice forced_offset

# Full render with forced-offset prep + custom name
python scripts/harness_podcast_autocut_render.py "E:\...\Episode" --mode full `
  --use-forced-offset-prep --output-name "full video with audio offset.mp4" --allow-overwrite

# Re-run A/B 1-min tests only (after prep + DSL exist)
python -c "from harness_av_sync_lib import ..."  # or harness_podcast_autocut_test with flag
```

---

## Host-only sync (experimental, not default)

`scripts/harness_av_sync_experiment.py --mode host-only-sync` correlates using
`Host Raw Audio.wav` instead of combined clean. Used to probe whether correlation
improves; **not** part of the default fallback until validated. Forced-offset is the
production fallback candidate when combined-clean correlation fails.