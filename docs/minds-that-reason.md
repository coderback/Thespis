# Minds that reason: a design for Thespis

*A proposal for review, 18 November 2026. Nothing here is built yet.*

Thespis gives an NPC a mind and a voice. The mind remembers what it saw and was told, believes it as far as it trusts
the teller, gossips, keeps secrets, catches lies and chooses among the actions a game declares. What it can't do is
put two things together. Every conclusion an NPC reaches today is one a game's author wrote out by hand. This doc
proposes how NPCs could reason for themselves, across many kinds of game, without handing their decisions to a
language model.

## Why

**What the playtest build of Before the Ice Goes Out shows.** Inspector Gilchrist looks shrewd because we wrote
every conclusion he can reach into his choices:
- "No account of where he was, and a lantern in the lane" opens his warning.
- "Said he was in bed, and someone says the back room, and a story pointing his way" lets him take Otto.
- Billy needed his own copy of that rule, and Anton his own again.

So he can't conclude anything we didn't foresee. If Maggie lied about her evening, he'd never notice. His reasoning
is invisible, so the player sees a man change behaviour, not a man think.

**What makes an NPC feel like a machine.** From the research ([redefining-the-npc.md](redefining-the-npc.md)) and the
craft review for Before the Ice:
- it only reacts;
- it concludes too fast, or knows too much;
- every character reasons the same way;
- it never notices the player's habits;
- it never changes its mind, or changes it without a sign of doubt;
- its thinking can't be seen.

Players don't judge a mind by how hard it thinks. They judge it by signs that it has one: it wants something, it
puts things together, it gets things wrong in its own way, and it lets you see a little of how.

**What stays fixed.** The rule the architecture already follows: the game writes, the model reads. A language model
may voice a line, read the player's words and suggest an idea, but it never decides what an NPC believes or does.
Models are good at stating a mental state and poor at acting on it (SimpleToM: 95.6% against 49.5%), they can't be
replayed, and they would break the fair-play guarantee a mystery needs.

## Principles

1. **Rules decide; the model voices.** Every conclusion comes from a rule in the game file applied to beliefs the NPC
   holds. The model may phrase it, and may propose an idea for the rules to check.
2. **Fair.** An NPC concludes only from what it saw or was told. The ledger's truth is never consulted. Every
   conclusion keeps its reasons.
3. **Bounded, so human.** Limited attention, a depth limit, forgetting and biases. A perfect reasoner reads as a
   machine; a fallible one reads as a person.
4. **Data, and reusable.** Rules live in the game file, written once for anyone. A game can start from shared
   reasoning packs (who did it and why, theft, threat, courtship) and add its own.
5. **Deterministic.** The same seed makes the same thoughts, so tests and seed sweeps keep working.
6. **Visible.** Every conclusion can be explained, traced and voiced.

## The layers

Six layers, each usable alone, each building on the ones before it. Syntax is a sketch for review, in the style of
the existing game file ([protocol.md](protocol.md)).

### 1. Inference, with variables

**What.** An NPC that believes these comes to believe that, for anyone. A variable (`{x}`) stands for whoever fits,
and the same variable must mean the same person everywhere in the rule.

```toml
# Two places at once: whoever is said to have been in two places at the same hour lied about one of them.
[[infer]]
name = "two_places"
from = [{ believes = { pred = "was_at", a = "{x}", place = "{p}", at = "{t}" } },
        { believes = { pred = "was_at", a = "{x}", place = "{q}", at = "{t}" } },
        { differs = ["{p}", "{q}"] }]
then = { pred = "lied_whereabouts", a = "{x}" }

# A liar with a story pointing his way: a suspect.
[[infer]]
name = "suspect"
from = [{ believes = { pred = "lied_whereabouts", a = "{x}" } },
        { any = [{ believes = { pred = "lantern", a = "{x}" } }, { believes = { pred = "fired", a = "{x}", b = "otto" } }] }]
then = { pred = "suspect", a = "{x}", b = "fire" }
strength = 0.8
```

