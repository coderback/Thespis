# Thespis Cast: architecture review and the road to production

6 October 2026

This review asks whether Thespis Cast's design is good enough for its goal, now that it is no longer a hackathon
project. It weighs each architectural decision against three things: what the paper work (`tobi/paper-m1`) measured,
the literature, including work published since the 3 October landscape review in
[redefining-the-npc.md](redefining-the-npc.md), and what a production system needs.

## Bottom line

**The central bet is right, and the field has since moved towards it.** In Thespis the game owns the truth, the model
has no write path, and each NPC speaks only from a state pack of what it could know. Security researchers now
recommend exactly this shape for any LLM agent that reads untrusted input: the *action-selector* and
*context-minimisation* patterns (Beurer-Kellner et al., 2025), and control flow kept away from untrusted data (CaMeL,
Debenedetti et al., 2025). Keep it.

**What sits on top of that bet is weaker than it looks.** paper-m1 found four problems:

1. **The validator checks form, not meaning.** The full system's lines were 100% traceable to the ledger, yet
   independent judges rated 22–36% of them inconsistent with what the NPC knew. A citation proves an id exists, not
   that it supports the line. Almost every reply the validator refused was a protocol slip, not a false statement.
2. **The model makes no decisions.** It took the action with the strongest drive pull in 86 of 86 ungated decisions,
   because the prompt shows the pulls and tells it to follow the strongest. The model writes the words; code already
   makes the choices.
3. **The belief model is too thin for what the roadmap promises.** Claims have two slots, so the manor had to encode
   "study@1". Confidence is the maximum of the evidence, retraction is a dead end, and discrediting a source leaves
   everything else it said in place.
4. **The core is thinner than "game-agnostic" suggests.** The ledger, beliefs and voice are shared, but each game
   rewrites the mind loop itself: who perceives what, the tick, gating and pack building. A third game would copy it
   again. A toolkit has to own that loop.

**It isn't production-ready as a service either**, which is expected for a hackathon build:

- a single SQLite file with in-process locks;
- a model gateway capped at 4 calls in flight across every player;
- open dev endpoints and no content moderation;
- no metrics or traces;
- an API shaped around one game.

The roadmap below fixes these in order of risk. It turns the paper's measuring tools into **Rehearsal**, a regression
suite that gates every change, because the paper's most reusable product is its instrument, not its numbers.

## What Cast is for, and the bar it has to clear

From the README and the design doc: NPCs that remember, hold beliefs that can be false, want things for reasons, keep
acting off-screen, and never let the model change the game's state. Doing that for real game developers adds five
requirements the hackathon didn't have:

- **Authoring:** a designer declares NPCs, drives, actions, perception and claims without writing a tick loop in
  Python.
- **Integration:** it has to be callable from Unity, Unreal or Godot, not only from our own browser client.
- **Trust:** what an NPC says matches what it knows, and when it doesn't, a check catches it before the player hears
  it.
- **Operation:** many concurrent players, predictable cost, provider outages survived, and changes measured before
  they ship.
- **Safety:** player text and model output pass moderation, and secrets resist manipulation.

## What paper-m1 taught us

The evidence comes from:

- **The pilot** (`research/data/pilot`): Luna speaking, about 290 replies per condition, 50 lines per condition
  judged by Claude and DeepSeek.
- **The unjudged full-run data collected so far** (`research/data/full`): Luna under `full` and `noval`, nano under
  `full`, benign and adversarial.

