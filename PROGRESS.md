# PROGRESS

Claude Code: update this file at the end of every milestone and whenever you make a decision. Read it first in every new session.

**Last updated:** 2026-11-02
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

### M9 Web app as the single front end: `done` (2026-11-01)
- [x] `Setup` page: doctor checklist with guided steps and a fix box per item (keys to `.env`, upload `client_secret.json`, channel ID, voice sample, 2D/3D picture style)
- [x] Setup page sign-in uses the per-channel sign-in from M-multi-channel (`tokens/<channel>.json`)
- [x] `Make a video` wizard (topic, script handoff with paste or upload, optional critique, voice, QA score, make, review, typed-yes approve, schedule/upload); resumes the newest unfinished video; kids channels route to the Kids builder
- [x] Shared `publish_ui` and `handoff_ui` (paste-or-upload box for Claude answers); Review page reuses them
- [x] `run_app.bat` (Windows one-click: Python check, venv, packages, `.env`, ffmpeg offer) and `run_app.sh`
- [x] Tests: `tests/test_web_setup_wizard.py` (298 tests total pass, ruff clean)
- Not tested in a real run: the `.bat` on Windows, Google sign-in and upload, edge-tts voice sample (needs internet), Blender 3D, winget ffmpeg install.

### M8 Docs and hardening: `done` (2026-10-28)
- [x] README setup steps updated to the real flow (prompt handoff, demo, licence notes, quota)
- [x] SPEC updated with decisions that changed (LLM, quota table, video tooling, new commands)
- [x] Full `pytest -q` green (93 tests)
- [ ] README verified against a real Google account (needs the owner's credentials)

---

## Decisions
- 2026-11-03: every prompt template (all packs, outline, plan, review, critique), the style/compliance text and channel guidance no longer ask for sources, citations or fact ids; a test guards it. The app drops a saved prompt file that still asks for them so it is rewritten.
Record any choice made without asking the owner, with date and reason.

| Date | Decision | Reason |
|---|---|---|
| 2026-11-01 | Script validation: beats like `explain` are auto-fixed (explain -> no beat, anecdote -> example, ...) with a note; flow diagrams with no values and charts labelled made-up/illustration need no source; the web app lists problems in plain words with a copy-able fix request and keeps the rejected answer in `prompts/<task>.rejected.json`. | A valid-looking pasted script hit a dead end pointing at a CLI file path. |
| 2026-11-01 | Added `doctor` (go/no-go check, files and settings only), `suggest`, `add-topic`, and FIRST_VIDEO.md runbook. | Owner wants one clear path to the first real video with their own topic or a suggested one. |
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

## 2026-10-31: optional Blender 3D renderer for kids mode
- Added `studio/blender/` (`provider.py` finds/validates Blender and runs it headless; `scene_script.py` runs inside
  Blender and builds flat-colour 3D scenes for all 12 characters, 5 backgrounds, 4 motions and 4 camera moves),
  `studio/kids/build3d.py` (frames + the same lyric captions and counting number as 2D), `RENDERER` / `BLENDER_PATH`
  settings, `--renderer` on `kids build` and `kids demo`, README "Optional 3D renderer" with Windows steps.
- Decisions: default stays `2d`; Blender is opt-in and falls back to 2D with a printed note if missing or older than
  4.2; no image textures and 1280x720 at 24 fps to suit a 4 GB GPU; the script avoids importing `studio` so it runs
  in Blender's bundled Python regardless of the system Python (3.11 or 3.12). The long-form (non-kids) pipeline is
  not changed: economics charts and diagrams gain nothing from 3D.
- Tests: 11 new (173 total) pass; ruff clean. The scene script was also run for real through the `bpy` module with
  the Cycles CPU engine and the output frames were inspected.
- Not tested: Eevee rendering (no GPU/OpenGL in the build sandbox), the `blender` executable on Windows 11, the RTX
  A1000's render speed and memory use, and the engine id on Blender 4.2-4.5 (`BLENDER_EEVEE_NEXT`; Blender 5.x uses
  `BLENDER_EEVEE`; the script tries both).
- Owner must: install Blender 4.2+ and run the demo command above, then report the render time.


## Dynamic channel profiles (2026-11-01)
- Any number of channel profiles (name, niche, description, audience, language, posts/week, voice, YouTube channel id) stored in `growth/channels.json`; one is active. Old `growth/profile.json` becomes the `default` channel automatically.
- CLI: `channels list|add|edit|use|show|remove|export|import`. App: sidebar channel selector + **Channels** page (add/edit/delete/switch, download/restore `channels.json`).
- Active profile now drives: TTS voice and YouTube channel id (override `.env` when set), script/outline brief and topic-ideas prompt (once the profile is customised), growth prompts and posting plan.
- Per-channel separation: ideas (and so videos, calendar, status, analytics report) carry `ideas.channel_id` (old databases upgrade in place; existing rows join `default`); series, performance, monetization and fact-check data live in `growth/c/<channel>/` (the `default` channel keeps the old `growth/` paths).
- Topic discovery follows the channel: once a niche is customised, hands-off suggestions use the niche and the business-word fit filter is relaxed (junk words are still blocked).