**How it works.**
- **Matching.** A variable matches any value of that field among the NPC's active beliefs. Conditions are joined on
  shared variables. `differs`, `same` and comparisons (`{ before = ["{t}", "{u}"] }`) test bound values.
- **How sure.** A conclusion is subjective-logic deduction from its premises: belief falls with the weakest premise
  and the rule's `strength`, and uncertainty grows with each step. A three-step chain of "likely"s ends "not sure",
  as a person's would.
- **It's evidence like any other.** A conclusion is held with source `inferred` and its premises as its origin. It
  fuses with anything the NPC was told about the same claim: a suspicion and a rumour add up.
- **When.** Forward chaining after each tick's gossip, and again when a belief changes, to at most 3 steps. Each NPC
  has an attention cap, a number of rule firings per tick. The night between days runs deeper (layer 5).
- **Withdrawn when its reasons go.** If a premise is retracted, or falls below its rule's threshold, the conclusion's
  evidence is withdrawn too. If the NPC was caught believing a liar, what it concluded from the lie unravels.
- **Theories aren't facts.** A conclusion isn't gossiped as fact. With `shares = true`, the NPC passes it on as its
  opinion ("I reckon it was Otto"), along ties at half weight.
- **Choices can use variables too.** `do = "take:{x}"` with `when = [{ believes = { pred = "suspect", a = "{x}" } }]`
  is offered once for each `{x}` that fits, scored separately. The per-person copies of today's rules collapse into
  one.

**What it shows.** `explain` gives the chain: "suspects Otto Brand: he said his bed (from Otto, day 4); Maggie says
the back room (from Maggie, day 2); two places at once; Martha says Brand burned his own book." `trace` shows
`inferred` links beside told ones.

**Across games.**
- **Stealth or heist:** a door open that should be shut, and a key gone from its hook, means an intruder in that wing.
- **Fantasy village:** a missing hammer, and the apprentice seen near the forge, means the apprentice is suspected.
- **Strategy or diplomacy:** troops massed at a border, with no war declared, means they intend to attack there.
- **Romance or drama:** two people seen together twice, and one avoiding me since, means they're close.

### 2. Personality in reasoning

**What.** The same facts, different minds. Each NPC carries a few numbers for how it reasons, and they can move with
its drives.

```toml
[npc.sandor.reasons]
leap = [0.3, { drive = "anger", weight = -0.02 }]   # how little support he needs to conclude (default 0.6)

[npc.gilchrist.reasons]
leap = 0.7                     # careful: he wants it solid
confirms = 0.1                 # but evidence for his leading theory weighs a tenth more

[[npc.vera.reasons.holds_back]]   # she won't let herself conclude it about her brother while she loves him
about = "player"
when = [{ trust = "player", gte = 3 }]
```

**How it works.**
- `leap` is the confidence a conclusion needs before the NPC holds it.
- `confirms` adds weight to evidence for whichever explanation leads (confirmation bias, layer 3).
- `holds_back` stops conclusions about someone while its `when` holds. The premises are still believed; only the
  conclusion waits. This is denial, not secrecy: `keeps` closes the mouth, `holds_back` closes the mind.
- When `holds_back` stops holding, everything it held back forms at once, and Thespis writes an event for it. The
  moment "it all came together" is visible and can be voiced.

**What it gives.**
- Sándor goes from a rumour to a fist.
- Gilchrist waits until it's solid, then is hard to shake.
- Věra believes every piece and refuses the whole until Anton loses her.
- Billy, frightened, concludes threats fast.

Most of what reads as alive comes from this layer, and it's a few numbers on shared rules.

### 3. Competing explanations, and curiosity

**What.** A thinker holds several explanations for something that happened, weighs them, acts on the leader, and
goes looking for whatever would settle it.

