# Output: one JSON object with exactly these keys
{{
  "topic": "string",
  "originality_note": "1-2 sentences: what this video adds that others do not",
  "hook_type": "the hook_type chosen in the plan",
  "arc": "the plan's arc label",
  "sensitive_topic": false,
  "synthetic_media": false,
  "titles": [{{"text": "string under 70 chars", "style": "string", "is_pick": true}}],
  "thumbnail_texts": ["1-5 words", "1-5 words", "1-5 words"],
  "description_summary": "Two short lines summarising the video.",
  "tags": ["10-15 tags"],
  "sources": [{{"id": "s1", "title": "string", "url_or_note": "https://..."}}],
  "segments": [
    {{
      "chapter": "short viewer-facing name",
      "narration": "Spoken words only.",
      "visual_keywords": ["4-6 concrete photographable terms"],
      "visual_intent": {{"shot_type": "wide | close | detail | map | chart | text", "must_show": "what must be visible", "avoid": "what must not appear"}},
      "est_seconds": 12,
      "emotion": "neutral | hook | reveal | tense | warm | excited",
      "beat": "question | reveal | example | pattern_break | null",
      "plants_loop": "loop id from the plan, or null",
      "pays_loop": "loop id from the plan, or null",
      "fact_ids": ["f1"],
      "chart_data": null
    }}
  ],
  "cta": "The call-to-action sentence used in the last segment."
}}
`chart_data` (when used): {{"type": "bar | pie | line | flow | number", "title": "...", "labels": [], "values": [],
"unit": "...", "source_ids": ["s1"], "fact_ids": ["f1"], "is_estimate": false}}. `bar`/`pie`/`line` need equal-length
labels and values; `flow` needs 2+ labels; `number` needs one label and one value.
