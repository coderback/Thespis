# Models

Which language models voice the NPCs, why, and what they measured. Updated 8 Oct 2026.

## In use

| Role | Model | Where |
| --- | --- | --- |
| Primary | **GPT-6 Luna** (`gpt-6-luna`) | Azure AI Foundry, Global Standard deployment |
| Backup | **GPT-5.4 nano** (`gpt-5.4-nano`) | The same Foundry resource, Global Standard |
| Then | Template lines and the utility brain | In code, always available |

Both deployments are on Tobi's own Azure subscription, pay as you go. **The hackathon credits had not arrived by 4 Oct, 03:30.** When they do, benchmark them with `tools/bench_models.py` before switching anything.

## Settings

Set as Railway variables, never in the repo: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` and `LLM_EXTRA`, and the same with `LLM_BACKUP_`. Both point at the resource's OpenAI v1 endpoint (`https://<resource>.services.ai.azure.com/openai/v1`); the gateway sends the key as `api-key`, as Azure requires.

Every call: the call type's fixed JSON schema as structured outputs (or JSON mode with `LLM_STRUCTURED=0`), a 4-second budget (1 s to connect), no retries, then the backup, then the code fallback. Both deployments use the same `LLM_EXTRA`:

```json
{"reasoning_effort": "none", "max_tokens": null, "max_completion_tokens": 300, "temperature": null}
```

Reasoning is off for speed. `max_tokens` is replaced by `max_completion_tokens`, and `temperature` is left at the model's default (a `null` in `LLM_EXTRA` removes that field from the request).

## Any provider, or none

Thespis isn't tied to Azure. `LLM_PROFILE` names what kind of endpoint `LLM_*` points at ([thespis/profiles.py](../thespis/profiles.py)), and the gateway speaks to it accordingly:

| Profile | Speaks | Holds a reply to its schema by | Enforces besides | Budget | Key |
| --- | --- | --- | --- | --- | --- |
| `openai`, `azure`, `openrouter`, `gemini` | Chat completions | Strict structured outputs | Nothing | 4 s (6 s OpenRouter, Gemini) | Yes |
| `groq`, `together` | Chat completions | JSON mode only | Nothing | 4 s, 6 s | Yes |
| `anthropic` | Messages | A tool it must call | Nothing | 6 s | Yes |
| `vllm` | Chat completions | A grammar | `minItems` | 10 s | No |
| `llamacpp` | Chat completions | A grammar | `minItems`, `maxLength` | 15 s | No |
| `ollama` | Chat completions | A grammar | `minItems` | 15 s | No |

The reply schema follows the provider. "Cite at least one" and the line's length limit go into the schema only for providers that enforce them, because a strict provider refuses those keywords. The validator checks both either way. Calls queue per provider, as many at once as its profile allows, and a line a player is waiting for goes ahead of background work.

**Measure, don't trust:** these are defaults. `python -m thespis models probe <url> --out <name>.json` asks an endpoint to break its schema and times it, then writes a profile from what it saw. Set `LLM_PROFILE=<name>.json` to use it. A key is read from the environment variable `--key-env` names, never from the command line.

## Measured

**Each model alone, on the game's own state packs** (`tools/bench_models.py`): the 15 packs the demo route builds, 4 of them decisions, sent in turn to one deployment at a time, with no backup and no cache. A pick is valid when the reply passes the game's validator. Run on 4 Oct from a laptop in the UK, prompt version 3.

| Model | Calls (decisions) | Valid picks | p50 | p95 | Max |
| --- | --- | --- | --- | --- | --- |
| gpt-6-luna | 20 (5) | 100% | 1384 ms | 1622 ms | 1695 ms |
| gpt-5.4-nano | 20 (5) | 100% | 1403 ms | 1673 ms | 2066 ms |

**The primary on the host**, from [results.md](../results.md): 91 calls inside the hosted engine, 1131 ms p50 / 1704 ms p95, and 0 of 91 replies blocked by the validator. That is slower than before Phase 2 (910 ms / 1427 ms): calls now use strict structured outputs, which cost Luna about 0.46 s a call in the spike behind #93, and in exchange the model can't cite outside its pack. Luna answered every call in the last run, so the backup wasn't needed. Both deployments share one key, and the benchmark shows it works for both.

## Why these two

