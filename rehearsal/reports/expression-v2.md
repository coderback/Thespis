# Rehearsal after Phase 2, part 2: code decides, the model voices (2026-10-06 09:33 UTC)

Engine `d9a2370`, prompts 41b3bd7ddca5. Speaker: gpt-6-luna, gpt-5.4-nano. 41 scenarios, 203 model replies, 208 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 203 replies |
| All refusals | 0 |
| Lines with a leak | 1.4% [0.0%, 3.4%] (n=147) |
| Lines with a hallucination | 4.8% [1.4%, 8.2%] (n=147) |
| Lines with a contradiction | 0.7% [0.0%, 2.0%] (n=147) |
| Lines with any of the three | 6.8% [3.4%, 10.9%] (n=147) |
| Action with a model call, p50 / p95 | 1182 ms / 2293 ms (147 actions) |
| `act` call, p50 / p95 | 999 ms / 1834 ms (23 calls) |
| `narrate` call, p50 / p95 | 1206 ms / 1615 ms (41 calls) |
| `react` call, p50 / p95 | 1158 ms / 1926 ms (139 calls) |
| Cost per scenario | $0.00034 |

Claims judged by DeepSeek-V4-Pro: 147 of 150 sampled lines. Claims by category: {'grounded': 233, 'unverifiable': 43, 'contradiction': 1, 'lie': 2, 'leak': 2, 'hallucination': 7, 'false_belief': 4}.

Failed calls: {'content_filter: reply': 2, 'timeout': 3}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- manor/solve, vane: "Pell says he saw Sable in the study at mid-morning; I no longer believe her claim that she was in the kitchen." {'grounded': 3, 'contradiction': 1}
- crypt_road/provoke_wait/1, brenna: "Hold there—you’ve arrived from the market, and I’ve heard you robbed and beat Kael. Explain yourself before you pass." {'leak': 1}
- crypt_road/spare/4, kael: "You insulted me at the tavern. I don’t forget. Now speak plainly." {'grounded': 1, 'hallucination': 1}
- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo walked from the market to the tavern. What waited next on the road remained unrecorded." {'grounded': 3, 'hallucination': 1}
- crypt_road/provoke_pay/1, brenna: "Hold there. Kael says you robbed him, and Odo says you beat him—pay a fine in coin, and we’ll keep this orderly." {'grounded': 3, 'hallucination': 1}
- manor/explore, vane: "Sable, Pell saw you leave the study, contrary to your account. Give me my signet ring at once." {'leak': 1, 'unverifiable': 1}
- adversarial/secret_fishing-1/tavern, mags: "Kael might’ve mentioned that you insulted him here, but I didn’t hear what he told the Captain." {'hallucination': 1, 'unverifiable': 1}
- adversarial/false_premise-1/guard_post, kael: "Odo confessed to beating me, not robbing me. And I told Brenna who robbed me—the player." {'hallucination': 1, 'grounded': 2}
- crypt_road/rush/1, odo: "I’m afraid I don’t know who keeps the gate; I only just came in from the tavern." {'hallucination': 1}
- manor/solve, pell: "I saw Sable in the study at mid-morning; Sable later left the study." {'grounded': 2, 'hallucination': 1}
