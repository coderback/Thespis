# Tuning: the numbers that decide outcomes

Whether an NPC acts on something comes down to how sure it is. This page says where that number comes from, how
it changes as a story travels and meets other stories, and which knobs in the game file move it. The rules
themselves are in the [protocol](protocol.md); here they are worked through with numbers. Every number below is
what the engine gives.

## How sure a belief starts

A belief's confidence is between 0 and 1: what `inspect` shows as `opinion.b`, and what a choice's
`{believes = ..., min = ...}` compares against.

| How the NPC learned it | Confidence | Knob |
| --- | --- | --- |
| It saw it (a witness, actor or target of `observe`) | 1.0, certain | |
| Told face to face (`observe(..., said=True)`) | By its trust in the speaker: **0.9** at trust 2 or more, **0.4** at 0 or 1, **0.2** below 0 | `trust_in`; or the call's `conf` |
| Gossip, without ties | The teller's confidence × `decay` | `[gossip] decay` (0.8) |
| Gossip, along a tie | The teller's confidence × what its trust in the teller gives (the row above) × the tie's carry | `trust_in`, `[gossip] along` |
| Gossip, standing with a tied teller | As along a tie, with `in_person` as the carry | `[gossip] in_person` (0.8) |

Trust runs from -5 to 5 and starts at 0 unless `trust_in` says otherwise. A stranger's word is worth 0.4.

`observe(..., said=True, conf=0.7)` overrides the trust ladder for every hearer. Use it when your engine already
rolled for persuasion: the dice decide how far the statement is believed, not the speaker's reputation.

## How far a story travels

A gossip passes on only what it holds at or above `[gossip] threshold` (0.5 unless given), so every story fades
out after a number of mouths.

**Without ties** (`decay = 0.8`): 1.0 (the witness), 0.8, 0.64, 0.51, then 0.41, which isn't passed on. A witness's
story can pass through four mouths beyond them. Only the NPCs in `gossips` pass news on, to whoever stands with them.

**Along ties, with trust.** In the [quickstart](../examples/quickstart/game.toml), Wat sees the player steal from
Mara. Edda is Wat's kin (carry 1.0) and trusts him at 2 (0.9). Mara is Edda's friend (carry 0.9) and trusts her
at 2 (0.9):

| Tick | Wat | Edda | Mara |
| --- | --- | --- | --- |
| 0 | 1.0 (saw it) | | |
| 1 | 1.0 | 1.0 × 0.9 × 1.0 = **0.9** | |
| 2 | 1.0 | 0.9 | 0.9 × 0.9 × 0.9 = **0.73** |

Down a chain of friends at trust 2 (0.81 a step), a story goes 1.0, 0.81, 0.66, 0.53, then 0.43, and stops.

**Along ties, without trust.** At trust 0, a listener believes a tied teller at 1.0 × 0.4 × 1.0 = **0.4**: it
hears the news and goes no further, because 0.4 is under the threshold. So in a town where nobody's `trust_in` is
set, gossip along ties stops after one mouth. This is the most common surprise. Either:
- set `trust_in` where people trust each other (family, friends, a guild), so stories travel where trust does; or
- lower `threshold` to 0.4, so anyone passes on what they heard from someone they don't distrust. Then the next
  mouth is at 0.16, so a story still dies quickly where nobody trusts anyone.

**What travels first.** Each tick a gossip tells each listener one thing they haven't heard: the highest
`priority` predicate first, then the surest. `about` limits whose news travels at all (`"everyone"`, or a list of
ids; the player by default). `most` caps how many things the whole town tells per tick, so news in a big town takes
its time.

## When stories meet

