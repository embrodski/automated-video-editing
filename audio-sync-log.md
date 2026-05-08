# Audio sync work log

Log of tooling and workflow changes for the **conversation-sync** / **video-sync** pipeline used with **Inkhaven Emmy** media.  
**This file lives in the repo:** `E:\PodcastRoom\Cursor\automated-video-editing`. Code changes under `scripts/` and `.cursor/skills/`. Typical **media working folder:** `E:\Inkhaven Emmy` (and `E:\Inkhaven Emmy\Raw` for video-sync).

---

## 1. Conversation-sync runs (manual)

| When (session) | Inputs | Output / notes |
|----------------|--------|----------------|
| Intro | `Intro Ben audio raw.wav` + `Intro Guest audio raw.wav` | `Combined Audio.wav` (+ JSON). Later re-run with **defaults** (piecewise, 22 s segments). |
| Main | `Main Ben` + `Main Guest` | `Main Combined Audio.wav` (+ JSON). Long piecewise (84 segments). |
| Play | `Play Emmy` + `Play Zoe` | `Play Emmy Zoe Combined Audio.wav` (piecewise), then `… seg22.wav` for comparison; piecewise-only tuning test. |

Working folder for these: **`E:\Inkhaven Emmy`** (sources and combined WAVs).

---

## 2. `sync_conversation_wavs.py` — default & behavior changes

### 2.1 Segment length default

- **`--segment-seconds` default:** `45` → **`22`** (finer piecewise grid; less mid-segment lag error).
- **Skill:** `.cursor/skills/conversation-sync/SKILL.md` updated to say default 22.

### 2.2 Piecewise as default

- **Default alignment:** **piecewise on** (was global-only unless `--piecewise`).
- **CLI:** `argparse.BooleanOptionalAction` — use **`--no-piecewise`** for single global offset + start trim only.
- **Removed** the **first** `if __name__ == "__main__"` block that exited mid-file so the real `main()` (with `--echo-suppress`) runs.
- **Docstring / SKILL:** describe default piecewise + `--no-piecewise`.

### 2.3 Global trim before piecewise (fix “first segment not synced”)

- **Issue:** Negative full-file lag → piecewise could not apply negative delay at `t=0` → clamp forced **0** on first segment while global mode would trim **reference (Ben)**.
- **Change:** **`_apply_initial_lag_trim`** — same trim as global mix — then piecewise on **trimmed** `a_pw` / `b_pw`. Report **`trim_start_samples_a` / `_b`**.
- **Drift check:** still uses **full-length** mono pair vs original `lag` for start-vs-end drift.

### 2.4 Glitch diagnosis (user listen)

- Clicks / phase at **~11:00** and **~26:24** on **`Main Combined Audio.wav`** aligned with **22 s nominal piecewise boundaries** (660 s, 1584 s): cosine delay blend + `np.interp` + 50/50 mix.
- Discussed mitigations **A–H**; agreed to pursue **D + E** and **quiet knot move** (before F = waveform-domain crossfade).

### 2.5 Quiet knot relocation (+8 s / −8 s)

- **Nominal** knot grid unchanged in spirit; each **interior** knot `j` is moved to the **lowest** `min(RMS_a, RMS_b)` in a short window (uniform ~40 ms) over search grid **hop 240** samples, window **[nominal_j − 8 s, nominal_j + 8 s]** clipped by **min segment length** `max(10 s, 0.75 × corr-window)`.
- **Helpers:** `_relocate_piecewise_knots`, `_enforce_monotonic_knots`, `_segment_delay_table_knots`, `_clamp_segment_delays_knots`.
- **Report / JSON:** `piecewise_knot_nominal_samples`, `piecewise_knot_adjusted_samples`, `piecewise_knot_shift_samples`.

### 2.6 D — Adaptive crossfade width

- Per join: wider cosine when **|Δlag|** is larger; **`--crossfade-ms`** = **baseline** samples; extra width **∝ lag delta** with cap **120 ms**; then clip so join does not consume most of shorter adjacent segment.
- **Report:** `piecewise_crossfade_samples` (= baseline, compat), `piecewise_crossfade_samples_base`, `piecewise_crossfade_max_ms`, `piecewise_adaptive_ms_per_lag_sample` (0.14).

### 2.7 E — Cubic fractional read of Guest

- Replaced **`np.interp`** with **`scipy.ndimage.map_coordinates(..., order=3, prefilter=True)`** per channel on `idx_read`.
- **Import:** `map_coordinates`, `uniform_filter1d` from `scipy.ndimage`.

### 2.8 Duplicate code in repo (known tech debt)

- **`sync_conversation_wavs.py`** still contains an **older** `sync_pair` / `main` block earlier in the file; **runtime** uses the **last** definitions. Optional cleanup: delete dead first `sync_pair` + first `main` to avoid drift.

---

## 3. Video-sync (Inkhaven Emmy tree)

- **Working folder used:** **`E:\Inkhaven Emmy\Raw`**
- **Audio:** `PlayCombined Audio clean.wav`
- **Videos:** `Play Emmy vid raw.mp4`, `Play Wide vid raw.mp4`, `Play Zoe vid raw.mp4`
- **Script:** `scripts/sync_video_wav_replace.py` per clip (no `--align`).
- **Outputs (next to sources in `Raw`):** `Play Emmy vid-synced.mp4`, `Play Wide vid-synced.mp4`, `Play Zoe vid-synced.mp4` (+ optional `* report.json` if run with `--json-report`).
- **Skill:** `.cursor/skills/video-sync/SKILL.md` (not edited in this session beyond prior repo state).

---

## 4. SKILL / docs touched

| File | Purpose |
|------|---------|
| `.cursor/skills/conversation-sync/SKILL.md` | Defaults (22 s, piecewise default, `--no-piecewise`), leading trim, knot/adaptive/cubic description. |

---

## 5. Reverting or trying alternatives

| Goal | What to revert / try |
|------|------------------------|
| Coarser segments | CLI **`--segment-seconds 45`** (or any value). |
| Global-only mix | **`--no-piecewise`**. |
| No Ben trim before piecewise | Would require **removing** `_apply_initial_lag_trim` from piecewise path (code) — not a flag today. |
| No knot move / fixed grid only | Would require **disabling** `_relocate_piecewise_knots` (use nominal boundaries only) — not a flag today; add `--no-knot-shift` or similar if needed. |
| Fixed 25 ms joins only | Code: force crossfade width = `cf_base` only (remove adaptive scaling in `_warp_b_piecewise_knots`). |
| Linear read again | Code: swap `map_coordinates` back to **`np.interp`** in `_warp_b_piecewise_knots`. |
| **F** (waveform-domain crossfade at joins) | Not implemented; would blend two rendered Guest branches over the join instead of only blending the delay ramp — heavier, often cleaner on **large** steps. |
| VAD / smarter “silence” | Replace or augment `min(uniform_filter1d(mono_a²), …)` with a proper VAD or spectral metric (code). |

---

## 6. Temp / QA files (deleted)

Session QA outputs under **Inkhaven Emmy** were removed after checks (e.g. `_qa_piecewise.wav`, `_trim_test_*`, `_test_default_piecewise.wav`). They are **not** listed as permanent deliverables.

---

*Append new dated sections below as you iterate.*