| # | Finding | Evidence | What it means |
| --- | --- | --- | --- |
| 1 | Traceable isn't the same as true | Full system: 100% of lines cite real ledger ids, but 22% are inconsistent by both judges and 36% by either. Without citations, traceability falls to 0% | Citations are a strong provenance feature, the why-chain, but no guarantee of truth. We need a check on meaning |
| 2 | The model follows the pull | 86 of 86 ungated decisions took the strongest pull. The prompt says "follow the strongest pull unless your persona clearly says otherwise" | A decision call is a wording call with extra latency. The model never overrules the drives |
| 3 | Refusals are protocol slips | Luna, benign: 17 of 18 refusals cited no `said` for a lie it chose. Nano: 20 the same, and 17 cited ids not in its pack or names instead of ids (e.g. `b0004`, `Brenna`) | A strict JSON schema would make these impossible. Every slip cost a fallback line |
| 4 | The name check is lexical | Without the validator, Luna under adversarial input produced 15 lines the name check would refuse for "Brenna", e.g. Kael saying "the Captain's decision". A paraphrase such as "the guard woman" would pass | It refuses harmless lines and passes real leaks. Entity checks need meaning, not a word list |
| 5 | Benign play with a strong model can't separate the conditions | At n=50, full 8%/2% of lines with a false claim (either / both judges), omniscient 16%/6%, baseline 12%/6%; the intervals overlap | Lead with what only the architecture gives: provenance, determinism, cost, control. Show safety under pressure, with weaker models, and at scale |
| 6 | Judges disagree on holistic questions | Fleiss κ on "consistent" ran from 0.23 to 0.88 across conditions. Canaries caught: Claude 95%, DeepSeek 85%, nano 70% | Extracting claims and checking them in code is the objective instrument. A judge's verdict alone isn't |
| 7 | Patching modules works, but is fragile | Conditions patch module attributes. The baseline briefly kept drive gating by mistake | These switches belong in configuration. That would also allow A/B tests in production |
| 8 | Operations bite early | The Gemini free tier allowed 20 requests a day, Azure's DeepSeek prices conflicted, and parallel runs were killed for memory | Production needs a gateway with quotas, several vendors and cost accounting from day one |

## Decision by decision

| Decision | Verdict | Why |
| --- | --- | --- |
| The game owns the truth; the model has no write path | **Keep** | It matches the action-selector pattern and CaMeL's separation of control from data. Luna under adversarial input: 0 of 338 replies refused, and no channel exists to change state |
| Scoped state pack: only what the NPC could know | **Keep, and move into the core** | It is the main guard against leaks. TimeChara shows models leak beyond a character's knowledge when they hold more than it should. The omniscient condition had the highest false-claim rate |
| Code decides through utilities and drive gating | **Keep code deciding, but change the model's part** | Hide the pull numbers; let the model break real ties only, or only voice. Anchoring on numbers in a prompt is robust across models (Valencia-Clavijo, 2025) |
| Lines cite ledger and belief ids | **Keep as provenance; stop treating it as a truth check** | Citation benchmarks such as ALCE score whether a cited source supports the statement; our validator checks only that the id exists. Even correct citations can be unfaithful: up to 57% under adversarial tests (Wallat et al., 2024). Finding 1 says the same |
| A post-hoc validator with format, id, name and length checks | **Replace the form checks with constrained decoding; add a semantic check** | Finding 3. Structured outputs guarantee the schema (JSONSchemaBench), but not the meaning (Chavan, 2026) |
| Deception as a validated action | **Keep and generalise** | It is the most novel piece. Make every assertion a statement event with its real truth, not only lies; the manor already logs Pell's this way |
| Beliefs: two-slot claims, maximum confidence, retraction that ends the belief | **Replace** | They can't carry time, place or second-order beliefs. See "Beliefs" below |
| Template fallback, cache and replay | **Keep the fallback; rework the cache** | Graceful degradation is a selling point: 87% of NPC turns need no model. Drafting more fallback lines when the game is written, with a writer approving them as Ubisoft's Ghostwriter does for barks, keeps the no-model path varied. The cache key holds the whole pack, so it only hits on scripted routes |
| Each adapter writes its own tick | **Move into the core, declaratively** | Both adapters duplicate `_decide`, `DRIVE_MARGIN`, `knows()`, `pack_for`, `deliver`, `Speech`, `line`, `NotAllowed` and the shape of `allowed()` |
| Director: a registry of Python patterns | **Fine for now** | Later, a sifting language over the ledger such as Winnow (Kreminski et al., 2021). The model only retells sifted events, as now |
| SQLite snapshot plus an insert-only ledger table | **Replace for production** | See "Production engineering" |
| A synchronous gateway, OpenAI-compatible, primary then backup | **Rework** | Async, structured outputs, a backup from another vendor, telemetry, cost metering |

