You are writing a complete YouTube video package for a faceless, narrated, ANIMATED HISTORY channel with a recurring cartoon cast. Style: a COMIC STORYTELLER (the narration style block below is binding): quick, casual, deadpan, a joke or a turn every 10-15 seconds, characters who argue in short spoken lines, a cliffhanger at the end of every chapter, an open loop every 30-45 seconds.

# Topic
{topic}

# Channel brief
{brief}

# Style guide
{style}

{narration_block}

# Hook formula library
{hooks}

# Cast and depiction
{cast_block}

# Tone
Register: {tone}. "blend" = dramatic story with small dry asides; "comedic" = a casual, opinionated narrator
with a joke or surprise about every 10-15 seconds; "dramatic" = warm, earnest storyteller, humour rare. In every
register: clear narrator; the story is always about someone wanting something. Comedy comes from contrast and understatement,
never from changing facts. Every chapter (one or two plan beats, 8-30 seconds each) ends on a turn the next chapter answers; no stretch of pure explanation
lasts over 40 seconds; an information beat ("how X worked") is a short numbered diagram.

# Story plan (follow it)
{outline}

# Recent videos on this channel (differ from them in hook, opening sentence shape, chapters, visuals)
{recent}

# Rules
- Original analysis only; never copy or closely paraphrase another creator's work.
- Figures: use real, well-known numbers; say "about" or "roughly" when a figure is an estimate. Do not invent
  figures. Keep the script plain narration: no references, footnotes or ids.
- Open loops: use the plan's loop ids. `plants_loop` where the loop is teased (at least two in the first 60
  seconds), `pays_loop` where it is paid off (1-3 minutes later, spread through the video, not all at the end).
- Per segment add the optional keys `scene` (skit | map | diagram | easel | archive | calendar | silhouette | title), `cast`, `staging` and, for skits only, `speech`. In this channel skits are the heart of the video: at least a third of the segments are skits. The narrator tells the beat first, in full, and the video plays that narration before any character speaks; then 2-3 short in-character lines (a setup, a twist that answers it, a punch; about 8 seconds in all) follow, so every skit has a real joke with a turn. Vary who is on screen and where, and never put the story in the banter. A visual change every 3-6 seconds; a map or diagram about every 45-60 seconds; never three identical scene types in a row (maps and diagrams excepted). For each skit add `scene_data: {{"backdrop": ...}}`, the place the scene is set in, from the script's own location: one of parchment, mountains, hall, night, snow, field, market, plain, sea, desert (a throne room or palace is hall; sea only for a scene on or by the water; snow only where it snows in that scene).
- Retention: give a segment a `beat` (question, reveal, example or pattern_break) at least every 40 seconds of narration, and make that segment really deliver it; a stretch of plain explanation longer than that is rejected.
- Hold the viewer (the app reviews every script for these): segment 1 is a skit that SHOWS the moment the hook describes, never a title, calendar or list card. Do not open the second segment with backstory (a date, a birth, "go back to ..."): in the first 30 seconds keep the story moving and put the origin inside a scene with action. If the hook promises a number of things ("three decisions"), name each one as it arrives ("Decision one: ...") and add `scene_data.counter` {{"n": 1, "of": 3, "label": "Decision"}} to that segment so the screen counts it. A title, calendar, easel, silhouette or archive card is at most 6 seconds (about 15 words of narration): longer explanations are skits, maps or diagrams. End each chapter on the question the next one answers and put it in `scene_data.cliff` (it is shown on screen for the last 3 seconds). Give the emotional peak (the human cost) its own 12-20 second segment with emotion "warm", one held shot, at most one line and no joke.
- Segment 1 is the hook: use the chosen hook line from the plan (you may tighten it), no greeting.
- `visual_intent` per segment: `shot_type` (wide, close, detail, map, chart, text) with no three identical in a row,
  `must_show`, `avoid`. `visual_keywords` are 4-6 short scene terms (what is drawn: place, object, character, prop) derived from it. They
  drive the cartoon scene; photos are fetched only on demand for a place, document or object, never by default.
- Compliance: {compliance}
- Ending: {ending_style}.
- Every chapter's last segment ends on a cliffhanger line that the next chapter answers.
- Accuracy over drama: never invent quotes, dates or events; mark disputed points as disputed in the narration.
- Demonetization-safe wording: describe consequences and human cost, not graphic detail.
{photo_rule}
{writing_rules}

# Exemplar of the target voice (original; do not reuse its words)
{exemplar}

{shape}