## Quality gate and retention feedback (2026-11-01)
- `studio/quality/`: `profiles.py` (channel types `explainer` (business, general), `story` (history), `kids`; set with `channels add|edit --type business|history|kids|general`, guessed from the niche otherwise), `gate.py` (six scored dimensions: script, hook, pacing, visuals, audio, metadata; verdict pass / warn / block), `rules.py` and `feedback.py` (retention loop).
- CLI: `gate <id>`; `review` now runs the gate and refuses on `block` unless `--accept-weak` (typed `yes` is unchanged and still required). `feedback learn [--mock|--live|--apply-mock]`, `feedback show`.
- Loop: retention curve + CTR per published video -> hook retention at 0:30, worst mid-video drop (mapped to the chapter), average viewed, end retention -> per-channel `rules.json` in the channel's growth folder: gate threshold tuning (hook length, beat gap, sentence length), edit limits (`shot_max_seconds`, `hook_shot_max_seconds`, respected by `visuals` and `build`), and lessons appended to the script/outline brief.
- Decisions: mock retention data (used automatically when YouTube Analytics is unavailable) is labelled and stays advisory; it changes nothing unless `--apply-mock`. Rules only tighten limits. Audio uses ffmpeg `ebur128` on `final.mp4`; when unmeasurable it is noted, not failed. Every threshold is a rule of thumb, not a YouTube rule.
- Tests: `tests/test_quality.py` (APIs mocked). Not tested live: real YouTube Analytics retention curves (`audienceWatchRatio`), ffmpeg loudness on a real build, how well the thresholds match this channel's real audience.
- Owner must: set the channel type; run `feedback learn` after each video has a few days of data.

## 2026-11-01: optional sung melody via OpenUtau (kids mode)
- Added `studio/kids/` `sing.py` (syllable-per-note melody plan, same tune for repeated lines, ends on the root),
  `sing_files.py` (MIDI with lyric events + `.ustx` YAML), `openutau.py` (find app, launch, pick up the exported WAV),
  `sing_mix.py` (ffmpeg mix command), `sing_step.py`, CLI `kids sing [--open] [--use wav]`, `OPENUTAU_PATH` setting,
  chords-only bed (`music.render(melody=False)`), README "Optional sung melody" with Windows steps.
- Decisions: OpenUtau has no documented CLI renderer, so rendering is a manual Export step; the build uses
  `sung/vocal.wav` (or the newest `sung/Export/*.wav`) when present and otherwise keeps the old narration + tune path.
  A sung vocal replaces the narration. The vocal is stretched to the video (x0.75-1.5) instead of re-timing scenes.
  The `.ustx` sets no singer; the phonemizer id is a best guess and the owner picks both in the app.
- Tests: 19 new (228 total) pass; ruff clean. MIDI also parsed with `mido`. The mix ran for real with ffmpeg using a
  generated WAV as a stand-in vocal.
- Not tested: OpenUtau itself (does it open the `.ustx`/launch argument cleanly, is the phonemizer id valid in the
  current release), any voicebank, how the sung result sounds, Windows paths. Owner must: install OpenUtau + a
  voicebank, check its licence, export once and report what happens.


## Multi-channel types, analytics and per-channel production settings (2026-11-01)
- Channel `type` (business, history, kids, general) in `studio/growth/channel_types.py`: drives prompt guidance, topic phrasing,
  music mood, colours, pipeline mode (kids vs narrated) and `selfDeclaredMadeForKids` on upload. Each channel has its own
  token (`tokens/<id>.json`; `default` keeps `token.json`) and `channels sign-in` records the YouTube channel id.
- Analytics: `studio/manage/multi_analytics.py` + `channels stats|compare` + app page "📊 Analytics" (per channel, all-channels overview,
  side-by-side table, date range, previous-period change, top videos, retention = average % viewed). Not-signed-in channels show a note,
  or labelled SAMPLE data with `--demo`.
- Production settings (`studio/production.py`): renderer, voice, tts provider, music, mood, colours resolved video > channel > type > `.env`;
  CLI `production show|set|reset`, `channels add|edit --renderer/--music/--music-mood/--tts-provider`, app Channels page and per-video box.
  Narrated videos get an optional Blender 3D title intro (`blender/title_card.py`); kids builds honour music none and the channel voice.
- Decisions: 3D for narrated channels is a title intro only (economics charts and diagrams gain nothing from 3D scenes); the app's Sign in
  button only works when the app runs on your own computer. Analytics for Made for Kids videos may be limited by YouTube.
- Tests: new files `test_multi_analytics.py` and `test_production.py`; 259 tests pass and ruff is clean. The Blender title scene was rendered for real through `bpy` (Cycles CPU).
- Not tested live: real YouTube Analytics API responses and metric availability (mocked), the Google sign-in browser flow with two accounts,
  Eevee rendering and the Windows `blender` executable for the title card, the Streamlit Sign-in button in a real browser.
- Owner must: run `channels sign-in <id>` once per channel (add your accounts as test users on the OAuth consent screen).

## Persistent storage and hosting (2026-11-01)
- `studio/storage/data.py` (usage, zip export/import, confirmed deletes), `studio/storage/sync.py` (folder/GitHub/S3 backup,
  autosave, restore on empty disk, secret files from env), `studio/web/data_ui.py` (Data page), `HOSTING.md`, `Dockerfile`.
- Decisions: one data dir = `STUDIO_HOME`; backups exclude media and secrets; GitHub backend refuses public repos;
  every delete needs the exact word DELETE. Not tested live: GitHub/S3 calls, Docker build, Hugging Face deploy.


## 3D and 2D scenes for narrated channels (2026-11-01)
- New `studio/scenes/`: scene kinds `timeline`, `map`, `artifact`, `chart3d` (optional `scene` on a script segment, validated, documented
  in `prompts/script.md`), `plan()` rules, 2D versions (`render2d.py`), Blender clips (`render3d.py`, `stage.py`), and the Blender scene
  builders in `blender/scene_script.py` (`kind: "scene"`).
- Style `scene_style` = 2d | 3d | mixed, resolved segment > video > channel > type (history/business mixed, general/kids 2d), shown in
  `production show`; per-segment picks in `production.json` (`segment_styles`). CLI `--scene-style`, `production scene`; app Channels page,
  per-video box and per-segment pickers. Narrated 3D title intro now follows it (`production.wants_blender`).
