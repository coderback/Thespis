# Results

Measured by `tools/harness.py` against **https://thespis-production.up.railway.app** on 2026-10-05 23:24 UTC, engine at `df0eed1`.
Models: gpt-6-luna (69 calls), then gpt-5.4-nano (1 call). Seeds: 1, 4.

## Headline numbers

| Measure | Value |
| --- | --- |
| NPC turns decided by code alone, with no model call | **87%** (494 of 568) |
| Invalid model replies blocked by the validator | **0** of 70 replies |
| Model call latency, p50 / p95 (on the host) | **910 ms / 1427 ms** (max 1916 ms, 70 calls) |
| `/act` round trip when it calls the model, p50 / p95 | **1010 ms / 1950 ms** (69 actions) |
| `/act` round trip with no model call, p50 / p95 | **40 ms / 59 ms** (135 actions) |
| Cost per run, every call to the model | **$0.00065** (11.2 calls per run) |
| Cost per run as played, with the cache | **$0.00020** (3.5 calls per run) |
| Rules routes matching the rules model | **10 of 10** |

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
| cache | 152 |
| fallback | 21 |
| llm | 70 |

Failed calls: {'timeout': 1}. Turns or lines that fell back because the model was unavailable: 0.

Tokens over all 20 model runs: gpt-6-luna: 24,828 in / 2,929 out, gpt-5.4-nano: 338 in / 51 out. Total cost: $0.0041.

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

Model pass: the brain on. The model chooses among the actions the NPC's drives rate close to the best, so an outcome can differ from the rules model's. On other seeds the duel dice differ too.

| Route | Seed | Outcome | Model calls | Lines: model / cache / template | Blocked | `/act` p50 |
| --- | --- | --- | --- | --- | --- | --- |
| rush | 1 | won@4 | 2 | 2 / 3 / 0 | 0 | 60 ms |
| provoke_pay | 1 | won@5 | 3 | 3 / 12 / 2 | 0 | 50 ms |
| provoke_no_pay | 1 | lost@5 | 3 | 3 / 10 / 1 | 0 | 59 ms |
| frame | 1 | won@5 | 3 | 3 / 14 / 0 | 0 | 44 ms |
| lie_unpaid | 1 | lost@5 | 4 | 4 / 13 / 1 | 0 | 39 ms |
| spare | 1 | won@5 | 3 | 3 / 7 / 4 | 0 | 40 ms |
| duel_lost | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 41 ms |
| provoke_wait | 1 | lost@5 | 4 | 4 / 9 / 0 | 0 | 42 ms |
| haggle | 1 | won@5 | 8 | 8 / 8 / 2 | 0 | 786 ms |
| lowball | 1 | lost@5 | 7 | 7 / 8 / 1 | 0 | 48 ms |
| rush | 4 | won@4 | 2 | 2 / 3 / 0 | 0 | 40 ms |
| provoke_pay | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 44 ms |
| provoke_no_pay | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 42 ms |
| frame | 4 | lost@4 | 4 | 4 / 8 / 1 | 0 | 44 ms |
| lie_unpaid | 4 | lost@4 | 3 | 3 / 9 / 1 | 0 | 42 ms |
| spare | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 56 ms |
| duel_lost | 4 | lost@4 | 4 | 3 / 6 / 1 | 0 | 40 ms |
| provoke_wait | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 42 ms |
| haggle | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 38 ms |
| lowball | 4 | lost@4 | 3 | 3 / 6 / 1 | 0 | 49 ms |

<!-- judged:start -->
## Model-judged (#37)

**Model-judged, not measured:** gpt-5.4-nano read 50 lines by gpt-6-luna, each beside the state pack it was spoken from, on 2026-10-05 23:26 UTC. The lines come from the scripted routes with fresh questions, played in-process with the same code and prompts as the host (prompt version 3), and only lines that passed the validator count, since those are the ones players hear.

| Measure (model-judged) | Value |
| --- | --- |
| Lines that state only what the NPC knew | **49 of 50** (98%) |
| Lines in character | **50 of 50** (100%) |
| Check on the judge: planted lines it flagged | 8 of 10 |

The planted lines are real lines moved to another NPC's moment, where nothing they cite is in the pack, so a careful judge should flag them. A line can be consistent and still wrong about the world: NPCs may hold false beliefs by design, and this checks only what each NPC knew.

Lines the judge flagged:

- Kael: "The relic is mine. You were too slow." (not consistent: It contradicts the state that the player took the relic, and it assumes the player was 'too slow' without that being in Kael's known facts.)
<!-- judged:end -->
