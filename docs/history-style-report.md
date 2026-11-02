# History channel: reference style report

Three reference videos were analysed for **structure, pacing and staging only**. Nothing here (jokes, wording,
scripts, character designs, art) is to be copied; the history channel uses its own cast, scripts and art
(see `history-cast-system.md`).

| Short name | Video | Length | Format |
|---|---|---|---|
| OS-WW1 | WW1 "Oversimplified" Part 1 | 6:24 | comedic, map-driven, one narrator |
| EH-Genghis | Genghis Khan "Extra History" Part 1 | 9:55 | dramatic, character-driven, one narrator |
| OS-Punic | Second Punic War "Oversimplified" Part 1 | 28:14 | comedic, cast scenes with voiced skits plus narrator |

## How it was measured

- Frames: contact sheets across each video, plus the last 12 seconds of each.
- Cuts: PySceneDetect content detector (threshold 27, min 8 frames). Dissolves and pans inside one drawing are not
  cuts, so true "visual change" rate is a little higher than shown.
- Words per minute: local Whisper `base.en` (int8) over 20-second chunks. Whisper hallucinated repeats in a few
  music-heavy chunks, so WPM is a range, not a point. Spoken pace is lower in OS-Punic because skits breathe.
- Loudness: ffmpeg `ebur128` (integrated LUFS, loudness range).
- Not measured: music identity (only EH-Genghis credits name its tracks), exact stinger timing, voice pitch.
  Check those by ear before locking the audio defaults.

## Numbers

| | OS-WW1 | EH-Genghis | OS-Punic |
|---|---|---|---|
| Cuts per minute | 16.1 | 8.9 | 7.8 |
| Median shot | 2.8 s | 4.4 s | 5.1 s |
| Mean shot | 3.7 s | 6.8 s | 7.7 s |
| Shots under 2 s | 37% | 7% | 18% |
| Shots over 10 s | 3% | 13% | 19% |
| Narration pace | about 165-185 wpm | about 150-170 wpm | about 140-160 wpm (narrated parts about 160) |
| Integrated loudness | -26.7 LUFS | -18.8 LUFS | -19.8 LUFS |
| Loudness range | 8.9 LU | 2.8 LU | 4.3 LU |
| Burned-in captions | none | none | none (only in-world speech lines, see below) |

YouTube normalises loudness, so OS-WW1's -26.7 is a quiet upload, not a target. Our pipeline masters to -14 LUFS.

## Structure

### EH-Genghis (dramatic)

1. **Cold open (0:00-0:30)**: one dramatic image of the ending of the story's first scene ("a young woman gives
   birth on a hillside... he would grow up to be Genghis Khan"). It states the stakes and the promise in two
   sentences.
2. **Rewind (0:30-2:00)**: "the story truly begins with his mother". The story starts one generation earlier, with a
   human decision (a sacrifice), not with dates.
3. **Chapters of roughly 60-120 seconds**, each a small complete scene with a turn: abandonment, survival, a friend
   (blood-brother oath), a betrayal inside the family, capture and escape, a marriage and a strategic gift.
4. **Ending (9:00-9:40)**: calm ("his troubles must have seemed far behind him"), then a hard turn: a new enemy
   comes for his wife. It stops mid-crisis. Then credits, patrons and a "next part" card.
5. **Open loops**: the opening promise (he will unite the tribes) stays open for the whole part. Smaller loops are
   planted as a person's problem and paid off within one or two chapters (a danger, then the escape).
6. **Explanation is handled as a custom or rule** ("alliances were forged in blood, not ink"), spoken as a short
   aside that makes the next decision make sense.

### OS-WW1 and OS-Punic (comedic)