- Decisions: 3D scenes are one continuous 15 fps / 1280x720 clip per segment (max 30 s, then it loops); a missing or failing Blender falls back
  to the 2D version per scene with a note; maps are schematic (x, y in 0-1), not real geography; an explicit `renderer 2d` beats the type's
  3D default but not an explicit `scene_style`.
- Tests: new `tests/test_scenes.py`; all scene kinds were also rendered for real through `bpy` (Cycles CPU) and the frames inspected.
- Not tested live: Eevee on the RTX A1000 and render speed, the Windows `blender` executable, how scenes look at full length with real
  narration, the Streamlit controls in a browser.
- Owner must: install Blender 4.2+ for 3D (see "Optional 3D renderer"), then try a history video with `production scene <id> <n> 3d`.


- 2026-11-01: Launchers (`run_app.bat`/`run_app.sh`) pre-write `~/.streamlit/credentials.toml` (empty email) so Streamlit's first-run email prompt never blocks; friendlier errors for Python, pip, winget/ffmpeg; `.env` created even without `.env.example`.

## 2026-11-01 Fix: topics stuck on nursery rhymes
- Cause: the Channels edit form resubmits the niche text; changing a kids channel to business kept the kids niche, so
  suggestions followed it. Fix: a niche/audience that is another type's stock text is replaced by the channel type's own
  (on save and on read, which also repairs saved channels). Business channels on the stock niche use the business subject list.
- Topics page now shows the active channel, type and niche, and resets its seed when the channel changes.

## 2026-11-01 Fix: "Save and apply" on the answer box did nothing
- Cause: on success the page called `st.rerun()` straight away, so the success message vanished and the outline/critique
  looked unchanged; failures that raised an unexpected error (wrong-shaped JSON) were not caught, and pasted answers with
  fences, chatter, smart quotes or trailing commas were rejected with a vague message.
