"""
The Crypt Road v2 - rules model and acceptance test.

A dependency-free model of the v2 rules, using the fallback (utility) brain only.
Use it three ways:
  1. python crypt_road_sim.py            -> route outcomes table + demo-route acceptance test
  2. import it in the harness and diff the real engine's state against it after each step
  3. generate client fixtures: run the demo route and dump snapshot() after each beat

Rules follow the v2 design doc: evidence-based beliefs (confidence = max of evidence),
trust-scaled claims, crime -> trust -2, gossip worst-news-first at x0.8, testimony
retraction, detain once per claim for 2 phases, gate at guard_post -> bridge,
tick order: player action, decisions (Brenna then Kael), gossip, moves, fear decay.
"""
import hashlib
import json
import sys

STOPS = ["tavern", "market", "guard_post", "bridge", "crypt"]
PHASES = ["morning", "noon", "evening", "night"]
ODO_WALK = [0, 1, 2, 1]                     # Odo's stop by phase % 4
GOSSIP_PRIORITY = {"robbed": 3, "beat": 2, "insulted": 1}
NPCS = ["kael", "brenna", "mags", "odo"]
DEMO_SEED = 1   # first duel (event e0002) wins on this seed; re-check once the real engine's event ids exist


def dice(seed, event_id):
    """Deterministic uniform [0, 1) from (seed, event_id)."""
    h = hashlib.sha256(f"{seed}:{event_id}".encode()).hexdigest()
    return int(h[:8], 16) / 0x100000000


def conf_from_trust(trust):
    if trust >= 2:
        return 0.9
    if trust >= 0:
        return 0.4
    return 0.2


