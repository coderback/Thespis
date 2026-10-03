// The client: sends verbs, renders state, animates moves. The engine owns every rule (docs/api.md).

import { HttpApi, FixtureApi } from "./api.js";
import { MapView } from "./map.js";
import { Inspector } from "./inspector.js";
import { Bar } from "./bar.js";
import { $, esc, sleep } from "./dom.js";
import { runAutoplay } from "./autoplay.js";
import { clock, name, splitReplies, beliefBursts, worldMemory, claimText, STOP_SHORT } from "./model.js";

const params = new URLSearchParams(location.search);

// ?fixtures=1 replays fixtures/ with no engine. They are bundled as lazy chunks, so the normal build never loads them.
const FIXTURES = import.meta.glob("../../fixtures/*.json", { import: "default" });

async function makeApi() {
  if (!params.has("fixtures")) return new HttpApi(params.get("api") || "");
  const entries = await Promise.all(Object.entries(FIXTURES).map(async ([p, load]) => [p.split("/").pop().replace(".json", ""), await load()]));
  return new FixtureApi(Object.fromEntries(entries));
}

// A still world for the title card, before any session exists.
const TITLE_STATE = {
  phase: 0, status: "playing", brain: "model", pending: null, ended_at: null, player: { loc: "tavern", coins: 10 },
  npcs: [
    { id: "kael", loc: "tavern", last_seen: null, drives: {}, trust_in: {}, frozen_until: null },
    { id: "brenna", loc: "guard_post", last_seen: null, drives: {}, trust_in: {}, frozen_until: null },
    { id: "mags", loc: "tavern", last_seen: null, drives: {}, trust_in: {}, frozen_until: null },
    { id: "odo", loc: "tavern", last_seen: null, drives: {}, trust_in: {}, frozen_until: null },
  ],
  beliefs: [], ledger_tail: [], decisions_tail: [],
};

export class Game {
  constructor(api) {
    this.api = api;
    this.map = new MapView($("map"));
    this.inspector = new Inspector();
    this.bar = new Bar({ onAct: (b) => this.act(b), onLine: (id) => this.inspector.openChain(id) });
    this.state = null;
    this.busy = false;
    this.autoplaying = false;
    this.cacheHits = 0;
    this.recentSources = [];
    this.map.setState(TITLE_STATE, { instant: true });
    this.map.setFog(0, 0);
    this.wire();
  }

  // --- sessions --------------------------------------------------------------------------------------

  async boot() {
    const sid = params.get("s");
    if (!sid) return; // the landing screen waits for a choice
    this.api.session = sid;
    try {
      const state = await this.api.state();
      $("landing").hidden = true;
      this.adopt(state, { instant: true });
      this.map.setFog(1, 0);
      // Bring back what was said to you, so a reload reads like nothing happened.
      this.bar.sys("Session resumed from the engine.");
      for (const d of state.decisions_tail || []) {
        if (d.kind === "react" && d.line) this.bar.line({ decision: d.id, npc: d.npc, line: d.line, source: d.source });
      }
      await this.refreshAllowed();
      if (state.status !== "playing") await this.showEnd(state, null);
    } catch {
      this.toast("That session has gone; starting a new one.");
      await this.newSession();
    }
  }

  async newSession(seed) {
    const out = await this.api.newSession(seed ?? (params.get("seed") ? +params.get("seed") : undefined));
    const url = new URL(location.href);
    url.searchParams.set("s", out.session);
    history.replaceState(null, "", url);
    this.resetUi();
    this.adopt(out.state, { instant: true });
    this.map.setFog(1, 600);
    await this.refreshAllowed();
  }

  resetUi() {
    this.bar.clearLog();
    $("feed").innerHTML = "";
    $("endcard").hidden = true;
    this.inspector.chainId = null;
    this.inspector.prev = null;
    this.map.clearBubbles();
  }

  adopt(state, { instant = false } = {}) {
    this.state = state;
    this.map.setState(state, { instant });
    this.inspector.update(state);
    this.header();
  }

  header() {
    const s = this.state;
    $("clock").textContent = clock(s);
    $("coins").textContent = `${s.player.coins} coins`;
    const b = $("brain");
    const offline = this.recentSources.length >= 3 && this.recentSources.slice(-3).every((x) => x === "fallback");
    if (s.brain === "fallback") { b.className = "badge offline"; b.textContent = "brain off"; }
    else if (offline) { b.className = "badge offline"; b.textContent = "offline brain"; }
    else { b.className = "badge model"; b.textContent = "model"; }
    $("dev-session").textContent = this.api.session || "-";
    $("dev-backend").textContent = this.api.kind;
    $("dev-model").classList.toggle("on", s.brain !== "fallback");
    $("dev-fallback").classList.toggle("on", s.brain === "fallback");
  }

