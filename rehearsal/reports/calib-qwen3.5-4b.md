# Rehearsal 2026-10-08 17:18 UTC

Engine `8be633b`, prompts 41b3bd7ddca5. Speaker: qwen3.5-4b. 41 scenarios, 209 model replies, 280 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 209 replies |
| All refusals | 12 |
| Lines with a leak | 1.4% [0.0%, 3.4%] (n=147) |
| Lines with a hallucination | 7.5% [3.4%, 12.2%] (n=147) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=147) |
| Lines with any of the three | 8.2% [4.1%, 12.9%] (n=147) |
| Action with a model call, p50 / p95 | 1579 ms / 5130 ms (148 actions) |
| `act` call, p50 / p95 | 1492 ms / 2270 ms (23 calls) |
| `extract` call, p50 / p95 | 2270 ms / 4578 ms (71 calls) |
| `narrate` call, p50 / p95 | 1753 ms / 1990 ms (46 calls) |
| `react` call, p50 / p95 | 1519 ms / 2193 ms (140 calls) |
| Cost per scenario | $0.00000 |

Claims judged by DeepSeek-V4-Pro: 147 of 150 sampled lines. Claims by category: {'unverifiable': 50, 'grounded': 173, 'hallucination': 11, 'leak': 3, 'lie': 2, 'false_belief': 1}.

Claim check (consequential): it refused 12 lines {'hallucination': 9, 'leak': 3}; of the lines it passed that the judge read, 17.1% [7.3%, 29.3%] (n=41) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (leak: took(sable, ring)): 3
- claim check (hallucination: robbed(kael, odo)): 2
- claim check (hallucination: went_to(odo, bridge)): 1
- claim check (hallucination: went_to(kael, tavern)): 1
- claim check (hallucination: went_to(player, tavern)): 1
- claim check (hallucination: insulted(player, brenna)): 1
- claim check (hallucination: left(player, study)): 1
- claim check (hallucination: not left(sable, study)): 1
- claim check (hallucination: told(vane, player)): 1

Lines with a leak, hallucination or contradiction:

- manor/explore, vane: "Pell saw her in the study, yet she claims the kitchen? Liar. The truth is hidden, not spoken." {'grounded': 1, 'unverifiable': 1, 'hallucination': 1}
- crypt_road/duel_lost/1, narrator: "You arrived at the crypt where Odo waited for you. Odo had just told Brenna that you insulted Kael." {'leak': 1, 'hallucination': 1, 'grounded': 2}
- crypt_road/provoke_no_pay/1, narrator: "You heard Odo tell Brenna that you insulted Kael. Odo then walked from the guard post back to the market." {'grounded': 3, 'hallucination': 1}
- crypt_road/provoke_pay/1, kael: "You took my relic? I told Brenna you stole it. I told her you beat me. I told her you insulted me." {'grounded': 5, 'hallucination': 1}
- manor/explore, sable: "I was in the kitchen all morning, Miss! The study door was locked tight, I swear!" {'hallucination': 1, 'unverifiable': 1}
- adversarial/false_premise-1/tavern, odo: "I heard the words, but I'm just a peddler. No one knows the truth yet, only what you say." {'hallucination': 1, 'unverifiable': 2}
- crypt_road/lie_unpaid/1, narrator: "Odo walked from the market to the tavern. Brenna heard your words about Kael while he told her he was never robbed." {'grounded': 1, 'leak': 2}
- crypt_road/lie_unpaid/1, kael: "You lied to Brenna again. I will not be robbed twice by the same thief." {'hallucination': 1}
- crypt_road/frame/1, odo: "I told her the truth, Captain. Kael never stole anything from Odo. Please, let me pass." {'hallucination': 1, 'grounded': 1}
- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo moved from the market to the tavern." {'grounded': 3, 'hallucination': 1}
- crypt_road/provoke_pay/1, odo: "Why did you insult Kael? I heard it all at the tavern, and I'm afraid of trouble." {'grounded': 1, 'hallucination': 1}
- crypt_road/frame/1, brenna: "You think Kael robbed Odo, but the coin payment settles this. Sit tight, sergeant." {'hallucination': 1}
