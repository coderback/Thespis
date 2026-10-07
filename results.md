# Results

Measured by `tools/harness.py` against **https://thespis-production.up.railway.app** on 2026-10-07 23:44 UTC, engine at `490dd88`.
Models: gpt-6-luna (91 calls). Seeds: 1, 4.

## Headline numbers

| Measure | Value |
| --- | --- |
| NPC turns played by code alone, with no model call | **87%** (494 of 568) |
| Invalid model replies blocked by the validator | **0** of 91 replies |
| Model call latency, p50 / p95 (on the host) | **1131 ms / 1704 ms** (max 1872 ms, 91 calls) |
| `/act` round trip when it calls the model, p50 / p95 | **1616 ms / 2187 ms** (83 actions) |
| `/act` round trip with no model call, p50 / p95 | **34 ms / 41 ms** (121 actions) |
| Cost per run, every call to the model | **$0.00071** (11.1 calls per run) |
| Cost per run as played, with the cache | **$0.00029** (4.5 calls per run) |
| Rules routes matching the rules model | **10 of 10** |

## How each number is counted

- **NPC turns:** one per NPC per phase that ran, epilogue included (4 NPCs). Code chooses every action; a turn counts as a model turn when the model was asked to voice the action code chose: a line from the model or the cache, or a fallback the model caused. Spoken lines are counted separately below.
- **Blocked replies:** model replies the validator rejected, so the NPC used its code choice and template line instead. Out of every reply the model returned.
- **Model call latency:** each call's time inside the host's gateway, from its own log (`GET /dev/calls`), successful calls only.
- **`/act` round trip:** the time for the harness, over the internet, to get each `/act` answer: what a player waits. Split by whether the action caused a model call, from the call log's count before and after it.
- **Cost:** tokens from each call's reported usage, priced at OpenAI list prices per 1M tokens: GPT-6 Luna $0.10 in / $0.50 out, GPT-5.4 nano $0.20 in / $1.25 out. Azure's pricing page listed Luna as "in processing" when this ran. "Every call to the model" prices each answer the cache gave as one more call at the measured average; "as played" is what was spent.
- **Model runs:** right after the first action, the player asks everyone nearby a question of its own, so every run makes new model calls. Talking changes nothing in the world.

## Where lines came from (model pass)

| Source | Lines |
| --- | --- |
| cache | 131 |
| fallback | 21 |
| llm | 91 |

Tokens over all 20 model runs: gpt-6-luna: 39,512 in / 3,717 out. Total cost: $0.0058.

## Route outcomes

Rules pass: the brain off, the demo seed. Each outcome must match the rules model (`tools/crypt_road_sim.py`).

| Route | Expected | Got |
| --- | --- | --- |
| rush | won@4 | won@4 ✓ |
| provoke_pay | won@5 | won@5 ✓ |
| provoke_no_pay | lost@5 | lost@5 ✓ |
| frame | won@5 | won@5 ✓ |
| lie_unpaid | lost@5 | lost@5 ✓ |
| spare | won@5 | won@5 ✓ |
| duel_lost | lost@4 | lost@4 ✓ |
| provoke_wait | lost@5 | lost@5 ✓ |
| haggle | won@5 | won@5 ✓ |
| lowball | lost@5 | lost@5 ✓ |

Model pass: the brain on. Code makes every choice and the model only words it, so on the demo seed each outcome matches the rules pass. On other seeds the duel dice differ.

| Route | Seed | Outcome | Model calls | Lines: model / cache / template | Blocked | `/act` p50 |
| --- | --- | --- | --- | --- | --- | --- |
| rush | 1 | won@4 | 4 | 4 / 1 / 0 | 0 | 962 ms |
| provoke_pay | 1 | won@5 | 6 | 6 / 9 / 2 | 0 | 41 ms |
| provoke_no_pay | 1 | lost@5 | 5 | 5 / 8 / 1 | 0 | 35 ms |
| frame | 1 | won@5 | 3 | 3 / 14 / 0 | 0 | 37 ms |
| lie_unpaid | 1 | lost@5 | 9 | 9 / 8 / 1 | 0 | 37 ms |
| spare | 1 | won@5 | 7 | 7 / 3 / 4 | 0 | 1123 ms |
| duel_lost | 4 | lost@4 | 7 | 7 / 2 / 1 | 0 | 1217 ms |
| provoke_wait | 1 | lost@5 | 6 | 6 / 7 / 0 | 0 | 36 ms |
| haggle | 1 | won@5 | 5 | 5 / 11 / 2 | 0 | 37 ms |
| lowball | 1 | lost@5 | 5 | 5 / 10 / 1 | 0 | 38 ms |
| rush | 4 | won@4 | 2 | 2 / 3 / 0 | 0 | 33 ms |
| provoke_pay | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 36 ms |
| provoke_no_pay | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 36 ms |
| frame | 4 | lost@4 | 6 | 6 / 6 / 1 | 0 | 41 ms |
| lie_unpaid | 4 | lost@4 | 3 | 3 / 9 / 1 | 0 | 34 ms |
| spare | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 37 ms |
| duel_lost | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 38 ms |
| provoke_wait | 4 | lost@4 | 5 | 5 / 4 / 1 | 0 | 864 ms |
| haggle | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 36 ms |
| lowball | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 34 ms |

<!-- judged:start -->
## Model-judged (#37)

**Model-judged, not measured:** gpt-5.4-nano read 50 lines by gpt-6-luna, each beside the state pack it was spoken from, on 2026-10-07 23:46 UTC. The lines come from the scripted routes with fresh questions, played in-process with the same code and prompts as the host (prompts 41b3bd7ddca5), and only lines that passed the validator count, since those are the ones players hear.

| Measure (model-judged) | Value |
| --- | --- |
| Lines that state only what the NPC knew | **43 of 50** (86%) |
| Lines in character | **50 of 50** (100%) |
| Check on the judge: planted lines it flagged | 9 of 10 |

The planted lines are real lines moved to another NPC's moment, where nothing they cite is in the pack, so a careful judge should flag them. A line can be consistent and still wrong about the world: NPCs may hold false beliefs by design, and this checks only what each NPC knew.

Lines the judge flagged:

- Kael: "Too late. You took it first; I won’t pretend otherwise." (not consistent: Kael claims you took it first/that it’s too late, but the state pack only confirms the player took the relic and doesn’t establish who arrived first.)
- Kael: "You took my purse and my pride. Keep moving—I’ll take the relic before you do." (not consistent: He accuses the player of taking his pride/purse (supported) but says “before you do,” implying the player will take the relic, which isn’t in his state pack.)
- Kael: "There you are. The Captain heard what you did. Now stand aside—I’m taking the relic." (not consistent: He says the Captain heard what you did, which isn’t supported by his state pack (only his own report is known).)
- Kael: "The relic’s mine. The player robbed, beat, and insulted me—now watch me win." (not consistent: He calls the relic “mine,” which isn’t supported by the state pack (he only has the goal to take it).)
- Kael: "The relic’s mine. I’ll take it and win this race." (not consistent: He declares ownership of the relic (“The relic’s mine”) without that being supported by his state pack.)
- Captain Brenna: "You and Kael have arrived together, then. Keep the road orderly—settle any trouble with a fine in coin." (not consistent: You and Kael both arrived at the guard post, but the line claims they arrived together (same time) which isn’t supported by the state pack.)
- Kael: "The relic is mine. I’ve won the race." (not consistent: He claims the relic is his and that he won, but the state pack shows the player took the relic (e5) and gives no support that Kael won.)
<!-- judged:end -->
