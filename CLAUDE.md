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
- Everything the owner needs must be doable in the app. Never ask them to edit files (`.env`) or paste paths; if no in-app setting exists, say so and list it as a gap.
- Never ask the owner for credentials.
- Keep fixes minimal: when fixing one thing, change no unrelated code or text.
- Disclose every change made to a PR after the owner reviewed it (conflict merges, extra commits, rule tweaks), including at merge time.
- There is no CI. Run the full `pytest -q` before any merge, and merge only after the owner says merge.

## Stack
Python 3.11, Typer, Streamlit app, SQLAlchemy + SQLite, google-api-python-client, Kokoro (offline) then edge-tts for voice, TTS word timings with optional faster-whisper for captions, ffmpeg, optional Blender (3D, PC only), Pixabay/Pexels API, Pillow, matplotlib, pytest.

## Channels
The app runs three channel types (details in `SPEC.md` Sections 1 and 9). Scripts carry no sources or fact ids (owner decision); use real figures and word estimates as estimates.
- **Business:** economics explainers, faceless narration with charts and diagrams. Narration default: calm explainer.
- **History:** animated storytelling. Narration default: comic storyteller. Defaults to the 2D cartoon cast renderer, not stock, photos or charts, unless asked. Characters come from the script (2D or 3D as it says), not a fixed cast. 3D needs Blender and has no history cast mode.
- **Kids:** 2D by default, warm sing-song narration.
- The narrator is muted while a character line plays; two voices never overlap.

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
2. Research real figures with web search; do not add `sources`, `source_ids` or `fact_ids` to the JSON.
   Never copy another creator's script or video; write original analysis.
3. Write ONLY the JSON object to the matching `<task>.response.json`.
4. Re-run the command; it validates the answer and prints any problems to fix.

Story tasks use the same flow: `outline` (retention outline) and `critique` (score the script on the 10-point
checklist, then return the full rewritten package in `revised`). Read `studio/prompts/hooks.md` first.
History scripts also use the `story_plan` and `story_review` prompts in the same flow.

## Token discipline
Prefer one consolidated pass per milestone. Do not re-read whole files unnecessarily; read only the section you need.