class World:
    def __init__(self, seed=DEMO_SEED):
        self.seed = seed
        self.phase = 0
        self.status = "playing"
        self.player = {"loc": 0, "coins": 10}
        self.kael = {"loc": 0, "grudge": 0, "fear": 1, "respect": 1, "ambition": 6,
                     "frozen_until": -1, "accused": False, "drink": False}
        self.brenna = {"loc": 2, "trust": {"player": 0, "kael": 2, "odo": 2, "mags": 1},
                       "crimes": set(), "detained_for": set()}
        self.locs = {"mags": 0, "odo": 0}
        self.ledger = []                    # (id, phase, verb, actor, target, claim, truth)
        self.beliefs = {n: {} for n in NPCS}  # npc -> claim -> {"evidence": [...], "status": ...}
        self.decisions = []
        self.log = []
        self.pending_duel = False

    # ---------- helpers ----------
    def loc_of(self, n):
        if n == "kael":
            return self.kael["loc"]
        if n == "brenna":
            return self.brenna["loc"]
        return self.locs[n]

    def at(self, loc):
        return [n for n in NPCS if self.loc_of(n) == loc]

    def event(self, verb, actor, target, claim=None, truth=True):
        eid = f"e{len(self.ledger) + 1:04d}"
        self.ledger.append({"id": eid, "phase": self.phase, "verb": verb, "actor": actor,
                            "target": target, "claim": claim, "truth": truth,
                            "loc": STOPS[self.player["loc"]]})
        return eid

    def conf(self, npc, claim):
        b = self.beliefs[npc].get(claim)
        if not b or b["status"] != "active":
            return 0.0
        return max(e["conf"] for e in b["evidence"])

    def add_evidence(self, npc, claim, conf, source, eid):
        b = self.beliefs[npc].setdefault(claim, {"evidence": [], "status": "active"})
        if b["status"] == "retracted":
            return
        b["evidence"].append({"source": source, "event": eid, "phase": self.phase, "conf": conf})
        if npc == "brenna" and claim[0] == "robbed" and self.conf(npc, claim) >= 0.5 \
                and claim not in self.brenna["crimes"]:
            self.brenna["crimes"].add(claim)
            self.brenna["trust"][claim[1]] -= 2
            self.log.append(f"p{self.phase}: Brenna believes {claim} ({self.conf(npc, claim):.1f} via {source}); "
                            f"trust[{claim[1]}] = {self.brenna['trust'][claim[1]]}")

    def witness(self, claim, actor, target, eid):
        for n in self.at(self.player["loc"]):
            if n not in (actor, target):
                self.add_evidence(n, claim, 1.0, "witnessed", eid)
        for n in (actor, target):
            if n in self.beliefs:
                self.add_evidence(n, claim, 1.0, "self", eid)

    def happened(self, claim):
        return any(e["claim"] == claim and e["truth"] for e in self.ledger)

    # ---------- player free actions ----------
    def insult(self):
        assert self.kael["loc"] == self.player["loc"]
        self.kael["grudge"] += 1
        claim = ("insulted", "player", "kael")
        self.witness(claim, "player", "kael", self.event("insult", "player", "kael", claim))

    def challenge(self):
        """Ends the phase unless won, in which case humiliate/spare must follow."""
        assert self.kael["loc"] == self.player["loc"]
        eid = self.event("challenge", "player", "kael")
        win = dice(self.seed, eid) < 0.6
        if win:
            self.kael["fear"] += 2
            self.kael["grudge"] += 2
            claim = ("beat", "player", "kael")
            self.witness(claim, "player", "kael", self.event("beat", "player", "kael", claim))
            self.pending_duel = True
        else:
            self.kael["grudge"] += 1
            claim = ("beat", "kael", "player")
            self.witness(claim, "kael", "player", self.event("beat", "kael", "player", claim))
            self.tick("wait")
        return win

    def humiliate(self):
        assert self.pending_duel
        self.pending_duel = False
        k = self.kael
        k["grudge"] += 3
        k["respect"] = max(0, k["respect"] - 1)
        self.player["coins"] += 30
        claim = ("robbed", "player", "kael")
        self.witness(claim, "player", "kael", self.event("humiliate", "player", "kael", claim))
        self.snapshot_before_tick = self.snapshot()
        self.tick("wait")

    def spare(self):
        assert self.pending_duel
        self.pending_duel = False
        k = self.kael
        k["grudge"] = max(0, k["grudge"] - 2)
        k["respect"] += 3
        claim = ("spared", "player", "kael")
        self.witness(claim, "player", "kael", self.event("spare", "player", "kael", claim))
        self.tick("wait")

    def bribe(self, amount=20):
        assert self.player["loc"] == 2 and self.player["coins"] >= amount >= 20
        self.player["coins"] -= amount
        self.brenna["trust"]["player"] += 2
        self.event("bribe", "player", "brenna")

    def tell_claim(self, npc, claim):
        assert self.loc_of(npc) == self.player["loc"]
        truth = self.happened(claim)
        eid = self.event("tell_claim", "player", npc, claim, truth)
        trust = self.brenna["trust"]["player"] if npc == "brenna" else 0
        c = conf_from_trust(trust)
        self.add_evidence(npc, claim, c, "player", eid)
        self.log.append(f"p{self.phase}: player tells {npc} {claim} -> {c} ({'true' if truth else 'FALSE'})")
        # an NPC named in a false claim it witnesses knows it was lied about
        for n in self.at(self.player["loc"]):
            if n in claim and n != npc and not truth and n == "kael":
                self.kael["grudge"] += 2
                self.add_evidence("kael", ("lied", "player", "kael"), 1.0, "self", eid)
                self.log.append(f"p{self.phase}: Kael witnessed the lie, grudge {self.kael['grudge']}")

    def take_relic(self):
        if self.player["loc"] == 4 and self.status == "playing":
            self.status = f"won@{self.phase}"
            return True
        return False

    # ---------- tick ----------
    def decide(self, npc, allowed, trigger):
        chosen = max(allowed, key=allowed.get)
        self.decisions.append({"npc": npc, "phase": self.phase, "trigger": trigger,
                               "allowed": sorted(allowed), "chosen": chosen, "source": "fallback"})
        return chosen

    def tick(self, action):
        p, pl, k, b = self.phase, self.player, self.kael, self.brenna
        # 1. player phase action
        if action == "move" and pl["loc"] < 4:
            if pl["loc"] == 2 and b["trust"]["player"] < 0:
                self.log.append(f"p{p}: player BLOCKED at the gate (trust {b['trust']['player']})")
            else:
                pl["loc"] += 1
        # 2a. Brenna decides: detain, question
        if k["loc"] == 2 and k["frozen_until"] < p:
            for claim in list(b["crimes"]):
                if claim[1] == "kael" and self.conf("brenna", claim) >= 0.5 and claim not in b["detained_for"]:
                    b["detained_for"].add(claim)
                    k["frozen_until"] = p + 1
                    self.decide("brenna", {"detain:kael": 10, "wait": 1}, "crime_belief")
                    self.log.append(f"p{p}: Brenna DETAINS Kael (phases {p}-{p + 1})")
        for w in ("odo", "mags"):
            if self.loc_of(w) != 2:
                continue
            for claim, bel in list(self.beliefs["brenna"].items()):
                if bel["status"] != "active" or w not in claim:
                    continue
                if all(e["source"] == w for e in bel["evidence"]):
                    continue
                if not self.happened(claim):       # the witness knows it never happened to them
                    bel["status"] = "retracted"
                    for src in {e["source"] for e in bel["evidence"]}:
                        if src in b["trust"]:
                            b["trust"][src] -= 3
                    self.event("testify", w, "brenna", claim, True)
                    self.log.append(f"p{p}: {w} testifies; Brenna RETRACTS {claim}; trust = {b['trust']}")
                    if k["frozen_until"] >= p:
                        k["frozen_until"] = p - 1
                        self.log.append(f"p{p}: Kael released")
        # 2b. Kael decides
        move = False
        if k["frozen_until"] < p:
            allowed = {"go_to": k["ambition"], "wait": 0}
            if k["loc"] == 4:
                allowed["take_relic"] = 100
            if (k["loc"] == 2 and b["loc"] == 2 and k["grudge"] >= 4 and not k["accused"]
                    and (self.conf("kael", ("robbed", "player", "kael")) or self.conf("kael", ("beat", "player", "kael")))):
                allowed["accuse:player"] = k["grudge"] + 3
            if k["respect"] >= 4 and k["loc"] == pl["loc"] and not k["drink"]:
                allowed["share_drink"] = k["respect"] + 3
            chosen = self.decide("kael", allowed, "tick")
            if chosen == "take_relic":
                if self.status == "playing":
                    self.status = f"lost@{p}"
            elif chosen == "accuse:player":
                k["accused"] = True
                claim = ("robbed", "player", "kael") if self.conf("kael", ("robbed", "player", "kael")) \
                    else ("beat", "player", "kael")
                eid = self.event("accuse", "kael", "brenna", claim, True)
                self.log.append(f"p{p}: Kael ACCUSES the player to Brenna (grudge {k['grudge']})")
                self.add_evidence("brenna", claim, conf_from_trust(b["trust"]["kael"]), "kael", eid)
            elif chosen == "share_drink":
                k["drink"] = True
                self.log.append(f"p{p}: Kael stays to share a drink (respect {k['respect']})")
            elif chosen == "go_to":
                if k["loc"] == 2 and b["trust"]["kael"] < 0:
                    self.log.append(f"p{p}: Kael BLOCKED at the gate")
                elif k["loc"] < 4:
                    move = True
        # 4. gossip on pre-move positions
        for g in ("odo", "mags"):
            mine = [(GOSSIP_PRIORITY.get(c[0], 0), self.conf(g, c), c) for c in self.beliefs[g]
                    if self.conf(g, c) >= 0.5 and ("player" in c or "kael" in c)]
            mine.sort(reverse=True)
            for listener in self.at(self.loc_of(g)):
                if listener == g:
                    continue
                for _, c_conf, claim in mine:
                    if claim not in self.beliefs[listener]:
                        eid = self.event("gossip", g, listener, claim, self.happened(claim))
                        self.add_evidence(listener, claim, round(c_conf * 0.8, 2), g, eid)
                        self.log.append(f"p{p}: {g} gossips {claim} to {listener}")
                        break
        # 5. moves
        if move:
            k["loc"] += 1
        self.locs["odo"] = ODO_WALK[(p + 1) % 4]
        # 6. drive upkeep
        k["fear"] = max(1, k["fear"] - 1)
        # 7. next phase
        self.phase += 1

    def snapshot(self):
        return {
            "phase": self.phase, "status": self.status,
            "player": dict(self.player),
            "kael": {x: self.kael[x] for x in ("loc", "grudge", "fear", "respect", "frozen_until")},
            "brenna_trust": dict(self.brenna["trust"]),
            "beliefs": {n: {",".join(c): {"conf": self.conf(n, c), "status": v["status"],
                                          "sources": [e["source"] for e in v["evidence"]]}
                            for c, v in self.beliefs[n].items()} for n in NPCS},
        }


