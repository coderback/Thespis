# Characters with a self: a design for Thespis

*A proposal for review, 18 November 2026. Nothing here is built yet. Its companion,
[minds-that-reason.md](minds-that-reason.md), is about how an NPC thinks; this one is about who is thinking.*

Thespis gives each NPC a persona to be voiced from, drives that rise and fade, trust in each person, secrets it
keeps, and the choices and lines its game writes for it. That's enough for a character to behave. It isn't yet
enough for a character to be someone: to want things of its own, feel an event differently from the next person,
love someone it no longer trusts, say no for its own reasons, crack under pressure, and come out of the week a
little changed. This doc proposes how.

## Why

**What Before the Ice Goes Out shows.** Every person in Coldwater is distinct, but almost all of it is written by
hand:
- Maggie "wants peace in her house" in a sentence the model reads. Nothing in her choices weighs it.
- The fire is a ruin to Otto, a grief to Sándor and, though she'd never say it, a reprieve to Věra. The engine
  doesn't know that; it knows only what each believes happened.
- Trust is the only thing one person feels about another. Věra can stop trusting her brother, but she can't stop
  trusting him while still loving him, the conflict her whole story turns on.
- A frightened Billy is frightened because we gave him a `fear` drive and wrote which choices it opens. A timid
  stranger in another game would need all of that written again.

**What the research says** ([redefining-the-npc.md](redefining-the-npc.md)):
- **Numbers, not descriptions.** The games with the most memorable characters model personality as numbers that
  change with events and push behaviour. In Crusader Kings III, traits weight every decision, and acting against them
  builds stress towards a breakdown. In RimWorld, thoughts with causes and durations stack into mood, and low mood
  risks a break. In Prom Week, traits, relationships and a history of social facts decide what each character wants
  to do; 263 playthroughs of one campaign were all distinct.
- **Prompt-only personas drift.** A personality kept only in a model prompt drifts within 8 exchanges, and model size
  doesn't fix it.
- **Players want resistance.** Players of Vaudeville, a murder-mystery game with AI NPCs, complained of NPCs who
  agreed with everything. NPCs must have reasons to say no.

**What makes a character feel like a self.**
- They're the same person tomorrow.
- They react unlike the person next to them.
- They want something, and pursue it unprompted.
- Their feelings have causes you could name.
- Their relationships have more than one side.
- They refuse you, for reasons.
- They change, a little and for a reason.
- You can predict them a little, and they can still surprise you.

## Principles

1. **Personality is numbers that act; the persona voices them.** The model is given the numbers on every call, and
   never owns them.
2. **Same rules, different people.** Traits weight rules and actions every character shares, so a game writes fewer
   per-person choices, not more.
3. **Feelings have causes.** Every emotion points to an event and to what it touched: a want, a value, a person.
4. **Few numbers, small ranges, every change explained.** A designer can hold a character in their head, and the
   inspector can say why anything moved.
5. **Change is slow and earned.** An arc is a logged event, never a drift nobody can account for.
6. **Deterministic and testable,** like everything else in Thespis.

## The layers

Seven layers. Syntax is a sketch, in the style of the game file ([protocol.md](protocol.md)).

### 1. Traits

**What.** Stable dispositions, a handful per game, each from -3 to 3. The game names its own dimensions; packs can
supply common sets (the Big Five, or a set for court intrigue).

```toml
[traits]
bold = "faces danger rather than avoiding it"
honest = "says what they believe"
warm = "minds other people's feelings"
patient = "waits for things to come right"
talkative = "passes things on"

[npc.sandor]
traits = { bold = 3, patient = -2, warm = 1, honest = 2 }

[actions]   # what each act says about whoever chooses it
threaten = { bold = 1, warm = -1 }
lie = { honest = -2 }
comfort = { warm = 1 }
wait = { patient = 1 }
```

**How it acts.**
- **On choices.** Every choice whose action expresses traits gets a utility term: the NPC's traits against the
  action's, times the game's `[traits] weight`. The same choice set picks differently per character, with no extra
  rules: Sándor confronts, Billy runs, Maggie talks it round.
- **On reasoning.** Traits supply defaults for the reasoning numbers in the companion doc. Patience raises `leap`.
  Stubbornness raises `confirms`. Loyalty with affection makes `holds_back`.
