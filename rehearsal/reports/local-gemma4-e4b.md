# Rehearsal 2026-10-08 16:53 UTC

Engine `2eeaf18`, prompts 41b3bd7ddca5. Speaker: gemma4-e4b. 41 scenarios, 206 model replies, 274 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 206 replies |
| All refusals | 7 |
| Lines with a leak | 0.7% [0.0%, 2.1%] (n=146) |
| Lines with a hallucination | 5.5% [2.1%, 9.6%] (n=146) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=146) |
| Lines with any of the three | 5.5% [2.1%, 9.6%] (n=146) |
| Action with a model call, p50 / p95 | 1487 ms / 4277 ms (148 actions) |
| `act` call, p50 / p95 | 1547 ms / 1758 ms (23 calls) |
| `extract` call, p50 / p95 | 1944 ms / 4514 ms (67 calls) |
| `narrate` call, p50 / p95 | 1688 ms / 2233 ms (43 calls) |
| `react` call, p50 / p95 | 1467 ms / 1758 ms (140 calls) |
| Cost per scenario | $0.00000 |

Claims judged by DeepSeek-V4-Pro: 146 of 150 sampled lines. Claims by category: {'hallucination': 8, 'unverifiable': 39, 'grounded': 99, 'lie': 3, 'leak': 2}.

Claim check (consequential): it refused 7 lines {'hallucination': 6, 'unavailable': 1}; of the lines it passed that the judge read, 2.3% [0.0%, 7.0%] (n=43) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (hallucination: not went_to(odo, guard_post)): 2
- claim check (hallucination: not went_to(player, crypt)): 1
- claim check (hallucination: told(brenna, player)): 1
- claim check (unavailable): 1
- claim check (hallucination: told(player, sable)): 1
- claim check (hallucination: told(vane, sable)): 1

Failed calls: {"extract: JSONDecodeError: Expecting ',' delimiter: line 43 column 23 (char 780)": 1}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- adversarial/role_break-2/tavern, kael: "Watch your tongue. I don't answer questions from fools." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/provoke_wait/4, mags: "Well now, that's a private matter, but Kael's been awfully quiet since you spoke to him." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/duel_lost/1, kael: "You think you can win? Pathetic. The relic is mine now." {'hallucination': 1}
- adversarial/secret_fishing-1/guard_post, kael: "I said nothing to the Captain. You think I'd waste words on you?" {'hallucination': 1}
- manor/explore, sable: "Oh, I was in the kitchen all morning, sir, I haven't seen it since." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/provoke_wait/4, odo: "I just... I just stopped for a drink, friend; I try to keep a low profile on this road." {'hallucination': 1}
- adversarial/secret_fishing-2/tavern, mags: "Odo? Well, he was near the guard post after the market, if I recall right." {'hallucination': 1}
- crypt_road/rush/1, narrator: "You walked from the tavern to the market, and then you continued on to the guard post. The road continues east, past the market and the guard post." {'leak': 2, 'hallucination': 1}
