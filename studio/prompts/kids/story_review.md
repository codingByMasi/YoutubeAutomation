You are reviewing a finished draft of a YouTube script. Review it as two people at once, and do NOT defend it:
1. A restless 4-year-old (and a tired parent) who wander off the moment it gets confusing or boring.
2. A skeptical editor who has seen a hundred videos like this and distrusts every claim.
You did not write this draft and you do not know why it was written this way. Be blunt; be specific; quote exactly.

# Topic
{topic}

# Rubric: score every criterion 0-5 (0 missing, 3 acceptable, 5 excellent)
- `hook`: first sentence {hook_words} words or fewer, a curiosity gap, no greeting, promises a payoff.
- `stakes`: within 30 seconds the viewer knows why it matters to them.
- `curiosity_loops`: open loops planted early and each paid off later.
- `pacing`: something changes at least every 20-40 seconds; no two flat explanations in a row.
- `concreteness`: numbers, named examples, pictures the viewer can imagine.
- `clarity`: one idea per sentence, written for the ear, {sentence_cap} words or fewer per sentence.
- `story_arc`: setup, escalation, twist, payoff; each segment pulls into the next.
- `payoff_ending`: callback to the hook, one-sentence takeaway, specific question, next video.
- `originality`: a fresh angle and own examples; nothing that reads like another creator's video.
- `trust`: no hype, no banned phrases, no advice or guarantees. Banned: {banned}.
{extra_criteria}

# Swipe-away simulation
List 3-5 moments where the distracted viewer would leave. For each give the `segment` number (1-based), an exact
`quote` from that segment's narration (word for word), `why` they leave, and `fix` (what the rewrite will do).
Code computes the timestamp from the segment and checks that the quote existed and is gone from the rewrite.

# Rewrite
Return the complete rewritten package in `revised`: same JSON shape and field names as the draft (including
`fact_ids`, `plants_loop`, `pays_loop`, `visual_intent`), every swipe-away moment fixed, every true figure and
source kept, no new figure without a fact id from the facts list. Hold length to {min_minutes}-{max_minutes}
minutes; `est_seconds` = words / {wps}. {compliance}
{deterministic}

# Facts available (ids and status only)
{facts}

# Draft package
```json
{package}
```

# Output: one JSON object with exactly these keys
{{
  "scores": {{{score_skeleton}}},
  "verdict": "two sentences: the biggest reason viewers leave and what the rewrite does about it",
  "swipe_points": [{{"segment": 4, "quote": "exact words", "why": "string", "fix": "string"}}],
  "fixes": ["quote -> problem -> fix (5-10 items, worst first)"],
  "revised": {{ "... the complete revised package ..." : "" }}
}}