**Independent stories add up.** Reports that go back to different people are fused as independent evidence
(subjective logic's cumulative fusion), so each one makes the NPC surer:

| Reports, each from a different witness | Belief |
| --- | --- |
| 0.4 and 0.4 | 0.57 |
| 0.4, 0.4 and 0.4 | 0.67 |
| 0.64 and 0.64 | 0.78 |
| 0.9 and 0.4 | 0.91 |

**One story counts once.** A report is weighed by whose story it is: whoever saw it or first said it, however many
mouths it passed through. Three gossips repeating one witness count as one report: the strongest of the three.

**A second witness.** By default a listener is told each thing once, by whoever reaches them first. With
`[gossip] corroborate = true`, a teller whose story goes back to a different witness tells them too, and the two
fuse as in the table above.

**Disbelief.** A report that something didn't happen (a denial, or the losing side of a conflict) counts against
it. 0.9 for and 0.4 against gives belief 0.84, disbelief 0.06.

## When stories conflict

`[claims] one_actor = ["stole_from"]` says a theft has one thief, so an NPC told two people did it keeps one story.

**The more trusted source wins.** What the NPC saw itself beats anyone's word. Otherwise its trust in each story's
best teller decides. With `[claims] first_hand = 3`, a teller who saw it counts for 3 more than one who only heard
it. A tie in trust settles nothing: both stories stay.

**Whoever started the losing story pays.** The NPC's trust in them falls by `[claims] caught` (2 unless given), and
everything else they told it is capped at the confidence their new trust gives (the ladder above). Someone who only
passed the story on keeps their trust.

**The loser is retracted.** The winning side's word counts against the losing story, at least as strongly as the
NPC still believed it.

Worked through, in the quickstart: after two ticks Mara believes the player robbed her at 0.73, from Edda. Then the
player tells her Wat did it.
- Mara trusts the player at 0, so the lie arrives at 0.4.
- Edda (trust 2) beats the player (trust 0), so the lie loses.
- The player started it, so Mara's trust in them falls from 0 to -2. The lie is capped at 0.2, what trust -2 gives.
- Edda's 0.73 counts against the lie, which ends retracted: belief 0.06, disbelief 0.68.
- Had the player lied before the story reached Mara, she'd have believed it at 0.4, enough for a choice with no
  `min`, until Edda's version arrived.

## From belief to action

- **`{believes = claim}`** in a choice's `when` holds for any active belief, however weak. Add `min` when a rumour
  shouldn't be enough: `{believes = {...}, min = 0.6}` needs a trusted teller or two independent stories.
- **Feelings** (`[npc.<id>.feels]`) move drives by the step given, scaled by confidence and rounded: `{grudge = 6}`
  moves grudge by 5 at 0.9 and by 2 at 0.4.
- **Drives** then score choices through `utility`. `settle` brings a drive back one step a tick toward its resting
  value; `decay` fades it by half-lives (`grudge = {to = 0, half_life = 2, keep = 0.25}` takes 6 to 4, 3, 2, and
  holds).

## Recipes

| You see | Try |
| --- | --- |
| News never spreads past the first listener | Set `trust_in` along the ties, or lower `threshold` to 0.4 |
| News reaches everyone, too fast | Raise `threshold`; lower `decay` or the `along` carries; cap `most` |
| One rumour is enough to turn an NPC | Add `min` to the choice's `believes`, so it needs a trusted teller or two stories |
| Lies are believed too easily | Strangers are at 0.4; start key NPCs at a negative `trust_in` for the player (0.2) |
| A liar is never found out | Add the deed to `one_actor`, and make sure a trusted witness's story can reach the NPC |
| Being caught once ruins a character for good | Lower `caught` to 1 |
| Witnesses lose to well-trusted gossips | Set `first_hand` |
| The wrong news travels first | Raise its predicate's `priority` |

## Check your numbers

Play the scene in a test and read the minds: `observe`, `tick`, then `inspect(npc)["beliefs"]` gives each belief's
opinion and the evidence behind it, `explain(npc, moment)` says which choices are open, what keeps the others
shut and how each scores, and `trace(claim)` shows a story's next hops with their sums and where it stops. [tests/test_one_story.py](../tests/test_one_story.py) is a scene written that way.
`thespis check game.toml` catches a misspelt knob before you start.
