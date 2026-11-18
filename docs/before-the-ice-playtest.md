# Before the Ice Goes Out: the playtest kit

The seed sweep can count endings, but it can't say what a week feels like. A playtest answers three questions:

1. **Does the town closing in read without a meter?** Do players feel watched, and can they say by whom and why?
2. **Do the odds feel fair?** When Gilchrist comes for them, or takes someone else, does it feel earned or arbitrary?
   Lying low ends in arrest on about 15 seeds in 24; is that tense or punishing?
3. **Do players tell their week as a story?** The research's honest measure is the retelling: ask players to tell
   their week in their own words, and compare that with what actually happened.

Each session takes about an hour: 40 minutes playing, 15 talking, a few minutes reading the record.

## What you need

- The game, either way:
  - **In a browser**, for a friend anywhere: <https://thespis-production.up.railway.app/ice/?seed=19>, with the seed
    in the link. Nothing to install. Watch them on a video call with their screen shared. Tell them to keep the
    game's tab in front: a browser pauses a tab it isn't showing.
  - **From this repo**: `godot --path games/before-the-ice -- --seed=<N>`. Thespis starts as a sidecar, as for
    `tools/week.tscn` (`$THESPIS_SIDECAR`; see the game's README).
- **No model, for now.** Offline, the town speaks its written lines and the minds are deterministic, so two players
  on one seed meet the same town. With a model the lines vary, which tests something else.
- This page, and a copy of the notes sheet below for each session.

When the ice goes out, the game writes **the week's record**: a page to read, and the same as JSON.

**In a browser** the record goes to the server instead, sent again each phase, so a closed tab still leaves the week
up to its last phase. List them and fetch one with the admin token (`ADMIN_TOKEN`, in `.env`):

```
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://thespis-production.up.railway.app/ice/records
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://thespis-production.up.railway.app/ice/records/<name>.md
```

A name is `<date>_<time>-seed<N>-<four digits>`; the time is the player's own clock.

**From the repo**, if the player stops early and closes the window, it writes what there was. The path is printed,
and on Windows it is:

```
%APPDATA%\Godot\app_userdata\Before the Ice Goes Out\playtest\<date>_<time>-seed<N>.md   (and .json)
```

`-- --log=<dir>` writes it somewhere else; `-- --log=none` writes nothing. The record holds:
- what the seed drew;
- each phase: where Anton went and who saw him, what he said and did, what he heard;
- what was said where he wasn't (Věra to Gilchrist, Martha's statement, Tamás's last choice);
- the news;
- each morning: what Gilchrist believed and how sure, what he had done (asked, warned, searched), and each person's
  trust in Anton;
- each morning, the pressure on Anton against the day's target, and what the director brought out, if anything;
- the ending, and the Inspector's Notebook.

## The seeds

Give every player **seed 19 first**, so the sessions can be compared, and then, if they play again, one of the
others. Don't tell players what their week holds. The endings are from the sweep with the pressure director (#175)
and show how open each week is.

| Seed | The week (for you, not the player) | Lie low | Alibi, sit with Tamás, keep Věra |
| --- | --- | --- | --- |
| **19** | A plain week. Brand blames his watchman's lamp; Tamás sees Anton's face on day 5. Every way of playing ends differently | arrest | nobody |
| 12 | Tamás remembers early (day 3). Downriver they say Brand burned his own book; only Otto saw the lantern. Nearly every way of playing ends in arrest | arrest | arrest |
| 21 | Maggie has heard the wood boy was at the back door, and Věra and Maggie talk. A careful week ends with Billy taken: a boy goes south for Anton | arrest | Billy taken |
| 2 | The fever week: Tamás sees Ashby's face on day 4, and is sure. Ashby goes south whatever Anton does, unless he confesses. Does the player notice, and how do they feel about it? | Ashby taken | Ashby taken |
| 7 | Věra saw his lantern come back, and Martha saw his face. Lying low, Věra gives herself up for him; a careful week sends Ashby south instead | Věra taken | Ashby taken |
| 3 | The hard week: Martha saw his face, and she talks with Maggie. The town knows by the third day | arrest | nobody |

Spare: **seed 20**, a quiet week. Tamás never remembers, and lying low is safe; useful against a player who found
the others unfair.

## Running a session

**Before.** Read the player this, and nothing more:

> You are Anton Holub. Four nights ago you set fire to Otto Brand's store, to burn the notes that would have taken
> your sister's claim. The night watchman was inside, asleep, and he was burned. An Inspector of the Mounted Police
> has come over the ice to find out who did it. When the ice goes out, in five days, he leaves on the first steamer,
> with someone or with no one. Get through the week.

Don't explain the town, Thespis, or how anything works. If they ask what to do, say "whatever Anton would do".

**During.** Sit beside them and keep quiet. Note the time (the clock on the screen, "Day 3, afternoon") whenever they:
- say something about being suspected, or about who knows what;
- look lost, or ask a question;
- are surprised;
- change plan.

Thinking aloud is welcome but not required; don't prompt for it.

**After: the retelling first.** Before any other question, and before anyone opens the record, ask:

> Tell me the story of your week, as you'd tell it to a friend who hasn't played.

Let them talk; record it if they agree. Then the questions on the notes sheet.

**Then the record.** Open the week's record and go through it with them for five minutes: "Here's what Gilchrist
believed each morning." Note what surprises them; that is what the Notebook will need to show.

**Send me** the record (.md and .json) and the notes sheet. I'll set each retelling beside what actually happened.

## Notes sheet

Copy this for each session.

```
Player:                     Seed:            Date:
Played before? (games like this / this game)
Minutes played:             Ending:          Stopped early? at:

DURING (time on screen, what happened, what they said)
-
-
-

THE RETELLING (their words; or "recorded")


QUESTIONS
1. When did you first feel watched? By whom?
2. Who do you think talked about you, and to whom?
3. Why did Gilchrist do what he did at the end?
4. Was there a moment you could have changed how it ended? Which?
5. Who in town do you remember? What did they want?
6. Did anyone surprise you?
7. Was anything confusing, or did anything feel unfair?
8. Would you play again? What would you try?

1 to 5:  tense ___   fair ___   clear what was going on ___   want to play again ___

AFTER THE RECORD
What surprised them in it:
What they missed that mattered:
```

## What I'll look for

- **The retelling against the record.** Did they name the moment that turned Gilchrist (a statement, a search, a
  lie caught), or a different one? Did they notice the people who pulled away from them (trust each morning)?
- **Where they felt watched**, against where the record shows Gilchrist's case grew.
- **Wrong-man endings.** Did a player who saw Ashby, Otto, Billy or Věra taken understand why? Did it land as relief,
  guilt or confusion?
- **What they missed that mattered.** That list is the Notebook's brief, step 4 of the build order. The odds and the
  pressure (step 3) get tuned from the ratings and the retellings.
