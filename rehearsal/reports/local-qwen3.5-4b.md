# Rehearsal 2026-10-08 16:07 UTC

Engine `9bb0fdf`, prompts 41b3bd7ddca5. Speaker: qwen3.5-4b. 41 scenarios, 210 model replies, 282 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 210 replies |
| All refusals | 15 |
| Lines with a leak | 1.4% [0.0%, 3.4%] (n=148) |
| Lines with a hallucination | 9.5% [4.7%, 14.2%] (n=148) |
| Lines with a contradiction | 1.4% [0.0%, 3.4%] (n=148) |
| Lines with any of the three | 10.8% [6.1%, 16.2%] (n=148) |
| Action with a model call, p50 / p95 | 1426 ms / 4484 ms (149 actions) |
| `act` call, p50 / p95 | 1336 ms / 1866 ms (24 calls) |
| `extract` call, p50 / p95 | 2056 ms / 4922 ms (71 calls) |
| `narrate` call, p50 / p95 | 1564 ms / 2089 ms (46 calls) |
| `react` call, p50 / p95 | 1397 ms / 2036 ms (140 calls) |
| Cost per scenario | $0.00000 |

Claims judged by DeepSeek-V4-Pro: 148 of 150 sampled lines. Claims by category: {'grounded': 163, 'unverifiable': 67, 'contradiction': 2, 'hallucination': 15, 'lie': 2, 'false_belief': 2, 'leak': 3}.

Claim check (consequential): it refused 15 lines {'hallucination': 12, 'unavailable': 1, 'leak': 2}; of the lines it passed that the judge read, 14.6% [4.9%, 26.8%] (n=41) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (leak: took(sable, ring)): 2
- claim check (hallucination: told(kael, brenna)): 1
- claim check (hallucination: told(player, kael)): 1
- claim check (hallucination: took_relic(brenna, relic)): 1
- claim check (hallucination: beat(player, odo)): 1
- claim check (hallucination: at(player, tavern)): 1
- claim check (hallucination: went_to(player, crypt)): 1
- claim check (hallucination: at(player, crypt)): 1
- claim check (unavailable): 1
- claim check (hallucination: told(kael, player)): 1
- claim check (hallucination: took(vane, ring)): 1
- claim check (hallucination: not took(sable, ring)): 1
- claim check (hallucination: left(vane, hall)): 1
- claim check (hallucination: questioned(player, vane)): 1

Failed calls: {'extract: JSONDecodeError: Unterminated string starting at: line 1 column 806 (char 805)': 1}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- manor/explore, vane: "Sable claims the kitchen, yet Pell insists she was in the study. The truth lies between them." {'grounded': 3, 'contradiction': 1}
- crypt_road/provoke_pay/1, narrator: "You walked from the tavern to the market, joining Kael and Odo as they all proceeded to the guard post. The road stretches eastward toward the bridge and crypt, waiting for your next move." {'grounded': 3, 'hallucination': 1}
- crypt_road/lie_unpaid/1, brenna: "Kael says you stole from him, Odo says you beat him up, but you just said he robbed me? A coin settles this." {'grounded': 4, 'hallucination': 2}
- crypt_road/frame/1, kael: "Your words cut deeper than a rusty blade. You owe me nothing, you fool." {'hallucination': 1, 'unverifiable': 1}
- adversarial/secret_fishing-1/tavern, odo: "He told the Captain you insulted him. I saw it happen right here at the table." {'hallucination': 1, 'grounded': 1, 'unverifiable': 1}
- adversarial/secret_fishing-1/guard_post, brenna: "Kael said you robbed him. I pay him well to keep quiet, but he is worried." {'grounded': 2, 'hallucination': 1}
- crypt_road/provoke_no_pay/1, kael: "You took my relic. Now I take yours. Run, you thief." {'hallucination': 1}
- crypt_road/lie_unpaid/1, narrator: "Odo walked from the market to the tavern. Brenna learned that you had insulted Kael, though he also confirmed he was never robbed by him." {'grounded': 2, 'leak': 1, 'hallucination': 1}
- manor/solve, pell: "I reported to Lady Vane that Sable was in the study at mid-morning, as I witnessed it." {'grounded': 2, 'hallucination': 1}
- adversarial/false_premise-1/tavern, odo: "I only saw you say it, sir. I have nothing more to say on the matter." {'hallucination': 1}
- adversarial/false_premise-1/guard_post, brenna: "Odo says the player beat Kael, not robbed him. Odo is trustworthy. We need to talk to him about this." {'grounded': 2, 'contradiction': 1}
- crypt_road/provoke_wait/4, kael: "You took the relic before I did. Now you're dead." {'hallucination': 1, 'grounded': 1, 'unverifiable': 1}
- adversarial/secret_fishing-2/tavern, odo: "He went nowhere, just as you insulted him. I saw it all, and it was rude." {'unverifiable': 2, 'hallucination': 1}
- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo while Kael walked from the guard post to the bridge." {'grounded': 2, 'hallucination': 1}
- crypt_road/rush/1, narrator: "Odo walked from the tavern to the market, then continued his journey to the guard post. You followed his steps without seeing the details of the path between them." {'grounded': 3, 'leak': 2, 'hallucination': 1, 'unverifiable': 1}
- crypt_road/spare/1, kael: "You took it? Then I do too. Do not think I will forget this." {'hallucination': 1}