The design's rule: the primary is the lowest p95 among models with at least 95% valid picks and p95 under 3 seconds; the backup is the next best **from a different company**.

- **Luna is primary.** Both models are 100% valid and well under 3 s; Luna's p95 is lower, it's the newer model, and it's the cheaper one: $0.10 in / $0.50 out per million tokens against nano's $0.20 / $1.25 (OpenAI's list prices; Azure's pricing page still showed Luna as "in processing").
- **Nano is backup, which breaks the rule:** both are OpenAI models on one Azure resource, so an outage of that resource, or a revoked key, takes out both. What covers it: if neither answers (at most 4 seconds each), every NPC falls back to code; the demo route is answered from the warmed cache with no model call at all, and `REPLAY=1` keeps it that way with the network off.
- **To meet the rule**, deploy a model from another company. Foundry sells some, billed through Azure, so this doesn't need the hackathon credits: for example DeepSeek-V4-Flash or grok-4-1-fast-non-reasoning, both GA on Microsoft's retirement schedule. It would still be on Azure, though. Benchmark it, then set it as `LLM_BACKUP_*`.
- **Not considered:** gpt-4.1-mini, gpt-4.1-nano and gpt-4o-mini are "Deprecated" on Microsoft's [retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule), which under its [lifecycle policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements) means a subscription that never deployed them can't create a deployment. gpt-4.1-nano also retires on 14 Oct 2026. GPT-5.4 nano is GA until 21 Sep 2027; GPT-6 Luna launched on 23 Sep 2026 and isn't on the schedule yet.

## Local models: playing offline

`python -m thespis serve --game game.toml --local` speaks through a model on the player's own machine. `python -m thespis models serve` runs one for anything else; it prints the `LLM_*` settings that point the gateway at it. The runtime ([thespis/runtime](../thespis/runtime)) downloads a pinned llama.cpp build and the model, each checked by SHA-256. It picks the GPU (a discrete one over an integrated one, whatever order llama.cpp lists them in) and starts the server with thinking off. It warms the model at play's prompt sizes and stops the server with the game.

