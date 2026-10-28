# SPEC: YouTube Channel Studio

Single source of truth for what gets built. Claude Code must read this file fully before writing code, and must update it (not silently diverge) if a decision changes.

Fill every `[PLACEHOLDER]` in Section 1 before starting the build.

---

## 1. Channel brief (fill this in)

| Field | Value |
|---|---|
| Niche | Business-model and economics explainers: how companies and industries make money (e.g. hotels, cruise lines, streaming, quick-commerce). Mostly global brands, with Indian companies as a differentiator. Chosen from vidIQ outlier research on 2026-10-27. |
| Channel name | [CHANNEL NAME: still to decide] |
| Language | English |
| Target audience | [AUDIENCE: default 18-35, curious about business and money, global English speakers] |
| Video style | Faceless narrated explainer: calm voiceover, stock footage, animated charts/diagrams and text cards for unit economics, burned-in captions |
| Long-form length | 10-15 min (median of the researched outliers was about 12.5 min) |
| Shorts | Yes; 2-3 per long video |
| Upload cadence | 2 long videos + 3 Shorts per week (default; change if needed) |
| 6-month goal | 1,000 subscribers and 4,000 watch hours (default) |
| Monetization plan | AdSense (default) |

---

## 2. What we are building

A command-line studio that runs a faceless YouTube channel from topic to published video to ongoing management. One Python codebase plus a SQLite database that tracks every video through a fixed set of stages.

**Core rule: nothing is published, posted, or replied to without the owner typing an explicit confirmation.**

### 2.1 Pipeline

```
research -> approve idea -> script -> voice -> visuals -> build -> thumbnail
        -> REVIEW GATE (human) -> publish/schedule -> analytics -> next topics
```

### 2.2 Video stage lifecycle (stored in `videos.stage`)

| Stage | Meaning | Set by |
|---|---|---|
| `idea` | Topic saved, not yet approved | `research` |
| `approved` | Owner approved the topic | `approve-idea` |
| `scripted` | Titles + script + segments saved | `script` |
| `voiced` | Narration audio generated per segment | `voice` |
| `visuals_ready` | Clips/images fetched per segment | `visuals` |
| `built` | Final MP4 + captions exported | `build` |
| `thumbnailed` | Thumbnail variants generated | `thumbnail` |
| `reviewed` | Owner typed "yes" at the review gate | `review` |
| `scheduled` | Uploaded as private/scheduled | `publish` |
| `live` | Public on YouTube | `status` sync |

Rules: a stage can only advance in order; re-running a finished stage is a no-op unless `--force` is passed; `publish` refuses unless stage is `reviewed`.

---

## 3. Tech stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| CLI | Typer |
| Database | SQLite via SQLAlchemy |
| Config | python-dotenv (`.env`) |
| YouTube | google-api-python-client, google-auth-oauthlib (Data API v3 + Analytics API) |
| LLM | One wrapper module. Default `claude_code`: the CLI writes a prompt file and Claude Code writes the JSON answer (no API key). Optional API providers: anthropic, openai, gemini |
| TTS | edge-tts default; ElevenLabs optional behind the same interface |
| Captions | faster-whisper (local) -> SRT |
| Video | ffmpeg (command builders in `util/ffmpeg.py`; MoviePy not needed) |
| Footage | Pexels API (fallback: generated text/image cards) |
| Charts/diagrams | matplotlib (and Pillow) to render animated or step-by-step charts, flow diagrams, and number cards from segment data |
| Thumbnails | Pillow with a template system |
| Tests | pytest with mocked APIs |

External API details (quota costs, OAuth flow, field names) must be read from the official docs at build time, not from memory. Treat any number in this spec as approximate and verify it.

### 3.1 Folder layout