def advance(w, steps):
    """Run phase-ending actions; the player takes the relic on arrival."""
    for a in steps:
        if w.status != "playing":
            return
        if w.take_relic():
            return
        w.tick(a)
    while w.status == "playing" and w.phase < 14:
        if w.take_relic():
            return
        w.tick("move")


def route_rush(seed):
    w = World(seed); advance(w, []); return w


def route_provoke(seed, pay=True, frame=False, wait_after=False):
    w = World(seed)
    w.insult()
    if not w.challenge():
        advance(w, []); return w
    w.humiliate()                            # ends phase 0
    if wait_after:
        w.tick("wait")
    w.tick("move")                           # phase 1 -> market
    w.tick("move")                           # phase 2 -> guard_post
    if w.status == "playing" and w.player["loc"] == 2:
        if frame:
            w.bribe(); w.bribe()
            w.tell_claim("brenna", ("robbed", "kael", "odo"))
        elif pay and w.brenna["trust"]["player"] < 0:
            w.bribe()
    advance(w, [])
    return w


def route_lie_unpaid(seed):
    w = World(seed)
    w.insult(); w.challenge(); w.humiliate()
    w.tick("move"); w.tick("move")
    w.tell_claim("brenna", ("robbed", "kael", "odo"))
    advance(w, []); return w