```toml
[[npc.gilchrist.questions]]
about = { pred = "fired", a = "{x}", b = "otto" }   # who set the fire
candidates = "suspect"                              # anyone he holds a suspect(x, fire) belief about, and "accident"

[[npc.gilchrist.choices.rounds]]
do = "ask:{whom}"
utility = [{ wants = "{whom}", weight = 4 }]        # what an answer from them is worth to him, 0 to 1
```

**How it works.**
- **The ranking.** A question keeps its candidates ranked by support, for and against: each candidate's conclusions
  from layer 1. The leader can be used in choices: `{ leads = "fired", who = "{x}" }`.
- **When the lead changes, it shows.** Thespis writes an event, so the NPC can be heard changing its mind: "I had it
  wrong about Ashby."
- **Curiosity is value of information.** Which claim the NPC doesn't hold, if it learned it, would most separate the
  top two candidates? Then who, by what the NPC believes, would know it: people it believes were there at the hour.
  `{ wants = "{whom}" }` scores that.
- **Fairness.** Gilchrist can only seek a witness he believes was there, so curiosity uses what he knows, never the
  ledger.

**What it gives.**
- Today we write each of Gilchrist's rounds by hand. With this, he goes to the sister because her answer would
  settle the alibi, and to Martha because someone said she saw the lane.
- His evening question becomes the one he most needs answered.
- The Notebook can show his ranked theories, not a list.

**Across games.**
- **Stealth:** a guard checks the spot that best tells "rat" from "intruder".
- **Strategy:** a rival sends scouts where your army's purpose is least clear.
- **Village:** a sheriff asks around in the order that would clear the most suspects.

### 4. Beliefs about beliefs

**What.** "He knows I know." Lying, bluffing, keeping a secret on purpose and setting a trap all need an NPC to hold
beliefs about what someone else believes.

```toml
when = [{ believes = { pred = "knows", a = "player", claim = { pred = "lantern", a = "player" } } }]
```

**How it works.**
- **What nests.** A claim can hold a claim (`knows`, `suspects`, `told`), two deep at most. Depth three and beyond
  collapses in people and models alike (FANToM: 26.6%).
- **Where they come from.** Witnessing a statement: you saw her tell him, so you believe he knows. Your own
  statements: you told him, so he knows you believe it. Inference rules.
- **A trap is a rule.** Someone who corrects a detail nobody had told them knows more than they should. Gilchrist
  says the fire started at the front. If Anton corrects him, Anton showed he knows it started at the back door, and
  only the arsonist does. This is Columbo's "one more thing", fair because it's built from what was said aloud.
- **Lying gets sharper.** An NPC won't lie to someone it believes knows the truth, and can tell a lie that fits what
  the listener already believes.

**Across games.**
- **Diplomacy:** "they think we're weak", so feint.
- **Romance:** "she thinks I'm angry with her".
- **Heist:** the guard suspects you know the patrol route, and changes it.
- **Card games and bluffing:** reading what an opponent thinks you hold.

### 5. Intentions that last, and the night's reflection

**Intentions.** Today an NPC makes one choice at a time by utility. People pursue something for days.

```toml
[[npc.sandor.intends]]
goal = "find:{x}"
when = [{ believes = { pred = "fired", a = "{x}", b = "otto" }, min = 0.4 }, { drive = "anger", gte = 5 }]
until = [{ with = "{x}" }]
drops = [{ not = { believes = { pred = "fired", a = "{x}", b = "otto" } } }]
```

- **How it works.** While an intention holds, its binding lifts the choices that serve it (`{ intends = "find:{x}" }`
  in a utility term). It ends when `until` holds and is dropped when `drops` does. Both are events, so "I'm looking
  for the stranger" and "I was wrong to go after him" can be said.
- **What it gives.** Commitment with a reason to stop, the minimal form of the planner the research roadmap proposes.
  It can grow into that planner later.

