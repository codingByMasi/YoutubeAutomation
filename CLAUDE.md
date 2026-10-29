# CLAUDE.md

Standing instructions for this repo. Keep under 80 lines.

## What this is
YouTube Channel Studio: a Python CLI that runs a faceless channel from topic research to published video to analytics. Full contract is in `SPEC.md`. Read it before coding. Progress is tracked in `PROGRESS.md`.

## Session start routine
1. Read `PROGRESS.md` to see what is done and what is next.
2. Read the relevant section of `SPEC.md` for the milestone you are on.
3. Do not redo finished milestones. Do not start a new milestone until the current one's tests pass.

## Hard rules
- Never publish, post, reply, or change a live video without a typed `yes` from the owner. This is enforced in code and covered by tests. Do not weaken it.
- Never commit or log secrets: `.env`, `client_secret.json`, `token.json`, API keys.
- Never copy other creators' content. Research finds topics only.
- Read official API docs at build time for quota costs, OAuth steps, and field names. Do not rely on memory for those.
- Do not add features outside `SPEC.md` Section 12 "Out of scope" without asking.

## Stack
Python 3.11, Typer, SQLAlchemy + SQLite, google-api-python-client, edge-tts, faster-whisper, ffmpeg/MoviePy, Pixabay/Pexels API, Pillow, matplotlib, pytest.

## Channel
Business-model and economics explainers, English, faceless narration with charts and diagrams. Every figure needs a source. Details in `SPEC.md` Sections 1 and 9.

## Layout
- `studio/cli.py` entry point; `studio/stages/` pipeline stages; `studio/manage/` channel management; `studio/youtube/` API clients and quota; `studio/providers/` TTS, footage, captions; `studio/util/` helpers.
- Per-video files live in `projects/<video_id>/`.
- Layout details: `SPEC.md` Section 3.1.

## Conventions
- Type hints and short docstrings on every public function.
- Every stage is idempotent and resumable: re-running a finished stage skips it unless `--force`.
- Stages advance in order only (see stage table in `SPEC.md` 2.2).
- Log every YouTube API call's quota cost to `quota_log` and stop before exceeding the daily limit minus the safety margin.
- Retry network errors with exponential backoff, max 5 attempts.
- Error messages must say what failed, why, and what to do next.
- Keep modules small; one responsibility each.

## Commands
- Run tests: `pytest -q`
- Run CLI: `python -m studio.cli --help`
- Lint: `ruff check .`
- Keyless dry run: `python -m studio.cli demo`

## Definition of done for any milestone
1. Code written and runs.
2. Tests for it written and passing (APIs mocked).
3. `PROGRESS.md` updated (status, date, notes, anything the owner must configure).
4. `README.md` or `SPEC.md` updated if a command, config, or behavior changed.

## When blocked
Make the most reasonable choice, write it down in `PROGRESS.md` under "Decisions", and continue. Ask the owner only for things that need their accounts or credentials.

## Answering prompt files (LLM_PROVIDER=claude_code, the default)
The owner has no LLM API key; Claude Code writes the creative text. Commands like `script` and
`comments` write `projects/<id>/prompts/<task>.prompt.md`, exit with code 3, and wait.
When asked to answer one:
1. Read the whole prompt file; it holds the rules, the style guide and the exact JSON shape.
2. Research real figures with web search; cite filings, annual reports or reputable articles in `sources`.
   Never copy another creator's script or video; write original analysis.
3. Write ONLY the JSON object to the matching `<task>.response.json`.
4. Re-run the command; it validates the answer and prints any problems to fix.

## Token discipline
Prefer one consolidated pass per milestone. Do not re-read whole files unnecessarily; read only the section you need.
