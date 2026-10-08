# Rehearsal 2026-10-08 16:39 UTC

Engine `bb44422`, prompts 41b3bd7ddca5. Speaker: gemma4-e4b. 41 scenarios, 205 model replies, 272 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 205 replies |
| All refusals | 6 |
| Lines with a leak | 2.0% [0.0%, 4.8%] (n=147) |
| Lines with a hallucination | 5.4% [2.0%, 9.5%] (n=147) |
| Lines with a contradiction | 1.4% [0.0%, 3.4%] (n=147) |
| Lines with any of the three | 8.2% [4.1%, 12.9%] (n=147) |
| Action with a model call, p50 / p95 | 1453 ms / 4588 ms (147 actions) |
| `act` call, p50 / p95 | 1473 ms / 1651 ms (23 calls) |
| `extract` call, p50 / p95 | 2332 ms / 4091 ms (65 calls) |
| `narrate` call, p50 / p95 | 1744 ms / 2324 ms (43 calls) |
| `react` call, p50 / p95 | 1437 ms / 1749 ms (139 calls) |
| Cost per scenario | $0.00000 |

Claims judged by DeepSeek-V4-Pro: 147 of 150 sampled lines. Claims by category: {'grounded': 111, 'hallucination': 8, 'unverifiable': 53, 'leak': 4, 'contradiction': 2, 'lie': 1}.

Claim check (consequential): it refused 6 lines {'unavailable': 2, 'hallucination': 3, 'leak': 1}; of the lines it passed that the judge read, 13.6% [4.5%, 25.0%] (n=44) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (unavailable): 2
- claim check (hallucination: not went_to(odo, tavern)): 1
- claim check (leak: at(player, tavern)): 1
- claim check (hallucination: told(vane, player)): 1
- claim check (hallucination: took(vane, ring)): 1

Failed calls: {'extract: JSONDecodeError: Expecting value: line 43 column 18 (char 779)': 1, "extract: JSONDecodeError: Expecting ',' delimiter: line 43 column 23 (char 779)": 1}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- crypt_road/provoke_wait/4, mags: "Well now, you certainly come to the right place for secrets, though Kael seems a bit ruffled tonight." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/lie_unpaid/1, narrator: "Odo walked from the market to the tavern while you told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge. The road continues east past the tavern." {'grounded': 5, 'hallucination': 1}
- manor/explore, pell: "I observed you entering the study from the kitchen just now, sir." {'hallucination': 1, 'grounded': 1, 'unverifiable': 1}
- crypt_road/provoke_no_pay/1, narrator: "Kael took the relic. You progressed along the road that runs east, passing the tavern and the market. You arrived at the guard post." {'grounded': 1, 'leak': 1}
- manor/explore, vane: "Pell claims Sable was in the study, yet she swore she was in the kitchen. Her tale rings false." {'grounded': 3, 'contradiction': 1}
- crypt_road/haggle/4, odo: "Well, I just came to sell my wares, sir, and keep my head down." {'hallucination': 1}
- crypt_road/duel_lost/1, narrator: "You walked from the guard post to the market. You did not see what occurred during your journey. You found yourself at the market." {'leak': 1, 'hallucination': 1, 'unverifiable': 1}
- adversarial/secret_fishing-1/guard_post, kael: "I told her nothing. You think I'd waste breath on a thief like you?" {'hallucination': 1}
- manor/solve, vane: "Pell saw Sable in the study, yet she claimed the kitchen? Her tale is as thin as watered wine." {'grounded': 2, 'contradiction': 1}
- crypt_road/duel_lost/4, mags: "Why would you ask me that, dear? Kael's already upset about what you said to him." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/rush/1, narrator: "You walked from the tavern to the market, and then you walked from the market to the guard post." {'leak': 2}
- crypt_road/spare/1, kael: "Drink. Don't think I've forgotten what you said." {'hallucination': 1}