- Fix: `studio/util/answer_json.py` reads the first JSON object tolerantly (fences, surrounding text, smart quotes,
  trailing commas, // comments, raw newlines in strings) and reports line/column on failure. All paste-back flows
  (script, outline, critique, series, pack, kids) use it. `handoff_ui.apply_answer` shows a green "what was saved"
  message that survives the rerun, or a red message saying what is wrong and that nothing was saved. Unexpected errors
  become readable messages instead of tracebacks.
- Note: the app has paste-back boxes for script, outline, critique, series ideas, title pack and kids script; there are no
  separate research, fact-check or thumbnail answer boxes (fact-check is a tick-list).

## 2026-11-01 Fix: finance video came out as plain images
- Causes: business default `mixed` kept bar/line charts 2D and only segments with a script `scene` went 3D, so a script without
  scenes was fully 2D; draft mode switched camera moves off; charts were static step images; captions were 7.4% of frame height;
  a missing Blender only printed a note.
- Added: `studio/render_report.py` (preflight + `render_report.json`, yellow warning in CLI and app banner); `mixed` now also turns
  bar/line charts into 3D charts; `studio/providers/chart_anim.py` (bars rise, lines draw, key numbers count up, played by `build`);
  draft keeps camera moves; opening segment uses a 2x camera move; captions 0.074 -> 0.048 of height. README: Windows Blender steps.
- Already existed and unchanged: music ducking, whoosh/pop/hit SFX, keyword-highlight captions, hook shot limit, story/quality gate, thumbnails.
- Owner must: install Blender 4.2+ for real 3D; try a full (non-draft) build. Not tested: Blender render, full-length build look.

## Beat normalisation on every path (2026-11-01)
- `validate_package` now normalises segment `beat` values itself (so script, critique, quality gate and web paths all accept `explain` etc.). Unknown words become `null` (plain explanation); many more synonyms map to the nearest allowed beat. Script/critique prompts state the allowed beats and that the outline's `explain` device is `null`.
- If an old checkout still shows "beat 'explain' not in [...]": run `git pull origin main`, restart the app/launcher.
## 2026-11-01: stock key errors no longer crash the build
- Cause: a Pixabay HTTP 401 (bad key) was re-raised raw by `with_retry`, and nothing caught it.
- Fix: `with_retry` now raises `RequestRejected` for non-retryable HTTP errors; `studio/providers/guard.py` wraps stock video and
  photo providers so a rejected/failing service is skipped with a yellow notice naming the service, likely cause and the exact
  variable, and the build continues with generated visuals.
- `.env` keys are cleaned (quotes, spaces, BOM); `PIXABAY_KEY`/`PIXABAY` etc. are accepted as misspellings of `PIXABAY_API_KEY`.
- Setup page > Footage has a "Test my footage key" button (`doctor.test_footage_keys`). Tests: `tests/test_key_errors.py`.
- Owner must: use `PIXABAY_API_KEY=yourkey` in `.env`, no quotes or spaces.

## 2026-11-01 Channel identity: niche statement, mascot, theme, playlists (any channel)
- New channel profile fields (`studio/growth/identity.py`): `niche_statement`, `tagline`, `mascot`, `theme`, `playlists`.
  Validated on save; exported/imported with the channel. Presets: `finance-stories` (Penny the gold coin, navy/gold, three
  playlists: Comeback Stories, How Giants Make Money, Biggest Business Mistakes) and a neutral `explainer` (Ollie the owl).
- Used by: script/series/title prompts (persona, positioning, playlist title patterns via `channels.summary`); charts, cards
  and thumbnails (theme colours beat the type palette via `brand.use(palette, theme)`); thumbnails (mascot badge, a different
  mood per variant); build (branded outro card with the next-video line, optional intro card, only when no file in
  assets/intro or assets/outro); series (playlists create series, `youtube_id` stored); publish (uses the series' playlist
  id when `--playlist` is not given).
- Commands: `channels identity [--preset NAME] [--file x.json] [--preview DIR]`; the app: Grow > Profile > Identity.
- Owner must: create the playlists in YouTube Studio and paste each playlist id into the channel's `playlists[].youtube_id`
  (creating playlists through the API is not built). Optional: own mascot art/fonts in assets (heading_font in assets/fonts).
- Decision: mascot is drawn in code (coin, owl, robot) so no art files are required; the mascot never states figures.



## 2026-11-01 Growth playbook built into the gate
- Research summary with sources: `docs/growth-playbook.md` (numbers are blog rules of thumb; only the July 2025 inauthentic-content policy is from YouTube).
- Quality gate gained three dimensions (`studio/quality/growth.py`): `fit` (visuals match what the segment says: figures over stock,
  date runs without timeline, cliche stock keywords, off-topic footage, stock share), `packaging` (title promise appears in the hook,
  title checklist, >=3 titles / >=2 thumbnail texts, thumbnail <=4 words, series hint), `originality` (script/structure repeats the
  channel's recent videos, missing `originality_note`). Kids skip fit/originality. Peers = last 10 scripted videos of the channel.
- Shorts plan: 25-55 s windows, hook line cut to <=12 words, CTA + related video, posts staggered at +2/+9/+16 days.
- `calendar.suggest_publish` (next free long slot at `publish_time`) added; not yet wired into the review screen.
- `prompts/script.md` states the growth rules so Claude writes scripts that pass them.
- Decisions: thresholds are tunable defaults (explainer stock max 60%, similarity 25%); new dimensions can raise block/warn on old videos.
- Owner must: nothing to configure. Add a real viewpoint per script; disclose realistic synthetic voices/footage on upload; run title/thumbnail tests.
## 2026-11-01: plan preview before building
- New `studio/plan_preview.py` and CLI `plan <video_id> [--draft]`: lists per segment the length, 3D/2D scene, chart type,
  stock search words and picture source, plus resolution, voice, music, captions, Blender and stock/photo availability,
  and plain warnings (unsourced chart, no stock key, Blender unusable, 3D clips are 1280x720 @ 15 fps, no charts at all).
  Reads only `script.json`, settings and `.env`; nothing is rendered or fetched.
- Make video page: "Plan: what this video will use" box above the run buttons. Search words can be edited there; scene 2D/3D
  stays in "Look and sound". "Approve this plan" is stored as a fingerprint in `plan_approval.json`; changing keywords, scenes,
  charts or settings asks again. The run buttons (except Voiceover) wait for approval in the app; the CLI is not gated.
- Tests: `tests/test_plan_preview.py`. Not tested: the Streamlit box in a browser.
## 2026-11-01 Fix: irrelevant stock footage and clipped big numbers
- Cause: stock video was taken from the first search hit with no relevance check (PS4 for "Nvidia", lavender for "survived"; photos were tag-filtered, videos were not).
  Number cards printed units like "trillion US$" as "5.03 trillion US" at a fixed 180 pt, so the figure ran off the frame.
- Fix: `footage.is_relevant` (Pixabay tags / Pexels slug must contain a keyword word), applied in both providers; irrelevant clips are skipped so
  the segment falls back to its chart or card. `charts.fmt` turns "trillion US$/USD/dollars" into "$5.03 trillion"; number cards auto-size.
- Found while diagnosing: the owner's Downloads copy is older than PR #24 (no render_report.py / chart_anim.py), so animated charts and the render report were absent.
  Owner must: `git pull origin main` or re-download, then rebuild (non-draft).
- Also: in `mixed`/`3d` style, pie charts now become 3D charts too (`scenes.chart_items`), so scripts with few explicit scenes are still mostly 3D. Flow and number charts stay 2D.

## Decision: sources in the description, not on screen
Charts, scene cards and 3D scenes no longer draw "Source: ..." footers. Sources are still required and validated
in `script.json`, and the generated YouTube description lists every source under "Sources" (`build_description`).

## 2026-11-01 In-app fix buttons on errors
- `studio/web/remedies.py` (pure, tested) classifies an error message into a plain title plus fix actions; `studio/web/remedy_ui.py`
  `error_panel` renders it with buttons. Used by `show()` in app.py (all Make-video runs), the page-level error catch, the wizard
  critique/quality boxes and pasted-answer failures.
- Errors with buttons: database locked (Release lock and retry), key rejected 401/403 (Test my keys, Open Setup, Retry), out of memory
  (Retry as quick draft), missing ffmpeg/Blender (Open Setup, check again), Google sign-in missing (Open Setup), network (Retry),
  failed step / unknown (Retry, Reset this step and run again, report to send for help with secrets masked).
  Invalid pasted answers keep their existing plain list + copy-able fix request.
- Decision: "release lock" flushes the SQLite log and checks a write works; it never breaks a lock held by a running step, it says to wait.
- Not tested: the Streamlit buttons in a browser. Layered on main so it can merge with the database-lock thread's change.

## Database lock hardening (2026-11-01)
- SQLite now opens in WAL mode with a 30 s busy timeout (`studio/db.py`).
- Pictures step collects assets in memory and writes them in one short transaction (no write lock during downloads/Blender).
- `Ctx.close()`; the web app closes every context at the end of each rerun and rolls back sessions after failed steps.
- "database is locked" gets a plain message (app and CLI subprocess output), plus tools to find/stop other Studio processes and clear stale journal files (`studio/util/dblock.py`, needs `psutil`: run `pip install -r requirements.txt`).


## Slow 3D pictures step (2026-11-01)
- Cause found on the owner's PC: video 3 was in `3d`/`mixed` style, so all 13 bar/pie charts became Blender scenes. Eevee on that PC
  needs ~2.5 s per frame; a 20 s scene is 300 frames (~12 min), so the step needed ~2.5 h with no progress shown. It was working, not hung.
- Fix (all videos): per-scene progress and time left (`projects/<id>/progress.json`, shown in the app and CLI), per-scene limit
  `SCENE_3D_TIMEOUT` (default 600 s) and total 3D budget `SCENE_3D_TOTAL` (default 3600 s). Blender speed is measured; a scene that would
  overrun is stopped early, re-tried shorter (min 6 s, the build loops the clip) or drawn in 2D. Finished identical scenes are reused on re-run
  (resume). Cancel: `python -m studio.cli cancel <id>` or the app's Cancel button; the rest of the scenes are drawn in 2D.
- Code: `studio/scenes/budget.py`, `studio/util/progress.py`, `provider.render_frames` (polling, timeout, kill), `scenes/stage.py`, `visuals.py`.
- Tests: `tests/test_render_budget.py` (Blender replaced by tiny scripts). Not tested: the Streamlit buttons in a browser, real Blender.
- Live progress panel (all long steps): voice, pictures, edit and thumbnails write `projects/<id>/progress.json` via `studio/util/progress.py`
  (`tracking`/`Run`). The app shows a checklist (done / running now / waiting), items done and to go, percent, time left and a Cancel
  button, refreshing every 3 s (`st.fragment`); `web.service.panel_model` builds it (tested). Works for every channel.

## Kids reference cast (2026-11-02)
- Five original recurring characters: Benny Bear, Pip the Duckling, Mango Monkey, Dotty Ladybug, Tilly Turtle (`studio/kids/roster/*.json`,
  hand-made primitive 3D models in `studio/blender/rhyme_cast.py`; stills in project files `youtube-studio/kids-cast/`).
- Easy to add more: drop `assets/kids/roster/<id>.json` (id, name, species, personality, main, accent, optional role/catchphrase/look/rhymes).
  Without a hand-made model the 3D renderer draws a generic round character in your colours and 2D draws a round face, so it works at once.
- Per channel: profile field `kids_cast` (list of ids; empty = whole roster). `kids script` puts the channel's cast and personalities in the prompt and
  accepts roster ids in `visual.characters`. `kids cast` lists them.
- Limits: simple shapes, no skeleton or lip-sync; they bounce, sway, pop in. Tested: unit tests (APIs mocked) and a real Blender (Cycles CPU) smoke render;
  Eevee on a PC GPU not tested here. The finance thread's character system was not on main, so this extends the existing per-channel profile instead.
- No web-app picker yet; set `kids_cast` via the channel profile (CLI/JSON).

## Host character 3D scenes (2026-11-01)
- New scene kind `host` (`studio/scenes/host.py`, `build_host`/`scene_host` in `studio/blender/scene_script.py`): the
  channel mascot acts per beat (9 actions, 5 sets, 7 generic props), camera cuts, mouth follows the narration audio
  (`host.envelope`, ffmpeg RMS). `scenes.plan_for` adds host scenes automatically in 3d/mixed style when the channel has
  a mascot; `host_scenes: off` in the channel profile disables it.
- Mascot kinds now: coin, owl, robot, piggy, bull, analyst (a stylised person; skin, hair, hair_style fields).
- Decisions: the mouth is loudness-driven (no phoneme lip-sync); no real logos (generic labelled blocks); 2D fallback
  shows the mascot picture. Owner must choose the default character per channel (`channels identity --file`).
- Tests: `tests/test_host.py`; the bpy smoke test runs only where `pip install bpy` is available.

## 2026-11-02: story quality and retention upgrade (phases 1-6)
- Status: done. Details, flags and decisions: `docs/CHANGELOG.md`.
- New: `studio/story/` (profile, facts, loops, hooks, ledger, engine, narration, mood, safety, titles, feedback loop),
  `studio/health.py` (issue log + fix buttons), TTS fallback chain, prompt packs under `studio/prompts/<pack>/`.
- Owner must: `pip install -r requirements.txt` (pydantic, faster-whisper, requests now required). Optional extras:
  `requirements-optional.txt`. First real video: `python -m studio.cli script <idea_id> --auto`, answer each prompt file
  (story_plan, script, story_review), re-run the same command, then `voice`, `visuals`, `build`, `gate`.
- Tests: `tests/test_story_units.py`, `tests/test_story_engine.py` (fake LLM in `tests/fake_llm.py`), opt-in `tests/test_dry_run.py`.

## 2026-11-02: history channel profile from reference videos
Status: done (profile, prompts, cast module, tests). Not done: a 2D history scene renderer that draws the cast
(see docs/history-cast-system.md). Decisions: history pack changed from dread/second-person to animated storytelling
(tone `blend`); loop distance left at 30-180 s; no sponsor slots; cast names are placeholders for the owner to rename.
Owner must configure: nothing; optionally set `story.tone` (`blend`, `comedic`, `dramatic`) on the history channel.
## Kids reference cast (2026-11-02)
- Five original recurring characters: Benny Bear, Pip the Duckling, Mango Monkey, Dotty Ladybug, Tilly Turtle (`studio/kids/roster/*.json`,
  hand-made primitive 3D models in `studio/blender/rhyme_cast.py`; stills in project files `youtube-studio/kids-cast/`).
- Easy to add more: drop `assets/kids/roster/<id>.json` (id, name, species, personality, main, accent, optional role/catchphrase/look/rhymes).
  Without a hand-made model the 3D renderer draws a generic round character in your colours and 2D draws a round face, so it works at once.
- Per channel: profile field `kids_cast` (list of ids; empty = whole roster). `kids script` puts the channel's cast and personalities in the prompt and
  accepts roster ids in `visual.characters`. `kids cast` lists them.
- Limits: simple shapes, no skeleton or lip-sync; they bounce, sway, pop in. Tested: unit tests (APIs mocked) and a real Blender (Cycles CPU) smoke render;
  Eevee on a PC GPU not tested here. The finance thread's character system was not on main, so this extends the existing per-channel profile instead.
- No web-app picker yet; set `kids_cast` via the channel profile (CLI/JSON).


## 2026-11-02: end-to-end 60 s test (history + kids) and what it fixed
Full run of both channel types to a finished 60 s video (stopped before review and publish; typed-yes gates untouched).
Report, videos and thumbnails: project files `youtube-studio/e2e-test/`. Measured here (4 CPU, no GPU): history 67.5 s video
made in about 2.3 min of machine time (voice 31 s, pictures 55 s, build 47 s, thumbnails 1.5 s); kids 56 s video in 49 s.

**Added**
- `studio/history/render.py`: the history cast scene renderer (lectern, skit with speech bubbles, map, diagram, calendar,
  easel, archive, silhouette, title). Mouths follow the narration loudness, characters blink. `visuals` draws one clip per
  segment that has a string `scene` when the `cast_scenes` flag is on; `build` shows it as one shot. `scene_data` holds
  map points, diagram steps, calendar days, titles. `studio/history/thumb.py`: cast thumbnails for history.
- `short60` story preset (`channels edit --story '{"preset": "short60"}'`): a native ~60 s video (5-10 beats of 4-20 s,
  2 open loops, shorter hook). Outline checks, prompts, QA and the quality gate read it; other channels are unchanged.
- `KokoroOnnxTTS`: offline neural voice (`pip install kokoro-onnx soundfile` + the two model files from the kokoro-onnx
  GitHub release into `assets/models/kokoro/`). Tried after `kokoro` and before edge-tts (`TTS_ORDER`), `KOKORO_VOICE`, `KOKORO_SPEED`.
- Kids: real animated 2D art (blink, mouth) for the 5 roster characters, a `puddle` object, loudness normalised to -16 LUFS,
  thumbnail uses the sprites and fits long titles.
- History descriptions use a neutral source line instead of the finance disclaimer; no business tags on non-business channels.

**Fixed (found by the test)**: `scene` as a string (cast scene) crashed the older 2D/3D scene code; QA and gate warned wrongly
for short videos (length, loops from `plants_loop`, repeated pictures for drawn scenes, hook question in sentence 3, CTA wording).

**Decisions**: native 60 s videos get their own preset instead of loosening the long-video rules; a title must match the hook
(the gate caught a title about elephants on a script that never mentions them). Cast art is still code-drawn placeholder.

**Not done / owner decisions**: stock footage (no key, network blocked here), Whisper word alignment (model host blocked),
edge-tts not testable here, per-character voices, real 3D for kids (6.3 s per frame on this CPU with Cycles: use a GPU PC),
sung vocals (OpenUtau), `gate` for kids (needs a DB video), `kids` has no research or title/SEO step.


## 2026-11-02: YouTube sign-in kept asking again and again
Causes found: (1) the CLI used the *current folder* as the studio folder while the app used its own folder, so
`token.json`/`client_secret.json` were "missing" depending on where a command ran; now both default to the repo folder
(`STUDIO_HOME` still overrides). (2) any refresh error deleted the token (even offline); now only a dead grant triggers
a new sign-in and the old file is replaced only after the new one works. (3) each channel has its own token slot
(`tokens/<channel>.json`), so a login made under another channel looks "missing" (`youtube-status --fix` adopts the old
shared `token.json`). (4) Google Testing-mode refresh tokens expire after 7 days: set the OAuth consent screen to
"In production" (or accept re-signing weekly). Sign-in now asks for `prompt=consent` so a refresh token is always issued.
New: `python -m studio.cli youtube-status [--check] [--fix]` (per channel connected/expired/missing, no secrets),
Setup-page status with a Fix button, and an Issues-panel fix `youtube_signin`.

## On-demand photo scenes (2026-11-02)
Videos keep the cast/drawn scenes from the 60 s test. A real photo appears only where the script asks: a segment may carry `photo` {subject, caption, layout: full|inset}. The `visuals` stage then searches Pixabay (then Commons) for the subject through the normal image search (relevance, near-duplicate check, footage reuse ledger, licence stored as an `image` asset) and renders a photo scene (`studio/scenes/photo.py`: full frame or framed inset with a caption plate, slow push-in). If the key is rejected, offline, or nothing fits, the segment keeps its drawn/cast scene and the build goes on. Script validation: max 3 per video, none in the hook, never back to back. The history, kids and general script prompts tell the writer to use it rarely (`studio/story/photo.py`). No photo backdrops anywhere. Owner: PIXABAY_API_KEY in .env (already set).

## 2026-11-02: weekly planner for three channels (finance, history, kids), 4 videos per week
Status: done. New `week` command (`studio/growth/weekly_plan.py`), profile fields `publish_days` and `publish_time`
(`channels add/edit --publish-days 1,3 --publish-time 16:00`), tests in `tests/test_weekly_plan.py`.
Decisions: "4 per week" is read as 4 total: finance 2 (Tue, Thu 16:00), history 1 (Sun 15:00), kids 1 (Sat 09:00); times are
the owner's local time (`publish --at` converts to UTC). The planner only suggests `publish <id> --at ...`; it never uploads,
and the private-by-default upload and typed-yes gates are untouched. Budget uses measured renders (~2.2 min machine time per
finished minute, from e2e-test/quality-report.md) plus estimated owner minutes and Claude handoff prompts per video.


## 2026-11-02 Prompt leak fixes (history/kids)
- Type-specific style guides (`studio/story/style.py`); SPEC section 9 only feeds the finance pack and has no placeholders. Prompts fail loudly on `[HEX CODES]`-style leftovers.
- Brief is type-specific (no 'charts and diagrams' or posts count for history/kids); `visual_keywords` are scene terms for cartoon packs; chapter-length text aligned with 8-30 s plan beats.
- Plan validator: hook numbers must be backed by beat 1 facts; unsourced superlatives rejected; prompt asks for causal/chronological beat order.


## 2026-11-02 Script screen as one path + prompt audit
- `2. Script` and the wizard's Script step share `studio/web/script_ui.py`: progress bar (Plan story, Write script, Review), one instruction, a Copy button (request collapsed), one paste box, one Apply button, auto-advance, then one "Continue to voice" button. The plan always comes first, so a script is never requested without facts and open loops. Nothing was removed: the extra outline, the older scored review, writing a script without a plan, file upload, "run next step" and reading the script live under one "Advanced" expander. Logic in `wizard_service.script_flow`.
- Prompt audit (finance, history, kids, rendered end to end): kids plan no longer asks for filings, "billion USD" or two loops in 60 s and facts are optional; history plan asks for museum/archive sources; example hook types match each channel's allowed formulas; cold open is 15 s everywhere (was 20 in the history beat sheet); "12-8 words" typo and "Child safety: Child safety:" duplicate fixed; "chart" wording no longer forced on kids.


## 2026-11-03 Voices page (hear and pick voices in the app)
Status: done. New sidebar page `🎙️ Voices` (`studio/web/voices_ui.py`, logic in `voices_service.py`, tests in `tests/test_voices.py`).
Narration: Hear it (edge-tts sample) and Use this voice, saved to `.env` (TTS_VOICE) and the active channel so the pipeline uses it.
Singing: lists only vetted voicebanks (PR 54 list) with licence, monetisation status, credit and warnings; AyaLuna shows a red
AI-content warning and needs a ticked confirmation. Selection saves `SING_VOICEBANK` (only vetted keys accepted by `save_env`).
Decisions: OpenUtau has no CLI renderer, so a voicebank "preview" is a clip exported from OpenUtau and uploaded to
`voicebank_previews/<key>.wav`; installed state is detected from OpenUtau's Singers folders; `C:\Tools\OpenUtau` is searched by default. No GPU needed.

## 2026-11-02 Script paste tolerance
- Pasting Claude's script reply no longer fails on near-misses. Auto-fixed (and noted): hook_type spelling/missing (set to the plan's), est_seconds far from the word count, extra or missing-pick titles, thumbnail texts over 3 / over 5 words, beat names.
- Titles: 10-15 accepted (was exactly 15).
- Taste rules (total length, sentence length/rhythm, reading grade, words vs seconds) are warnings now (`checks.style_notes`); the quality gate still flags them. Banned phrases, sources, facts and loop rules still block.
- Sources are optional for every channel type (decision, 2026-11-02): no script/outline/chart/scene/fact check blocks on missing sources any more, charts draw no footnote without one, and the prompts say sources are optional ("never invent a source"). A source given with a bad link or unknown id is no longer an error. Facts that have a `source_url` are still verified; unsourced facts are not.

- Failed steps show a plain-language message (what happened, what happens next) with the raw error under a collapsed "Technical details" expander, plus a primary "Fix this" button (2026-11-04). Known logged errors run their existing in-app fix then retry; unknown errors save a masked report to `logs/error_reports/`, show it with a copy button, and retry. Nothing for the owner to configure.
## 2026-11-03: scripts no longer need facts or sources
- Decision: a pasted script is never blocked by fact ids, figures-in-facts, chart-vs-fact, sources, or title count (fewer than 15 is a warning). Script prompts no longer ask for `sources`, `source_ids` or `fact_ids`; old saved scripts that still carry them load fine. Step 0 facts are only used by the story plan, not the script check.

## Optional real character models (2026-11-03)
- Mascot fields `model` (.glb/.gltf in `assets/characters/`), `model_scale`, `clips`. `scene_script._build_model` imports
  it, sizes it to 2 units, loops the clip chosen by `host.CLIP_WORDS` (or the channel's `clips` override) with an NLA
  strip. Missing or unreadable model: one note and the built-in shapes. No GPU needed.
- Decision: no mouth flaps for imported models (they have no mouth shapes); gestures come from the clip.
- Not verified: a real Kenney pack (kenney.nl is blocked from the build sandbox). Tested with a generated .glb.
  Owner: download the Kenney "Animated Characters" CC0 pack, copy a .glb into `assets/characters/`, set `model`.

## 2026-11-03: history videos match the reference format (PR 1 of the series)
- Cause of the "chart slides, stock stills, blank circles" render: a pasted script has no `scene` keys, so `visuals`
  fell back to stock, alternating photos, text cards and charts; fonts were Linux-only paths (tiny bitmap text on
  Windows) and characters became blank circles when cairosvg/cairo was missing.
- Now: on a cast channel (history) a script without scene types prints one line, `No scenes assigned for this script.`,
  and Claude assigns scene, cast, speech and map/diagram data once (`studio/history/scene_plan.py`, prompt task
  `scenes`, saved into script.json). If the provider fails, `studio/history/autoscene.py` word rules fill in.
  Issues panel offers "Assign scenes with Claude". Stock, photos and 3D chart scenes are never used on cast
  channels; a chart only appears on an explicit `easel` scene; a photo only where the segment has a `photo` request.
- Fonts come from matplotlib's bundled DejaVu (fails loudly, never Pillow's bitmap font); `render.pil_character`
  draws the cast with Pillow when cairo is missing.
- Next (PR 2): richer skits, terrain maps, more backdrops, internal cuts, true 1080p; (PR 3): per-character voices,
  speech-only captions, end card. Gap list: `youtube-studio/audit/reference-gap-list.md`.
- Look (same branch): five new backdrops (snow, field, market, plain, sea) picked from the skit's words; crowds of
  extras on army/crowd scenes; wide <-> close-up cuts every 4.5 s on skits; history no longer burns word captions
  (`burn_captions` flag, `captions.srt` still written). Sample: `youtube-studio/e2e-test/history-v2-sample-hannibal.mp4`.
- Character voices: skit speech lines are spoken in each character's own voice (`history/speech_audio.py`, synthesised
  in `visuals`, mixed into the narration in `build` with the narrator ducked); mouths follow that audio.
