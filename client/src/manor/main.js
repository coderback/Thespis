// The manor mystery's client: the house on the map, the action bar, the case notes and the inspector, wired to the
// engine's /manor API. Built like The Crypt Road's client (src/main.js) and sharing its styles and helpers.

import { $, esc, sleep } from "../dom.js";
import { ManorApi } from "./api.js";
import { runAutoplay } from "./autoplay.js";
import { Bar } from "./bar.js";
import { Inspector } from "./inspector.js";
import { actionText, ARRIVAL, bursts, caseNote, isLie, memory, name, spokenLines } from "./model.js";
import { ManorView } from "./scene.js";

const params = new URLSearchParams(location.search);
const DEADLINE = 7;
// The house as you find it, drawn behind the title card before any case is open.
const ARRIVING = {
  phase: ARRIVAL, clock: "Noon", status: "playing", player: { loc: "hall", asked: [] }, beliefs: [], ledger: [], decisions: [],
  npcs: [{ id: "vane", loc: "hall", drives: {} }, { id: "pell", loc: "study", drives: {} }, { id: "sable", loc: "kitchen", drives: { fear: 1 } }],
};

class ManorGame {
  constructor(api) {
    this.api = api;
    this.state = null;
    this.busy = false;
    this.autoplaying = false;
    this.cacheHits = 0;
    this.map = new ManorView($("map"));
    this.inspector = new Inspector();
    this.bar = new Bar({ onAct: (b) => this.act(b), onSay: (t, x) => this.say(t, x), onLine: (id) => this.inspector.openChain(id) });
    this.map.setState(ARRIVING, { instant: true });
    this.wire();
  }

  async boot() {
    const s = params.get("s");
    if (!s) return;
    this.api.session = s;
    try {
      const state = await this.api.state();
      $("landing").hidden = true;
      this.adopt(state, { instant: true });
      this.restore(state);
      await this.refreshAllowed();
      if (state.status !== "playing") this.showEnd(state);
    } catch {
      this.api.session = null;
      this.toast("That case has closed; open a new one.");
    }
  }

  async newSession() {
    const out = await this.api.newSession();
    const url = new URL(location.href);
    url.searchParams.set("s", out.session);
    history.replaceState(null, "", url);
    this.bar.clearLog();
    $("feed").innerHTML = "";
    $("endcard").hidden = true;
    this.inspector.chainId = null;
    this.inspector.prev = null;
    this.adopt(out.state, { instant: true });
    this.feed({ when: out.state.clock, items: [{ text: "You arrive at the manor. Lady Vane's signet ring is missing from the study." }] });
    await this.refreshAllowed();
  }

  adopt(state, opts = {}) {
    this.state = state;
    this.map.setState(state, opts);
    this.inspector.update(state);
    $("clock").textContent = state.clock;
    const left = DEADLINE - state.phase;
    $("deadline").textContent = state.status !== "playing" ? "Case closed" : left > 1 ? `${left} till evening` : "Evening next";
    const b = $("brain");
    b.className = state.brain === "fallback" ? "badge offline" : "badge model";
    b.textContent = state.brain === "fallback" ? "brain off" : "model";
    $("dev-session").textContent = this.api.session || "";
    $("dev-model").classList.toggle("on", state.brain !== "fallback");
    $("dev-fallback").classList.toggle("on", state.brain === "fallback");
  }

  /** After a reload: the lines already spoken and the notes so far, rebuilt from the state. */
  restore(state) {
    this.bar.clearLog();
    for (const r of spokenLines(state)) this.bar.line(r, { lie: isLie(state, state.decisions.find((d) => d.id === r.decision)) });
    $("feed").innerHTML = "";
    const seen = state.ledger.filter((e) => e.phase >= ARRIVAL && e.verb !== "arrive");
    this.feed({ when: "The case so far", items: seen.length ? seen.map((e) => ({ text: e.text, lie: Boolean(e.claim) && !e.truth })) : [{ text: "Nothing yet. Lady Vane is waiting in the hall." }] });
  }

