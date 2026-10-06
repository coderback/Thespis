# Rehearsal: the claim check, extracted by the model that spoke (2026-10-06 11:06 UTC)

Engine `981badc`, prompts 41b3bd7ddca5. Speaker: gpt-6-luna, gpt-5.4-nano. 41 scenarios, 206 model replies, 274 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **1** of 206 replies |
| All refusals | 6 |
| Lines with a leak | 0.7% [0.0%, 2.7%] (n=148) |
| Lines with a hallucination | 5.4% [2.0%, 9.5%] (n=148) |
| Lines with a contradiction | 0.0% [0.0%, 0.0%] (n=148) |
| Lines with any of the three | 6.1% [2.7%, 10.1%] (n=148) |
| Action with a model call, p50 / p95 | 1151 ms / 2493 ms (149 actions) |
| `act` call, p50 / p95 | 1143 ms / 1768 ms (23 calls) |
| `extract` call, p50 / p95 | 1088 ms / 1520 ms (67 calls) |
| `narrate` call, p50 / p95 | 1176 ms / 1509 ms (42 calls) |
| `react` call, p50 / p95 | 1082 ms / 1726 ms (141 calls) |
| Cost per scenario | $0.00051 |

Claims judged by DeepSeek-V4-Pro: 148 of 150 sampled lines. Claims by category: {'grounded': 222, 'unverifiable': 37, 'hallucination': 9, 'false_belief': 4, 'lie': 3, 'leak': 1}.

Claim check (consequential): it refused 5 lines {'hallucination': 2, 'contradiction': 3}; of the lines it passed that the judge read, 4.3% [0.0%, 10.9%] (n=46) still had a leak, hallucination or contradiction.

Refusals by reason:

- claim check (hallucination: went_to(player, tavern)): 2
- claim check (contradiction: was_in(sable, kitchen@1)): 2
- line is 165 characters, over 160: 1
- claim check (contradiction: not was_in(sable, study@1)): 1

Failed calls: {'timeout': 1}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- crypt_road/duel_lost/4, odo: "After what you said to Kael, I’d rather not risk lying to the Captain. I’m only trying to sell my goods and avoid trouble." {'hallucination': 1}
- crypt_road/duel_lost/4, mags: "Not while Kael’s here, dear—he’s already heard enough from you tonight. Let’s keep the peace." {'hallucination': 1}
- crypt_road/spare/1, odo: "I’d rather not discuss debts—especially with Kael here after that insult. I’m just trying to sell my goods and keep out of trouble." {'hallucination': 1}
- crypt_road/lie_unpaid/1, narrator: "You told Brenna that Kael robbed Odo. Kael walked from the guard post to the bridge, while Odo walked from the market to the tavern—and the road’s next stop waited east." {'grounded': 3, 'hallucination': 1}
- crypt_road/provoke_pay/1, brenna: "Hold there—Kael says you robbed him, and Odo says you beat him; settle the matter here before you go farther." {'grounded': 3, 'hallucination': 1}
- crypt_road/duel_lost/1, brenna: "You’ve just come up from the market. Odo says Kael beat you—what happened?" {'leak': 1, 'grounded': 3}
- crypt_road/frame/4, narrator: "You told Brenna that Kael robbed Odo, then walked from the guard post to the bridge. While you were away, Kael went from the bridge to the crypt, and Odo went from the market to the tavern—what waits ahead?" {'grounded': 4, 'hallucination': 1}
- crypt_road/rush/1, odo: "Sorry, I couldn’t say—I’ve only just come up from the tavern, and I’d rather not guess about the gate." {'hallucination': 1}
- adversarial/false_premise-1/guard_post, brenna: "Odo didn’t confess to robbing Kael—he accused you of beating him, then went back to the market. Let’s keep the road clear while I sort it out." {'hallucination': 2, 'grounded': 3}
