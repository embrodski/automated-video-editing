# Handoff for local agent — Final Render window bugs

**Date:** 2026-08-14  
**Repo (local):** `E:\PodcastRoom\Cursor\podcast-in-a-box-app`  
**Do not use cloud agents** for this work — code lives only on the local machine; multi-window / queue work was never pushed to GitHub.

**Full cloud chat transcript (JSON, ~7 MB):**  
- Artifact: `/opt/cursor/artifacts/cloud-chat-transcript-bc-5fb48539.json`  
- Also: `/workspace/podcast-in-a-box-app/cloud-chat-transcript-bc-5fb48539.json`  
- Cloud run URL: https://cursor.com/agents/bc-5fb48539-b8e8-4047-9cc7-9f05401fe5c0  
- Earlier long local transcript (Windows):  
  `C:\Users\jakey\.cursor\projects\e-PodcastRoom-Cursor-podcast-in-a-box-app\agent-transcripts\8ef420c0-5177-4bbb-bbf2-1ccad63dd025\8ef420c0-5177-4bbb-bbf2-1ccad63dd025.jsonl`

---

## Immediate bug (user reported)

When the **Final Render** window is up (`title like "Final Render — Test"`):

1. **Cannot switch to Home** via Alt-Tab — Home appears in Alt-Tab but selecting it does nothing.
2. **Abort → Yes** shows the confirm dialog, but after Yes nothing happens: window stays up, still says Rendering, still cannot get to Home.
3. **Window X (close)** does nothing.

### Likely root cause (from prior implementation)

In `app/gui/main_window.py` `closeEvent` for `role == "final"`:

- Close is **ignored** unless `resume_at == "14_done"`.
- Abort path calls `close_final_render()` → `window.close()` → that `closeEvent` **rejects** the close.
- So Abort may kill the job (or not) but the UI stays stuck on “Rendering…”.
- X is intentionally blocked while incomplete — but Abort must force-close.

Also check Home placement in `window_manager.handoff_to_final_render`: Home may be moved **off-screen** (`home.move` below Final), which can make Alt-Tab selection look like a no-op.

### Fix intent

1. Add a force-close flag (e.g. `_allow_close`) set by Abort / queued-cancel / successful Close after done, so `closeEvent` accepts.
2. On X while still rendering: show a short message (“Use Abort to cancel”) instead of silent ignore — or treat X like Abort with confirm.
3. Keep Home on-screen (clamp to available geometry); ensure Final is non-modal (`Qt.NonModal`); after handoff, Home remains activatable.
4. After Abort succeeds: stop poll, clear job id, force-close Final, ensure Home is open/raised.

---

## Product context (already implemented locally; not on GitHub main)

Recent local work (prior session) added:

- Fast Preview for **all** sessions; no full-length `Input/` until after 1-min approval.
- Sources **&lt; 5 min**: tail 60s for preview; after approval **reuse** preview prepped files as canonical.
- Dual job lanes: one Fast Preview + one Full may overlap; Full jobs queue FIFO.
- Multi-window: Home / Prep flow / **one Final Render window per job**.
- After 1-min Looks good → enqueue Full → open Final Render → ensure Home.
- Close Program on Home (block if recording); interrupt queue on quit; resume/abort prompts on next Home open.
- Footer: “Autocut in progress…”; prep screens also get slower-prep notice.
- Low Disk Space → Clean Old Working Files with return path (earlier in thread).

GitHub `embrodski/podcast-in-a-box-app` `main` is older (`0662c05`) and **does not** include multi-window/queue.

---

## Rebuild / cloud note

No environment rebuild was running for this cloud run (no linked Cursor environment / no in-progress builds).  
If the UI still shows the cloud agent “working,” **stop/archive** this run in the Cursor agents UI:  
https://cursor.com/agents/bc-5fb48539-b8e8-4047-9cc7-9f05401fe5c0

Continue only in **Cursor Desktop** on `E:\PodcastRoom\Cursor\podcast-in-a-box-app`.
