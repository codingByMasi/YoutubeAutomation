# YouTube Channel Studio

A command-line studio that runs a faceless YouTube channel from topic research to published video to ongoing management, with a human approval gate before anything goes public.

```
research -> approve -> script -> voice -> visuals -> build -> thumbnail
        -> review (you type "yes") -> publish -> analytics -> next topics
```

Nothing is published, posted, or replied to without your typed confirmation.

Full design: see `SPEC.md`. Build progress: see `PROGRESS.md`.

---

## Web app (no code needed)

Everything above also runs from a browser app built with Streamlit: pick a topic, copy the script request into
Claude and paste the answer back, click once to make the video, then watch and download it.

**Run on Windows** (PowerShell in this folder; needs Python 3.11+ and ffmpeg on PATH):

```
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Or double-click `run_app.bat`. It opens http://localhost:8501. On macOS/Linux: `streamlit run app.py`.

**Deploy on Streamlit Community Cloud** (free):

1. Push this repo to GitHub, then go to share.streamlit.io, click **Create app**, pick the repo and branch,
   and set **Main file path** to `app.py`. `requirements.txt` and `packages.txt` (installs ffmpeg) are picked up.
2. Under **Advanced settings -> Secrets** paste the lines from `.streamlit/secrets.toml.example`. Set `APP_PASSWORD`
   so strangers cannot use your keys. Add `PIXABAY_API_KEY` for stock footage and photos (optional; without keys the
   studio uses Wikimedia Commons photos and generated cards).
3. Deploy. Free hosting has about 1 GB RAM and temporary disk, so **download each video from step 4 before the app
   sleeps**. Long videos build slowly there; for long videos run the app locally.

**What works where**

| Feature | Local | Streamlit Cloud |
|---|---|---|
| Topic suggestions | yes, plus outlier signals if signed in to Google | suggestions only |
| Script via paste-in | yes | yes |
| Voice, visuals, edit, thumbnails, Shorts | yes | yes (slower, temporary storage) |
| Watch and download | yes | yes |
| Review gate and YouTube upload | yes (needs `client_secret.json`) | no: download and upload by hand |

**Why not Vercel?** Vercel runs short serverless functions with a hard time limit, a small bundle size and no
persistent disk. Video work (ffmpeg, TTS, many downloads, minutes to hours of rendering) does not fit, and Streamlit
cannot run there. Streamlit Community Cloud runs a normal Python process with ffmpeg, so it is the supported choice.
If you outgrow it, the same `app.py` runs on any small VM or container host (Render, Fly.io, Railway).

The typed-yes rule still holds: approving and uploading each need you to type `yes` in the page.

**Speed.** Tick **Fast draft** on the "Make the video" page for a 720p, 24 fps, fastest-encode build (several times
faster). For the final cut, untick it and redo "Edit the video". Environment knobs (secrets or `.env`):
`STUDIO_WORKERS` (parallel shot renders, default 2), `STUDIO_FFMPEG_THREADS` (x264 threads, default 2; lower on
1 GB hosts), `STUDIO_DRAFT=1` (draft for every run). Skip Shorts unless you need them.

---

## Kids mode (nursery rhymes and learning songs)

A separate mode for short, original sing-along videos (counting, colours, animals, bedtime). It draws simple
animated characters with Pillow, narrates with a free child-friendly edge-tts voice (`KIDS_TTS_VOICE`
overrides it) and burns in big lyric captions. It does **not** copy any existing channel and it **never
uploads**. In the web app pick **🧸 Kids mode**; on the command line:

```
python -m studio.cli kids demo                  # keyless dry run, silent narration
python -m studio.cli kids script "counting five little ducks"   # writes the prompt, exit 3
python -m studio.cli kids build  "counting five little ducks"   # projects/kids_<slug>/final.mp4
python -m studio.cli kids checklist "counting five little ducks"  # Made for Kids checklist
```

Kids videos must be marked "Made for Kids" in YouTube Studio (no comments or personalised ads, lower RPM).
Do not mass-produce near-identical videos: YouTube demonetises repetitive content.

### Growing the channel (page 5)
The **5. Grow the channel** page has tabs for: channel profile, series/playlists (each video points to the next), a
content calendar, 5 titles + 3 thumbnail concepts per video (scored by a checklist), description/tags/chapters with
sources and photo credits, a Shorts plan, a fact and source checklist (must be complete before approval on page 4),
pasting YouTube Studio numbers for next-script advice, and a Partner Program tracker with a monetization checklist.
Where Claude's writing helps, copy the shown prompt into Claude and paste the JSON answer back. No API key needed.

## 1. Requirements

- Python 3.11+
- ffmpeg installed and on PATH
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: `winget install ffmpeg` (or download from ffmpeg.org and add to PATH)
- A Google account that owns the YouTube channel
- API keys: none required. Optional free stock-footage key: Pixabay (or Pexels if you already have one). No LLM key is needed: Claude Code writes the scripts (see section 8). ElevenLabs is optional.

## 2. Install

```bash
git clone <your-repo-url> yt-studio
cd yt-studio
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Google Cloud setup (one time, done by hand)