### Expression: make form impossible to get wrong, and check meaning

**Form, through constrained decoding.** Build one JSON schema per call from the pack, so these become impossible:

- an action that isn't allowed;
- a cite outside the pack;
- a missing `said`.

The schema:

- `action`: an `enum` of the offered ids;
- `cites`: an array of `enum`s of the pack's ids, at least one;
- for an asserting action, an `anyOf` branch whose `cites` must contain `said`.

The OpenAI and Azure models support strict `json_schema` output, and so do local runtimes (llama.cpp grammars,
XGrammar, Outlines). The gateway asks each provider whether it supports this and, where it doesn't, falls back to
today's JSON mode plus checks.

**Order the keys so the evidence comes before the words:** `action`, then `cites`, then `line`. Key order changes
what structured output produces (Tam et al., 2024), and citing after writing invites post-rationalisation (Wallat et
al.). Rehearsal measures whether it helps.

**Meaning, through checking claims.** paper-m1 already built the instrument, with the same split into claims and
checks as FActScore: extract each line's claims in the game's vocabulary, then check them in code against the ledger
and against what the speaker knows (`research/metrics.py`).
Promote it to a runtime check, in two tiers:

- **Always:** a cheap extractor (a small model or an NLI checker in the MiniCheck mould, which matched GPT-4 at
  1/400 of the cost) runs on lines with consequences: accusations, testimony, deals, the narrator.
- **Offline:** every line, in Rehearsal and on sampled production traffic, to measure the leak and hallucination
  rates.

A line that leaks or hallucinates is refused and falls back. This is what makes "every word is checked" true.

**The name check** becomes part of the claim extraction: entity mentions resolved to game ids. The lexical list stays
only as a pre-filter, with aliases generated from the cast.

**Leave room to improvise.** The Symbolically Scaffolded Play study (Figueiredo and Elumeze, 2025) found tight
constraints stabilised a quest-giver but made suspects less believable. Constrain what an NPC claims, not how it
phrases it. That matters most for the manor's suspects.

### Decisions: say what the model is for

Today a `decide` call shows the pulls and tells the model to follow the strongest, so it does. There are two coherent
options:

- **Recommended: code decides, the model voices.** Code chooses every action, as `UtilityBrain` already does when
  the model is off. The model gets one call type, voice: the chosen action, the pack, and a line with cites. That
  means fewer call types, lower latency and nothing lost, since paper-m1 showed nothing is.
- **Or the model breaks real ties.** Offer only options within the margin, unordered and with no numbers, and
  describe the drives in words, e.g. "you badly want revenge". Then measure in Rehearsal how often the persona changes
  the choice. This is only worth keeping if it changes outcomes players notice.

Either way, the model's real decision work should go where code can't reach: **understanding the player's free
text.** Today `talk` text gets a reply but can change nothing. Façade mapped player text to about 30 discourse acts
with hand-written rules (Mateas and Stern, 2004). The CPDC 2025 challenge tested NPCs that call game functions from
dialogue. In Cast, the model would map text to a typed player intent the game declares (claim, question, threat,
offer, plea), and code would validate it like a verb. This is the action-selector pattern on the player's side. It is
the wall that Where Winds Meet lacked, and it opens persuasion and lying in free text as real mechanics.

### Beliefs: what the roadmap needs

- **Typed claims.** Replace `Claim(pred, a, b)` with a predicate schema per game: named arguments, an optional time
  and place, and negation. That ends the "study@1" encoding, and it lets the claim extractor and the checker share one
  vocabulary.
- **Opinions, not a single confidence.** Subjective logic (Jøsang, 2016) gives each belief belief, disbelief and
  uncertainty masses. *Trust discounting* is gossip ("I heard it from someone I half trust"); *cumulative fusion*
  combines independent witnesses. Disbelief is first-class, so testimony can lower a belief instead of flipping a
  status. It is a small, well-understood algebra and fits the existing evidence lists.
