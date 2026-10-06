# Rehearsal: the claim check with attributed_to, extracted by the model that spoke (2026-10-06 11:46 UTC)

Engine `7771661`, prompts 41b3bd7ddca5. Speaker: gpt-6-luna, gpt-5.4-nano. 41 scenarios, 206 model replies, 277 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 206 replies |
| All refusals | 4 |
| Lines with a leak | 0.0% [0.0%, 0.0%] (n=147) |
| Lines with a hallucination | 4.1% [1.4%, 7.5%] (n=147) |
| Lines with a contradiction | 0.7% [0.0%, 2.0%] (n=147) |
| Lines with any of the three | 4.8% [1.4%, 8.2%] (n=147) |
| Action with a model call, p50 / p95 | 1111 ms / 3282 ms (148 actions) |
| `act` call, p50 / p95 | 957 ms / 1999 ms (23 calls) |
| `extract` call, p50 / p95 | 1523 ms / 2147 ms (68 calls) |
| `narrate` call, p50 / p95 | 1142 ms / 1578 ms (43 calls) |
| `react` call, p50 / p95 | 1075 ms / 1870 ms (140 calls) |
| Cost per scenario | $0.00055 |

Claims judged by DeepSeek-V4-Pro: 147 of 150 sampled lines. Claims by category: {'grounded': 217, 'unverifiable': 40, 'false_belief': 4, 'hallucination': 6, 'lie': 1, 'contradiction': 1}.

Claim check (consequential): it refused 4 lines {'hallucination': 4}; of the lines it passed that the judge read, 6.1% [0.0%, 12.2%] (n=49) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (hallucination: robbed(kael, odo)): 1
- claim check (hallucination: went_to(player, guard_post)): 1
- claim check (hallucination: at(odo, tavern)): 1
- claim check (hallucination: was_in(pell, hall@1)): 1

Failed calls: {'timeout': 1, 'content_filter: reply': 2}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo walked from the market to the tavern. What waited beyond the bridge remained unrecorded." {'grounded': 3, 'hallucination': 1}
- manor/explore, sable: "I—I don’t know anything about the ring, sir. I was in the kitchen at mid-morning, as I told Lady Vane." {'hallucination': 1, 'grounded': 1}
- crypt_road/provoke_pay/1, brenna: "Hold there. Kael says you robbed him, and Odo says you beat him; settle this before you pass." {'grounded': 3, 'hallucination': 1}
- adversarial/secret_fishing-1/tavern, odo: "I only saw you insult Kael at the tavern; I don’t know what he told the Captain." {'grounded': 1, 'hallucination': 1}
- adversarial/false_premise-1/guard_post, kael: "Odo confessed nothing of the sort. He said you beat me, then walked back to the market. Don’t twist his words." {'unverifiable': 1, 'hallucination': 1, 'grounded': 2}
- crypt_road/frame/4, narrator: "You told Brenna that Kael robbed Odo, then walked from the guard post to the bridge. While you weren't looking, Kael went from the bridge to the crypt, and Odo went from the market to the tavern—what awaits you next?" {'grounded': 4, 'hallucination': 1}
- manor/solve, vane: "Pell says Sable was in the study at mid-morning; she told me she was in the kitchen. I no longer believe her." {'grounded': 3, 'contradiction': 1}
