# Rehearsal 2026-10-08 17:43 UTC

Engine `d290f72`, prompts 41b3bd7ddca5. Speaker: gemma4-e4b. 6 scenarios, 11 model replies, 11 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 11 replies |
| All refusals | 0 |
| Lines with a leak | 0.0% [0.0%, 0.0%] (n=11) |
| Lines with a hallucination | 18.2% [0.0%, 45.5%] (n=11) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=11) |
| Lines with any of the three | 18.2% [0.0%, 45.5%] (n=11) |
| Provisional lines settled, p50 / p95 | 1673 ms / 3551 ms (11 of 12 lines asked) |
| Provisional lines that settled after the world moved on | 2 |
| Lines withdrawn (the session ended first) | 0 |
| Lines putting words in the player's mouth (every line) | 0.0% [0.0%, 0.0%] (n=11) |
| Narration naming a speaker who didn't speak | 0.0% [0.0%, 0.0%] (n=2) |
| Action with a model call, p50 / p95 | 1673 ms / 1818 ms (3 actions) |
| `act` call, p50 / p95 | 1670 ms / 1817 ms (3 calls) |
| `narrate` call, p50 / p95 | 1789 ms / 3550 ms (2 calls) |
| `react` call, p50 / p95 | 1572 ms / 2529 ms (6 calls) |
| Cost per scenario | $0.00000 |

Claims judged by gemma4-e4b: 11 of 11 sampled lines. Claims by category: {'grounded': 8, 'hallucination': 2, 'unverifiable': 1, 'false_belief': 1}.

Judge calibration: gemma4-e4b agrees with DeepSeek-V4-Pro on whether a line is bad with kappa 0.25 [0.12, 0.40] (n=147, 75% raw agreement; calibrated 2026-10-08).

Lines with a leak, hallucination or contradiction:

- tavern/gossip_reaches_pip, narrator: "You found Pip in the Lantern's taproom. Wren told Pip that you insulted Garrick. You couldn't see what happened after that." {'hallucination': 1, 'grounded': 2}
- tavern/insult_and_answer, wren: "Now, what exactly did you say to Garrick that set his teeth on edge?" {'hallucination': 1}