- Cast scenes are resampled once to the video size and frame rate (1080p/30 by default; draft 720p/24).
- Maps: textured satellite-style terrain, tinted territories with white borders, a marching army and a troop
  counter (`scene_data.troops`). Still a western-Mediterranean schematic only.
- Still open: a title card at ~40 s, a Part 2 end card scene, maps outside the western Mediterranean, static long
  lectern shots, richer art/props/gags, Whisper-synced captions for non-cast channels.

## Story-based costumes (2026-11-03)
- `studio/history/wardrobe.py`: 10 era outfits (roman, greek, viking, medieval, desert, egyptian, samurai, renaissance, sail, modern). Same face, body shape, badge letter, colour and voice; only headwear, garment, cape, collar and (non-signature) prop change. Code-drawn SVG, no GPU, no extra files.
- Choose with `era` on the script (top level, or per segment when the story jumps period). Missing `era` is guessed from the title; no match keeps the default outfit, so old scripts render as before.
- Planner/script prompt lists the eras; `scene_problems` rejects unknown eras. Thumbnails use the same era.
- Preview: `python -m studio.cli wardrobe <character> --out sheet.png`.
- Decision: kids cast not included in this change (separate 2D/3D sprite pipeline); named historical figures keep their own headwear/prop.

## 2026-11-03 Narration styles (comic storyteller for history)
- Compared the new history sample with transcripts of the three references (first 3 min each): the references run 2.5-3.2 words/s with jokes and character lines every 5-15 s; our sample ran 2.1 words/s with 4 lines in 58 s and one flat narrator.
- New `studio/story/narration_styles.py`: 7 selectable styles (comic_storyteller, calm_explainer, warm_singsong, dramatic_documentary, hushed_suspense, high_energy_hype, motivational_coach). Each has script rules, Kokoro narrator voice and speed, per-emotion prosody and pace. Channel field `narration` (Channels page picker, `channels add/edit --narration`); blank = history comic, business/general calm, kids sing-song. `{narration_block}` is in every script prompt; the history prompt now asks for skits with 3-6 in-character lines. `get_tts` uses the style's Kokoro voice unless `KOKORO_VOICE` is set.
- Decisions: history `tone` default is `comedic`; cast speech limit raised to 6 lines of 12 words so skits can carry banter; history pace 2.8 words/s. Per-character voices stay in `providers/voices.py` (renderer thread).
- Guide per niche: `docs/narration-and-presentation-guide.md`. Audio comparison: project files `youtube-studio/narration/`.

