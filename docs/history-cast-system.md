# History channel: cast, depiction and staging system

Goal: the history channel looks and moves like the animated reference channels (recurring cartoon characters,
depicted events, map and diagram set pieces) while every character, script and drawing is **ours**. Structure and
pacing come from `history-style-report.md`; the code is `studio/history/cast.py`.

## Recurring cast (original)

| Id | Name | Job in the story |
|---|---|---|
| `quill` | Quill | Host. Stands at the lectern between chapters, asks the chapter question |
| `dusty` | Dusty | The viewer's stand-in; asks what the viewer is thinking |
| `vex` | Vizier Vex | The schemer: advisers and rivals who pull strings |
| `blunder` | Captain Blunder | The overconfident officer; stands in for a doomed plan |
| `coin` | Madame Coin | The treasurer; counts what a war, tax or trade cost (keeps the channel's economics angle) |
| `dash` | Dash | The courier; delivers bad news and ends chapters on a cliffhanger |

A lineup preview is in the project files: `youtube-studio/history-cast/history-cast-lineup.png`. The art is a
simple placeholder drawn in code; an artist can replace any `<id>.svg` (same four group ids) without code changes.

## Historical figures

Built from the same body: `cast.build_svg(body, headwear, prop, badge)`.

- **Faction colour**: one colour per side for the whole video (`faction_color(n)`), also used for map flags.
- **Letter badge** on the chest so similar figures stay distinguishable.
- **One headwear and one prop** (`HEADWEAR`, `PROPS`) per figure, kept for the video.
- **Never a real likeness**; no photographs of living people. Archive images only for places, documents and objects,
  at most one per chapter.
- **Atrocity, death and torture** are never drawn: cut to a map, a silhouette or Quill at the lectern, and say the
  human cost in one plain sentence.
- **Invented dialogue is tone only**; real quotes go in the narration with a source; disputed claims get a "?"
  above the speaker.

## Scene types and staging

`lectern` (chapter card with Quill), `skit` (2-4 on-screen speech lines, at most 10 words each), `map` (political
map, arrows, flags, place label timed to the narration), `diagram` ("how X worked" in 3-5 numbered steps),
`easel` (a list or chart on an easel), `archive` (one still, 2-3 s), `calendar` (time passing, days crossed out),
`silhouette` (violence or loss without detail), `title`.

Segments may carry optional keys `scene`, `cast`, `staging`, `speech`. They are optional, so old scripts and other
channel types are unaffected. For history, `cast_scenes` is on by default and `cast.scene_problems` reports:
unknown scene types, a skit with no cast, more than 4 speech lines, speech over 10 words, speech outside a skit, and
three of the same scene in a row (maps and diagrams excepted).

## How it plugs into the repo

- The prompts for `script` and `story_plan` get a `{cast_block}` (roster, depiction rules, scene keys) only when
  the profile has `cast` (history today).
- Characters use the existing sprite contract (`studio/kids/sprites.py`: `eyes-open`, `eyes-closed`, `mouth-closed`,
  `mouth-open`) so `SpriteBank(user_dir=...)` can blink and lip-sync them. `cast.export_roster(dir)` writes the SVGs.
- Rendering is the next step and is not in this change: a 2D history scene renderer would compose sprites,
  backgrounds and speech text per `scene`, using `render2d` for maps and diagrams. Until then the visuals stage
  keeps using `visual_intent` and stock or 2D scenes.

## Open questions for the owner

1. Keep the cast names, or rename? Names are data in `ROSTER`.
2. Tone: the profile ships as `blend` (dramatic story, light comic asides). Switch to `comedic` or `dramatic` by
   setting `story.tone` on the channel.
3. Sponsor slots: the references have them; the profile has none. Say if you want a mid-roll placeholder.

## Cast of ten and per-character voices

Four characters were added to the original six (`brine`, `hindsight`, `ironhand`, `alma`). Art direction: **paper-cutout
storybook**: one flat body template, identity from silhouette (`shape`: standard, tall, wide, stocky, small),
headwear, prop, letter badge and colour. This keeps every historical figure cheap to generate and matches the
existing sprite contract. Preview: `youtube-studio/characters-v2/history-cast-of-10.png` in the project files.

| Id | Name | Job | Shape |
|---|---|---|---|
| `brine` | Admiral Brine | sea power: fleets, harbours, trade routes | wide |
| `hindsight` | Inspector Hindsight | the clue everyone missed | tall |
| `ironhand` | Ironhand | weapons, tools, factories | stocky |
| `alma` | Almanac Alma | dates, calendars, how long it took | small |

Every roster entry has `personality` and a `voice` (see `studio/providers/voices.py`): `edge` (edge-tts name), `rate` %,
`pitch` Hz, `kokoro` (offline voice id) and `speed`. `cast.voice_for(id)` returns it; `voices.engines(voice)` builds
the edge and Kokoro engines and `voices.prosody(voice)` the rate/pitch dict they take. Nothing in the video pipeline
voices characters yet (speech lines are on-screen text); this is the hook for it. Check edge names with
`edge-tts --list-voices`: the names were not verified against the live service from the build sandbox.