- **On gossip.** `talkative` scales how much an NPC passes on and how far. `keeps` stays for secrets that are
  specific.
- **Acting against yourself costs** (layer 5): an honest NPC that lies, or a timid one made to stand its ground,
  gains stress.

**What it shows.** `explain` names the trait in a choice's score: "confront:ashby scores 7 (bold +3)".

### 2. Wants and values

**What.** What an NPC is after, and what it holds right.

```toml
[npc.otto]
wants = { money = 3, standing = 2 }
values = { law = 1, family = 0 }

[npc.vera]
wants = { brother_safe = 3, the_claim = 2 }
values = { family = 3, honesty = 1 }

[actions]
pay = { serves = { money = 1 } }
take_claim = { serves = { money = 2 }, harms = { the_claim = 3 } }
```

**How it acts.**
- **Choices that serve a want score higher.** An action declares which wants it serves or harms.
- **Wants start intentions** (reasoning doc, layer 5): Otto's money is why he presses debtors, unprompted.
- **Values are the standards** an NPC judges acts by: their own, which brings pride or shame, and others', which brings
  admiration or reproach (layer 3).
- **Resistance.** An NPC refuses what costs its wants or offends its values, unless what's offered outweighs it. This
  is the "moderate agreeability" the research asks for. Persuasion works by offering what they want, or arguing
  from what they believe, never by asking nicely enough.

**What it shows.** A refusal can cite its reason. Věra's "Keep your money. You'll need it." is family over money,
and the inspector says so.

### 3. Feelings with causes

**What.** Emotions an NPC has *about* something, worked out from how an event bears on its wants, values and
people. This is a short form of the appraisal model (OCC) the research cites, as rules.

| An event… | …bears on | Feeling |
| --- | --- | --- |
| something I want happened, or was lost | my wants | joy, distress |
| something I want may happen, or be lost | my wants, by how sure I am it will | hope, fear |
| I did something | my values | pride, shame |
| someone else did something | my values | admiration, reproach |
| someone's act helped or harmed what I want | my wants, and them | gratitude, anger, with a target |
| something happened to someone I feel for | my relationship to them | happy-for, pity, resentment, gloating |

**How it acts.**
- **Feelings are drives with a target and a cause.** "Anger at Ashby, because Maggie says his lantern was in the lane."
  They decay as drives already do (`[npc.x.decay]`).
- **Mood is their sum.** It moves utility, the reasoning thresholds (anger lowers `leap`) and the voice.
- **The engine ships the appraisal rules** for the table above. A game adds its own, or adjusts strengths. Today's
  `feels` becomes the simplest case of them.
- **Feelings come from beliefs, not facts.** Sándor is angry at whoever he believes did it. If he's wrong, his anger is
  real and misplaced, which is a story.

**The fire, appraised.**
- **Otto:** distress (money, standing), anger at whoever did it.
- **Sándor:** distress (his father), anger, and pity for his father.
- **Věra:** relief (the claim) and fear for her brother, at once. The engine knows she's torn, not just quiet.
- **Maggie:** fear, since the bottle she sold is part of it.
- **Tamás:** shame, at the bottle.

### 4. Relationships with more than one side

**What.** Four directed numbers per pair, from -5 to 5:
- **trust:** what I believe from you (exists today);
- **affection:** what I'd do for you;
- **fear:** what you could do to me;
- **respect:** how much your judgement weighs with me.

**How they act.**
- **Trust gates belief,** as now.
- **Affection gates protection.** It feeds `holds_back` and `keeps`, and makes harming someone cost stress.
- **Fear gates compliance and silence.** Billy keeps quiet because he fears the police, not because a flag says so.
- **Respect weighs opinion.** Shared opinions (reasoning doc) count for more from someone respected: Gilchrist comes
  to respect Martha's eye.
- **All four move by appraisal.** Gratitude raises affection, being caught lowers trust, a threat raises fear and
  lowers affection, a sound call raises respect.
- **They pull apart,** which is where drama lives. Věra can trust Anton 1 and love him 5.

New conditions read like `{ affection = "player", gte = 3 }`. `[[tie]]` kinds set starting values (`kin` begins
with affection), as they set gossip weights now.