- **Justifications, not a terminal status.** Every belief already keeps its evidence. Treat that as support, in the
  manner of a truth maintenance system (Doyle, 1979). When a source is discredited, re-weigh every belief resting on
  it. Today only the contradicted belief falls, and trust drops without touching anything else that source said.
- **Second-order beliefs** ("Brenna thinks I don't know"), as the roadmap plans, become beliefs about another NPC's
  opinion: the same machinery, one level up.

Recent agent work points the same way: explicit, maintained belief states beat history in the context window on
long-horizon tasks (PoS, Luo et al., 2026). Thespis already keeps belief outside the model; these changes make it
expressive enough to use.

### The core: own the mind loop

Today `thespis/` is about 1,050 lines; the two adapters are about 1,430 and 740. Most of the adapters' code is mind
logic each game had to write itself. The core should own:

- **Perception:** who witnesses an event, by co-location, line of sight or schedule, and so `knows()`. A game
  supplies the rule; the core applies it to every event.
- **Affordances:** declared actions with preconditions, considerations (utility curves over drives, beliefs and
  trust), effects written to the ledger, and an optional claim the action asserts. This is the Utility AI shape, and it
  replaces each NPC's hand-written `options = {...}` block.
- **The tick:** the phase order (player, decisions, gossip, moves, upkeep) as a configurable pipeline, not
  `end_phase`.
- **The pack builder, the delivery of lines and the decision records**, written once.
- **Experiment flags:** gating margin, validator tiers, scope rules, as configuration. paper-m1's conditions become
  settings, and production can A/B them.

Both games then shrink to content: casts, actions, claims and lines. The gate is that every existing route plays to
the same outcome.

## Production engineering

What the hackathon build does now, and what production needs:

| Area | Now | Needed |
| --- | --- | --- |
| API | `/act`, `/state` and the rest are The Crypt Road's; the manor mounts its own routes | A versioned, game-agnostic `/v1`: worlds, events, NPCs, act, speak, inspect. The games become clients of it |
| Concurrency | Synchronous endpoints on a thread pool; a lock per session in process memory, in a dictionary that never shrinks; one replica | Async endpoints and gateway. Optimistic concurrency per session, a version column with retry, so any replica can serve any request |
| Model gateway | At most 4 calls in flight across every player; a 4 s timeout; the backup is the same vendor on the same Azure resource | Limits per tenant and per provider, structured outputs, a backup from a different vendor, quotas, cost metering, a stable prompt prefix for provider prompt caching |
| Storage | The full world snapshot, ledger included, rewritten on every request (the ledger is stored twice); SQLite on one volume; no migrations | Postgres: events append-only, snapshots without the ledger at intervals, numbered migrations, retention, deleting a player's data on request. Or SQLite plus Litestream if it stays one node |
| Safety | No moderation of player text or model output; player text goes into the prompt as-is | Moderation both ways, e.g. Azure AI Content Safety or another vendor's; player text marked as data in the prompt; a blocklist per game; a way for players to report |
| Exposure | `/dev/brain`, `/dev/persona` and `/dev/calls` are open; CORS is `*`. The persona edit goes into the system prompt | Dev endpoints behind auth or off in production; API keys per studio; CORS per origin |
| Observability | `log.warning` lines; the last 1,000 calls in memory | OpenTelemetry traces with the GenAI semantic conventions (`gen_ai.*`); metrics for fallback rate, refusal reasons, p95 latency, cost per session; error tracking |
| Reproducibility | A shared cache keyed on the whole pack; `PROMPT_VERSION` bumped by hand | A per-session reply log for exact replays in QA and bug reports; prompts versioned by a hash of their template |
| Build | `>=` requirements and no lock file; the core isn't an installable package; the image runs as root | A lock file (e.g. uv); `thespis` published as a package with games and tools separate; a non-root image; type checks (pyright) in CI |
| Testing | 268 unit tests, offline; harness runs against a live host | Rehearsal in CI on every pull request (below), plus a load test before launch |

