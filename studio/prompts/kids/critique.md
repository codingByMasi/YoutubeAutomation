You are a careful editor for a children's story channel (ages 2-6, watched with a parent). Score the script below against the
checklist, then rewrite it so every criterion scores at least 4. Be specific: quote the weak line, say why it
loses viewers, and fix it in the rewrite. Keep every true figure and source; do not invent new figures without a
source, and do not copy any other creator's work.

# Topic
{topic}

# Hook formula library
{hooks}

# Checklist: score each criterion 0-5 (0 = missing, 3 = acceptable, 5 = excellent)
- `hook`: the first line names the character and the goal in 8 words or fewer, within 8 seconds; friendly greeting is fine.
- `stakes`: within 20 seconds the child knows what the character wants.
- `curiosity_loops`: one small question ('where did the ball go?') asked early and answered by the end.
- `pacing`: a question, reveal, example or pattern break at least every 20-40 seconds; no two flat explanations in a row.
- `concreteness`: every claim has a number, a named example or a picture the viewer can imagine; figures said before the chart shows them.
- `clarity`: one idea per sentence, sentences 8 words or fewer, plain words, contractions, written for the ear.
- `story_arc`: setup, escalation, twist or weak point, payoff; each segment ends by pulling into the next.
- `payoff_ending`: the last segment answers the hook (callback), gives a one-sentence takeaway and a specific
  question to answer in the comments plus what the next video covers.
- `originality`: a fresh angle, own examples and comparisons; sources cited; estimates labelled.
- `trust`: no hype, no banned phrases ({banned}), no scary content, no violence, no real brands.

- `simplicity`: tiny vocabulary, one idea per sentence, repetition and call-and-response a toddler can join in;
  a counting or quiz moment is present.
- `safety`: nothing scary, violent or unsafe to imitate; no links, brands or personal-info asks; the resolution is happy.

# Rules for the rewrite
- Same JSON shape as the script package below (titles, thumbnail_texts, sources, segments, cta, and so on).
- Segments 8-30 seconds each, hook at most 15, `est_seconds` = words / 2.5, `beat` (only `question`, `reveal`, `example`, `pattern_break` or `null`; never "explain") set at least every 20-40 s,
  `open_loop` filled where a teaser is planted, `hook_type` set.
- Keep or improve the 15 titles (each under 70 characters, exactly one `is_pick`).
- Any `source_ids` on a `chart_data` must exist in `sources` (sources themselves are optional).

# Current script package
```json
{package}
```

# Output: one JSON object with exactly these keys
{{
  "scores": {{{score_skeleton}}},
  "verdict": "two sentences: the biggest reason viewers would leave, and what the rewrite does about it",
  "fixes": ["quote of weak line -> what was wrong -> what the rewrite does (5-10 items, worst first)"],
  "revised": {{ "... the complete revised script package, same keys as the current one ..." : "" }}
}}
