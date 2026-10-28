# PROGRESS

Claude Code: update this file at the end of every milestone and whenever you make a decision. Read it first in every new session.

**Last updated:** [DATE]
**Current milestone:** M0
**Overall status:** Not started

Status values: `todo`, `in progress`, `blocked`, `done`

---

## Milestones

### M0 Foundation: `todo`
- [ ] Project scaffold, folder layout, `.gitignore` (ignore `.env`, `token.json`, `client_secret.json`, `projects/`)
- [ ] `config.py` with validation and clear missing-key messages
- [ ] SQLAlchemy models and DB init for all tables in SPEC Section 5
- [ ] `llm.py` wrapper
- [ ] `quota.py` with logging, limit and safety margin
- [ ] YouTube OAuth flow with cached `token.json`; expired-token handling
- [ ] Retry/backoff utility; logging utility
- [ ] Stage-order enforcement and idempotency helpers
- [ ] Tests: config validation, quota tracker, stage ordering
- [ ] CLI skeleton with `--help` for every command

### M1 Topics: `todo`
- [ ] `research "<seed>"` (suggestions, top recent videos, outlier scoring, ranking)
- [ ] `approve-idea <id>`
- [ ] Tests: outlier scoring, ranking, idempotency

### M2 Scripts: `todo`
- [ ] Title generation (15 variants, under 70 chars, banned-phrase check, pick)
- [ ] Script generation with hook, retention beats, CTA, sources for sensitive topics
- [ ] Segment list with visual keywords and estimated seconds
- [ ] Tests: title validation, segment structure

### M3 Voice and visuals: `todo`
- [ ] `voice` with edge-tts and optional ElevenLabs interface
- [ ] Real duration measurement and segment timing update
- [ ] `visuals` with Pexels, caching, fallback cards, licence/attribution records
- [ ] `providers/charts.py`: render charts, flow diagrams and number cards from `chart_data` (matplotlib/Pillow); require a source per chart
- [ ] Tests: segment timing, fallback behavior (mocked)

### M4 Assembly: `todo`
- [ ] `build`: stitch, music ducking, faster-whisper captions burned in, intro/outro, 1080p export
- [ ] `shorts`: 2-3 vertical 9:16 clips
- [ ] Sample dry-run producing a playable MP4
- [ ] Tests: timing math, ffmpeg command construction

### M5 Thumbnails: `todo`
- [ ] 3 variants from templates, 1280x720, under 2 MB
- [ ] Tests: size/dimension validation

### M6 Review and publish: `todo`
- [ ] `review` checklist with typed `yes`, writes `review.json`
- [ ] `publish` with scheduling, metadata, chapters, thumbnail, captions, playlist
- [ ] Synthetic-media disclosure flag (verify field name in current docs)
- [ ] Detect and report uploads forced private (API audit restriction)
- [ ] Tests: publish refuses without `reviewed`; refuses without typed `yes`; licence-unknown fails review

### M7 Channel management: `todo`
- [ ] `analytics` with stored metrics and plain-English report
- [ ] `ab-log`
- [ ] `comments` (draft only; separate guarded post command)
- [ ] `calendar`, `status`, `run-all`
- [ ] Tests: report generation, comment draft never posts, run-all stops at review gate

### M8 Docs and hardening: `todo`
- [ ] README setup steps verified against the real flow
- [ ] SPEC updated with any decisions that changed
- [ ] Full `pytest -q` green
- [ ] Final summary for owner

---

## Decisions
Record any choice made without asking the owner, with date and reason.

| Date | Decision | Reason |
|---|---|---|
| | | |

## Owner must configure manually
- [ ] Google Cloud project, YouTube Data API v3 and YouTube Analytics API enabled
- [ ] OAuth consent screen and Desktop-app client secret saved as `client_secret.json`
- [ ] Add owner's Google account as a test user if the app is in testing mode
- [ ] `.env` filled in (see SPEC Section 6)
- [ ] ffmpeg installed and on PATH
- [ ] Pexels API key
- [ ] Music files placed in `assets/music/` with licence notes
- [ ] Intro/outro clips and brand fonts placed in `assets/`
- [ ] SPEC.md Section 1 (channel brief) and Section 9 (style guide) filled in
- [ ] Decide on API compliance audit if uploads are forced private

## Known issues
| Date | Issue | Status |
|---|---|---|
| | | |

## Session log
Add one line per session: date, what was done, what is next.
