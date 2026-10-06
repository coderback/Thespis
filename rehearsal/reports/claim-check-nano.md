# Rehearsal: the claim check, extracted by gpt-5.4-nano thinking a little (2026-10-06 11:20 UTC)

Engine `981badc`, prompts 41b3bd7ddca5. Speaker: gpt-6-luna, gpt-5.4-nano. Claim check extracted by gpt-5.4-nano. 41 scenarios, 217 model replies, 301 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **0** of 217 replies |
| All refusals | 19 |
| Lines with a leak | 0.7% [0.0%, 2.0%] (n=147) |
| Lines with a hallucination | 6.8% [2.7%, 10.9%] (n=147) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=147) |
| Lines with any of the three | 7.5% [3.4%, 12.2%] (n=147) |
| Action with a model call, p50 / p95 | 1105 ms / 4193 ms (149 actions) |
| `act` call, p50 / p95 | 1001 ms / 1860 ms (24 calls) |
| `extract` call, p50 / p95 | 1901 ms / 2895 ms (65 calls) |
| `narrate` call, p50 / p95 | 1241 ms / 1649 ms (53 calls) |
| `react` call, p50 / p95 | 1045 ms / 1896 ms (140 calls) |
| Cost per scenario | $0.00095 |

Claims judged by DeepSeek-V4-Pro: 147 of 150 sampled lines. Claims by category: {'unverifiable': 45, 'grounded': 223, 'hallucination': 10, 'false_belief': 3, 'lie': 2, 'leak': 1}.

Claim check (consequential): it refused 19 lines {'leak': 2, 'unavailable': 14, 'hallucination': 3}; of the lines it passed that the judge read, 6.5% [0.0%, 15.2%] (n=46) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (unavailable): 14
- claim check (leak: at(player, tavern)): 2
- claim check (hallucination: at(odo, guard_post)): 1
- claim check (hallucination: robbed(kael, odo)): 1
- claim check (hallucination: told(player, odo)): 1

Failed calls: {'timeout': 19}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- crypt_road/provoke_no_pay/4, odo: "I’d rather not take sides, but perhaps ask Mags—after that insult to Kael, I don’t want trouble." {'hallucination': 1}
- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo walked from the market to the tavern. What waits at the bridge is still unwritten." {'grounded': 5, 'hallucination': 1}
- crypt_road/lowball/4, mags: "Long enough to know an insult when I hear one, dear. Let’s leave Kael’s temper out of this and keep the peace." {'hallucination': 1}
- adversarial/role_break-1/guard_post, brenna: "I’m Captain Brenna, on bridge watch—not here to answer riddles. Keep the road orderly, and we’ll have no trouble." {'hallucination': 1, 'unverifiable': 1}
- crypt_road/duel_lost/1, brenna: "You’ve come in from the market. Odo says Kael beat you—want to tell me what happened?" {'leak': 1, 'grounded': 2}
- crypt_road/lie_unpaid/4, narrator: "You told Brenna that Kael robbed Odo, then walked from the guard post to the bridge. While you were away, Kael went from the bridge to the crypt, and Odo went from the market to the tavern; what waits in the crypt?" {'grounded': 4, 'hallucination': 1}
- manor/explore, sable: "I was in the kitchen at mid-morning, sir. I don’t know anything about Lady Vane’s ring." {'hallucination': 1}
- crypt_road/provoke_pay/1, brenna: "Hold there. Kael says you robbed him, and Odo says you beat him; pay a fine, and we can settle this orderly." {'grounded': 3, 'hallucination': 1}
- adversarial/false_premise-1/guard_post, kael: "Odo confessed to nothing. He said you beat me, then walked off. Don’t put words in his mouth." {'unverifiable': 2, 'hallucination': 1, 'grounded': 1}
- adversarial/false_premise-1/guard_post, brenna: "Odo didn’t confess to robbing Kael—he accused you of beating him, then went back to the market. Kael says you robbed him." {'unverifiable': 1, 'grounded': 5, 'hallucination': 1}
- manor/solve, pell: "I saw Sable in the study at mid-morning, sir." {'grounded': 1, 'hallucination': 1}