  async refreshAllowed() {
    try {
      const { verbs } = await this.api.allowed();
      const firstTime = !this.state.ledger_tail?.length && !$("hint").hidden;
      this.bar.render(verbs, this.state, { pulse: firstTime ? (v) => v.verb === "insult" && v.target === "kael" : null });
      this.bar.setBusy(this.busy);
    } catch (e) {
      this.toast(e.reason || String(e));
    }
  }

  toast(text) {
    const t = $("toast");
    t.textContent = text;
    t.hidden = false;
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => (t.hidden = true), 3500);
  }

  speak(r) {
    this.bar.line(r);
    this.recentSources.push(r.source);
    if (r.source === "cache") { this.cacheHits++; $("dev-replay").textContent = `${this.cacheHits} cache hits`; }
    return this.map.say(r.npc, r.line);
  }

  // --- acting ----------------------------------------------------------------------------------------

  async act(body) {
    if (this.busy) return null;
    this.busy = true;
    this.bar.setBusy(true);
    $("hint").hidden = true;
    const prev = this.state;
    let res;
    try {
      res = await this.api.act(body);
    } catch (e) {
      this.toast(e.reason || String(e));
      this.busy = false;
      this.bar.setBusy(false);
      return null;
    }
    this.bar.sys(actionText(body, prev));
    if (body.verb === "challenge") await this.map.rollDice(res.events.some((e) => e.verb === "beat" && e.actor === "player"));

    const { before, after } = splitReplies(res.replies, res.state, prev.phase);
    const bursts = beliefBursts(prev, res.state);
    if (!res.tick) {
      this.adopt(res.state);
      for (const b of bursts) this.map.burst(b.npc, b.kind);
      for (const r of before) await this.speak(r);
    } else {
      for (const r of before) await this.speak(r);
      const digest = this.api.digest(prev.phase).catch(() => null);
      this.feedWaiting();
      // Lines from decisions inside the tick are heard only if the speaker was at your stop.
      const here = (id) => prev.npcs.find((n) => n.id === id)?.loc === prev.player.loc;
      const spoken = new Set(res.replies.map((r) => r.decision));
      for (const d of res.tick.decisions) {
        if (d.line && here(d.npc) && !spoken.has(d.id)) await this.speak({ decision: d.id, npc: d.npc, line: d.line, source: d.source });
      }
      for (const e of res.tick.events) if (e.verb === "gossip") this.map.gossip(e.actor, e.target);
      await this.map.animateMoves(res.tick.moves, res.state);
      this.adopt(res.state);
      for (const b of bursts) this.map.burst(b.npc, b.kind);
      for (const r of after) await this.speak(r);
      this.feed(await digest, prev.phase);
    }
    if (res.epilogue) await this.playEpilogue(res, prev);
    this.busy = false;
    await this.refreshAllowed();
    return res;
  }

  feedWaiting() {
    const el = document.createElement("div");
    el.className = "digest waiting";
    el.id = "digest-waiting";
    el.textContent = "Meanwhile, out of sight...";
    $("feed").prepend(el);
  }

  feed(d, phase) {
    $("digest-waiting")?.remove();
    if (!d || !d.text) return;
    const el = document.createElement("div");
    el.className = "digest";
    const when = `Day ${Math.floor(phase / 4) + 1} · ${["morning", "noon", "evening", "night"][phase % 4]}`;
    el.innerHTML = `<div class="when">${when}</div>${esc(d.text)}${d.hook ? `<div class="hook">${esc(d.hook)}</div>` : ""}`;
    $("feed").prepend(el);
  }

  /** The race is over: lift the fog and let the world carry on for two more phases, then the end card. */
  async playEpilogue(res, prev) {
    const won = res.state.status === "won";
    this.caption(won ? "<b>You took the relic.</b> But the world doesn't stop when you win..." : "<b>Kael took the relic.</b> The world carries on...");
    this.map.setFog(0, 1200);
    // Rebuild where everyone stood when the race ended, then replay each epilogue tick.
    const view = structuredClone(res.state);
    view.phase = res.state.ended_at;
    const first = new Map();
    for (const t of res.epilogue) for (const m of t.moves) if (!first.has(m.who)) first.set(m.who, m.from);
    for (const n of view.npcs) if (first.has(n.id)) n.loc = first.get(n.id);
    if (first.has("player")) view.player.loc = first.get("player");
    this.map.setState(view);
    await sleep(1400);
    for (const t of res.epilogue) {
      for (const d of t.decisions) if (d.line) await this.speak({ decision: d.id, npc: d.npc, line: d.line, source: d.source });
      for (const e of t.events) if (e.verb === "gossip" || e.verb === "testify") this.map.gossip(e.actor, e.target);
      const next = structuredClone(view);
      next.phase = view.phase + 1;
      for (const m of t.moves) {
        if (m.who === "player") next.player.loc = m.to;
        else next.npcs.find((n) => n.id === m.who).loc = m.to;
      }
      await this.map.animateMoves(t.moves, next);
      Object.assign(view, next);
    }
    this.adopt(res.state);
    for (const b of beliefBursts(prev, res.state)) this.map.burst(b.npc, b.kind);
    await sleep(1600);
    this.caption(null);
    await this.showEnd(res.state, prev);
  }

  async showEnd(state) {
    const won = state.status === "won";
    $("endcard").classList.toggle("lost", !won);
    $("end-title").textContent = won ? "Victory" : "Defeat";
    $("end-sub").textContent = won
      ? `You took the relic on day ${Math.floor(state.ended_at / 4) + 1}, ${["morning", "noon", "evening", "night"][state.ended_at % 4]}.`
      : "Kael reached the crypt first and took the relic.";
    $("epilogue").textContent = "The Dungeon Master is telling the tale...";
    $("memory").innerHTML = worldMemory(state).map((l) => `<li>${esc(l)}</li>`).join("");
    $("endcard").hidden = false;
    try {
      const d = await this.api.digest(state.ended_at ?? state.phase);
      $("epilogue").textContent = d.epilogue || d.text || "";
      if (d.hook) $("epilogue").insertAdjacentHTML("beforeend", `<div class="digest hook">${esc(d.hook)}</div>`);
    } catch {
      $("epilogue").textContent = "";
    }
  }

  caption(html) {
    const c = $("caption");
    if (!html) { c.hidden = true; return; }
    c.innerHTML = html;
    c.hidden = false;
    c.style.animation = "none";
    void c.offsetWidth;
    c.style.animation = "";
  }

  // --- wiring ----------------------------------------------------------------------------------------

  wire() {
    $("play").onclick = async () => {
      $("landing").hidden = true;
      await this.newSession();
      let seen = false;
      try { seen = localStorage.getItem("cr-hint") === "1"; localStorage.setItem("cr-hint", "1"); } catch { /* private mode */ }
      if (!seen) { $("hint").textContent = "Try insulting Kael"; $("hint").hidden = false; await this.refreshAllowed(); }
    };
    $("watch").onclick = () => { $("landing").hidden = true; runAutoplay(this); };
    $("credits-link").onclick = () => ($("credits").hidden = false);
    $("credits-close").onclick = () => ($("credits").hidden = true);
    $("reset").onclick = async () => {
      if (this.busy && !this.autoplaying) return;
      this.autoplaying = false;
      try {
        if (!this.api.session) return this.newSession();
        const { state } = await this.api.reset();
        this.resetUi();
        this.map.setFog(1, 300);
        this.adopt(state, { instant: true });
        await this.refreshAllowed();
      } catch (e) { this.toast(e.reason || String(e)); }
    };
    $("again").onclick = () => $("reset").onclick();
    $("inspect").onclick = () => { $("endcard").hidden = true; this.inspector.show("beliefs"); };

    document.addEventListener("keydown", (e) => {
      if (e.key === "`" && !e.target.closest("input, select, textarea")) $("dev").hidden = !$("dev").hidden;
    });
    $("dev-reload").onclick = async () => {
      try { const { state } = await this.api.reload(); this.adopt(state); await this.refreshAllowed(); this.toast("Reloaded from disk"); } catch (e) { this.toast(e.reason); }
    };
    const brain = async (mode) => {
      try { await this.api.brain(mode); this.adopt(await this.api.state()); } catch (e) { this.toast(e.reason); }
    };
    $("dev-model").onclick = () => brain("model");
    $("dev-fallback").onclick = () => brain("fallback");
    $("dev-new").onclick = () => { $("landing").hidden = true; this.newSession(+$("dev-seed").value || undefined); };
  }
}

function actionText(body, state) {
  const t = body.target ? name(body.target) : "";
  switch (body.verb) {
    case "talk": return `You to ${t}: "${body.text}"`;
    case "insult": return `You insult ${t}.`;
    case "challenge": return `You challenge ${t} to a duel.`;
    case "humiliate": return `You humiliate ${t} and take his purse.`;
    case "spare": return `You spare ${t}.`;
    case "tell_claim": return `You tell ${t}: "${claimText(body.claim)}."`;
    case "bribe": return `You pay ${t} a fine of ${body.amount} coins.`;
    case "move": return `You walk on from ${STOP_SHORT[state.player.loc]}.`;
    case "wait": return "You wait.";
    case "take_relic": return "You take the relic.";
    default: return `You ${body.verb} ${t}`;
  }
}

function fit() {
  const k = Math.min(innerWidth / 1280, innerHeight / 720);
  $("stage").style.transform = `scale(${k})`;
}
addEventListener("resize", fit);
fit();

makeApi().then((api) => {
  const game = new Game(api);
  window.game = game; // handy in the console and for recording
  game.boot();
});