**The night.** Between days each NPC reflects:
- inference runs to full depth;
- trust moves on patterns: someone caught twice is trusted less than twice as little;
- weak, unused beliefs fade;
- if its leading explanation changed, it writes one thought event. That gives the morning visible changes of heart
  ("I've been thinking about what Billy said"), and a cheap place to spend reasoning: NPCs far from the player can
  reason only at night.

**Noticing the player.**
- The player's habits become beliefs: counts of where they go and whom they visit, held as
  `habit(player, visits, mission)` once past a threshold.
- Choices and lines can use them: "You sit with the watchman a great deal, Mr Holub."
- Nothing makes a world feel more awake than being noticed. It's the same machinery, pointed at the player.

### 6. Showing the thinking

Reasoning nobody sees reads as randomness.
- **Lines cite reasons.** The state pack for a line can carry a conclusion's chain, so the model says "You said your
  sister's. She says half past eleven." Offline, a line template takes `{because}`, filled from the chain. The claim
  check accepts a line that cites a conclusion only if the line agrees with its premises.
- **Changes of mind are events.** Layers 2, 3 and 5 write them, so they can be voiced, noticed and put in news.
- **The Notebook's "therefore".** An ending can be told as the chain that led to it: "His sister says he left at half
  past eleven. Mrs Matthias saw a lantern at one. Therefore…". Every ending traced to a moment the player could
  have seen, which is what the sifted Notebook is for.
- **The inspector** shows each NPC's questions, candidates, leader and intentions.

## The model's place

- **Voice.** Turning a reasoning chain into a line in character.
- **Ear.** Reading what the player types into the game's acts.
- **Imagination, checked.** Optional, budgeted, cached.
  - A `propose` call asks the model for explanations an NPC might entertain, each with the beliefs it thinks support
    it: "the stranger and Otto were in it together".
  - Thespis keeps a proposal only if the NPC holds those beliefs and they support it at the NPC's `leap` by the
    game's rules. Kept ones join the NPC's candidates with source `imagined`; the rest are dropped.
  - Creativity without unfair leaps. With no model, or on replay, nothing is imagined and everything else still runs.

The model never sets a belief, a trust, a flag or a choice.

## Cost and scale

- **Indexed.** Matching uses the per-predicate lookups the engine already keeps for scans (0.3.0).
- **Bounded.**
  - Rule firings per NPC per tick (the attention cap), and a depth of 3 by day and full depth at night.
  - Distant NPCs reason only at night, the level-of-detail idea from the research roadmap.
- **Incremental.** Only rules with a premise that changed are re-tried.
- **Deterministic.** Rules fire in file order, bindings in name order, ties broken by name.
- **To measure.** A 9-NPC week like Before the Ice should add milliseconds per tick, not seconds. A 100-NPC town is
  the stress test, as in the roadmap's phase 4.

## Fair play and testing

- **Invariants, tested.**
  - No conclusion without held premises.
  - The ledger's truth is never read by inference.
  - A withdrawn premise withdraws what rests on it.
  - The same seed gives the same thoughts.
- **`thespis check`.** Every variable in `then` is bound in `from`; predicates are declared; no rule can loop past
  the depth.
- **Seed sweeps.** They keep working, and get a new column: what each NPC concluded, and when.
- **Every ending has a why.** `explain` on the deciding choice reaches back through the chain to things someone saw.

## Before the Ice, rewritten

What the hand-written sums in `coldwater.toml` would become:

| Today | With these layers |
| --- | --- |
| Warn and arrest each spell out "no account, or a broken alibi, or left at half past eleven, with a lantern" | `two_places` and a `no_account` rule make `lied_whereabouts(x)`; `suspect` combines it with a lantern; warn and arrest turn on how far `suspect(player)` has got |
| `take:otto`, `take:billy`, `take:ashby` and `arrest` each with their own conditions | One `take:{x}` on `leads = "fired"`, plus `breakup` when "accident" leads |
| Rounds written per witness (`see_vera`, `see_martha`, `see_otto`, `see_billy`) | `ask:{whom}` by what an answer is worth |
| Věra's silence `keeps` while she trusts him | `keeps` for her mouth, `holds_back` for her mind: when he loses her, she puts it together, and that's an event |
| Sándor fights whoever he believes did it at 0.4 | `leap` 0.3 lowered by anger, and an intention to find the man |
| The Notebook lists beliefs with sources | It shows his candidates, the leader's chain, and the "therefore" |