## 2026-11-04 Script screen stuck on "Nothing to answer"
- Cause: `read_prompt` (PR #61) deleted any saved prompt that matched the word "source" anywhere, including data embedded in the prompt (an older outline with source or fact-id fields). The step then wrote a fresh prompt and the next read deleted it again, so the main panel was empty while the real request sat in Advanced.
- Fix: the old-prompt check matches only old field names; a prompt just written is never dropped (`fresh=True`); an empty panel now shows a "Write the request for Claude" button instead of "Nothing to answer". Removed the "Pending: ... answer file" caption. The wizard forgets the selected video when the channel changes.

## 2026-11-04 Characters follow the script, not the fixed cast
- Cause: scripts that already carry scenes (project 8) never ran the scene-planning step, so `script.json` had no `characters`. Names such as "Mir Jafar" or "Ramesh" were then drawn from the fixed cast's headwear and props, and the recurring ids (`coin`, `dusty`...) always won over the script.
- Fix: `visuals` asks Claude once (`characters` prompt) to describe every on-screen name the script has not described; `Cast.described` matches short or long names ("mapmaker" for "Mapmaker Odo"), lets a script description win over a recurring id, and draws an undescribed unknown name with `figures.draw` from its own words. Only Quill (host) always stays the recurring cast.
- Not done: a script-chosen 3D style. Blender path only knows kids cast and chart scenes; it would need a style field in the script and a Blender builder for `figures` specs.
- Also: the rule-based scene fallback (`autoscene._pick_cast`) no longer picks recurring cast ids by keyword; it casts the people the script names, else the host. The scene prompt tells Claude to use only `quill` from the recurring cast.

## 2026-11-04 Charts and stills are rare, everything moves
- `studio/quality/visual_mix.py`: at most 3 charts per video, never within 3 segments of each other (extras dropped, noted in the log); pie charts are drawn as bar charts so they animate. Still stock photos are a fallback only (clips first, at most 2 per video). With `cast_scenes` on, a segment with no scene and no chart gets the default animated `lectern` cast scene.
- Removed the "no chart for 90 s" warnings (script pacing, `chart_gaps`) and the "chart every 60-90 s" prompt rule; the script prompt now asks for charts only when a number needs to be seen.
- Not changed: `flow` charts stay static (diagram work is in another thread); script-requested photo scenes (max 3) already have a camera move.
