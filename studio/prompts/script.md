You are writing a complete YouTube video package for a faceless, narrated explainer channel.

# Topic
{topic}

# Channel brief (from SPEC.md section 1)
{brief}

# Style guide (from SPEC.md section 9)
{style}

# Hard rules
- Original analysis only. Do not copy or closely paraphrase any existing video, script or article.
  Explain the money flow in your own structure, with your own examples and comparisons.
- Every figure shown on screen needs a source in `sources` (annual report, filing, reputable article).
  Label estimates as estimates (`"is_estimate": true`). No investment advice; no guarantees.
- Banned phrases anywhere: {banned}.
- Titles: exactly 15, each under 70 characters, one clear promise, no ALL-CAPS words longer than
  3 letters, no claims the video cannot back up. Mark exactly one `"is_pick": true`.
- Segment 1 is the hook: at most 15 seconds, states the problem and the payoff. No "subscribe first".
- Follow the 7-part structure: hook, product/customer, money in, costs, clever trick or weak point,
  takeaway, call to action. Use the `chapter` field to name each part (short, viewer-facing).
- A retention beat (`question`, `reveal`, `example`, or `pattern_break`) at least every 30-45 seconds.
- A chart, diagram or number card (`chart_data`) at least every 60-90 seconds, and for every major figure.
- Target total length {min_minutes}-{max_minutes} minutes at about 150 spoken words per minute.
  `est_seconds` = words / 2.5. Keep each segment 15-60 seconds so visuals change often.
- `visual_keywords`: 2-4 plain stock-footage search terms describing the setting (not brands' logos).
- Set `synthetic_media` true only if the video would show realistic AI-generated people, places or events.

# Output: one JSON object with exactly these keys
{{
  "topic": "string",
  "originality_note": "1-2 sentences: what this video adds that others do not",
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
      }}
    }}
  ],
  "cta": "The call-to-action sentence used in the last segment."
}}
Chart types: `bar`/`pie`/`line` need equal-length labels and values; `flow` needs labels (steps in order,
values optional); `number` needs one label and one value.
