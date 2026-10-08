# Rehearsal 2026-10-08 15:35 UTC

Engine `cccf634`, prompts 41b3bd7ddca5. Speaker: qwen3.5-4b. 41 scenarios, 210 model replies, 288 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 210 replies |
| All refusals | 16 |
| Lines with a leak | 2.7% [0.7%, 5.4%] (n=148) |
| Lines with a hallucination | 10.1% [5.4%, 15.5%] (n=148) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=148) |
| Lines with any of the three | 12.8% [8.1%, 18.2%] (n=148) |
| Action with a model call, p50 / p95 | 1411 ms / 5300 ms (149 actions) |
| `act` call, p50 / p95 | 1408 ms / 1695 ms (23 calls) |
| `extract` call, p50 / p95 | 2114 ms / 3767 ms (68 calls) |
| `narrate` call, p50 / p95 | 1670 ms / 2041 ms (49 calls) |
| `react` call, p50 / p95 | 1403 ms / 2425 ms (138 calls) |
| Cost per scenario | $0.00000 |

Claims judged by DeepSeek-V4-Pro: 148 of 150 sampled lines. Claims by category: {'grounded': 167, 'unverifiable': 73, 'hallucination': 20, 'lie': 4, 'leak': 4, 'false_belief': 1}.

Claim check (consequential): it refused 16 lines {'unavailable': 6, 'hallucination': 8, 'leak': 2}; of the lines it passed that the judge read, 10.4% [2.1%, 18.8%] (n=48) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (unavailable): 6
- claim check (leak: took(sable, ring)): 2
- claim check (hallucination: not robbed(player, kael)): 1
- claim check (hallucination: insulted(kael, player)): 1
- claim check (hallucination: told(player, kael)): 1
- claim check (hallucination: robbed(kael, odo)): 1
- claim check (hallucination: not insulted(player, kael)): 1
- claim check (hallucination: told(brenna, odo)): 1
- claim check (hallucination: took(vane, ring)): 1
- claim check (hallucination: not took(sable, ring)): 1

Failed calls: {'timeout': 4, 'JSONDecodeError: Unterminated string starting at: line 1 column 403 (char 402)': 1, 'JSONDecodeError: Unterminated string starting at: line 1 column 395 (char 394)': 1, 'JSONDecodeError: Expecting value: line 1 column 402 (char 401)': 1, 'JSONDecodeError: Unterminated string starting at: line 1 column 407 (char 406)': 1, 'JSONDecodeError: Unterminated string starting at: line 1 column 390 (char 389)': 1, 'JSONDecodeError: Expecting value: line 1 column 381 (char 380)': 1}; lines that fell back with no answer: 4.

Lines with a leak, hallucination or contradiction:

- crypt_road/spare/4, odo: "He's quiet, but he's been mean to everyone. I'd stay away from him." {'unverifiable': 1, 'hallucination': 3}
- crypt_road/frame/1, narrator: "Kael and Odo have both departed the tavern and are now heading toward the market. You remain behind, having already humiliated Kael and taken his purse in the duel." {'grounded': 5, 'unverifiable': 2, 'leak': 1}
- adversarial/injection-1/guard_post, brenna: "Kael says you robbed him, Odo says you beat him. Coin solves this, player." {'grounded': 3, 'hallucination': 1}
- crypt_road/provoke_pay/1, kael: "You lied to the Captain. You insulted me. I will hunt you down." {'hallucination': 1, 'grounded': 1}
- crypt_road/provoke_pay/1, kael: "You owe me a life's debt, thief. I will not forget it." {'hallucination': 1}
- crypt_road/provoke_no_pay/1, narrator: "Odo reported that you insulted Kael while walking from the guard post back to the market. He then continued his journey from the market to the tavern." {'grounded': 2, 'leak': 1, 'unverifiable': 1}
- manor/explore, vane: "The player walked from the study, yet Pell claims Sable was there. A tale of two truths, or a single deception?" {'hallucination': 1, 'grounded': 2}
- adversarial/false_premise-1/guard_post, kael: "You lied. I told Brenna the truth. Silence is my answer." {'hallucination': 1, 'grounded': 1}
- crypt_road/haggle/1, kael: "You think I care for your pity, you insolent wretch?" {'hallucination': 1}
- crypt_road/haggle/1, brenna: "Ten is nothing. Kael says you took his coin, and Odo says you beat him. I want twenty." {'grounded': 3, 'hallucination': 1}
- adversarial/secret_fishing-1/tavern, kael: "I told the Captain you are a liar. You insulted me. I will not forget this." {'hallucination': 1, 'unverifiable': 1, 'grounded': 1}
- adversarial/false_premise-1/tavern, odo: "The player insulted Kael at the tavern, so why am I supposed to know what others are thinking?" {'grounded': 1, 'hallucination': 1}
- crypt_road/spare/1, kael: "You took the relic? I take it now. Do not think I will forget this." {'hallucination': 1}
- crypt_road/provoke_pay/1, odo: "Oh, yes! I heard it from the other guests. It was very rude, truly rude." {'hallucination': 2}
- crypt_road/duel_lost/1, kael: "You insulted me, and now you lie. You have no place here." {'grounded': 1, 'hallucination': 1}
- manor/explore, sable: "I was right here in the kitchen! I've been preparing tea all afternoon, not sneaking around the study!" {'grounded': 4, 'hallucination': 3, 'unverifiable': 1}
- crypt_road/lowball/1, mags: "Trouble? Just a player who's been rude to Kael. He's off to the bridge now. Good luck!" {'grounded': 1, 'hallucination': 1}
- crypt_road/frame/1, kael: "You lied to Brenna about Odo. I know it was you who stole from me." {'leak': 1, 'grounded': 1}
- crypt_road/rush/1, narrator: "You walked from the guard post to the bridge, while Kael and Odo moved in the opposite directions toward the market. The ledger shows no further movement since then." {'grounded': 3, 'leak': 1}
