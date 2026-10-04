# Results

Measured by `tools/harness.py` against **https://thespis-production.up.railway.app** on 2026-10-04 02:17 UTC, engine at `60784e9`.
Models: gpt-6-luna (80 calls). Seeds: 1, 4.

## Headline numbers

| Measure | Value |
| --- | --- |
| NPC turns decided by code alone, with no model call | **87%** (395 of 452) |
| Invalid model replies blocked by the validator | **0** of 80 replies |
| Model call latency, p50 / p95 (on the host) | **1315 ms / 1585 ms** (max 2115 ms, 80 calls) |
| `/act` round trip when it calls the model, p50 / p95 | **1445 ms / 2173 ms** (68 actions) |
| `/act` round trip with no model call, p50 / p95 | **43 ms / 79 ms** (92 actions) |
| Cost per run, every call to the model | **$0.00066** (10.8 calls per run) |
| Cost per run as played, with the cache | **$0.00030** (5.0 calls per run) |
| Rules routes matching the rules model | **8 of 8** |

## How each number is counted

- **NPC turns:** one per NPC per phase that ran, epilogue included (4 NPCs). A turn counts as a model turn when the model was asked to choose the NPC's action: a decision from the model or the cache, or a fallback the model caused. Spoken lines are counted separately below.
- **Blocked replies:** model replies the validator rejected, so the NPC used its code choice and template line instead. Out of every reply the model returned.
- **Model call latency:** each call's time inside the host's gateway, from its own log (`GET /dev/calls`), successful calls only.
- **`/act` round trip:** the time for the harness, over the internet, to get each `/act` answer: what a player waits. Split by whether the action caused a model call, from the call log's count before and after it.
- **Cost:** tokens from each call's reported usage, priced at OpenAI list prices per 1M tokens: GPT-6 Luna $0.10 in / $0.50 out, GPT-5.4 nano $0.20 in / $1.25 out. Azure's pricing page listed Luna as "in processing" when this ran. "Every call to the model" prices each answer the cache gave as one more call at the measured average; "as played" is what was spent.
- **Model runs:** right after the first action, the player asks everyone nearby a question of its own, so every run makes new model calls. Talking changes nothing in the world.

## Where lines came from (model pass)

| Source | Lines |
| --- | --- |
| cache | 93 |
| fallback | 16 |
| llm | 80 |

Tokens over all 16 model runs: gpt-6-luna: 32,080 in / 3,336 out. Total cost: $0.0049.

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

Model pass: the brain on. The model chooses among the actions the NPC's drives rate close to the best, so an outcome can differ from the rules model's. On other seeds the duel dice differ too.

| Route | Seed | Outcome | Model calls | Lines: model / cache / template | Blocked | `/act` p50 |
| --- | --- | --- | --- | --- | --- | --- |
| rush | 1 | won@4 | 4 | 4 / 1 / 0 | 0 | 840 ms |
| provoke_pay | 1 | won@5 | 6 | 6 / 9 / 2 | 0 | 81 ms |
| provoke_no_pay | 1 | lost@5 | 5 | 5 / 8 / 1 | 0 | 54 ms |
| frame | 1 | won@5 | 3 | 3 / 14 / 0 | 0 | 44 ms |
| lie_unpaid | 1 | lost@5 | 9 | 9 / 8 / 1 | 0 | 58 ms |
| spare | 1 | won@5 | 7 | 7 / 3 / 4 | 0 | 1063 ms |
| duel_lost | 4 | lost@4 | 7 | 7 / 2 / 1 | 0 | 1418 ms |
| provoke_wait | 1 | lost@5 | 8 | 8 / 5 / 0 | 0 | 793 ms |
| rush | 4 | won@4 | 2 | 2 / 3 / 0 | 0 | 41 ms |
| provoke_pay | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 62 ms |
| provoke_no_pay | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 55 ms |
| frame | 4 | lost@4 | 8 | 8 / 4 / 1 | 0 | 79 ms |
| lie_unpaid | 4 | lost@4 | 3 | 3 / 9 / 1 | 0 | 50 ms |
| spare | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 42 ms |
| duel_lost | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 52 ms |
| provoke_wait | 4 | lost@4 | 6 | 6 / 3 / 1 | 0 | 941 ms |

<!-- judged:start -->
## Model-judged (#37)

**Model-judged, not measured:** gpt-5.4-nano read 50 lines by gpt-6-luna, each beside the state pack it was spoken from, on 2026-10-04 10:09 UTC. The lines come from the scripted routes with fresh questions, played in-process with the same code and prompts as the host (prompt version 3), and only lines that passed the validator count, since those are the ones players hear.

| Measure (model-judged) | Value |
| --- | --- |
| Lines that state only what the NPC knew | **48 of 50** (96%) |
| Lines in character | **50 of 50** (100%) |
| Check on the judge: planted lines it flagged | 9 of 10 |

The planted lines are real lines moved to another NPC's moment, where nothing they cite is in the pack, so a careful judge should flag them. A line can be consistent and still wrong about the world: NPCs may hold false beliefs by design, and this checks only what each NPC knew.

Lines the judge flagged:

- Kael: "The relic is mine. You were too slow." (not consistent: He claims the relic is his and that the player was too slow, but the state pack only says the player took the relic, not that it was Kael’s by right or that he lost a race.)
- Odo: "I haven't seen the Captain, I'm afraid. Let's keep things civil here, eh?" (not consistent: It claims he hasn't seen the Captain, which isn't supported by his state pack (he only knows about the player insulting Kael).)
<!-- judged:end -->
