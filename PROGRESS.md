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
| 2026-10-31 | Review page plays a 480p browser-safe `preview.mp4` (H.264 main, yuv420p, AAC, faststart) made from `final.mp4` on first view, warns if the full file is not browser-compatible, and falls back to download buttons on any preview error. Intro/outro re-encode now sets yuv420p and faststart. | Player did not play the built video on the hosted app; the cause could not be checked without the file, so the preview is guaranteed-compatible and small. |
| 2026-10-31 | Web stages run in a child process (an out-of-memory kill shows an error instead of crashing the app). Build speedups: captions are the only full re-encode (audio mix copies the picture), shots render 2 at a time, narration synthesis 4 at a time, Pexels/Pixabay clips stream to disk and are capped at 1920 px, a failing image source is dropped after 2 failures. `STUDIO_DRAFT=1` / the Fast draft checkbox gives 720p. | Hosted app crashed after the voice step on a ~1 GB host (log ended with no traceback) and builds were slow. |
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
| 2026-10-31 | Auto topic suggestions (`studio/stages/discover.py`) | "Suggest topics for me" button: picks fresh subjects, asks YouTube search suggestions, dedupes near-duplicates, drops off-channel (games, pay, jobs), skips anything already saved. Also a paste-to-Claude prompt route. Autocomplete-only demand is now 0-10 and competition shows n/a without Google sign-in. |

## 2026-10-31: quality pass (story first, then picture and sound)
Owner feedback on the first real video: weak story, weak editing, broken images, viewers drop off. Changes:

**Story (priority)**
- `studio/prompts/hooks.md`: hook formula library and curiosity devices, injected into every story prompt.
- `outline <idea_id>` (optional, before `script`): retention outline with 3 hook options, 3-5 open loops with plant and
  payoff beats, a 10-18 beat sheet (a non-explain beat at least every 40 s), ending with callback, takeaway, CTA
  question and next video. Validated; the saved outline is added to the script prompt automatically.
- Script prompt rewritten: hook formulas, storytelling arc, open loops, pattern interrupts every 20-40 s, spoken
  style rules, callback ending with a specific CTA, segments 8-30 s, new `hook_type` and `open_loop` fields.
- `critique <video_id>` (optional, before `voice`): scored 10-point checklist plus a full rewrite. Rewrite is validated
  with the normal script rules, applied as a new script version, original kept as `script.original.json`.
- `qa <video_id>` and the `script`/`build` stages print a story and visuals report (weak hook opener, missing open
  loops, no CTA, long sentences, beat gaps, plain cards, repeated pictures). Never blocks. Saved as `qa.json`.
- Streamlit "2. Script" page has outline and critique blocks (copy request, paste answer back).

**Picture and sound**
- Quality gate for every photo and clip (`util/media_check.py`): readable, at least 1280x720, landscape, not flat
  or blurry, not a near-duplicate (perceptual hash). Bad candidates are skipped and the next one is tried.
- Image relevance: Pixabay hits ranked by tag overlap with the keywords; Commons results need title overlap and
  are dropped when named logo/map/flag/diagram/etc.
- Editing: shots 5 s max (3 s in the hook), varied Ken Burns moves centred on the frame (the old zoom drifted to the
  top-left), blurred-backdrop fit for boxy photos, cross-dissolves inside a segment, one colour grade.
- Word-by-word highlighted captions (ASS) and chapter banners; Shorts use the same style.
- Generated royalty-free music bed (own work, licence recorded) unless `assets/music` has a track; sidechain ducking
  under the voice; whoosh, impact and pop effects on cuts, reveals and chart steps; loudness normalised to -16 LUFS.

**Decisions**
- Outline and critique are not pipeline stages (stage table unchanged) so existing videos keep working.
- Critique refuses after `voice`: a rewrite changes the narration, so the voice would be stale.
- Music is synthesized with numpy rather than downloaded: no licence risk, no network.

**Not tested live**: edge-tts, Pixabay/Pexels/Commons and YouTube calls (this container's proxy blocks them), and
real Claude answers to the new prompts. Rendering was checked with synthetic photos and clips and the keyless demo.
Music and effects were checked for level and clipping, not by ear: listen once and tell us if the music is too busy.

## 2026-10-31: kids mode (nursery rhymes / learning songs)
- Added `studio/kids/` (spec, script prompt, Pillow drawing, build, checklist, demo, Streamlit page), `kids` CLI group
  and a "Kids mode" page. Main pipeline files only got the mode switch (cli.py group, app.py page entry).
- Decisions: no DB rows for kids projects (folder `projects/kids_<slug>/`); never publishes (out of SPEC scope, so
  upload is manual after `kids checklist`); fixed visual vocabulary so no paid art tools are needed;
  narration is spoken, not sung (edge-tts cannot sing).
- Tests: 21 new, all passing, 138 total; ruff clean. Not tested: real edge-tts voice (no network to Bing here),
  the Streamlit page in a browser, music mixing with a real track, playback on YouTube.
- Owner must: drop a royalty-free track in `assets/music/` if wanted; set Made for Kids on every upload.

## 2026-10-31: channel growth tools (page "5. Grow the channel")
- New `studio/growth/` (profile, series, packs, seo, shorts_plan, factcheck, perf, monetize) plus `studio/web/growth_service.py` and `growth_ui.py`. All free, no LLM key; creative parts give a copy-paste prompt and a paste-back box. Data lives in `growth/*.json` and `projects/<id>/growth/*.json`.
- Series planner (each video links to the next, outro and end-screen text, description line), calendar tab fills long slots with made videos then planned series topics, title/thumbnail pack (5 titles, 3 concepts, checklist-scored), SEO description/tags/chapters with source lines and photo credits, Shorts plan, fact/source checklist, performance advice from pasted CSV or quick form, Partner Program tracker with projected date and monetization checklist.
- Decisions: the fact checklist locks the "Run the pre-publish checklist" button on page 4 (UI only; `review.run` and the typed-`yes` gates are unchanged). Partner Program thresholds (1,000 subs + 4,000 public watch hours, or 10M Shorts views in 90 days) were read from YouTube Help on 2026-10-31; re-check before relying on them. Hosted storage is temporary, so growth data is lost when a free host sleeps; run locally to keep it.
- Owner to configure: channel profile answers on the Channel profile tab (defaults are used otherwise).

## 2026-10-31: kids mode stage 2 (free quality upgrades)
- Added `sprites.py` (SVG cast with blink and mouth sync, owner overrides in `assets/kids/characters/`), camera moves
  in `draw.py`, `music.py` (original generated tune per title), `variety.py` (repetitive-content warning in the
  checklist), 3 s minimum scene length. New deps: numpy, cairosvg (+ libcairo2 in packages.txt); both optional at run time.
- Decisions: characters are generated flat-colour originals, not copies of any franchise; generated music is a
  simple pentatonic tune, not a sung melody (still the biggest quality gap; see the roadmap).
- Tests: 22 more (160 total) pass; ruff clean. Not tested: real edge-tts voice, Streamlit page in a browser, how the
  music sounds to a child, hosted app with libcairo2, YouTube upload and Made for Kids behaviour.