```
yt-studio/
  CLAUDE.md  SPEC.md  PROGRESS.md  README.md
  .env  .gitignore  client_secret.json  token.json   (last three never committed)
  studio/
    cli.py                 # Typer entry point
    config.py              # env loading + validation
    db.py  models.py       # SQLAlchemy
    llm.py                 # LLM wrapper
    youtube/               # auth.py, data_api.py, analytics_api.py, quota.py
    stages/                # research.py, script.py, voice.py, visuals.py,
                           # build.py, thumbnail.py, review.py, publish.py
    manage/                # analytics_report.py, ab_log.py, comments.py,
                           # calendar.py, status.py
    providers/             # tts_edge.py, tts_eleven.py, pexels.py, whisper.py, charts.py
    util/                  # ffmpeg.py, retry.py, logging.py
  assets/                  # music/, intro/, outro/, fonts/, thumb_templates/
  projects/<video_id>/     # script.md, script.json, voice/, clips/, captions.srt,
                           # final.mp4, shorts/, thumbs/, review.json
  tests/
```

---

## 4. Commands

Every command is resumable and idempotent.

### 4.1 Topics
- `research "<seed>"`: fetch search suggestions and top recent videos; compute views-per-subscriber to flag outliers from small channels; rank ideas by demand vs competition; save to `ideas`; print a ranked table.
- `approve-idea <id>`: move an idea to `approved` and create the `videos` row.

### 4.2 Scripts
- `script <idea_id>`: (with the default `claude_code` provider this writes `prompts/script.prompt.md` and stops until Claude Code writes `script.response.json`; re-run to continue) generate 15 title variants (under 70 characters, no misleading clickbait, mark a pick); generate the full script; output a segment list (narration text, visual keywords, estimated seconds); save `script.md` + `script.json`.

Script rules: a 15-second hook; a retention beat (question, reveal, example, or pattern break) every 30-45 seconds; a clear call to action; original commentary, structure, or analysis in every video.

### 4.3 Voice and visuals
- `voice <video_id>`: synthesize narration per segment; measure real durations and update segment timings.
- `visuals <video_id>`: for each segment fetch matching Pexels clips by keyword (fallback: generated cards); cache; record attribution and licence info in `assets`.
  - Segments that contain numbers (revenue splits, margins, prices, growth) must also produce a chart, diagram, or number card via `providers/charts.py`, driven by a `chart_data` field in `script.json` (type, labels, values, unit). Target at least one chart or diagram every 60-90 seconds.
  - Every number in `chart_data` must have a source URL or note in `script.json`; `review` fails if a chart has no source.

### 4.4 Build
- `build <video_id>`: stitch clips to narration timing; add background music from `assets/music` ducked under voice; burn in captions; add intro/outro; export 1080p MP4.
- `shorts <video_id>`: cut 2-3 vertical 9:16 highlight clips with captions into `projects/<id>/shorts/`.

### 4.5 Thumbnails
- `thumbnail <video_id>`: generate 3 variants (different text and layout), 1280x720, under 2 MB each, saved to `thumbs/`.

### 4.6 Review and publish
- `review <video_id>`: print a checklist (title, description, tags, chapters, thumbnail, file paths, synthetic-content flag, licence list) and require the owner to type `yes`. Writes `review.json` and advances to `reviewed`.
- `publish <video_id> --at "<datetime>"`: requires a second typed `yes`; refuses if `final.mp4` changed since review; upload as private/scheduled; set title, description, tags, chapters, thumbnail, captions, playlist; set the synthetic-media disclosure when the video contains realistic AI-generated content (`status.containsSyntheticMedia`, confirmed in the Data API revision history, 2024-10-30). Refuses without `reviewed`.

### 4.7 Channel management
- `analytics`: pull last 28 days per video (views, watch time, average view duration, CTR, impressions, retention, traffic sources); store in `metrics_daily`; write a plain-English report of best topics, title styles, lengths, upload days, drop-off points, and what to make next.
- `ab-log <video_id>`: record title/thumbnail changes with timestamps and before/after metrics.
- `comments <video_id>`: fetch recent comments and write draft replies to `comments_drafts.json` for review. Never posts. A separate `comments post <file>` command may post only after per-reply typed confirmation.
- `calendar`: 4-week content calendar from approved ideas; flag gaps against cadence.
- `status [--sync]`: one-screen table of every video and its stage; `--sync` marks published videos `live`.
- `quota`: today's usage per quota bucket.
- `demo`: dry run that builds a playable MP4 and thumbnails from the bundled sample script with no API keys (cannot be published).
- `run-all "<seed>"`: chain research through thumbnail for the top approved idea (approving the top-ranked new idea if none is in progress), then stop at the review gate.

