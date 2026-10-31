# PROGRESS

Claude Code: update this file at the end of every milestone and whenever you make a decision. Read it first in every new session.

**Last updated:** 2026-10-31
**Current milestone:** M8 done; next is the owner's setup and the first real video
**Overall status:** Build complete. 93 tests pass (`pytest -q`), `ruff check .` is clean, and `demo` builds a playable 1080p MP4

Status values: `todo`, `in progress`, `blocked`, `done`

---

## Milestones

### M0 Foundation: `done` (2026-10-28)
- [x] Project scaffold, folder layout, `.gitignore` (ignore `.env`, `token.json`, `client_secret.json`, `projects/`)
- [x] `config.py` with validation and clear missing-key messages
- [x] SQLAlchemy models and DB init for all tables in SPEC Section 5 (+ `schema_version` row)
- [x] `llm.py` wrapper (default `claude_code` prompt-file handoff; optional anthropic/openai/gemini)
- [x] `quota.py` with logging, limit, safety margin and separate search/upload buckets
- [x] YouTube OAuth flow with cached `token.json`; expired/revoked token is deleted and sign-in rerun
- [x] Retry/backoff utility (5 attempts); logging utility with secret redaction
- [x] Stage-order enforcement and idempotency helpers
- [x] Tests: config validation, quota tracker, stage ordering, retry, auth, LLM handoff
- [x] CLI skeleton with `--help` for every command

### M1 Topics: `done` (2026-10-28)
- [x] `research "<seed>"` (YouTube autocomplete suggestions, top recent videos, outlier scoring, ranking; same seed same day is cached)
- [x] `approve-idea <id>`
- [x] Tests: outlier scoring, ranking, idempotency

### M2 Scripts: `done` (2026-10-28)
- [x] Title generation (15 variants, under 70 chars, banned-phrase and all-caps check, one pick)
- [x] Script generation with hook, retention beats, CTA, sources; prompt reads SPEC sections 1 and 9 live
- [x] Segment list with visual keywords, estimated seconds, chapter names and `chart_data`
- [x] Tests: title validation, segment structure, pacing warnings, handoff flow

### M3 Voice and visuals: `done` (2026-10-28)
- [x] `voice` with edge-tts, optional ElevenLabs, and `silent` for dry runs
- [x] Real duration measurement and segment timing update (DB and script.json)
- [x] `visuals` with Pexels (v1 videos endpoint), caching, several shots per segment, fallback cards, licence/attribution records
- [x] `providers/charts.py`: bar, line, pie, flow and number charts, revealed step by step; source footnote required
- [x] Tests: segment timing, fallback behavior, Pexels file choice and caching

### M4 Assembly: `done` (2026-10-28)
- [x] `build`: stitch to narration timing, music at -20 dB, captions burned in (faster-whisper if installed, else script-timed), intro/outro, 1080p export; also `clean.mp4` without captions
- [x] `shorts`: 2-3 vertical 9:16 clips with their own captions
- [x] Sample dry-run producing a playable MP4 (`demo`)
- [x] Tests: timing math, ffmpeg command construction, captions, licence sidecars

### M5 Thumbnails: `done` (2026-10-28)
- [x] 3 variants (split, full-bleed, big-number layouts), 1280x720 JPEG, under 2 MB; optional overlay template
- [x] Tests: size/dimension validation

### M6 Review and publish: `done` (2026-10-28)
- [x] `review` checklist with typed `yes`, writes `review.json` (with file hash)
- [x] `publish` with second typed `yes`, quota precheck, scheduling, metadata, chapters, thumbnail, captions, playlist, resumable extra steps
- [x] Synthetic-media disclosure: `status.containsSyntheticMedia` (verified in Data API revision history)
- [x] Detect and report uploads forced private (API audit restriction)
- [x] Tests: publish refuses without `reviewed`; refuses without typed `yes`; licence-unknown fails review; changed file refused

