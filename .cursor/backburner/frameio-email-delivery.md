# Backburner: Frame.io email delivery after harness full render

**Status:** Planning complete; **no code implemented.** User asked to pause (2026-07-28) and resume later.

## Goal

At harness start: opt-in to email the finished video when done; collect and **confirm** recipient email.

After full render completes (in addition to normal UI output):

1. Upload deliverable MP4 to Frame.io (v4 local upload + chunked PUT).
2. Poll until `upload_complete` (GET `…/files/{file_id}/status`).
3. Create Share with `expiration: null`, use `short_url` as recipient link (never send expiring S3 upload URLs).
4. Record `file_id`, `share_id`, `short_url` in session state.
5. Email `short_url` to confirmed address; on failure, email failure notice instead.
6. Print success block: recipient, file ID, share ID, short_url. No credentials in logs or user messages.

## Scope agreed in plan (pending user confirmation)

- **Phase 1:** PIAB only — hook in `scripts/piab_run_full_render.py` after `Full Interview.mp4`.
- **Phase 2 (optional):** Inkhaven harness → `Complete Episode.mp4` after stitch.

## Proposed touchpoints (not built)

| File | Change |
|------|--------|
| `scripts/piab_start_session.py` | Email opt-in + confirm before init |
| `.cursor/skills/lighthaven-podcast-in-a-box/SKILL.md` | Agent asks same at session start |
| `scripts/piab_run_full_render.py` | Post-render delivery orchestration |
| `scripts/harness_delivery_prompt.py` | New — prompt/validate/confirm email |
| `scripts/frameio_client.py` | New — upload, poll, create share |
| `scripts/harness_email.py` | New — SMTP success/failure templates |
| `scripts/harness_deliver_video.py` | New — orchestrator + state update |
| `podcast-in-a-box.json` | New `delivery` block (see plan below) |

## Frame.io v4 flow (from API docs)

1. `POST /v4/accounts/{account_id}/folders/{folder_id}/files/local_upload` → file ID + presigned upload URLs.
2. `PUT` chunks with `x-amz-acl: private` (internal only; never email/log URLs).
3. Poll `GET /v4/accounts/{account_id}/files/{file_id}/status` until `upload_complete`.
4. `POST /v4/accounts/{account_id}/projects/{project_id}/shares` with `asset_ids: [file_id]`, `expiration: null`, `access: public`.
5. Use response `short_url` (e.g. `https://f.io/…`).

## Proposed state schema

```json
"delivery": {
  "enabled": true,
  "email": "user@example.com",
  "email_confirmed_at": "ISO8601",
  "deliverable": "full_interview",
  "frameio": {
    "status": "completed | failed | skipped",
    "file_id": "…",
    "share_id": "…",
    "short_url": "https://f.io/…",
    "error": "sanitized",
    "completed_at": "ISO8601"
  },
  "email_delivery": {
    "status": "sent | failed",
    "sent_at": "ISO8601",
    "error": "…"
  }
}
```

Also write `Temp/delivery-summary.json` for future job-summary UI.

## Env vars (not in repo)

**Frame.io:** `FRAMEIO_ACCESS_TOKEN`, `FRAMEIO_ACCOUNT_ID`, `FRAMEIO_PROJECT_ID`, `FRAMEIO_UPLOAD_FOLDER_ID`

**Email (SMTP):** `HARNESS_SMTP_HOST`, `HARNESS_SMTP_PORT`, `HARNESS_SMTP_USER`, `HARNESS_SMTP_PASSWORD`, `HARNESS_SMTP_FROM`, `HARNESS_SMTP_USE_TLS`

## Open decisions (ask user before implementing)

1. PIAB only vs both harnesses in v1?
2. Email transport: SMTP vs SendGrid/Office365?
3. Frame.io token/setup — existing IDs or setup script?
4. Share: public + download OK, or passphrase (`secure`)?
5. Failure email: include local path or agent-only?
6. Resume sessions: skip re-prompt if email already confirmed?

## Testing plan (not started)

- Unit tests with mocked HTTP/SMTP.
- `--delivery-dry-run` on full render.
- Manual integration with small MP4 + test inbox.

## Related work already shipped this session (separate from this feature)

Pause-seam padding, flag phrase reporting, Jessiah full rerender — see git diff and `scripts/podcast_flag_phrases.py`. Do not conflate with delivery work.