---

## 5. Database

| Table | Key columns |
|---|---|
| `ideas` | id, seed, topic, demand_score, competition_score, outlier_score, status, created_at |
| `videos` | id, idea_id, stage, youtube_video_id, publish_at, created_at, updated_at |
| `titles` | id, video_id, text, style, length, is_pick, is_live |
| `scripts` | id, video_id, markdown_path, json_path, word_count, version |
| `segments` | id, video_id, position, narration, visual_keywords, est_seconds, real_seconds, audio_path, clip_path |
| `assets` | id, video_id, kind, path, source, licence, attribution_url |
| `metrics_daily` | id, youtube_video_id, date, views, watch_minutes, avg_view_duration, impressions, ctr, traffic_json |
| `ab_tests` | id, video_id, field (title/thumbnail), old_value, new_value, changed_at, metrics_before_json, metrics_after_json |
| `comments_drafts` | id, video_id, youtube_comment_id, comment_text, draft_reply, status |
| `quota_log` | id, date, endpoint, units, ok |

Use migrations or `create_all` with a schema version row; never drop tables silently.

---

## 6. Configuration (`.env`)

| Variable | Required | Purpose |
|---|---|---|
| `LLM_PROVIDER` | no | `claude_code` (default, no key), or `anthropic` / `openai` / `gemini` |
| `LLM_API_KEY` | only for API providers | LLM key |
| `LLM_MODEL` | only for API providers | Model name |
| `CHANNEL_ID` | yes | Target channel |
| `GOOGLE_CLIENT_SECRET_PATH` | yes | Path to `client_secret.json` |
| `PEXELS_API_KEY` | yes (for visuals) | Stock footage |
| `ELEVENLABS_API_KEY` | no | Optional TTS |
| `TTS_PROVIDER` | no | `edge` (default), `eleven`, or `silent` (dry runs only) |
| `TTS_VOICE` | no | Voice name |
| `DAILY_QUOTA_LIMIT` | no | Default 10000 |
| `QUOTA_SAFETY_MARGIN` | no | Default 500 units reserved |

Missing required values must produce a clear message naming the variable and the command that needs it.

---

## 7. Quota budget

Verified against the official quota calculator (developers.google.com/youtube/v3/determine_quota_cost) on 2026-10-28. Since late 2025, `search.list` and `videos.insert` have **their own daily buckets of 100 calls each**; every other endpoint draws from the shared daily budget (default 10,000 units).

| Call | Cost | Bucket |
|---|---|---|
| `videos.insert` | 1 call | upload (100/day) |
| `search.list` | 1 call | search (100/day) |
| `captions.insert` | 400 units | shared |
| `thumbnails.set` | 50 units | shared |
| `playlistItems.insert` | 50 units | shared |
| `videos.update`, `comments.insert` | 50 units | shared |
| `videos.list`, `channels.list`, `commentThreads.list` | 1 unit | shared |

Worked example for one fully-published video:
1. Shared units: captions 400 + thumbnail 50 + playlist 50 + status check 1 = 501 units; plus 1 upload call
2. (10,000 - 500 margin) / 501 = 18.9, so about 18 full videos per day; uploads are capped at 100/day
3. Quota is no longer the bottleneck for this channel's cadence

