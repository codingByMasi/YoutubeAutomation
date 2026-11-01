# Growth playbook (finance / business-storytelling channels)

Researched 2026-11-01. This is the "why" behind the growth checks in `studio/quality/growth.py`.
Most numbers below are **rules of thumb from creator-education blogs, not YouTube rules**; many are
uncited claims by their authors. The pipeline uses them as warnings you can tune, never as facts.
Only the policy items (section 1) come from YouTube itself, as relayed by the press.

## 1. Stay monetisable: YouTube's "inauthentic content" policy (effective 2025-07-15)
- YouTube renamed "repetitious content" to **inauthentic content** (mass-produced or repetitive). Its own examples:
  channels that upload narrative stories with only superficial differences, and slideshows that all have the same narration.
  ([Social Media Today](https://www.socialmediatoday.com/news/youtube-clarifies-monetization-update-inauthentic-repeated-content/752892/))
- AI use is **not** the target: channels that use AI remain eligible. Realistic content that is altered or synthetic must be disclosed.
- Practical checklist for faceless channels ([summary](https://faceless.my/youtube/youtube-inauthentic-content-policy-faceless-ai-2026/)):
  a distinct angle per video, original analysis, a human deciding what each video says, varied structure
  (a similar pattern is fine if the substance differs), no slideshows with little narrative, no AI narration of other people's material.
- Pipeline response: `originality` gate dimension flags a video whose script or structure is too similar to the channel's recent
  videos; sources are mandatory; the owner's typed `yes` stays the human decision.

## 2. Retention is the main lever
- Keep at least ~60% of viewers past the 30-second mark; strong hooks hold above ~65%
  ([vidIQ](https://vidiq.com/blog/post/increase-audience-retention-youtube/)).
- Hook inside 15 seconds: state the value, preview the payoff, or open a question. Cold open, no logo or "welcome back".
- Hook-deliver cycles and open loops: tease the best point early, pay it off later.
- Pattern interrupt about every 60-90 seconds (a change of visual, chart, music or camera)
  ([Isaacson](https://johnisaacson.co.uk/how-youtube-algorithm-works-2026/)). Pacing differs by format, so match it to the format, not generic "fast cuts".
- Match length to value; padding creates dips. Check retention at 48 hours and 7 days.
- Pipeline response: already covered by `hook`, `pacing`, open-loop checks and the retention feedback loop; this PR adds a
  **title-to-hook promise check** (a mismatch reads as bait-and-switch and shows up as a first-30-second drop).

## 3. Packaging: title and thumbnail
- The title and thumbnail make a promise and the opening must keep it
  ([vidIQ](https://vidiq.com/blog/post/increase-audience-retention-youtube/)). Healthy CTR is roughly 4-10% (blog claim).
- Prepare several title and thumbnail variants and test them (YouTube's Test & Compare); pick on watch time, not clicks alone.
- Thumbnail: 1-4 words, one focal element, high contrast, and it adds something the title does not say.
- Pipeline response: `packaging` gate dimension checks the title scores on the existing checklist, matches the hook,
  and that a title/thumbnail variant pack exists (>=3 titles, >=2 thumbnails) so you can run a test.

## 4. Content-aware visuals (the user's main complaint)
- Explainer retention comes from visuals that carry the argument: charts for numbers, timelines for sequences, diagrams for
  mechanisms. Generic stock b-roll over a spoken figure reads as the "AI slideshow" the policy targets.
- Pipeline response: `fit` gate dimension classifies each segment from what it says (numbers, comparison, timeline, mechanism,
  people/story) and checks the visual matches: figures need a chart or number card, stock keywords must relate to the narration,
  generic filler stock (handshake, skyline, laptop typing) is flagged, and an explainer may not be mostly stock footage.

## 5. Shorts as a funnel
- Hook lands in the first ~2 seconds; a visual or text change inside the first second; keep to 25-55 seconds for clean loops
  ([InfluenceFlow](https://influenceflow.io/resources/youtube-shorts-and-long-form-video-strategy-the-complete-2026-creators-guide-1/)).
- Each Short points to the full video (pinned comment, related video link) and stagger them over weeks.
  Typical mix quoted: 3-5 Shorts per long video (blog claim, figures conflict between sources).
- Pipeline response: `shorts_plan` now rewrites the hook line to a short opener, adds a `cta` and `related video` field,
  prefers 25-55 s windows, and staggers post days over ~3 weeks.

## 6. Series, playlists, cadence
- A sustainable schedule beats raw volume; rushed videos hurt performance ([Umbrella](https://umbrellacreators.com/blog/how-to-grow-a-youtube-channel-2026)).
  Viewer-session value (series that lead to the next video) matters more than single-video views.
- Pipeline response: `packaging` notes when a video is not in a series; `calendar.suggest_publish` picks the next free long slot at the
  channel's `publish_time` (default 16:00). It is a helper only for now: not yet shown in the review screen. Playlist creation itself is handled by the playlists work.

## 7. What the owner must still do
- Read the retention graph at 48 h and 7 d and run `feedback` so thresholds tune to your audience.
- Add a real viewpoint to every script (a thesis, not a summary); the gate cannot judge insight.
- Disclose realistic synthetic voices/footage of real people or events when you upload (YouTube Studio's altered-content toggle).
- Run title/thumbnail tests in YouTube Studio on the variants in `pack`.

## Sources
[Isaacson](https://johnisaacson.co.uk/how-youtube-algorithm-works-2026/) ·
[vidIQ retention](https://vidiq.com/blog/post/increase-audience-retention-youtube/) ·
[Social Media Today](https://www.socialmediatoday.com/news/youtube-clarifies-monetization-update-inauthentic-repeated-content/752892/) ·
[faceless.my](https://faceless.my/youtube/youtube-inauthentic-content-policy-faceless-ai-2026/) ·
[InfluenceFlow Shorts](https://influenceflow.io/resources/youtube-shorts-and-long-form-video-strategy-the-complete-2026-creators-guide-1/) ·
[Umbrella Creators](https://umbrellacreators.com/blog/how-to-grow-a-youtube-channel-2026)
