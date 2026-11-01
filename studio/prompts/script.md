You are writing a complete YouTube video package for a faceless, narrated explainer channel.

# Topic
{topic}

# Channel brief (from SPEC.md section 1)
{brief}

# Style guide (from SPEC.md section 9)
{style}

# Hook formula library
{hooks}

# Retention outline (follow it: its hook, open loops, beat order, ending and sources)
{outline}

# Hard rules
- Original analysis only. Do not copy or closely paraphrase any existing video, script or article.
  Explain the money flow in your own structure, with your own examples and comparisons.
- Every figure shown on screen needs a source in `sources` (annual report, filing, reputable article).
  Label estimates as estimates (`"is_estimate": true`). No investment advice; no guarantees.
- Banned phrases anywhere: {banned}.
- Titles: exactly 15, each under 70 characters, one clear promise, no ALL-CAPS words longer than
  3 letters, no claims the video cannot back up. Mark exactly one `"is_pick": true`.
- Segment 1 is the hook: at most 15 seconds (about 35 words). No greeting, no channel intro, no "in this
  video", no "subscribe first". The first sentence is 12 words or fewer and lands a specific number, a
  contradiction, or a question the viewer cannot answer yet. Then state the payoff ("by the end you will know ...").
  Pick ONE hook formula and record it in `hook_type`:
  `number_stakes` ("A $300 ticket is the cheapest thing you will pay for. Here is where the other $1,400 goes."),
  `contradiction` ("The most profitable part of this business is the part it gives away."),
  `hidden_answer` (a question whose answer is the video), `cold_open` (start mid-scene, explain after).
- Storytelling arc, in order: hook; the familiar situation and what is at stake; the money flow in 2-4 steps,
  each with a surprising figure; the complication or weak point; the payoff that answers the hook; a one-sentence
  takeaway; the call to action. Use the `chapter` field to name each part (short, viewer-facing).
- Open loops: in the first 60 seconds plant at least two teasers that are paid off later ("The third source is
  the one nobody notices", "And that is not even where the real profit hides"). Each payoff should plant the
  next teaser. Describe each teaser in the segment's `open_loop` field (empty string if none).
- Pattern interrupt (`question`, `reveal`, `example`, or `pattern_break`) in `beat` at least every 20-40
  seconds: ask the viewer something, drop a number, flip an assumption ("but here is the catch"), use a
  comparison they can picture, or tell a 1-2 sentence anecdote. Never two flat explanatory segments in a row.
- Spoken style: write for the ear. Sentences of 18 words or fewer, contractions, plain words, "you". One idea
  per sentence. Say the number BEFORE the chart shows it, then say what it means in everyday terms. No filler
  ("basically", "let's dive in", "without further ado"), no list of five things in one breath.
- Ending: the last segment pays off the hook in one sentence (call back to its first line), then a specific
  call to action tied to this topic: ask one concrete question to answer in the comments and name what the
  next video covers. A generic "like and subscribe" alone is not enough.
- A chart, diagram or number card (`chart_data`) at least every 60-90 seconds, and for every major figure.
- Optional `scene` (leave it `null` when a plain chart or footage is enough): a short animated scene that the owner can
  draw in 3D or 2D. Use it for at most one segment in four, only where it explains something better than footage.
  Kinds and their `items`: `timeline` (2-10 `{{label: "1066", text: "Norman conquest"}}`, in order, `source_ids` required),
  `map` (2-10 places in route order, `{{label, x, y}}` with x and y between 0 and 1: a schematic map, not real
  geography), `artifact` (exactly one `{{label, shape}}`, shape coin, column, vase or box), `chart3d` (bars
  from the segment's bar/line `chart_data`; give `items` `{{label, value}}` plus `source_ids` only if there is no chart_data).
  `style` is "" (follow the video's setting), "2d" or "3d".
- Typical total length is {min_minutes}-{max_minutes} minutes at about 150 spoken words per minute; go longer if the
  topic needs it. There is no maximum length: never cut the money flow short to fit.
  `est_seconds` = words / 2.5. Keep each segment 8-30 seconds so the picture changes often (hook: 15 at most).
- `visual_keywords`: 4-6 plain search terms, most specific first. They are searched as stock video AND as
  photos (Pixabay, Wikimedia Commons), and results are filtered by how many keyword words match the photo's
  tags. Use concrete, photographable nouns (places, objects, people at work), 2-3 words each, mixing wide and
  close-up shots ("cruise ship deck", "casino slot machines", "restaurant kitchen"). Avoid abstract terms
  ("economy", "profit"), logos and brand names.
- Set `synthetic_media` true only if the video would show realistic AI-generated people, places or events.

# Output: one JSON object with exactly these keys
{{
  "topic": "string",
  "originality_note": "1-2 sentences: what this video adds that others do not",
  "hook_type": "number_stakes | contradiction | hidden_answer | cold_open",
  "sensitive_topic": true,
  "synthetic_media": false,
  "titles": [{{"text": "How Cruise Lines Make Money", "style": "how-x-makes-money", "is_pick": true}}],
  "thumbnail_texts": ["3-5 words", "3-5 words", "3-5 words"],
  "description_summary": "Two short lines summarising the video.",
  "tags": ["10-15 tags"],
  "sources": [{{"id": "s1", "title": "Carnival Corp 2025 Annual Report", "url_or_note": "https://..."}}],
  "segments": [
    {{
      "chapter": "The $300 question",
      "narration": "Spoken words only.",
      "visual_keywords": ["cruise ship at sea", "ship deck"],
      "est_seconds": 12,
      "beat": "question",
      "open_loop": "Promises to reveal where the other $1,400 goes",
      "chart_data": null
    }},
    {{
      "chapter": "Where the money comes in",
      "narration": "...",
      "visual_keywords": ["..."],
      "est_seconds": 40,
      "beat": "reveal",
      "chart_data": {{
        "type": "bar | pie | line | flow | number",
        "title": "Revenue per passenger",
        "labels": ["Tickets", "Onboard spending"],
        "values": [65, 35],
        "unit": "%",
        "source_ids": ["s1"],
        "is_estimate": false
      }},
      "scene": null
    }}
  ],
  "cta": "The call-to-action sentence used in the last segment."
}}
Chart types: `bar`/`pie`/`line` need equal-length labels and values; `flow` needs labels (steps in order,
values optional); `number` needs one label and one value.