`quota.py` logs every call to `quota_log` (failed calls count too), tracks all three buckets, shows remaining units (`quota` command), and aborts a command before it would exceed `DAILY_QUOTA_LIMIT - QUOTA_SAFETY_MARGIN` (or a bucket's 100 calls). `publish` checks its whole plan before uploading. The YouTube Analytics API has its own quota; its calls are logged but not charged to the Data API budget.

**Important:** YouTube restricts videos uploaded through unaudited API projects (created after 2020-07-28) to private. `publish` uploads as private (with `publishAt` when `--at` is given); if the schedule comes back missing it reports the audit requirement instead of failing silently. The owner must either pass the audit or publish manually from YouTube Studio.

---

## 8. Policy rules (non-negotiable)

1. **Human approval:** no publish, no comment or reply posting, no metadata change on a live video without a typed `yes`.
2. **Originality:** every script must add commentary, structure, or analysis. Never copy other creators' videos, scripts, or thumbnails. Competitor research is for finding topics, not for reuse.
3. **Inauthentic content:** do not produce mass-repetitive videos from one template with swapped words. Vary structure and add real value per video.
4. **Synthetic media:** set the disclosure when the video contains realistic AI-generated people, places, or events. Review step must show this flag.
5. **Licensing:** only use footage, music, and fonts with licences that allow YouTube use and monetization; store licence info per asset; fail `review` if an asset has an unknown licence.
6. **Factual claims:** scripts on finance, health, legal, or news topics must list sources in `script.json` and avoid advice phrased as guarantees. Add a disclaimer line where relevant.
7. **Secrets:** never log or commit API keys, tokens, or `client_secret.json`.

---

## 9. Style guide (fill in or keep defaults)

- **Tone:** clear, curious, analytical, no hype; plain English; second person sparingly. Explain like a smart friend, not a lecturer.
- **Banned phrases:** "you won't believe", "shocking", "guaranteed", "secret they don't want you to know", "get rich", [add more]
- **Titles:** under 70 characters; one clear promise; no all-caps shouting; no claims the video can't back up. Preferred patterns: "How X Makes Money", "The Economics of X", "How X Really Works", with a concrete number or price where the video supports it (e.g. "$300 Cabin vs $50,000 Suite", "a ₹518 Order").
- **Video structure:** (1) hook with a surprising number or question, (2) the product or customer, (3) where the money comes in, (4) where the costs go, (5) the clever trick or weak point, (6) what it means / takeaway, (7) call to action. Every video walks the money flow end to end.
- **Visual rule:** show the money. Use a chart, diagram, or number card for every major figure; stock footage only illustrates the setting.
- **Accuracy:** every figure needs a named source (annual report, filing, reputable article) in `script.json`. Label estimates as estimates. No investment advice; add a one-line "educational, not financial advice" disclaimer in the description.
- **Hook:** first 15 seconds state the problem and the payoff; no long intros or "before we start, subscribe".
- **Pacing:** visual change at least every 4-6 seconds; one retention beat every 30-45 seconds.
- **Thumbnails:** 3-5 words max; one focal element; high contrast; brand colors [HEX CODES]; font [FONT NAME].
- **Intro/outro:** under 5 seconds each.
- **Music mood:** [e.g. calm, light, instrumental], ducked at least 15 dB under voice.
- **Description template:** 2-line summary, chapters, sources, disclaimer, links.

---

## 10. Error handling

| Situation | Required behavior |
|---|---|
| Quota exhausted or near limit | Stop before the call, show units left, say when it resets (midnight Pacific time) |
| Expired/revoked token | Delete cached token, rerun auth flow, clear message |
| ffmpeg missing | Name the install command for the platform |
| Missing API key | Name the variable and the command that needs it |
| Network/API 5xx | Retry with exponential backoff, max 5 attempts, then fail with context |
| Pexels returns no clips | Fall back to generated card; log it |
| Upload forced private | Report it and point to the audit requirement |
| Re-run of finished stage | Skip with a "already done" message |

---

## 11. Testing (pytest, all APIs mocked)

Required tests:
- Outlier scoring (views-per-subscriber, small-channel flagging)
- Quota tracker (logging, limit enforcement, margin)
- Title validation (length, banned phrases)
- Segment timing (real durations replace estimates; total length check)
- Publish gate (refuses without `reviewed`; refuses without typed `yes`)
- Stage ordering (cannot skip stages)
- Idempotency (second run of a stage changes nothing)
- Config validation (missing keys give the right message)

Definition of done for the build: all tests pass, `status` and `run-all` work end to end against mocked APIs, and one dry-run build produces a playable MP4 from sample inputs.

---

## 12. Out of scope (for now)

- Auto-posting comments or replies
- Auto-publishing without review
- AI-generated thumbnail images or video (phase two)
- Multi-channel support
- Web dashboard
- Copying, re-uploading, or transcribing other creators' videos for reuse

---

## 13. Phase two ideas (do not build yet)

- AI-generated thumbnail backgrounds
- Multi-language dubbing
- Web dashboard over the same database
- Scheduled weekly jobs for `research` and `analytics`