def route_spare(seed):
    w = World(seed)
    w.insult()
    if w.challenge():
        w.spare()
    advance(w, []); return w


def route_duel_lost(seed):
    # find a seed where the first duel loses
    s = seed
    while dice(s, "e0002") < 0.6:
        s += 1
    w = World(s); w.insult(); w.challenge(); advance(w, []); return w


def demo_acceptance(seed=DEMO_SEED):
    """The v2 demo route, asserting the 'Must be true' column after each beat."""
    w = World(seed)
    # Beat 1: phase 0, tavern
    w.insult()
    assert w.challenge(), f"seed {seed}: first duel must win; pick another DEMO_SEED"
    w.humiliate()
    s = w.snapshot_before_tick
    assert s["kael"]["grudge"] == 6 and s["kael"]["fear"] == 3 and s["kael"]["respect"] == 0, s["kael"]
    assert s["player"]["coins"] == 40
    for n in ("mags", "odo"):
        assert s["beliefs"][n]["robbed,player,kael"]["conf"] == 1.0
    assert w.decisions[-1]["npc"] == "kael" and w.decisions[-1]["chosen"] == "go_to"
    assert w.kael["fear"] == 2                                  # after the tick
    # Beat 2: phase 1, talk to Mags (no state change), move
    w.tick("move")
    # Beat 3: phase 2, market, move -> offscreen accusation at tick 2
    w.tick("move")
    assert any(d["chosen"] == "accuse:player" and d["phase"] == 2 for d in w.decisions)
    assert w.conf("brenna", ("robbed", "player", "kael")) == 0.9
    assert "kael" in [e["source"] for e in w.beliefs["brenna"][("robbed", "player", "kael")]["evidence"]]
    assert w.brenna["trust"]["player"] == -2
    # Beat 4: restart -> state must reload identically (engine test; here: snapshot round-trip)
    before = json.dumps(w.snapshot(), sort_keys=True)
    assert json.loads(before) == json.loads(json.dumps(w.snapshot(), sort_keys=True))
    # Beat 5: phase 3, guard post; Kael still there, move would be blocked
    assert w.phase == 3 and w.player["loc"] == 2 and w.kael["loc"] == 2
    # Beat 6: bribe twice, lie, move
    w.bribe(); w.bribe()
    w.tell_claim("brenna", ("robbed", "kael", "odo"))
    assert w.conf("brenna", ("robbed", "kael", "odo")) == 0.9 and not w.happened(("robbed", "kael", "odo"))
    assert w.brenna["trust"]["kael"] == 0
    assert w.kael["grudge"] == 8 and w.conf("kael", ("lied", "player", "kael")) == 1.0
    w.tick("move")
    assert any(d["chosen"] == "detain:kael" and d["phase"] == 3 for d in w.decisions)
    assert w.player["loc"] == 3
    # Beat 7: phase 4 move, phase 5 take relic
    w.tick("move")
    assert w.take_relic() and w.status == "won@5"
    # Epilogue: two more phases; Odo exposes the lie at phase 6
    w.status = "epilogue"
    w.tick("wait"); w.tick("wait")
    assert w.beliefs["brenna"][("robbed", "kael", "odo")]["status"] == "retracted"
    assert w.brenna["trust"]["player"] == -1
    return w


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else DEMO_SEED
    rows = [
        ("Rush", route_rush(seed)),
        ("Provoke and pay", route_provoke(seed, pay=True)),
        ("Provoke, don't pay", route_provoke(seed, pay=False)),
        ("Frame Kael (demo)", route_provoke(seed, frame=True)),
        ("Lie without paying", route_lie_unpaid(seed)),
        ("Spare", route_spare(seed)),
        ("Duel lost", route_duel_lost(seed)),
        ("Provoke, then wait", route_provoke(seed, pay=True, wait_after=True)),
        ("Provoke, wait, frame", route_provoke(seed, frame=True, wait_after=True)),
    ]
    print(f"seed {seed}; first duel {'WINS' if dice(seed, 'e0002') < 0.6 else 'loses'}\n")
    print(f"{'route':24} {'result':10} coins  kael_grudge")
    for name, w in rows:
        print(f"{name:24} {w.status:10} {w.player['coins']:5}  {w.kael['grudge']}")
    w = demo_acceptance(seed)
    print("\ndemo route acceptance test: PASS")
    print("\n".join("  " + line for line in w.log))