### 5. Stress and breaking points

**What.** Pressure that builds and must go somewhere.

```toml
[npc.billy]
stress = { breaks_at = 7, relief = ["comfort", "eat"] }

[[npc.billy.choices.break]]
do = "blurt"
asserts = { pred = "woodpile", a = "self" }     # it all comes out: he was taking the wood
```

**How it acts.**
- **What raises it:** fear, acting against one's traits or values, being pressed (threatened, asked again and
  again), and holding a secret one's values dislike.
- **What lowers it:** relief acts, and time.
- **Breaking.** At `breaks_at` the NPC takes a choice from its `break` set: confess, flee, lash out, drink.
  Thespis writes an event, and the NPC's stress drops.

**What it gives.**
- Pressure becomes a skill with visible risk, the research's "breaking points" mechanic.
- Push Billy too far and he blurts what he was doing at the back door, which may be the last thing Anton wanted
  said aloud.
- Maggie, asked about the bottle every evening, may confess it on the fourth.

### 6. A voice that holds

**What.** The same person in every line, with or without a model.

**How it works.**
- **What the model is given.** The state pack for a line carries the numbers in words: traits, the feelings now and
  their causes, how the speaker feels about the listener, and what's at stake for them. The persona text stays, as
  the sound of them, not the substance.
- **Lines by feeling, offline.** Written lines can vary by the speaker's feeling (`told.angry`, `told.afraid`), so a
  game with no model still sounds like these people in this mood.
- **Voice rules.** `voice = { register = "plain", says = ["mister"], never = ["modern slang"] }` go to the model and
  to the claim check.
- **Measured.** Rehearsal judges persona consistency over many lines. The research found a judge model agrees with
  people about 80% of the time.

### 7. Change over the story

**What.** Character arcs: traits and relationships that shift slowly with repeated experience.

```toml
[[arc]]
when = [{ count = "stood_ground", gte = 3 }]    # stood up to danger three times
shift = { bold = 1 }
```

**How it acts.**
- **An arc is an event**, so it can be told: the inspector shows it, lines can say "I'd not have done that a week
  ago", the Notebook can note it.
- **Bounded.** Shifts are capped per stretch of time, and a designer can lock a trait.
- **Baselines drift too.** A relationship's resting point drifts with history: a week of kindness raises where
  affection returns to.

**Long or short games.** In a five-day game, arcs are small and few: Věra hardening, Billy daring. In a long RPG
they're the point.

## How it meets reasoning

One set of numbers, two docs:

| From personality | Shapes reasoning |
| --- | --- |
| Patient, or careful | A higher `leap`: concludes later |
| Stubborn, or proud | A higher `confirms`; slower to change the leading explanation |
| Affection with loyalty | `holds_back`: won't conclude against someone loved |
| Anger | A lower `leap`, and a pull towards the explanation that names whoever they're angry at |
| Fear | Threat explanations weigh more |
| Respect | Shared opinions from the respected count for more |

And reasoning feeds personality back: a conclusion is a belief, so it's appraised. When Věra finally puts it together,
the conclusion brings distress, and her affection and trust pull apart. That's the scene.

## The player as a person to them

The player's acts are appraised against each NPC's values like anyone's:
- Gilchrist reproaches an offered bribe.
- Billy is grateful for the five dollars, and a little afraid of why.
- Martha respects plain dealing.

So reputation is personal and many-sided, the sum of what each person feels, not a meter. The player's habits
(reasoning doc, layer 5) are appraised too: the man who sits with the watchman every morning earns Tamás's affection
and Sándor's thanks.

## The model's place

- **Voice:** the numbers and their causes, said in character.
- **Ear:** the player's words read into acts, which are then appraised like any act.

The model never sets a trait, a want, a feeling, a relationship, stress or an arc.

## Before the Ice, with selves

A sketch for review, to tune in play.