### M7 Channel management: `done` (2026-10-28)
- [x] `analytics` with stored metrics, traffic sources, retention drop-offs and a plain-English report in `reports/`
- [x] `ab-log` (records only; never edits the live video)
- [x] `comments` (draft only) and `comments post <file>` with per-reply typed `yes`
- [x] `calendar`, `status [--sync]`, `run-all`, `quota`
- [x] Tests: report generation, comment draft never posts, run-all stops at review gate (end to end with real ffmpeg and mocked APIs)

### M8 Docs and hardening: `done` (2026-10-28)
- [x] README setup steps updated to the real flow (prompt handoff, demo, licence notes, quota)
- [x] SPEC updated with decisions that changed (LLM, quota table, video tooling, new commands)
- [x] Full `pytest -q` green (93 tests)
- [ ] README verified against a real Google account (needs the owner's credentials)

---

## Decisions
Record any choice made without asking the owner, with date and reason.

| Date | Decision | Reason |
|---|---|---|
| 2026-10-31 | Added a Streamlit web app (`app.py`, `studio/web/service.py`) that calls the existing stages; no pipeline logic was duplicated. Script step keeps the file handoff: copy prompt, paste JSON answer. Hosted target is Streamlit Community Cloud, not Vercel. Typed `yes` gates are fed from text boxes and still refuse anything else. YouTube upload is local-only (OAuth desktop flow). | Owner asked for an app instead of the CLI, deployable on Streamlit or Vercel. Vercel cannot run long ffmpeg jobs. Owner request overrides the old SPEC 12 "web dashboard" exclusion for the pipeline UI. |
| 2026-10-28 | LLM default is `claude_code`: commands write `prompts/<task>.prompt.md`, exit code 3, and continue when Claude Code writes `<task>.response.json`. API providers stay optional. | Owner has no LLM API key and wants Claude Code to do the writing. |
| 2026-10-28 | Quota tracked in three buckets: shared units (10,000), `search.list` (100 calls/day), `videos.insert` (100 calls/day). | Official quota calculator (checked 2026-10-28) shows upload dropped from ~1,600 units to its own bucket in Dec 2025. SPEC section 7 updated. |
| 2026-10-29 | Footage is a pluggable provider (`studio/providers/footage.py`): Pixabay added, Pexels kept, chosen by `FOOTAGE_PROVIDER` (auto/pexels/pixabay/none). No key is required: `visuals` falls back to generated cards and charts and prints a message. An explicit provider with a missing key is an error. | Pexels paused new API key issuance. Pixabay docs and licence summary (checked 2026-10-29): free key, commercial use allowed, attribution not required, 24 h search cache requested, 100 req/60 s. Licence and page URL are still stored per asset; descriptions credit the provider. |
| 2026-10-28 | ffmpeg directly, no MoviePy. | Fewer dependencies and pure command builders are easy to test. |
| 2026-10-28 | Charts render as step frames (one bar/flow step at a time) shown in sequence, rather than a true animation. | Gives the "revealed step by step" effect with matplotlib only; fast to render. |
| 2026-10-28 | Captions come from faster-whisper when installed, otherwise from the script text timed by word count. | faster-whisper is a large optional install; the narration text is already exact. |
| 2026-10-28 | Music is mixed at a constant -20 dB under the narration. | Meets the style guide's "at least 15 dB under voice" simply. |
| 2026-10-28 | Licences for music/intro/outro come from a sidecar `<file>.licence.txt`; no note means `unknown`, which blocks review. | SPEC 8.5 requires a known licence per asset. |
| 2026-10-28 | Each segment gets up to 4 stock shots so the picture changes every 6 s or less; charts take over after a short lead-in. | Style guide pacing rule (visual change every 4-6 s). |
| 2026-10-28 | `script` takes the idea id (as SPEC says); every later command takes the video id. `approve-idea` prints the video id. | Keeps the documented command shapes. |
| 2026-10-28 | `run-all` auto-approves the top-ranked new idea when no approved idea is in progress, and says so. | Approving is reversible and not a publish action; keeps run-all useful. |
| 2026-10-28 | `publish` asks for a second typed `yes` and refuses if `final.mp4` changed since review (SHA-256 in review.json). | Spec test requires publish to refuse without typed yes; the hash keeps the gate honest. |
| 2026-10-28 | Videos are always uploaded `private`; with `--at` they carry `publishAt`. Without `--at` they stay private. | Safer default; YouTube needs private + publishAt to schedule. |
| 2026-10-28 | Impressions and CTR are requested opportunistically; if the Analytics API rejects them, they are stored as empty and the report points to YouTube Studio. | They are not listed in the Analytics API metrics reference (checked 2026-10-28). |
| 2026-10-28 | Brand colours default to navy #0F172A, amber #F59E0B, sky #38BDF8; font is the first file in `assets/fonts`, else DejaVu Sans. | SPEC section 9 still has placeholders. |
| 2026-10-28 | Default cadence slots: long videos Tue and Fri, Shorts Mon, Wed and Sat. | SPEC section 1 says 2 long + 3 Shorts per week but no days. |
| 2026-10-28 | Added `quota` and `demo` commands; the demo video can never be published. | `demo` satisfies the dry-run definition of done without keys. |

## Owner must configure manually
- [ ] Google Cloud project, YouTube Data API v3 and YouTube Analytics API enabled
- [ ] OAuth consent screen and Desktop-app client secret saved as `client_secret.json`
- [ ] Add owner's Google account as a test user if the app is in testing mode
- [ ] `.env` filled in from `.env.example` (CHANNEL_ID; no LLM key needed)
- [ ] ffmpeg installed and on PATH
- [ ] Optional: free Pixabay API key (`PIXABAY_API_KEY`) for stock footage; without it `visuals` uses generated cards and charts
- [ ] Music files placed in `assets/music/` with a `<file>.licence.txt` each
- [ ] Intro/outro clips (under 5 s, with licence notes) and brand fonts placed in `assets/`
- [ ] SPEC.md Section 1 (channel name, audience) and Section 9 (brand colours, font, music mood) filled in
- [ ] Phone-verify the channel (needed for custom thumbnails)
- [ ] Decide on API compliance audit if uploads are forced private

## Known issues
| Date | Issue | Status |
|---|---|---|
| 2026-10-28 | edge-tts could not be tested live here (no access to Microsoft's speech service from the build machine); the demo falls back to silent narration. | Verify on the owner's machine |
| 2026-10-28 | Real Google OAuth, upload, captions and Analytics calls are only tested against mocks. | Verify with the first real video |
| 2026-10-28 | Search suggestions use YouTube's public autocomplete endpoint, which is unofficial; research continues without it if it fails. | Accepted |

## Session log
- 2026-10-28: Built M0-M8 in one session. 93 tests pass, demo builds a 49 s sample MP4 with charts, captions, 3 thumbnails and 2 Shorts. Next: owner setup (above), then `research` -> first real video.

## 2026-10-31: image search and no length caps
- `studio/providers/images.py`: Pixabay photos + Wikimedia Commons (licence allow-list, author credit recorded); `visuals` alternates clip/photo shots, falls back to cards only if nothing is found.
- Removed the 4-shot cap per segment and the 10-15 min length warning (now only warns under 5 min). Shorts stay 15-58 s (platform rule).
- Photos are cropped to 16:9 before the slow zoom. CC BY credits are appended to the description (`Image credits`).
- Untested live: Wikimedia/Pixabay image endpoints were blocked in the build sandbox (403), so the first real run is on the owner's machine. Image source failures are skipped, not fatal.
| 2026-10-31 | `IMAGE_PROVIDER=auto` default | Commons needs no key, so photos work out of the box |
