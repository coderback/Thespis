# Models

Which language models voice the NPCs, why, and what they measured. Updated 4 Oct 2026.

## In use

| Role | Model | Where |
| --- | --- | --- |
| Primary | **GPT-6 Luna** (`gpt-6-luna`) | Azure AI Foundry, Global Standard deployment |
| Backup | **GPT-5.4 nano** (`gpt-5.4-nano`) | The same Foundry resource, Global Standard |
| Then | Template lines and the utility brain | In code, always available |

Both deployments are on Tobi's own Azure subscription, pay as you go. **The hackathon credits had not arrived by 4 Oct, 03:30.** When they do, benchmark them with `tools/bench_models.py` before switching anything.

## Settings

Set as Railway variables, never in the repo: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` and `LLM_EXTRA`, and the same with `LLM_BACKUP_`. Both point at the resource's OpenAI v1 endpoint (`https://<resource>.services.ai.azure.com/openai/v1`); the gateway sends the key as `api-key`, as Azure requires.

Every call: JSON mode, a 4-second budget (1 s to connect), no retries, then the backup, then the code fallback. Both deployments use the same `LLM_EXTRA`:

```json
{"reasoning_effort": "none", "max_tokens": null, "max_completion_tokens": 300, "temperature": null}
```

Reasoning is off for speed. `max_tokens` is replaced by `max_completion_tokens`, and `temperature` is left at the model's default (a `null` in `LLM_EXTRA` removes that field from the request).

## Measured

**Each model alone, on the game's own state packs** (`tools/bench_models.py`): the 15 packs the demo route builds, 4 of them decisions, sent in turn to one deployment at a time, with no backup and no cache. A pick is valid when the reply passes the game's validator. Run on 4 Oct from a laptop in the UK, prompt version 3.

| Model | Calls (decisions) | Valid picks | p50 | p95 | Max |
| --- | --- | --- | --- | --- | --- |
| gpt-6-luna | 20 (5) | 100% | 1384 ms | 1622 ms | 1695 ms |
| gpt-5.4-nano | 20 (5) | 100% | 1403 ms | 1673 ms | 2066 ms |

**The primary on the host**, from [results.md](../results.md): 80 calls inside the hosted engine, 1315 ms p50 / 1585 ms p95, and 0 of 80 replies blocked by the validator. The backup has never been needed on the host: Luna answered every call. Both deployments share one key, and the benchmark shows it works for both.

## Why these two

The design's rule: the primary is the lowest p95 among models with at least 95% valid picks and p95 under 3 seconds; the backup is the next best **from a different company**.

- **Luna is primary.** Both models are 100% valid and well under 3 s; Luna's p95 is lower, it's the newer model, and it's the cheaper one: $0.10 in / $0.50 out per million tokens against nano's $0.20 / $1.25 (OpenAI's list prices; Azure's pricing page still showed Luna as "in processing").
- **Nano is backup, which breaks the rule:** both are OpenAI models on one Azure resource, so an outage of that resource, or a revoked key, takes out both. What covers it: if neither answers (at most 4 seconds each), every NPC falls back to code; the demo route is answered from the warmed cache with no model call at all, and `REPLAY=1` keeps it that way with the network off.
- **To meet the rule**, deploy a model from another company. Foundry sells some, billed through Azure, so this doesn't need the hackathon credits: for example DeepSeek-V4-Flash or grok-4-1-fast-non-reasoning, both GA on Microsoft's retirement schedule. It would still be on Azure, though. Benchmark it, then set it as `LLM_BACKUP_*`.
- **Not considered:** gpt-4.1-mini, gpt-4.1-nano and gpt-4o-mini are "Deprecated" on Microsoft's [retirement schedule](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule), which under its [lifecycle policy](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements) means a subscription that never deployed them can't create a deployment. gpt-4.1-nano also retires on 14 Oct 2026. GPT-5.4 nano is GA until 21 Sep 2027; GPT-6 Luna launched on 23 Sep 2026 and isn't on the schedule yet.

## Cost

Under a tenth of a cent per run: $0.00066 for a run where every call goes to the model, about 11 calls of roughly 400 tokens in and 40 out ([results.md](../results.md)). Lines answered from the cache cost nothing.

## Re-run

```bash
python tools/bench_models.py                                         # each model alone, from .env
python tools/harness.py https://thespis-production.up.railway.app    # the whole engine on the host
```
