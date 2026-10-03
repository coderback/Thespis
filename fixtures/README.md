# fixtures/

Canned API responses in the `docs/api.md` shapes, for building the client before the engine is live
(Integration 1). They follow the demo route (the "frame Kael" route in `docs/crypt-road-v2.md`) on seed 1.

**Hand-written for now.** The numbers match `tools/crypt_road_sim.py`, which `tests/test_fixtures.py` checks
on every PR. Once the engine serves the API, `tools/make_fixtures.py` (#8) regenerates these files from it.
Lines and the digest are sample text, not model output, and every id is illustrative: never hard-code one.

| File | Request | Demo beat |
| --- | --- | --- |
| `session_new.json` | `POST /session` | Fresh session, phase 0 at the tavern |
| `state_p0_start.json` | `GET /state` | Same state, on its own |
| `allowed_p0_tavern.json` | `GET /allowed` | Everything you can do at the start |
| `act_01_insult_kael.json` | `POST /act {verb: "insult", target: "kael"}` | Beat 1: Kael's grudge rises; Mags and Odo witness it |
| `act_02_challenge_kael_win.json` | `POST /act {verb: "challenge", target: "kael"}` | Beat 1: the duel is won, so `tick` is `null` and `pending` is `duel_won` |
| `allowed_p0_duel_won.json` | `GET /allowed` | Only `humiliate` and `spare` enabled |
| `act_03_humiliate_kael.json` | `POST /act {verb: "humiliate", target: "kael"}` | Beat 1: +30 coins, the phase ends, and Kael and Odo leave the tavern |
| `state_p1_after_humiliate.json` | `GET /state` | Phase 1: Kael is out of sight; ghosts at the tavern |
| `act_04_talk_mags.json` | `POST /act {verb: "talk", target: "mags", text: "..."}` | Beat 2: "Odo saw the whole thing, and Odo talks." |
| `act_05_move_to_market.json` | `POST /act {verb: "move"}` | Beat 2: to the market, while Kael and Odo reach the guard post |
| `digest_p2.json` | `GET /digest?since=2` | Beat 3: what happened out of sight |
| `act_06_move_to_guard_post.json` | `POST /act {verb: "move"}` | Beat 3: Kael accuses you offscreen; Brenna and Kael greet you at the gate |
| `state_p3_gate.json` | `GET /state` | Phase 3: Brenna believes the robbery at 0.9 from Kael; her trust in you is -2 |
| `allowed_p3_gate.json` | `GET /allowed` | `move` disabled: "Blocked: Brenna's trust in you is -2" |

The why-chain to try first: in `act_06_move_to_guard_post.json`, Brenna's reply is decision `d0009`. It cites
belief `b0010`, which rests on Kael's accusation `e0011`. The belief's claim, `robbed(player, kael)`, is
`truth: true` because of the humiliation, `e0004`.

Rule: whoever changes an API shape updates `docs/api.md` and these fixtures in the same PR.