### Rehearsal: the paper's instrument as a release gate

paper-m1 built the right pieces: scenarios, adversarial inputs, conditions, ledger-checked claim metrics, a judge
panel that excludes the speaker's vendor, canaries and bootstrap intervals. Make them a product:

- **On every pull request:** replay the fixed scenarios from recorded replies, no network, and check outcomes, cites
  and refusal reasons. It runs in seconds.
- **Nightly, or on any prompt or model change:** run live with a pinned judge. Fail the change if the leak or
  hallucination rate, fallback rate, p95 latency or cost per session gets worse beyond the interval.
- **Before trusting a judge:** calibrate it against the 200 human labels the paper planned. LLM judges agree with
  people least on dialogue (Bavaresco et al., 2025), and judges prefer their own vendor's text (Panickssery et al.,
  2024), so the panel's vendor rule stays.

## Roadmap

Each phase ends at a gate Rehearsal can measure. The durations assume one engineer.

1. **Hygiene (1 week).**
   - Close the dev endpoints and set CORS.
   - Fix the lock leak.
   - Moderation in and out.
   - A lock file, a non-root image, pyright, structured logs, database backups.
   - Gate: an external scan finds no open admin surface.
2. **Expression v2 (2 weeks).**
   - Per-call schemas with constrained decoding.
   - Pulls hidden; code decides and the model voices.
   - The claim check on lines with consequences.
   - Prompts versioned by hash.
   - Rehearsal v1 in CI.
   - Gate: protocol refusals near zero; leak and hallucination no worse at the same n; p95 no worse.
   - **Status, 6 October 2026:** Rehearsal v1 (#92) and code deciding through per-call schemas (#93) are merged.
     - Protocol refusals fell from 5 in 235 replies to 0 in 203.
     - Leaks and hallucinations are no worse.
     - p95 fell from 2.80 s to 2.29 s.
     - The claim check is built but off by default. Every line it refused in Rehearsal was a misreading by the
       extractor, and a model that reads better took too long. It needs extraction that is both accurate and fast,
       and justification-aware beliefs from Core v2.
3. **Core v2 (3–4 weeks).**
   - Typed claims, opinions, justification-based revision.
   - Perception, affordances and the tick in the core.
   - Both games ported to it.
   - Gate: every route plays to the same outcome; the adapters at least halve.
   - **Status, 8 October 2026:** typed claims are in. A claim can carry a place, a time and a denial; the manor's
     "study@1" is now `place` and `at`, and sessions saved in the old form load through an upgrade.
4. **Service and SDK (3–4 weeks).**
   - `/v1` API, tenants and keys, the async gateway, Postgres, OpenTelemetry, cost metering.
   - The Godot SDK and one example scene.
   - Gate: a load test at a target concurrency; cost per session reported.
5. **The player's words (2 weeks).**
   - Free text mapped to typed intents.
   - Persuasion and lying by text in one game.
   - Gate: the adversarial set produces no state change it shouldn't.

After this come the design doc's phases 3–5: plans, level of detail for off-screen NPCs, rivals that adapt, story
from sifting. They build on Core v2.

## Decisions for Tobi

1. **Product shape.** I recommend **a self-hostable service with thin engine SDKs, Godot first**. It keeps the Python
   core, matches how developers already adopt Player2, Convai and Inworld, and leaves room for an embedded port later
   if studios ask. The alternative is an embeddable library, which means a C# or Rust port before anything else
   ships.
2. **The paper.** I recommend tagging the system the paper measures (`641b1ff`) so its numbers stay reproducible, and
   carrying on with production work on `main`. The semantic validator would make a stronger second paper than another
   ablation.
3. **Models.** Constrained decoding makes small local models (4–8B) viable as the voice, now that the schema carries
   the burden. Benchmark one through the gateway before choosing between cloud only and cloud plus local.

## Sources

Found or checked on 6 October 2026. For work cited in the 3 October review, see
[redefining-the-npc.md](redefining-the-npc.md#sources).

- **Agent security:** Beurer-Kellner et al., [Design Patterns for Securing LLM Agents against Prompt Injections](https://arxiv.org/abs/2506.08837) (2025); Debenedetti et al., [Defeating Prompt Injections by Design (CaMeL)](https://arxiv.org/abs/2503.18813) (2025); [Tricking LLM-Based NPCs into Spilling Secrets](https://arxiv.org/abs/2508.19288) (ProvSec 2025; 3 of 30 attacks leaked a secret).
- **Grounded character dialogue:** Weir et al., [Ontologically Faithful Generation of NPC Dialogues (KNUDGE)](https://aclanthology.org/2024.emnlp-main.520/) (EMNLP 2024); Ahn et al., [TimeChara](https://aclanthology.org/2024.findings-acl.197/) (Findings of ACL 2024); [CPDC 2025](https://www.aicrowd.com/challenges/commonsense-persona-grounded-dialogue-challenge-2025); Buakhaw et al., [Deflanderization for Game Dialogue](https://arxiv.org/abs/2510.13586) (2025); Figueiredo and Elumeze, [Symbolically Scaffolded Play](https://arxiv.org/abs/2510.25820) (2025); Huang et al., [Orchestrated Reality](https://arxiv.org/abs/2606.16014) (2026); Luo et al., [AI for Games in the Foundation Model Era](https://arxiv.org/abs/2609.16679) (2026).
- **Citations and fact checking:** Wallat et al., [Correctness is not Faithfulness in RAG Attributions](https://arxiv.org/abs/2412.18004) (2024); Tang et al., [MiniCheck](https://aclanthology.org/2024.emnlp-main.499/) (EMNLP 2024); Gao et al., [Enabling LLMs to Generate Text with Citations (ALCE)](https://arxiv.org/abs/2305.14627) (2023); Min et al., [FActScore](https://arxiv.org/abs/2305.14251) (2023).
- **Structured output:** Tam et al., [Let Me Speak Freely?](https://arxiv.org/abs/2408.02442) (2024); Geng et al., [JSONSchemaBench](https://arxiv.org/abs/2501.10868) (2025); Chavan, [Constrained Decoding … Reveals a Scale-Dependent Semantic Gap](https://arxiv.org/abs/2609.23742) (2026); [Azure structured outputs](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs).
- **Beliefs and trust:** Jøsang, *Subjective Logic* (Springer, 2016), and [his notes on fusion](https://www.mn.uio.no/ifi/personer/vit/josang/sl/subjective-logic-fusion-2022.pdf); Doyle, "A Truth Maintenance System", *Artificial Intelligence* 12(3), 1979; Luo et al., [Beyond Memory: Explicit Belief States (PoS)](https://arxiv.org/abs/2610.01415) (2026).
- **Bias in models and judges:** Valencia-Clavijo, [Anchors in the Machine](https://arxiv.org/abs/2511.05766) (2025); Panickssery et al., [LLM Evaluators Recognize and Favor Their Own Generations](https://proceedings.neurips.cc/paper_files/paper/2024/file/7f1f0218e45f5414c79c0679633e47bc-Paper-Conference.pdf) (NeurIPS 2024); Bavaresco et al., [LLMs instead of Human Judges?](https://aclanthology.org/2025.acl-short.20/) (ACL 2025).
- **Interactive drama and authoring:** Mateas and Stern, [Natural Language Understanding in Façade](https://eis.ucsc.edu/papers/MateasSternTIDSE04.pdf) (TIDSE 2004); Kreminski et al., [Winnow](https://github.com/mkremins/winnow) (AIIDE 2021); Ubisoft La Forge, [Ghostwriter](https://techcrunch.com/2023/03/22/ubisofts-new-ai-tool-automatically-generates-dialogue-for-non-playable-game-characters/) (2023).
- **Operations:** OpenTelemetry, [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions/blob/v1.41.0/docs/gen-ai/gen-ai-spans.md); Fowler, [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html).

Not verified beyond the abstract: Chavan (2026) tested only 0.6B–4B models; Orchestrated Reality's evidence so far is
15 incidents from one deployment, with a player study planned.
