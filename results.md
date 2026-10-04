# Results

Measured by `tools/harness.py` against **https://thespis-production.up.railway.app** on 2026-10-04 01:56 UTC, engine at `ba64672`.
Models: gpt-6-luna (44 calls). Seeds: 1, 4.

## Headline numbers

| Measure | Value |
| --- | --- |
| NPC turns decided by code alone, with no model call | **87%** (395 of 452) |
| Invalid model replies blocked by the validator | **20** of 44 replies |
| Model call latency, p50 / p95 (on the host) | **967 ms / 1513 ms** (max 1576 ms, 44 calls) |
| `/act` round trip when it calls the model, p50 / p95 | **1012 ms / 1560 ms** (44 actions) |
| `/act` round trip with no model call, p50 / p95 | **41 ms / 57 ms** (116 actions) |
| Cost per run, every call to the model | **$0.00055** (10.8 calls per run) |
| Cost per run as played, with the cache | **$0.00014** (2.8 calls per run) |
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
| cache | 129 |
| fallback | 36 |
| llm | 24 |

Blocked replies by reason:

- no cites: 17
- names someone absent from its state pack: 3

Tokens over all 16 model runs: gpt-6-luna: 13,547 in / 1,793 out. Total cost: $0.0023.

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
| rush | 1 | won@4 | 2 | 0 / 3 / 2 | 2 | 43 ms |
| provoke_pay | 1 | won@5 | 3 | 2 / 12 / 3 | 1 | 45 ms |
| provoke_no_pay | 1 | lost@5 | 3 | 2 / 10 / 2 | 1 | 44 ms |
| frame | 1 | won@5 | 3 | 3 / 14 / 0 | 0 | 48 ms |
| lie_unpaid | 1 | lost@5 | 3 | 0 / 14 / 4 | 3 | 49 ms |
| spare | 1 | won@5 | 3 | 3 / 7 / 4 | 0 | 51 ms |
| duel_lost | 4 | lost@4 | 3 | 2 / 6 / 2 | 1 | 41 ms |
| provoke_wait | 1 | lost@5 | 3 | 3 / 10 / 0 | 0 | 46 ms |
| rush | 4 | won@4 | 2 | 1 / 3 / 1 | 1 | 38 ms |
| provoke_pay | 4 | lost@4 | 3 | 2 / 6 / 2 | 1 | 40 ms |
| provoke_no_pay | 4 | lost@4 | 3 | 1 / 6 / 3 | 2 | 46 ms |
| frame | 4 | lost@4 | 3 | 3 / 9 / 1 | 0 | 40 ms |
| lie_unpaid | 4 | lost@4 | 1 | 0 / 11 / 2 | 1 | 36 ms |
| spare | 4 | lost@4 | 3 | 0 / 6 / 4 | 3 | 43 ms |
| duel_lost | 4 | lost@4 | 3 | 1 / 6 / 3 | 2 | 54 ms |
| provoke_wait | 4 | lost@4 | 3 | 1 / 6 / 3 | 2 | 44 ms |
