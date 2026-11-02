# Changelog: story quality and retention upgrade

One coherent set of changes for every channel type (finance/explainer, history, kids, general). Everything new sits
behind a per-channel-type flag (all default ON for new videos) and degrades to the older behaviour when an optional
tool is missing. The two typed `yes` gates, the final.mp4 hash check, licence tracking, private-by-default upload and
quota logging are untouched.

## Honest notes first
- **The reviewer is the same model family as the writer.** `story_review` asks the answering session to review as a
  distracted viewer plus a skeptical editor and to quote exact lines, and code checks that every quoted line really
  existed and is gone from the rewrite. That reduces self-flattery; it does not make the review independent. Treat the
  scores as advice, and use `LLM_CRITIC_PROVIDER` (below) if you ever want a different model for that one task.
- Code can check numbers, loops, sentence shape, repetition and timing. It cannot check taste. The human typed `yes` stays.
- Fact verification proves "the figure/quote is on the page the model cited", not that the page is right.

## Phase 1: integrity fixes
- `studio/llm.py`: the cache key is a hash of the prompt (`prompts/<task>.meta.json`). A changed topic, facts or rules
  archives the old answer as `<task>.stale<N>.json` (never deleted) and asks again. API providers raise a clear error on
  truncation (`max_tokens` / `length` / `MAX_TOKENS`). Every task answer is validated with a Pydantic model
  (`studio/story/models.py`) that names the exact field (`outline.beats[2].seconds: ...`).
- `discover.py`: topics are blocked by whole-phrase patterns (`BLOCKED_PATTERNS`), not single words like free/app/pay/income/game.
- Lengths, words per second, loudness, shot length and banned phrases moved to the story profile (below). The 5 vs 6 minute
  mismatch is unified (explainer 8-12 min target, warning below the profile minimum). Word counts are checked against
  `est_seconds` (+-40%) and the total against the type's range. `BANNED_PHRASES` grew from 5 to 60+ (whole-phrase match).
- `critique` apply is atomic: `script.original.json` (first draft, once) + `script.v1.json`, `v2`... and one DB transaction
  with file rollback on failure (`script.replace_package`).
- `faster-whisper`, `pydantic`, `requests` are normal requirements. Everything else is in `requirements-optional.txt`.

