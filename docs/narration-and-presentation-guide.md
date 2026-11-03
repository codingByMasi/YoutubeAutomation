# Narration styles and how each niche should be presented

Pick a narration style per channel: Channels page, "Narration style" (or `channels edit --narration <id>`).
Blank = the channel type's default. The style sets how the script is written, the offline narrator voice and speed,
and the per-emotion delivery. Cast characters keep their own voices (`studio/providers/voices.py`).

## Narration styles
- **Comic storyteller** (`comic_storyteller`): History, mythology, 'how it all went wrong' stories, animated casts (OverSimplified style).
- **Calm explainer** (`calm_explainer`): Finance, business, economics, tech and science explainers; anything number-led.
- **Warm sing-song** (`warm_singsong`): Toddlers and preschoolers: stories, rhymes, counting, songs.
- **Dramatic documentary** (`dramatic_documentary`): Serious history, war, biography, geopolitics (Extra History style).
- **Hushed suspense** (`hushed_suspense`): True crime, mysteries, disasters, unsolved cases.
- **High-energy hype** (`high_energy_hype`): Gaming, tech reviews, challenges, reactions, top-10 lists.
- **Motivational coach** (`motivational_coach`): Self-improvement, habits, productivity, life lessons.

Defaults: history = comic storyteller, finance/business = calm explainer, kids = warm sing-song.

## What the reference videos do (measured on the first 3 minutes of each)
| | OverSimplified (Punic War, WW1) | Extra History (Genghis Khan) | Our first history sample |
|---|---|---|---|
| Pace | 2.5-2.9 words/s | about 3.2 words/s | 2.1 words/s |
| Tone | casual, modern slang, deadpan, a joke every 5-15 s | earnest, vivid, dry humour rare | formal, no jokes |
| Characters | spoken lines swap with the narrator every 5-15 s | narrator only | 4 short lines in 58 s |
| Voice | one lively narrator plus distinct character voices | one warm, steady narrator | one flat narrator |

## Presentation guide per niche
| Niche | Look | Pacing and length | Voice | Hook (first 5 s) | Thumbnail | Ending |
|---|---|---|---|---|---|---|
| Finance / business | clean charts, diagrams, big numbers, one running example | picture change every 4-7 s; 8-12 min | calm explainer | a surprising number or contradiction | one number plus 3 words, high contrast | callback to the hook, one takeaway, a comment question |
| History (animated) | recurring cartoon cast, maps, skits | change every 3-6 s; 8-15 min; a joke or turn every 10-15 s | comic storyteller plus character voices | a funny or tense scene, rewind to the cause | two characters, one expression, 3 words | land the beat, name the next threat, point to part 2 |
| Kids | bright simple characters, big shapes, songs | change every 3-5 s; 3-8 min; repeat refrains | warm sing-song | a character wave or a question | one face, huge, 1-2 words | everyone happy, repeat the song line, wave goodbye |
| Tech | screen captures, product shots, simple diagrams | 4-6 s; 6-10 min | high-energy hype or calm explainer | the verdict or the surprising spec | product plus a short claim | verdict plus who should buy |
| Science | animations of the mechanism, analogies | 5-7 s; 6-12 min | calm explainer, a little wonder | a "how is that possible" question | the weird thing itself | the open question science still has |
| True crime / mystery | dim maps, documents, silhouettes (no gore) | 5-8 s; 10-20 min; withhold then reveal | hushed suspense | the single strangest fact | a document or place, dark tone | what is still unsolved |
| Gaming | gameplay, quick cuts, on-screen counters | 2-4 s; 6-15 min | high-energy hype | the payoff shown first | face or moment, 2 words | tease the next challenge |
| Self-improvement | calm footage, text cards, simple animation | 5-8 s; 6-10 min | motivational coach | a direct problem the viewer has | a bold promise in 3 words | one action to try today |

Rules for all niches: hook in 3-5 seconds, no greeting; an open loop about every 30-60 s; a visual change at least every
6 s; end with one clear next step; never copy another creator's script, jokes or characters.
