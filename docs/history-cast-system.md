# History channel: cast, depiction and staging system

Goal: the history channel looks and moves like the animated reference channels (cartoon characters from the script,
depicted events, map and diagram set pieces) while every character, script and drawing is **ours**. Structure and
pacing come from `history-style-report.md`; the code is `studio/history/cast.py`.

## No fixed cast

There is no recurring cast and no host. Every character comes from the script: each one gets a short description
(role, age, gender, era costume, face traits) and is drawn from it by `studio/history/figures.py`. A name nobody
described is drawn from its own words, and a scene that needs someone but names nobody uses a generic bystander
(`cast.GENERIC`). Voices come from the description too (`speech_audio.voice_from_spec`), stable per name.

## Historical figures

Built from the same body: `cast.build_svg(body, headwear, prop, badge)`.

- **Faction colour**: one colour per side for the whole video (`faction_color(n)`), also used for map flags.
- **Letter badge** on the chest so similar figures stay distinguishable.
- **One headwear and one prop** (`HEADWEAR`, `PROPS`) per figure, kept for the video.
- **Never a real likeness**; no photographs of living people. Archive images only for places, documents and objects,
  at most one per chapter.
- **Atrocity, death and torture** are never drawn: cut to a map, a silhouette or a title card, and say the
  human cost in one plain sentence.
- **Invented dialogue is tone only**; real quotes go in the narration with a source; disputed claims get a "?"
  above the speaker.

## Scene types and staging

`skit` (2-4 on-screen speech lines, at most 10 words each), `map` (political
map, arrows, flags, place label timed to the narration), `diagram` ("how X worked" in 3-5 numbered steps),
`easel` (a list or chart on an easel), `archive` (one still, 2-3 s), `calendar` (time passing, days crossed out),
`silhouette` (violence or loss without detail), `title` (chapter card). Older scripts that say `lectern` are drawn as a
`title` card.

Segments may carry optional keys `scene`, `cast`, `staging`, `speech`. They are optional, so old scripts and other
channel types are unaffected. For history, `cast_scenes` is on by default and `cast.scene_problems` reports:
unknown scene types, a skit with no cast, more than 4 speech lines, speech over 10 words, speech outside a skit, and
three of the same scene in a row (maps and diagrams excepted).

## How it plugs into the repo

- The prompts for `script` and `story_plan` get a `{cast_block}` (depiction rules, scene keys) only when
  the profile has `cast` (history today).
- Characters use the existing sprite contract (`studio/kids/sprites.py`: `eyes-open`, `eyes-closed`, `mouth-closed`,
  `mouth-open`) so `SpriteBank(user_dir=...)` can blink and lip-sync them.
- Rendering is the next step and is not in this change: a 2D history scene renderer would compose sprites,
  backgrounds and speech text per `scene`, using `render2d` for maps and diagrams. Until then the visuals stage
  keeps using `visual_intent` and stock or 2D scenes.