  async refreshAllowed() {
    if (!this.api.session) return;
    try {
      const { verbs } = await this.api.allowed();
      const hint = !$("hint").hidden;
      this.bar.render(verbs, this.state, { pulse: hint ? (v) => v.verb === "ask" && v.target === "vane" : null });
      this.bar.setBusy(this.busy || this.autoplaying);
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

  caption(html) {
    $("caption").innerHTML = html || "";
    $("caption").hidden = !html;
  }

  feed(note) {
    const el = document.createElement("div");
    el.className = "digest";
    el.innerHTML = `<div class="when">${esc(note.when)}</div>${note.items.map((i) =>
      `<div class="note${i.lie ? " lie" : ""}">${esc(i.text)}${i.lie ? ' <span class="badge lie" title="The ledger logged it false">false</span>' : ""}</div>`).join("")}`;
    $("feed").prepend(el);
  }

  // --- acting ----------------------------------------------------------------------------------------

  act(body) { return this.perform(body, () => this.api.act(body)); }

  /** What you type to someone: the engine reads it as one of the buttons open now, or as nothing (POST /manor/say). */
  say(target, text) { return this.perform({ target, text }, () => this.api.say({ target, text })); }

  async perform(body, send) {
    if (this.busy) return null;
    this.busy = true;
    this.bar.setBusy(true);
    this.bar.closePop();
    this.bar.clearAsk();
    $("hint").hidden = true;
    const prev = this.state;
    let res;
    try {
      res = await send();
    } catch (e) {
      this.toast(e.reason || String(e));
      this.busy = false;
      this.bar.setBusy(false);
      return null;
    }
    const heard = res.understood;
    if (heard) {
      this.bar.sys(`You to ${name(body.target)}: "${body.text}"`);
      if (heard.status !== "act") { // nothing was done: the readings are put to you, or there was nothing in it
        if (heard.status === "ask") this.bar.ask(heard.readings);
        else this.bar.sys(`${name(body.target)} finds nothing in that to answer. Ask about this morning or the ring.`);
        this.busy = false;
        this.bar.setBusy(false);
        return res;
      }
      body = heard.intent.act;
    }
    this.bar.sys(actionText(body));
    if (body.verb === "move") await this.map.walkPlayer(res.state);
    const called = body.verb === "request_questioning" ? body.target : null;
    if (called) await this.map.summon(called);
    this.adopt(res.state);

    const fx = bursts(prev, res.state, res.events);
    let retracted = false;
    for (const r of res.replies) {
      const d = res.state.decisions.find((x) => x.id === r.decision);
      const lie = Boolean(d) && isLie(res.state, d);
      if (lie) this.map.burst(r.npc, "lie");
      const told = fx.find((b) => b.kind === "testify" && b.npc === r.npc);
      if (told) this.map.testify(r.npc, told.to);
      if (r.source === "cache") { this.cacheHits++; $("dev-replay").textContent = `${this.cacheHits} cache hits`; }
      this.bar.line(r, { lie });
      if (r.npc === "vane" && !retracted) {
        for (const b of fx.filter((x) => x.kind === "retract")) this.map.burst(b.npc, "retract");
        retracted = true;
      }
      await this.map.say(r.npc, r.line);
    }
    if (!retracted) for (const b of fx.filter((x) => x.kind === "retract")) this.map.burst(b.npc, "retract");
    if (called) await this.map.dismiss(called);
    const note = caseNote(res.events, res.state.clock);
    if (note) this.feed(note);
    this.busy = false;
    await this.refreshAllowed();
    if (res.state.status !== "playing") {
      await sleep(1200);
      this.showEnd(res.state);
    }
    return res;
  }

  showEnd(state) {
    const won = state.status === "won";
    $("endcard").classList.toggle("lost", !won);
    $("end-title").textContent = won ? "Case solved" : "Case lost";
    $("end-sub").textContent = state.outcome || "";
    const last = [...state.decisions].reverse().find((d) => d.npc === "vane" && d.line);
    $("epilogue").innerHTML = last ? `<b>Lady Vane:</b> "${esc(last.line)}"` : "";
    $("memory").innerHTML = memory(state).map((l) => `<li>${esc(l)}</li>`).join("");
    $("endcard").hidden = false;
  }

  // --- wiring ----------------------------------------------------------------------------------------

  wire() {
    $("play").onclick = async () => {
      $("landing").hidden = true;
      await this.newSession();
      let seen = false;
      try { seen = localStorage.getItem("manor-hint") === "1"; localStorage.setItem("manor-hint", "1"); } catch { /* private mode */ }
      if (!seen) { $("hint").textContent = "Try asking Lady Vane about the ring"; $("hint").hidden = false; await this.refreshAllowed(); }
    };
    $("watch").onclick = () => { $("landing").hidden = true; runAutoplay(this); };
    $("credits-link").onclick = () => ($("credits").hidden = false);
    $("credits-close").onclick = () => ($("credits").hidden = true);
    $("again").onclick = async () => { $("endcard").hidden = true; await this.newSession(); };
    $("inspect").onclick = () => { $("endcard").hidden = true; this.inspector.show("ledger"); };
    $("reset").onclick = async () => {
      if (!this.api.session || this.busy) return;
      this.autoplaying = false;
      this.caption(null);
      try {
        const { state } = await this.api.reset();
        this.bar.clearLog();
        $("endcard").hidden = true;
        this.adopt(state, { instant: true });
        this.restore(state);
        await this.refreshAllowed();
      } catch (e) { this.toast(e.reason || String(e)); }
    };
    document.addEventListener("keydown", (e) => {
      if (e.key === "`" && !e.target.closest?.("input, select, textarea")) $("dev").hidden = !$("dev").hidden;
    });
    $("dev-backend").textContent = this.api.kind;
    $("dev-reload").onclick = async () => {
      try { const { state } = await this.api.reload(); this.adopt(state); await this.refreshAllowed(); this.toast("Reloaded from disk"); } catch (e) { this.toast(e.reason); }
    };
    const brain = async (mode) => {
      try { await this.api.brain(mode); this.adopt(await this.api.state()); } catch (e) { this.toast(e.reason); }
    };
    $("dev-model").onclick = () => brain("model");
    $("dev-fallback").onclick = () => brain("fallback");
    $("dev-new").onclick = async () => { $("landing").hidden = true; await this.newSession(); };
  }
}

function fit() {
  const k = Math.min(innerWidth / 1280, innerHeight / 720);
  $("stage").style.transform = `scale(${k})`;
}
addEventListener("resize", fit);
fit();

const game = new ManorGame(new ManorApi());
window.game = game; // handy in the console and for recording
game.boot();
