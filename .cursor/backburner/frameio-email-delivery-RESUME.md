# Backburner: Frame.io + email delivery after harness full render

**Status:** Phase 1 **implemented** (PIAB only, 2026-07-28).

---

## Decisions (confirmed by user)

| # | Decision |
|---|----------|
| 1 | **PIAB only** v1 (`Full Interview.mp4`) |
| 2 | **SMTP** via Gmail (App Password) |
| 3 | User has Frame.io account — configure via env vars |
| 4 | **Public** share, download enabled, no expiration |
| 5 | Failure email includes **local file path** |
| 6 | **Skip re-prompt** on resume if email already confirmed in session |
| — | Confirm prompt: **“Is this correct? [Y/N or A to abort]”** — abort = no delivery |
| — | **`Full Interview.delivery.json`** in Output (permanent: file_id, share_id, short_url) |
| — | **`Full Interview Transcript.json`** copied to Output |
| — | Logs may include recipient email unmasked |

---

## Implemented modules

| File | Role |
|------|------|
| `scripts/harness_delivery_prompt.py` | Opt-in, email entry, Y/N/A confirm |
| `scripts/frameio_client.py` | Chunked upload, poll, public share |
| `scripts/harness_email.py` | Gmail/SMTP success + failure emails |
| `scripts/harness_deliver_video.py` | Orchestrator + Output/Temp artifacts |
| `delivery-config.example.env` | Env var template |

**Hooks:** `piab_start_session.py`, `piab_init_session.py`, `piab_run_full_render.py`  
**Docs:** `.cursor/skills/lighthaven-podcast-in-a-box/SKILL.md`

---

## Env vars

See `delivery-config.example.env`:

- Frame.io: `FRAMEIO_ACCESS_TOKEN`, `FRAMEIO_ACCOUNT_ID`, `FRAMEIO_PROJECT_ID`, `FRAMEIO_UPLOAD_FOLDER_ID`
- Gmail SMTP: `HARNESS_SMTP_*`

---

## Chunking note (for user)

Frame.io returns one presigned S3 URL for small files and **many ~20 MB URLs** for large files (~2 GB interviews). Chunking means splitting the file into those parts and PUT-ing each directly to S3; Frame.io stitches them server-side. It is required for large uploads, not optional complexity — same end result, just more HTTP requests during upload.

---

## Phase 2 (not started)

- Inkhaven `Complete Episode.mp4` delivery
- Optional Frame.io setup/validation script

---

## Tests

```powershell
cd scripts
python -m unittest test_harness_delivery_prompt test_frameio_client test_harness_deliver_video -v
```