1. Go to the Google Cloud Console and create a project.
2. Enable **YouTube Data API v3** and **YouTube Analytics API** for that project.
3. Configure the **OAuth consent screen**. While the app is in "Testing" mode, add your own Google account under **Test users**.
4. Create credentials: **OAuth client ID**, application type **Desktop app**.
5. Download the JSON and save it in the project root as `client_secret.json`.
6. Never commit this file. It is already in `.gitignore`.

First-run authorization: the first command that needs YouTube opens a browser window, asks you to sign in and grant access, and saves a `token.json`. If the token expires or is revoked, the tool deletes it and asks you to sign in again.

Note on uploads: YouTube may force videos uploaded through API projects that have not passed its compliance audit to **private**. If your uploads show up private, either apply for the audit (see the official YouTube API docs) or switch the video to public manually in YouTube Studio. The tool will tell you when this happens.

## 4. Other keys

1. **LLM provider (optional):** not needed. By default Claude Code answers prompt files. Only if you want fully hands-off runs, set `LLM_PROVIDER` to `anthropic`, `openai` or `gemini`, add `LLM_API_KEY` and `LLM_MODEL`, and `pip install` that provider's package.
2. **Stock footage (optional):** Pexels has paused new API keys, so use **Pixabay**: sign up (free) at pixabay.com, open https://pixabay.com/api/docs/ while logged in, copy your key and put it in `.env` as `PIXABAY_API_KEY=...`. Pixabay's content licence allows commercial use (including monetized YouTube) with no attribution required; the licence is still recorded per clip. With no key, `visuals` still works: it uses generated cards, charts and number cards and says so. `FOOTAGE_PROVIDER` picks the source: `auto` (default: Pexels key if set, else Pixabay key, else none), `pexels`, `pixabay` or `none`. Existing Pexels keys keep working.
   **Photos:** `visuals` also searches still images (Pixabay photos if keyed, plus Wikimedia Commons with no key) and mixes them with clips, slowly zooming each photo. `IMAGE_PROVIDER=auto|pixabay|commons|none` controls this. Commons files are used only under public domain, CC0, CC BY or CC BY-SA, and the required credits go into the video description automatically.
3. **ElevenLabs (optional):** only if you want higher-quality voices than the free edge-tts default.

## 5. Configure `.env`

Copy the example and fill it in:

```bash
cp .env.example .env
```

```
# LLM: "claude_code" (default) needs no key. Claude Code answers prompt files.
# Optional API providers: anthropic, openai, gemini (then LLM_API_KEY and LLM_MODEL are required).
LLM_PROVIDER=claude_code
LLM_API_KEY=
LLM_MODEL=

CHANNEL_ID=
GOOGLE_CLIENT_SECRET_PATH=./client_secret.json
PEXELS_API_KEY=
PIXABAY_API_KEY=
FOOTAGE_PROVIDER=auto

# TTS: edge (default, free), eleven (needs ELEVENLABS_API_KEY), silent (dry runs only)
TTS_PROVIDER=edge
TTS_VOICE=en-US-AndrewNeural
ELEVENLABS_API_KEY=

DAILY_QUOTA_LIMIT=10000
QUOTA_SAFETY_MARGIN=500
```

Find your `CHANNEL_ID` in YouTube Studio under Settings > Channel > Advanced settings.

## 6. Add your assets

Place these in `assets/`:
- `music/` background tracks (keep licence info with each file)
- `intro/` and `outro/` short clips (under 5 seconds)
- `fonts/` brand fonts
- `thumb_templates/` optional `overlay.png` (1280x720, transparent) laid over every thumbnail

Every music, intro and outro file needs a licence note next to it: `song.mp3` + `song.mp3.licence.txt` (first line, e.g. "YouTube Audio Library, monetization allowed"). `review` refuses to approve a video that uses a file with no licence note. Stock clips (Pixabay or Pexels) are recorded automatically with their licence and page URL.

Only use music, footage, and fonts whose licences allow YouTube use and monetization.

## 7. Fill in the brief

Open `SPEC.md` and complete Section 1 (channel brief) and Section 9 (style guide). The tool reads these to decide tone, title style, and pacing.

## 8. Run the full flow (example)

Try the pipeline first with no keys at all:

```bash
python -m studio.cli demo        # builds projects/<id>/final.mp4 + thumbnails from a sample script
```

Then a real video:

