# First video: checklist

## What you must provide (only you can)
1. **A YouTube channel** you own, phone-verified (needed for custom thumbnails). Copy its channel ID (`UC...`) from YouTube Studio > Settings > Channel > Advanced settings.
2. **Google Cloud project** with YouTube Data API v3 and YouTube Analytics API enabled, an OAuth consent screen (add your Google account as a Test user), and a **Desktop app** OAuth client. Save the JSON as `client_secret.json` in the project folder. Steps: README section 3.
3. **ffmpeg** installed (Windows: `winget install ffmpeg`; Mac: `brew install ffmpeg`).
4. **`.env`** copied from `.env.example` with `CHANNEL_ID=UC...`. No LLM key is needed.
5. Optional but better pictures: a free **Pixabay API key** (`PIXABAY_API_KEY`). Without it the video uses generated charts and cards only.
6. Optional: your own music in `assets/music/` with a `<file>.licence.txt` each; otherwise a generated royalty-free bed is used.

## Run it
```bash
python -m studio.cli doctor                      # must say Verdict: GO
python -m studio.cli demo                        # keyless dry run, check it plays

# Pick the topic: your own, or a suggestion
python -m studio.cli add-topic "how Costco makes money" --approve
#   or: python -m studio.cli suggest            then: approve-idea <id>
#   or: python -m studio.cli research "<seed>"  (ranked by demand vs competition; opens Google sign-in once)

python -m studio.cli outline <idea_id>           # Claude Code answers the prompt file, re-run
python -m studio.cli script <idea_id>            # same handoff
python -m studio.cli critique <video_id>         # score and rewrite, re-run after answering
python -m studio.cli voice <video_id>
python -m studio.cli visuals <video_id>
python -m studio.cli build <video_id>
python -m studio.cli qa <video_id>               # fix anything it flags
python -m studio.cli thumbnail <video_id>
python -m studio.cli review <video_id> --thumb 2 # type yes
python -m studio.cli publish <video_id> --at "2026-11-05 18:00"   # type yes again
```
The web app (`run_app.bat`, pages 1 to 4) does the same steps; upload runs on your own PC.

## Know before you publish
- Uploads are always private, or scheduled with `--at`. YouTube may force API uploads from unaudited projects to private; the tool tells you, then you flip it public in Studio.
- Listen to the first 20 seconds of narration and check every figure against its source before typing `yes`.
- Not yet tested live: Google sign-in, real upload, captions upload, edge-tts voice, Analytics. The first real video is that test.
