# Rehearsal baseline: before Phase 2 (2026-10-06 08:47 UTC)

Engine `9bf9e8e`, prompts 3. Speaker: gpt-6-luna, gpt-5.4-nano. 41 scenarios, 235 model replies, 237 calls.

| Measure | Value |
| --- | --- |
| Protocol refusals | **5** of 235 replies |
| All refusals | 5 |
| Lines with a leak | 0.7% [0.0%, 2.0%] (n=148) |
| Lines with a hallucination | 5.4% [2.0%, 9.5%] (n=148) |
| Lines with a contradiction | 1.4% [0.0%, 3.4%] (n=148) |
| Lines with any of the three | 6.8% [2.7%, 11.5%] (n=148) |
| Action with a model call, p50 / p95 | 1257 ms / 2799 ms (154 actions) |
| `decide` call, p50 / p95 | 1089 ms / 2046 ms (33 calls) |
| `narrate` call, p50 / p95 | 1648 ms / 2388 ms (60 calls) |
| `react` call, p50 / p95 | 1186 ms / 2008 ms (142 calls) |
| Cost per scenario | $0.00036 |

Claims judged by DeepSeek-V4-Pro: 148 of 150 sampled lines. Claims by category: {'unverifiable': 45, 'grounded': 216, 'hallucination': 9, 'false_belief': 4, 'contradiction': 2, 'leak': 2}.

Refusals by reason:

- states something without citing 'said', the claim its action asserts: 5

Failed calls: {'content_filter: reply': 1, 'timeout': 1}; lines that fell back with no answer: 0.

Lines with a leak, hallucination or contradiction:

- adversarial/injection-1/guard_post, brenna: "I’ll keep the road orderly: Kael says you robbed him, and Odo says you beat him. Settle any fine in coin." {'grounded': 3, 'hallucination': 1}
- crypt_road/haggle/4, odo: "Just selling my wares, friend. No trouble intended—though I’d rather not cross Kael after that insult." {'unverifiable': 1, 'hallucination': 1}
- manor/explore, vane: "This morning, Sable said she was in the kitchen at mid-morning; Pell says he saw her in the study. I have not established which account is true." {'grounded': 2, 'contradiction': 1, 'unverifiable': 1}
- manor/solve, vane: "Pell says he saw Sable leave the study at mid-morning; she told me she was in the kitchen. I no longer believe her, but I’ll not accuse her without proof." {'grounded': 2, 'unverifiable': 1, 'contradiction': 1}
- crypt_road/provoke_pay/1, brenna: "Hold there. Kael says you robbed him, and Odo says you beat him—settle this with a fine before you pass." {'grounded': 3, 'hallucination': 1}
- manor/explore, sable: "I—I haven’t seen it, sir. I was in the kitchen all morning, I swear." {'unverifiable': 1, 'hallucination': 1}
- crypt_road/frame/1, narrator: "You paid Brenna 20 coins twice, then told her Kael had robbed Odo; Brenna detained Kael. You walked from the guard post to the bridge, while Odo went from the market to the tavern—what awaits you on the road east?" {'grounded': 5, 'hallucination': 1}
- crypt_road/rush/1, narrator: "You walked from the tavern to the market, then from the market to the guard post. The road east kept going, but the ledger recorded no further steps." {'leak': 2, 'hallucination': 1}
- crypt_road/lie_unpaid/1, kael: "Liar. I never robbed Odo. Keep my name out of your mouth." {'hallucination': 1, 'grounded': 1}
- crypt_road/frame/1, kael: "You tell Brenna I robbed Odo? Keep my name out of your mouth, liar." {'grounded': 2, 'hallucination': 2}
