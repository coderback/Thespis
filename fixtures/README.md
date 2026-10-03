# fixtures/

Real API responses in the `docs/api.md` shapes. They follow the demo route (the "frame Kael" route in
`docs/crypt-road-v2.md`) on seed 1, from a fresh session to the win and the epilogue.

**Generated, not written by hand.** `python tools/make_fixtures.py` plays the route through the engine's HTTP API and
rewrites this folder. `tests/test_fixtures.py` fails if these files differ from what the engine produces, and checks
their numbers against `tools/crypt_road_sim.py`. Every id is real but may change between engine versions, so never
hard-code one. Until #10 lands, NPC lines are absent (`replies` is empty and decisions have `line: null`), and the
digest is built from the ledger in code.

| File | Request | Demo beat |
| --- | --- | --- |
| `session_new.json` | `POST /session` | Fresh session, phase 0 at the tavern. The session id is replaced with `demo-0001` |
| `state_p0_start.json` | `GET /state` | The same state, on its own |
| `allowed_p0_tavern.json` | `GET /allowed` | Everything you can do at the start |
| `act_01_insult_kael.json` | `POST /act {verb: "insult", target: "kael"}` | Beat 1: Kael's grudge rises; Mags and Odo witness it |
| `act_02_challenge_kael_win.json` | `POST /act {verb: "challenge", target: "kael"}` | Beat 1: the duel is won, so `tick` is `null` and `pending` is `duel_won` |
| `allowed_p0_duel_won.json` | `GET /allowed` | Only `humiliate` and `spare` enabled |
| `act_03_humiliate_kael.json` | `POST /act {verb: "humiliate", target: "kael"}` | Beat 1: +30 coins, the phase ends, and Kael and Odo leave the tavern |
| `state_p1_after_humiliate.json` | `GET /state` | Phase 1: Kael is out of sight, with `last_seen` ghosts at the tavern |
| `act_04_talk_mags.json` | `POST /act {verb: "talk", target: "mags", text: "..."}` | Beat 2 (her line arrives with #10) |
| `act_05_move_to_market.json` | `POST /act {verb: "move"}` | Beat 2: to the market, while Kael and Odo reach the guard post |
| `act_06_move_to_guard_post.json` | `POST /act {verb: "move"}` | Beat 3: Kael accuses you offscreen, and Odo gossips to Brenna |
| `digest_p2.json` | `GET /digest?since=2` | Beat 3: what happened out of sight |
| `state_p3_gate.json` | `GET /state` | Phase 3: Brenna believes the robbery at 0.9 from Kael; her trust in you is -2 |
| `allowed_p3_gate.json` | `GET /allowed` | `move` disabled: "Blocked: Brenna's trust in you is -2" |
| `act_07_bribe_brenna.json`, `act_08_bribe_brenna.json` | `POST /act {verb: "bribe", target: "brenna", amount: 20}` | Beat 6: trust back to 2 |
| `act_09_tell_brenna_lie.json` | `POST /act {verb: "tell_claim", target: "brenna", claim: robbed(kael, odo)}` | Beat 6: the lie lands at 0.9 (`truth: false`); Kael overhears it |
| `act_10_move_to_bridge.json` | `POST /act {verb: "move"}` | Beat 6: Brenna detains Kael; you reach the bridge |
| `act_11_move_to_crypt.json` | `POST /act {verb: "move"}` | Beat 7 |
| `act_12_take_relic.json` | `POST /act {verb: "take_relic"}` | Beat 7: you win; `epilogue` holds two more ticks, where Odo exposes the lie |
| `state_p7_end.json` | `GET /state` | After the epilogue: the lie is retracted, and Brenna's trust in you is -1 |
| `allowed_p7_end.json` | `GET /allowed` | Everything disabled: "The race is over" |
| `digest_epilogue.json` | `GET /digest?since=5` | The epilogue text, for the win card |

Rule: whoever changes an API shape updates `docs/api.md` and regenerates these fixtures in the same PR.