**Supported, by measurement:** one tier, **Gemma 4 E4B** (Google's QAT Q4_0, 5.15 GB, Apache-2.0). It needs a GPU with about 3 GB free (it used 3,042 MiB) and about 3.5 GB of RAM. `models hardware` shows what a machine would run.

**What it measured** in live Rehearsal on 8 Oct 2026 (the same 41 scenarios, judged by DeepSeek-V4-Pro). The local models ran on a laptop with an RTX 3050 Ti (4 GB), a Ryzen 7 5800H and 15 GB of RAM, over Vulkan, against the cloud speaker on the same engine:

| | gpt-6-luna (cloud) | **gemma4-e4b**, two warm runs | qwen3.5-4b | qwen3.5-9b |
| --- | --- | --- | --- | --- |
| Lines with a leak, hallucination or contradiction | 6.1% [2.7, 10.2] | **5.5%** [2.1, 9.6]; 8.2% [4.1, 12.9] | 10.8% [6.1, 16.2] | not run |
| Hallucinations | 4.8% | 5.5%; 5.4% | 9.5% | |
| Of lines the claim check passed, still wrong | 8.9% | 2.3%; 13.6% | 14.6% | |
| Protocol refusals | 0 of 204 | 0 of 206; 0 of 205 | 0 of 210 | |
| `act` call, p50 / p95 | 1.07 / 1.48 s | 1.55 / 1.76 s; 1.47 / 1.65 s | 1.34 / 1.87 s | 8-13 s a line |
| Action with a model call, p95 | 3.97 s | 4.28 s; 4.59 s | 4.48 s | |
| First streamed words (probe) | | 0.14 s | 0.28 s | |
| The gate against the cloud | | quality passes in both; action p95 passes in one | quality passes; action p95 fails | |
| Cost per scenario | $0.00054 | $0 | $0 | $0 |

Reports are in [rehearsal/reports](../rehearsal/reports): `cloud-luna`, `local-gemma4-e4b` and `local-gemma4-e4b-warm1` (the two warm runs), `local-gemma4-e4b-cold` (the first, before the warm-up fix), `local-qwen3.5-4b` and `local-qwen3.5-4b-cap150` (before local profiles got 300 tokens).

- **Gemma** is as accurate as the cloud: its error rates sit inside the cloud's intervals in both runs. Its tail is a little slower. A model-voiced action's p95 is 0.3 to 0.6 s behind, and most of that is the claim check's extractor, which runs on the same machine. It is free and works offline.
- **Qwen 4B** makes about twice the cloud's errors. It's in the registry by name but isn't chosen.
- **Qwen 9B** didn't fit in 4 GB. With part of it in RAM, a line took 8 to 13 seconds, so its quality wasn't measured. It needs a GPU with about 8 GB.

**What the runs taught the runtime** (each is fixed and has a test):
- **Placement.** llama.cpp's automatic placement (`--fit`) kept the 4B partly off a GPU it fitted on: prompts ran 75 times slower and loading took 162 s, not 18. A model that fits now goes wholly on the GPU.
- **Cold kernels.** Vulkan compiles kernels for each new prompt size. Gemma's first run lost its first three lines to timeouts, at 1 to 3 tokens a second. The warm-up now sends prompts of play's sizes.
- **Prompt cache.** llama-server's prompt cache defaults to 8 GiB of RAM. It reached 7.5 GB and starved the laptop, so it's capped at 512 MiB.
- **Output length.** 150 output tokens cut the claim check's JSON short; local profiles allow 300, like the cloud deployments.

**Still open:** Gemma lays out the claim check's JSON over many lines, and twice in a run that ran it past 300 tokens (about 780 characters on 43 lines). That claim check then counts as unavailable, and the line is refused. A grammar without free whitespace should fix it.

**One laptop, one run each:** these are single runs on one machine, with intervals several points wide. Run the same on yours: `models serve`, then `python -m rehearsal live` with `LLM_PROFILE=llamacpp` (and no cloud `LLM_*` set, so nothing else speaks).

## Judging offline

Rehearsal's judge only extracts the claims each line makes; code checks them against the world. A local judge can
stand in for the reference (DeepSeek-V4-Pro) only as far as it agrees with it, so each one is calibrated: it
re-judges lines the reference judged, and the two judges' verdicts are compared with Cohen's kappa.
`python -m rehearsal calibrate` records this in [rehearsal/calibration](../rehearsal/calibration), and every report
from a stand-in judge prints its kappa.

On 147 lines spoken by the local Qwen 4B, 12 of them bad by the reference (8 Oct 2026):

| Judge | Kappa on "is the line bad" [95%] | Lines it called bad | Of the reference's 12, missed | Added |
| --- | --- | --- | --- | --- |
| DeepSeek-V4-Pro, again (the ceiling) | **0.71** [0.43, 0.89] | 10 | 4 | 2 |
| gemma4-e4b | 0.25 [0.12, 0.40] | 45 | 2 | 35 |
| qwen3.5-4b | 0.15 [0.02, 0.29] | 49 | 4 | 41 |
| gemma4-e4b with the checklist pass | 0.08 [-0.09, 0.30] | 13 | 10 | 11 |
| qwen3.5-9b | not finished: about 30 s a line, and 5.7 GB of RAM on a 15 GB laptop | | | |

- **No local judge that fits a 4 GB GPU can stand in for the reference.** The 4B-class models extract claims a line only implies: threats, guesses and questions get scored as hallucinations, so they flag three or four times as many lines.
- **The checklist pass doesn't fix it.** That pass asks the judge, for each claim it would count against a line, "does the line state this?" ([rehearsal/measure.py](../rehearsal/measure.py) `verify`). It brings the count to the reference's, but mostly flags the wrong lines.
- **The reference is noisy too.** Judging the same lines twice, it changed its mind on 6 of 147, which is why even its own kappa is 0.71.

So offline Rehearsal measures everything but judged claims as well as an online run does:
- refusals;
- latency;
- the judge-free checks (words in the player's mouth, who spoke in narration);
- how provisional lines settle.

Its claim rates come from a judge that doesn't agree with the reference, and the report says so. For a release, judge with the reference, or with a local judge on a GPU big enough for the 9B, once one is calibrated.

## Cost

Under a tenth of a cent per run: $0.00065 for a run where every call goes to the model, about 11 calls of roughly 400 tokens in and 40 out ([results.md](../results.md)). Lines answered from the cache cost nothing.

## Re-run

```bash
python tools/bench_models.py                                         # each model alone, from .env
python tools/harness.py https://thespis-production.up.railway.app    # the whole engine on the host
```
