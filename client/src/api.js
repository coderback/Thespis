// The only module that talks to the engine. Two backends with one interface:
//   http     - the real engine (same origin in production, proxied by Vite in dev)
//   fixtures - replays fixtures/ along the demo route, for building without an engine (?fixtures=1)

import { eventText } from "./model.js";

export class ApiError extends Error {
  constructor(status, error, reason) {
    super(reason || error);
    this.status = status;
    this.error = error;
    this.reason = reason || error;
  }
}

export class HttpApi {
  constructor(base = "") {
    this.base = base;
    this.session = null;
    this.kind = "http";
  }

  async req(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    if (this.session) headers["X-Session"] = this.session;
    let res;
    try {
      res = await fetch(this.base + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      throw new ApiError(0, "network", "Can't reach the engine. Is it running?");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(res.status, data.error || "error", data.reason || `HTTP ${res.status}`);
    return data;
  }

  async newSession(seed) {
    const out = await this.req("POST", "/session", seed == null ? {} : { seed });
    this.session = out.session;
    return out;
  }
  state() { return this.req("GET", "/state"); }
  allowed() { return this.req("GET", "/allowed"); }
  act(body) { return this.req("POST", "/act", body); }
  say(body) { return this.req("POST", "/say", body); } // {target, text}: read as one of the buttons, or as talk
  digest(since) { return this.req("GET", `/digest?since=${since}`); }
  reset() { return this.req("POST", "/reset", {}); }
  reload() { return this.req("POST", "/reload", {}); }
  brain(mode) { return this.req("POST", "/dev/brain", { mode }); }
  persona(npc, persona) { return this.req("POST", "/dev/persona", { npc, persona }); }
}

const ROUTE = [
  ["act_01_insult_kael", { verb: "insult", target: "kael" }],
  ["act_02_challenge_kael_win", { verb: "challenge", target: "kael" }],
  ["act_03_humiliate_kael", { verb: "humiliate", target: "kael" }],
  ["act_04_talk_mags", { verb: "talk", target: "mags" }],
  ["act_05_move_to_market", { verb: "move" }],
  ["act_06_move_to_guard_post", { verb: "move" }],
  ["act_07_bribe_brenna", { verb: "bribe", target: "brenna" }],
  ["act_08_bribe_brenna", { verb: "bribe", target: "brenna" }],
  ["act_09_tell_brenna_lie", { verb: "tell_claim", target: "brenna" }],
  ["act_10_move_to_bridge", { verb: "move" }],
  ["act_11_move_to_crypt", { verb: "move" }],
  ["act_12_take_relic", { verb: "take_relic" }],
];

/** Replays the demo route from fixtures. Anything off the route is refused with a 409, like a disabled verb. */
export class FixtureApi {
  constructor(files) {
    this.f = files; // { name: json }, without the .json
    this.kind = "fixtures";
    this.session = "demo-0001";
    this.step = 0;
    this.current = files.session_new.state;
    this.personas = {}; // live persona edits (#39), laid over every state the fixtures return
  }
  clone(x) { return JSON.parse(JSON.stringify(x)); }
  withPersonas(s) {
    for (const n of s.npcs) if (this.personas[n.id]) { n.persona = this.personas[n.id]; n.persona_edited = true; }
    return s;
  }
  async newSession() {
    this.step = 0;
    this.personas = {};
    this.current = this.f.session_new.state;
    return this.clone(this.f.session_new);
  }
  async state() { return this.withPersonas(this.clone(this.current)); }
  async reset() { this.step = 0; this.personas = {}; this.current = this.f.session_new.state; return { state: this.clone(this.current) }; }
  async persona(npc, persona) {
    const text = (persona || "").trim();
    if (text) this.personas[npc] = text;
    else delete this.personas[npc];
    return { npc, persona: text || this.current.npcs.find((n) => n.id === npc)?.persona, default: !text };
  }
  async reload() { return { state: this.clone(this.current) }; }
  async brain(mode) { return { mode }; }

  async allowed() {
    const s = this.current;
    if (s.status !== "playing") return this.clone(this.f.allowed_p7_end);
    if (s.pending === "duel_won") return this.clone(this.f.allowed_p0_duel_won);
    if (this.step === 0) return this.clone(this.f.allowed_p0_tavern);
    if (this.step === 6) return this.clone(this.f.allowed_p3_gate);
    const [, req] = ROUTE[this.step] || [];
    if (!req) return { verbs: [] };
    const verbs = [{
      verb: req.verb, target: req.target || null, label: labelFor(req), ends_phase: req.verb === "move",
      enabled: true, reason: null,
      args: req.verb === "talk" ? { max_len: 200 } : req.verb === "move" ? { to: nextStop(s.player.loc) }
        : req.verb === "bribe" ? { amount: 20, min: 1, max: s.player.coins } : {},
    }];
    return { verbs };
  }

  async act(body) {
    const [name, req] = ROUTE[this.step] || [];
    if (!req || req.verb !== body.verb || (req.target && req.target !== body.target)) {
      throw new ApiError(409, "not_allowed", req ? `Fixture mode follows the demo route: next is ${labelFor(req)}` : "The race is over");
    }
    this.step++;
    const out = this.clone(this.f[name]);
    this.current = this.clone(out.state); // kept as the fixture has it, so an edit can be undone
    this.withPersonas(out.state);
    return out;
  }

  /** The fixtures hold no readings, so whatever is typed is talk, where the demo route talks. */
  async say({ target, text }) {
    const out = await this.act({ verb: "talk", target, text });
    return { ...out, understood: { status: "talk", intent: { verb: "talk", act: { verb: "talk", target } }, sure: "unsure", readings: [], path: "none", why: "fixture mode reads nothing" } };
  }

  async digest(since) {
    if (this.current.ended_at != null && since >= this.current.ended_at) return this.clone(this.f.digest_epilogue);
    if (since === 2) return this.clone(this.f.digest_p2);
    const events = (this.current.ledger_tail || []).filter((e) => e.phase === since);
    return { text: events.map((e) => eventText(e) + ".").join(" ") || "Nothing stirred.", hook: null, cites: events.map((e) => e.id), epilogue: null };
  }
}

function labelFor(req) {
  const t = req.target ? req.target[0].toUpperCase() + req.target.slice(1) : "";
  return { talk: `Talk to ${t}`, move: "Move on", bribe: `Bribe ${t}...`, tell_claim: `Tell ${t}...`, take_relic: "Take the relic" }[req.verb]
    || `${req.verb[0].toUpperCase()}${req.verb.slice(1)} ${t}`.trim();
}

function nextStop(loc) {
  const stops = ["tavern", "market", "guard_post", "bridge", "crypt"];
  return stops[stops.indexOf(loc) + 1] || null;
}

export { ROUTE as DEMO_ROUTE };