1. **Cold open (0:00-0:20)**: a joke-framed, compressed summary of the situation ("the world in 1914... let's have a
   war"), or a short in-world skit (OS-Punic opens on an "appreciation day" for mercenaries who were not paid).
   The cold open states the problem, not the date.
2. **Title card** after the first scene (OS-Punic: after about 40 seconds).
3. **Chapter by cause and effect**, each one a small chain: who wants what, what they do, what goes wrong.
   Alliances and causes are explained as a "who is friends with whom" run, with a map and flag icons.
4. **Alternating beats**: narrator explains (map, flags, arrows) -> characters act the moment out in a skit with
   2-4 spoken lines -> narrator draws the consequence in one dry sentence -> next skit.
5. **Informational set pieces** break up the story: "how trench warfare works" (diagram, 4 steps), a "spot the
   difference" quiz about uniforms, a chart or easel listing "examples of X".
6. **Ending**: a cliffhanger that names the next part's threat ("a monster loose in their territory"), or a sombre
   still image (cemetery) with a "Part 2:" end card and a click-through.
7. **Sponsor**: OS-Punic carries a sponsor read at 0:00 and a mid-roll at about 10:30. The channel profile leaves
   sponsor slots out by default; they are an owner choice.

## Hook patterns worth reproducing (as patterns)

| Pattern | What it does | Seen in |
|---|---|---|
| `absurd_summary` | one-breath, tongue-in-cheek compression of why everyone is about to fight | OS-WW1 |
| `scene_cold_open` | start inside a small in-world scene with a conflict already running | OS-Punic |
| `birth_of_a_legend` | open on a human moment, then name who this will become | EH-Genghis |
| `rewind_to_the_cause` | after the hook, step back to the person or event that explains it | EH-Genghis |

## Pacing model

- **Comedic (OS)**: a new visual about every 3-5 seconds, with a flash of 1-2 second reaction shots; a joke or
  surprise about every 10-15 seconds; an information beat every 30-45 seconds.
- **Dramatic (EH)**: a character pose or prop change about every 4-5 seconds; a decision or turn every 20-30
  seconds; a chapter end every 60-120 seconds; narration over a soft, steady music bed.
- **Common**: never more than 40 seconds of pure explanation; every chapter ends on a turn; the story is always
  about someone wanting something.

## Narration and humour

- **OS**: modern, casual register applied to old events; running understatement; the narrator is a character with
  opinions. Sentences are short to medium; many sentences end on the turn. Humour comes from contrast (modern
  language vs old events, big claims vs small causes). This is **register**, not material: never reuse a joke.
- **EH**: warm, earnest, third-person storyteller. Longer sentences that end on a small beat ("...and he lived and
  worked with them for several years."), emotional anchors ("breath and smell are part of a person's soul").
  Humour is rare and gentle; cultural context is explained as a custom.
- **Both**: concrete nouns, named people, time jumps are flagged, causes before consequences.

## Visual style

- **Characters**: simple flat vector bodies with big hands and expressive faces. EH-Genghis puts a **letter badge**
  on each character's chest (H, Y, T...) so viewers can tell similar figures apart; the host stands at a lectern
  between chapters. OS gives each nation or faction a colour, flag or headwear.
- **Maps**: coloured political maps with zoom, arrows, flag icons for armies, a place-name label that appears as
  the narrator says it. A satellite-style map for travel and terrain.
- **Props as icons**: a coat, a shovel, earrings, a calendar being crossed out for passing time, a button panel for
  "choices", an easel with a list, a banner with a town name. One prop = one idea.
- **Archive cutaways**: one old photograph or drawing, held 2-3 seconds, to ground a claim.
- **Backgrounds**: pale plain background for intimate scenes, painted landscape for travel or war, dark vignette for
  a dramatic close-up.
- **Captions**: no burned-in subtitles. Speech lines in skits appear as short on-screen text next to the speaker.
  Name labels appear when a person is introduced.
- **Motion**: slow push-ins, pans across a map, characters slide in. No heavy 3D. A fully static still never lasts
  over 6 seconds in the comedic format.

## Sound

- Narration is the loudest element in every video; EH-Genghis keeps a very steady loudness range (2.8 LU),
  OS-WW1 has the widest (8.9 LU) because skit lines and effects are louder than the narrator.
- A music bed sits under narration. EH-Genghis lists library-style cues in its credits (instrumental, folk-epic);
  that is the target mood for dramatic parts.
- Silence: short beats before a punchline or a reveal (typically 0.3-0.7 s).

## Comparison

| Aspect | Comedic (OS) | Dramatic (EH) |
|---|---|---|
| Goal of each scene | a joke or a surprise that also teaches a cause | a human decision with a cost |
| Narrator | opinionated, modern register | warm, earnest storyteller |
| Cuts per minute | 8-16 | about 9 |
| Visual unit | map + icons + character skits | character pair + prop + occasional map |
| Open loops | "wait, what happens next" with a punchline | "what will this child become" |
| Chapter ending | a punchline that turns into a threat | a reversal or a crisis |
| Ending | cliffhanger + "Part 2" card | cliffhanger + credits + next part |
| Risk | information dump between gags | dragging between decisions |

## What the pipeline must reproduce

1. A cold open that states a problem or promise in 20 seconds, then a rewind or title card.
2. Chapters of 60-120 seconds, each ending on a turn that the next chapter answers.
3. A recurring cast (narrator, host, 4-6 original characters) plus historical figures built from the same body
   system, with badges or colours so viewers can tell them apart.
4. A visual change every 3-6 seconds, a map or diagram every 45-60 seconds, one archive image per chapter at most.
5. Information beats ("how X worked") as short numbered diagrams.
6. A part-style ending with a named next threat.
7. Facts that stay exact: this channel's fact ledger, source list and disputed-point labels still apply.

The numeric values are in `studio/story/profile.py` (`PACKS["history"]`), the prompts in `studio/prompts/history/`,
and the cast in `studio/history/`.