And new things none of the current rules can do:
- he notices a lie we didn't plan for;
- he sets the "front door" trap;
- he says he'd had it wrong about Ashby;
- he remarks that Anton visits the watchman a great deal.

## Across genres

| Game | What they reason about | Personality that shows | Beliefs about beliefs | Curiosity |
| --- | --- | --- | --- | --- |
| Mystery (Before the Ice) | Who did it: alibis, sightings, lies | The careful inspector, the hot-headed son, the sister in denial | Traps; who knows what | Rounds and questions chosen by what settles it |
| Stealth or heist | Is someone here, and where | Jumpy rookie, bored veteran | "He knows the patrol" | Search where it best tells rat from intruder |
| Fantasy village | Theft, feuds, who wronged whom | The gossip, the fair-minded elder, the grudge-holder | Who knows the secret | The sheriff's questions; the gossip's prying |
| Strategy or diplomacy | Intentions from moves | Paranoid, trusting, opportunist | "They think we're weak" | Scouting what's least clear |
| Romance or drama | Feelings from what people do | The jealous, the oblivious | "She thinks I'm angry" | Asking a friend what he said about me |
| Survival or horror | Where the danger is, who to trust | The panicky, the steady | "He's hiding the bite" | Checking the noise, or not |

## Build order

Each step ends at a gate measured in tests, a seed sweep or a playtest.

1. **Inference with variables, choices over bindings, reasons in `explain`.** The smallest step with the biggest
   gain.
   - Gate: Before the Ice rewritten on it, with no ending lost in the sweep and fewer, shorter rules.
   - Gate: `explain` shows chains.
   - Gate: a tick stays within budget.
2. **Personality in reasoning.**
   - Gate: tests where the same facts give different conclusions.
   - Gate: Věra's "it all came together" event fires when she stops trusting him.
3. **Questions and curiosity.**
   - Gate: Gilchrist finds Martha, the sister and the liars without a hand-written round.
   - Gate: the sweep shows his rounds follow what he needs.
4. **Beliefs about beliefs.**
   - Gate: the front-door trap in a test.
   - Gate: an NPC won't lie to someone it believes knows the truth.
5. **Intentions, the night's reflection, noticing the player.**
   - Gate: Sándor's search lasts days and stops for a reason.
   - Gate: a changed mind shows in the morning.
6. **Imagination** (optional).
   - Gate: no proposal kept without support, in a test that feeds the model bad ideas.
   - Gate: the call budget holds.

The playtest decides the pace. If players describe Gilchrist as a man working things out ("he figured out I…"),
steps 1 and 2 may be enough for Before the Ice. If they call him a list being read, step 3 comes first.

## Open questions

- **Shared rules or each NPC's own?** The sketch has both: `[[infer]]` for everyone, `[npc.x.reasons]` to tune. Is a
  pack (`use = ["whodunit"]`) worth a format of its own?
- **The confidence maths.** Subjective logic has deduction and abduction operators; the engine already fuses opinions
  that way. Is the deduction operator readable enough for designers tuning `strength`, or should conclusions use a
  simpler product with an uncertainty floor?
- **How far conclusions travel.** Shared as opinion at half weight is a guess for the playtests.
- **Writing rules without an explosion.** Packs and variables should keep a game to tens of rules. Does that hold
  for a 100-NPC town?
- **Teaching the player.** How does a player learn what Gilchrist can work out, so his conclusions feel fair and not
  magic? Tells, the evening remarks, the Notebook: enough?
- **Multiplayer.** Beliefs about beliefs with several players: whose `knows`?