## Phase 2: channel profiles and prompt packs
- `studio/story/profile.py`: one profile per pack (explainer / history / kids / general) with audience, language and region
  (finance: India + US notes), beat sheet, hook formulas, length range, words per second, shot interval, sentence cap,
  reading-grade cap, voice/prosody table, music moods, banned phrases, compliance rules, ending style, loudness, flags.
  Override any key per channel: `channels edit --story '<json>'` (stored as the channel's `story` field), e.g.
  `--story '{"min_minutes": 6, "flags": {"prosody": false}}'`.
- `studio/prompts/<pack>/` has `story_plan.md`, `script.md`, `story_review.md` (plus the older `outline.md`, `critique.md`,
  `hooks.md`); the explainer pack falls back to the original files in `studio/prompts/`. Original exemplar passages are in
  `studio/prompts/exemplars/`.
- Defaults: explainer 8-12 min, shots every 4-7 s; history 8-15 min, 5-8 s; kids 3-8 min, 3-5 s, sentence cap 8 words,
  grade <= 3, no pauses before reveals, strict safety.

## Phase 3: story engine (three handoff tasks per video)
`script <idea> --auto` (and `run-all`, unless `--classic`) runs:
1. **story_plan**: facts + outline (audience question, big idea, arc, beats, loops with ids, ending) + 8 scored hooks, in ONE prompt.
   The prompt tells the answering session to use web search and to give `source_url` + `quote_snippet` per figure.
   This task is always a file handoff, even if `LLM_PROVIDER` is an API.
2. **script**: follows the plan, cites only fact ids, adds `plants_loop` / `pays_loop` and `visual_intent`.
3. **story_review**: rubric scores (+ channel criteria: history accuracy+dread, finance number accuracy+actionability,
   kids simplicity+safety), 3-5 swipe-away moments (quote + segment; code computes the timestamp), and the rewrite.
   One automatic repeat (`story_review_r2`) only if deterministic checks still fail. State: `projects/<id>/story_state.json`;
   scores and swipe points: `story_review.json` (the owner's `review.json` is not touched).

Checked in code after each task (with specific fixes printed): fact verification (fetch, numeric normalisation 1.2B vs
1,200M, quote match; verified/unverified/unfetchable; `facts <id> --accept f3` lets you vouch for a paywalled source),
numbers in narration and chart values must trace to cited fact ids (unverified only as `is_estimate` with estimate wording),
loop plant/payoff (>=2 in the first 60 s, spread, 1-3 min apart on long videos), hook best-of-8 (gate `check_hook` + model
score) with rotation (never the channel's last 3 hook types), sentence cap and rhythm variance, banned phrases, reading
grade, title promise delivered in the first two segments, visual shot rule, and a cross-video ledger
(`growth/story_ledger.json`) that feeds "differ from these" into the prompts and extends `check_originality` to opening-sentence
templates, beat sequence, chapter structure and arc (3rd repeat is critical).
Helpers: `python -m studio.cli next <video_id>` (what is pending + exact command), `facts <video_id>`, `issues`, `fix <id>`.
The old `outline`, `critique`, `script` (no `--auto`) commands work as before. Gate checks that need engine fields only
run as advisory (minor) for scripts from the classic path.
`LLM_CRITIC_PROVIDER` (default empty = file handoff): set to `anthropic|openai|gemini` (+ `LLM_API_KEY`, `LLM_MODEL`) to run
**only** story_review through an API. Never required; facts stay handoff-only.

## Resilience (added requirement)
- Every external tool has a fallback: voice Kokoro > Edge > Piper (`TTS_ORDER`; missing engines skipped; `FallbackTTS`),
  stock Pexels > Pixabay (`ChainedFootage`) > generated cards, captions voice word-timing > faster-whisper > script timing,
  loudness ffmpeg > pyloudnorm, fact pages trafilatura > built-in extractor, fuzzy match rapidfuzz > word coverage,
  readability textstat > built-in, semantic stock ranking open_clip/sentence-transformers > tag overlap, music mood bed >
  standard bed, Manim > matplotlib, AI images null by default.
- Every failure is recorded in `logs/issues.json` with a plain cause and a fix. The app shows it where the error appears
  (**Fix** button) and in the sidebar (**issue(s) to fix**); the CLI prints `fix <id>`. Fixes only change settings, clear
  caches, or `pip install` an optional package. Run `issues` / `fix <id>`.
- Efficiency: finished work is reused (voice chapter groups are cached by text+prosody+voice in `voice/groups.json`; fact pages
  cached in `facts_cache/`; prompts/answers keyed by prompt hash; stage skip/resume unchanged). Chapter groups and
  segments synthesize in parallel (4 workers). Stages that depend on earlier output stay sequential on purpose.

## Phase 4: narration and captions
- Prosody per emotion (rate/pitch/volume offsets: hook faster, reveals slower, kids more expressive), pauses before reveals
  and after loop plants (`voice.pauses`, none before reveals for kids).
- Synthesis per chapter group (same chapter + emotion) so intonation does not reset; split by edge-tts `WordBoundary` times.
  If a voice has no word times, or word counts do not line up (>8%), that group falls back to one call per segment.
  ElevenLabs gets `previous_text` / `next_text` / `stability`.
- Word times are stored per segment (`script.json` `words`) and captions use them; else faster-whisper; else script timing.
  Build writes `caption_sync.json`; the gate flags drift > 250 ms (`captions` dimension).

## Phase 5: visuals and audio
- `visual_intent` (shot_type, must_show, avoid) drives stock queries; no 3 identical shot types in a row (validator).
- Footage reuse ledger (`growth/footage_ledger.json`): assets from the last 3 videos are skipped while tries remain.
- Semantic ranking (flag `semantic_visuals`, OFF by default because it downloads a model) when sentence-transformers / open_clip exist.
- `studio/providers/ai_images.py` (null default; ComfyUI and diffusers adapters are stubs/optional), `manim_scenes.py` (detect-only stub).
- Mood-aware music: tense / neutral / resolve per chapter, crossfades, near-silence before a `pattern_break`, stinger on reveals
  (not kids). Your own files in `assets/music/<mood>/` win. Loudness default -14 LUFS / -1 dB true peak, configurable per channel.
- Safety (kids, history): keyword screen (+ Detoxify if installed) on narration, NSFW frame check only if `nudenet` is installed.
  Flags go into the gate; nothing auto-publishes.

## Phase 6: packaging and feedback
- Title ranking + `title_promise_fulfilled` check in the gate; top outlier competitor titles saved by `research` are shown to
  `story_plan` as pattern references only.
- After each analytics report `feedback learn` runs automatically (mock curves stay advisory). Per-video story metrics
  (hook_type vs 30 s retention, drop-off beat/chapter/loop, title style vs CTR) are stored in `growth/story_metrics.json`;
  top 3 / bottom 3 are fed into the next `story_plan` (silent if fewer than 3 real videos). The analytics report gains a retention heatmap.

## Flags (channel `story.flags`, default ON unless noted)
word_count_check, sentence_rules, fact_ledger (off for kids), loop_ids (off for kids), hook_rotation, repetition_ledger,
story_review, prosody, chapter_tts, caption_sync_check, visual_intent, semantic_visuals (OFF), footage_reuse_ledger,
mood_music, title_judge, feedback_loop.

## Adding a channel type
1. Add an entry to `PACKS` in `studio/story/profile.py` (copy `general`) and map the type id in `PACK_FOR_TYPE`.
2. Add the type to `studio/growth/channel_types.py` and a gate type in `studio/quality/profiles.py` (`GATE_TYPE`).
3. Optional: `studio/prompts/<pack>/` with `story_plan.md`, `script.md`, `story_review.md` (missing files fall back to explainer),
   an exemplar in `studio/prompts/exemplars/<pack>.md`, and criteria in `PACK_CRITERIA` (`studio/stages/story.py`).

## Optional dependencies (all have fallbacks)
`pip install -r requirements-optional.txt` (or one at a time): trafilatura, rapidfuzz, textstat, sentence-transformers, kokoro +
soundfile, piper-tts (+ `PIPER_MODEL`), whisperx, open-clip-torch, manim, pyloudnorm, diffusers, detoxify, nudenet.

## New keys and costs
No new key is required. `LLM_CRITIC_PROVIDER` (optional, uses your API key and bills per call), `TTS_ORDER`, `PIPER_MODEL`,
`AI_IMAGE_PROVIDER`, `COMFYUI_URL`, `COMFYUI_WORKFLOW`, `DIFFUSERS_MODEL`. Fact verification fetches public web pages
(no key, a few seconds each, cached). YouTube quota use is unchanged.

## Decisions (made without asking)
- `script` without `--auto` stays the classic single prompt (existing tests and habits); `--auto` and `run-all` use the engine.
- Story review log is `story_review.json`, not `review.json` (that file is the typed-yes gate record).
- Heavy tools are detect-and-fallback stubs: Manim templates, ComfyUI workflow, open_clip image scoring, WhisperX.
- Kids song videos (`kids script/build/sing`) keep their own pipeline; they share the banned/safety lists only.
- Tests that render full 8-15 minute videos are opt-in (`STUDIO_SLOW_TESTS=1`, about 2 minutes each).

## History channel: animated storytelling profile (2026-11-02)
- Analysis of three reference videos (structure, pacing, visuals, sound; style only): `docs/history-style-report.md`.
- `PACKS["history"]` now describes animated storytelling: cold open, rewind, 60-120 s chapters ending on a turn, an
  info beat per chapter, shots every 3-6 s, 2.6 words per second, four new hook formulas, `tone`, `cast` and
  `depiction` keys. Test expectation for history `shot_interval` is now (3, 6).
- `studio/history/cast.py`: six original recurring characters, a figure builder for historical figures (sprite
  contract of `studio/kids/sprites.py`), scene types and `scene_problems`; flag `cast_scenes` (on for history only).
- `{cast_block}` and `{tone}` placeholders in the history prompts; docs in `docs/history-cast-system.md`.