| Who | Traits | Wants and values | Feels at the start | Might break by | Might change |
| --- | --- | --- | --- | --- | --- |
| Gilchrist | patient 3, honest 2, proud 1 | the truth; the steamer on time; law 3, mercy 1 | duty | never, on purpose | respect for whoever told him true |
| Věra | loyal 3, practical 2, honest 1 | her brother safe 3, the claim 2; family 3, honesty 1 | relief and fear at once | confessing in his place | hardening, if he loses her |
| Tamás | warm 2, patient 1 | to remember, to be forgiven; faith | shame at the bottle | telling the Inspector | forgiving, or not |
| Sándor | bold 3, patient -2, honest 2 | someone to pay; family 3 | grief, anger | a fight | cooling, if shown the truth |
| Billy | bold -2, talkative 1, warm 1 | to eat, the boat; loyalty to Maggie | fear of the police | blurting the woodpile | daring, if paid kindly |
| Maggie | warm 2, talkative 3 | peace in her house, the Mountie's money | fear for the bottle | confessing the bottle | — |
| Otto | proud 2, honest -2 | money 3, standing 2 | distress, anger | blaming a debtor loudly | — |
| Ashby | guarded 3, warm 1 | to leave on the first boat | fear of the warrant | running | — |
| Martha | honest 2, proud 2 | Brand's account paid, the cabin finished; fairness | reproach for Otto | — | respect for whoever asks properly |

Martha's numbers must be hers as a person, never a type. Like the rest of her portrayal, they go to the Hän reader
before release ([before-the-ice-han-1898.md](before-the-ice-han-1898.md)).

**What the town could do then that it can't now:**
- Billy cracks under one threat too many.
- Maggie confesses the bottle on the fourth evening.
- Věra loves her brother after she stops trusting him, and the gap shows.
- Sándor's anger cools if Tamás tells him the truth.
- Gilchrist takes Anton south with mercy because Anton's honesty earned his respect, not because a flag was set.

## Across genres

| Game | What personality drives | A break | An arc |
| --- | --- | --- | --- |
| Mystery | Who covers, who talks, who cracks | A confession | The loyal sister hardens |
| Stealth or heist | Which guard checks a noise, which shrugs | A guard deserts his post | A rookie grows bold |
| Fantasy village | Feuds, favours, who forgives | A brawl at the inn | An enemy becomes a friend |
| Strategy or diplomacy | Who honours a pact, who betrays | A ruler's rash war | A cautious house turns hawkish |
| Romance or drama | Who confesses, who withdraws | A scene at the wedding | Trust rebuilt, or lost |
| Survival or horror | Who shares, who hoards, who panics | Panic: running into the dark | The coward who holds the door |

## Build order

Interleaved with the reasoning doc's, since they share numbers. Each step ends at a gate.

1. **Traits on shared actions, and the four relationship numbers.**
   - Gate: tests where one choice set picks differently per character.
   - Gate: Before the Ice keeps its endings in the sweep with fewer per-person choices.
2. **Wants, values, and feelings with causes.**
   - Gate: one event appraised differently by four NPCs in a test.
   - Gate: `explain` gives "angry at Ashby because…".
   - Gate: refusals cite their reasons.
3. **Stress and breaking points.**
   - Gate: Billy breaks under repeated threats in a test.
   - Gate: the sweep shows breaks are rare and depend on play and the seed.
4. **A voice that holds.**
   - Gate: lines by feeling offline.
   - Gate: Rehearsal's consistency judge over 50+ lines.
5. **Arcs.**
   - Gate: shifts bounded and logged.
   - Gate: a long simulated run shows arcs only where their `when` was met.

Suggested order across both docs: reasoning 1, personality 1, then reasoning 2 with personality 2 (they meet
there), then reasoning 3, personality 3, and the rest as the playtests ask.

## Open questions

- **Which traits by default?** The sketch lets each game name its own, with packs. Is a built-in Big Five worth
  having, or would it pull games towards sameness?
- **How many numbers before designers drown?** Five traits, a few wants, four relationship numbers: is that the
  ceiling?
- **Appraisal rules as data.** Shipped by the engine and adjustable, or written per game?
- **Reading feelings without a meter.** Lines by feeling, portraits that change with mood, posture in the town,
  remarks: which carry best? The playtest's question 1 again.
- **Portraying real peoples.** Traits for characters drawn from real communities must be individual, never a type,
  and reviewed by people from those communities.
- **Arcs in short games.** How fast is believable in five days?
