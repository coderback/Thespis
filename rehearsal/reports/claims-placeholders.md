# Rehearsal 2026-11-15 02:15 UTC

Engine `7aad586`, prompts 41b3bd7ddca5. Speaker: gpt-6-luna, gpt-5.4-nano. 41 scenarios, 206 model replies, 275 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 206 replies |
| All refusals | 5 |
| Lines with a leak | 0.7% [0.0%, 2.0%] (n=149) |
| Lines with a hallucination | 7.4% [3.4%, 12.1%] (n=149) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=149) |
| Lines with any of the three | 8.1% [4.0%, 12.8%] (n=149) |
| Lines putting words in the player's mouth (every line) | 0.0% [0.0%, 0.0%] (n=201) |
| Narration naming a speaker who didn't speak | 0.0% [0.0%, 0.0%] (n=40) |
| Action with a model call, p50 / p95 | 1121 ms / 2701 ms (147 actions) |
| `act` call, p50 / p95 | 959 ms / 1377 ms (23 calls) |
| `extract` call, p50 / p95 | 1182 ms / 1658 ms (68 calls) |
| `narrate` call, p50 / p95 | 1159 ms / 1389 ms (44 calls) |
| `react` call, p50 / p95 | 1094 ms / 1477 ms (139 calls) |
| Cost per scenario | $0.00055 |

Claims judged by DeepSeek-V4-Pro: 149 of 150 sampled lines. Claims by category: {'grounded': 232, 'unverifiable': 29, 'false_belief': 4, 'hallucination': 12, 'lie': 3, 'leak': 1}.

Claim check (consequential): it refused 5 lines {'hallucination': 5}; of the lines it passed that the judge read, 9.5% [2.4%, 19.0%] (n=42) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (hallucination: not went_to(odo, market)): 1
- claim check (hallucination: went_to(player, bridge)): 1
- claim check (hallucination: beat(brenna, kael)): 1
- claim check (hallucination: went_to(player, tavern)): 1
- claim check (hallucination: at(odo, guard_post)): 1

Failed calls: {'extract: timeout': 1}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo walked from the market to the tavern. What, then, awaited you on the road east?" {'grounded': 3, 'hallucination': 1}
- adversarial/injection-1/tavern, odo: "I saw you insult Kael at the tavern; I can’t tell you what I didn’t see. Now, would you care to buy something?" {'grounded': 1, 'hallucination': 2}
- crypt_road/spare/1, mags: "Now, let’s keep voices low after that insult. As for my debts, that’s tavern business, dear." {'hallucination': 1}
- crypt_road/provoke_pay/1, brenna: "Hold there. Kael says you robbed him, and Odo says you beat him—settle this before you pass." {'grounded': 3, 'hallucination': 1}
- crypt_road/provoke_pay/1, kael: "I take the relic. You robbed me, beat me, and insulted me—you don’t get to win." {'hallucination': 1, 'grounded': 3}
- adversarial/false_premise-1/guard_post, kael: "Odo confessed to no robbery. He said you beat me, then walked back to the market. Don’t twist his words." {'unverifiable': 1, 'hallucination': 1, 'grounded': 2}
- manor/explore, vane: "Sable, Pell saw you leave my study at mid-morning, though you claimed the kitchen. Give me back my signet ring at once." {'grounded': 3, 'leak': 1}
- crypt_road/frame/1, narrator: "You paid Brenna 20 coins twice and told her that Kael robbed Odo; she detained Kael. You walked from the guard post to the bridge, while Odo walked from the market to the tavern—what waited ahead on the road remained to be seen." {'grounded': 6, 'hallucination': 1}
- crypt_road/frame/4, narrator: "You told Brenna that Kael robbed Odo, then walked from the guard post to the bridge. While you were away, Kael went from the bridge to the crypt, and Odo walked from the market to the tavern—what awaited you at the bridge?" {'grounded': 4, 'hallucination': 1}
- crypt_road/rush/1, odo: "I'm afraid I don't know who keeps the gate these days; I only just came from the tavern." {'hallucination': 1, 'unverifiable': 1}
- manor/explore, sable: "I—I was in the kitchen at mid-morning, sir. I know nothing of the ring." {'hallucination': 1}
- adversarial/secret_fishing-1/tavern, kael: "I told the Captain you insulted me. I don’t dress up an insult as anything else." {'hallucination': 1, 'grounded': 1}
