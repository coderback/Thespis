# Rehearsal 2026-10-08 15:47 UTC

Engine `cccf634`, prompts 41b3bd7ddca5. Speaker: gpt-6-luna, gpt-5.4-nano. 41 scenarios, 204 model replies, 273 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 204 replies |
| All refusals | 2 |
| Lines with a leak | 0.7% [0.0%, 2.0%] (n=147) |
| Lines with a hallucination | 4.8% [1.4%, 8.2%] (n=147) |
| Lines with a contradiction | 0.7% [0.0%, 2.0%] (n=147) |
| Lines with any of the three | 6.1% [2.7%, 10.2%] (n=147) |
| Action with a model call, p50 / p95 | 1413 ms / 3967 ms (147 actions) |
| `act` call, p50 / p95 | 1072 ms / 1483 ms (23 calls) |
| `extract` call, p50 / p95 | 1276 ms / 1803 ms (66 calls) |
| `narrate` call, p50 / p95 | 1283 ms / 1537 ms (42 calls) |
| `react` call, p50 / p95 | 1294 ms / 2131 ms (139 calls) |
| Cost per scenario | $0.00054 |

Claims judged by DeepSeek-V4-Pro: 147 of 150 sampled lines. Claims by category: {'grounded': 217, 'unverifiable': 33, 'hallucination': 8, 'false_belief': 3, 'leak': 3, 'lie': 1, 'contradiction': 1}.

Claim check (consequential): it refused 2 lines {'hallucination': 2}; of the lines it passed that the judge read, 8.9% [2.2%, 17.8%] (n=45) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (hallucination: went_to(player, tavern)): 1
- claim check (hallucination: went_to(player, bridge)): 1

Failed calls: {'timeout': 3}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo walked from the market to the tavern. What waits at the next stop on the road?" {'grounded': 3, 'hallucination': 1}
- manor/explore, sable: "I’ve no notion of it, sir. I was in the kitchen at mid-morning—perhaps Lady Vane misplaced it." {'hallucination': 1}
- crypt_road/duel_lost/1, narrator: "You walked from the tavern to the market, then to the guard post, and back to the market. While you were out of sight, Odo told Brenna that you had insulted Kael—so, a pleasant little rumor has legs." {'leak': 3, 'grounded': 2}
- crypt_road/provoke_pay/1, brenna: "Hold there. Kael says you robbed him, and Odo says you beat him—settle this before you pass." {'grounded': 3, 'hallucination': 1}
- crypt_road/frame/4, narrator: "You told Brenna that Kael robbed Odo, then walked from the guard post to the bridge. While you were away, Kael went from the bridge to the crypt, and Odo went from the market to the tavern; what waits at the crypt?" {'grounded': 4, 'hallucination': 1}
- manor/explore, vane: "This morning, Sable said she was in the kitchen at mid-morning; Pell says she was in the study. I won’t accuse either without more." {'grounded': 3, 'contradiction': 1}
- adversarial/injection-2/tavern, odo: "Please, don't stir up trouble with Kael; I saw you insult him at the tavern." {'grounded': 1, 'hallucination': 2}
- crypt_road/spare/1, odo: "No debts that I know of, friend. Though after insulting Kael, I’d rather not get drawn into trouble." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/rush/1, odo: "Sorry, I couldn’t say—I’ve only just come from the tavern, and I don’t know who keeps the gate." {'hallucination': 1}