```bash
# 1. Find topics (needs client_secret.json; first run opens a browser to sign in)
python -m studio.cli research "how cruise lines make money"

# 2. Approve the idea you like (ID from the ranked table). This prints the new video id.
python -m studio.cli approve-idea 3

# 3. Script: takes the IDEA id. It writes projects/<video_id>/prompts/script.prompt.md and stops.
python -m studio.cli script 3
#    In Claude Code, say: "Answer the prompt in projects/1/prompts/script.prompt.md"
#    Claude Code researches sources and writes script.response.json. Then re-run:
python -m studio.cli script 3

# 4. Voice, visuals, build, thumbnails (these take the VIDEO id)
python -m studio.cli voice 1
python -m studio.cli visuals 1
python -m studio.cli build 1
python -m studio.cli thumbnail 1

# 5. Optional: cut Shorts
python -m studio.cli shorts 1

# 6. Watch projects/1/final.mp4, then review (type "yes" to approve)
python -m studio.cli review 1 --thumb 2

# 7. Schedule the upload (asks for "yes" again)
python -m studio.cli publish 1 --at "2026-11-05 18:00"
```

Or run everything up to the review gate in one go (re-run it after Claude Code answers the script prompt):

```bash
python -m studio.cli run-all "how cruise lines make money"
```

## 9. Command reference

| Command | What it does |
|---|---|
| `research "<seed>"` | Find and rank topic ideas, flag small-channel outliers |
| `approve-idea <id>` | Approve a topic and start a video record |
| `script <idea_id>` | Generate titles, script, and segment list (via a prompt file Claude Code answers) |
| `voice <video_id>` | Generate narration audio per segment |
| `visuals <video_id>` | Fetch stock clips per segment, record licences |
| `build <video_id>` | Assemble the final MP4 with captions and music |
| `shorts <video_id>` | Cut vertical Shorts from the video |
| `thumbnail <video_id>` | Generate 3 thumbnail variants |
| `review <video_id>` | Checklist and typed approval gate |
| `publish <video_id> --at "<datetime>"` | Upload and schedule after review |
| `analytics` | Pull 28-day metrics and write a plain-English report |
| `ab-log <video_id>` | Record title/thumbnail changes with before/after metrics |
| `comments <video_id>` | Draft comment replies to a file (never posts) |
| `comments post <file>` | Post edited replies, one typed `yes` per reply |
| `calendar` | 4-week content calendar |
| `status [--sync]` | Every video and its current stage; `--sync` marks published videos live |
| `quota` | Today's YouTube API quota use |
| `demo` | Keyless dry run that builds a sample MP4 |
| `run-all "<seed>"` | Chain research through thumbnail, stop at review |

Add `--force` to re-run a finished stage. Run `python -m studio.cli <command> --help` for flags.

## 10. Weekly routine

1. **Monday:** `analytics`, read the report, pick what to make more of.
2. **Monday:** `research` on 2-3 seeds, `approve-idea` for the week's topics.
3. **Tue-Wed:** `run-all` for each approved topic.
4. **Thu:** watch each video fully, edit anything you dislike, then `review`.
5. **Thu:** `publish` with scheduled times.
6. **Fri:** `comments` on recent videos, edit the drafts, post replies yourself.
7. **Ongoing:** `ab-log` whenever you change a title or thumbnail.

## 11. Quota

The default daily YouTube Data API quota is 10,000 units, plus separate allowances of 100 uploads and 100 searches per day (verified 2026-10-28). One fully published video costs about 500 shared units (captions 400 + thumbnail 50 + playlist 50) plus one upload, so quota will not limit a 2-videos-a-week channel. The tool tracks usage in `quota_log`, shows it with `quota`, and stops before the limit minus a 500-unit safety margin. Quota resets at midnight Pacific time.

## 12. Troubleshooting

| Problem | Fix |
|---|---|
| "Missing API key" | Add the named variable to `.env` |
| Browser sign-in loop or auth error | Delete `token.json` and rerun a YouTube command |
| "Access blocked" during sign-in | Add your account as a test user on the OAuth consent screen |
| "ffmpeg not found" | Install ffmpeg and make sure it is on PATH |
| Quota exceeded | Wait for the midnight Pacific reset, or request a quota increase from Google |
| Uploaded videos are private | API audit restriction; see section 3, or publish manually in YouTube Studio |
| No stock clips found | The tool falls back to generated cards; try broader visual keywords |
| `publish` refuses | Run `review <video_id>` and type `yes` first |
| "Prompt written to ..." (exit code 3) | Ask Claude Code to answer that prompt file, then re-run the same command |
| Review fails: unknown licence | Add a `<file>.licence.txt` next to the music/intro/outro file, rebuild, review again |
| edge-tts fails | It needs internet access to Microsoft's speech service; retry, or set `TTS_PROVIDER=eleven` |

## 13. Tests

```bash
pytest -q
```

All external APIs are mocked, so tests need no keys or network. Tests that render video need ffmpeg and are skipped without it.

## 14. Security

- `.env`, `client_secret.json`, and `token.json` must never be committed or shared.
- The tool never logs keys or tokens.
- Publishing and posting always require a typed `yes`.

## 15. Policy reminders

- Every video needs original commentary, structure, or analysis. Do not copy other creators' content.
- Avoid mass-producing near-identical videos; YouTube can demote or demonetize repetitive, low-effort content.
- Disclose realistic AI-generated or altered content when YouTube requires it. The review step shows this flag.
- Add sources and a disclaimer to finance, health, legal, and news videos.
