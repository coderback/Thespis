// The manor's bottom bar: the dialogue log, and the buttons built from GET /manor/allowed. Asking opens a choice of
// topics, or a box for your own words (POST /manor/say); accusing asks once more, because it ends the case.

import { $, esc, badge } from "../dom.js";
import { name, roomName, topicName, readingLabel } from "./model.js";

export class Bar {
  constructor({ onAct, onSay, onLine }) {
    this.onAct = onAct; // (body) => Promise
    this.onSay = onSay; // (target, text) => Promise
    this.onLine = onLine; // (decisionId) => void, opens the why-chain
    this.busy = false;
    this.verbs = [];
    $("log").addEventListener("click", (e) => {
      const l = e.target.closest("[data-decision]");
      if (l) this.onLine(l.dataset.decision);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.closePop(); });
    document.addEventListener("click", (e) => {
      if (!$("pop").hidden && !e.target.closest("#pop, #actions")) this.closePop();
    });
  }

  // --- log -------------------------------------------------------------------------------------------

  line(reply, { lie = false } = {}) {
    const el = document.createElement("div");
    el.className = "logline";
    el.dataset.decision = reply.decision;
    el.title = "Click to see why they said it";
    el.innerHTML = `<span class="who ${esc(reply.npc)}">${esc(name(reply.npc))}</span><span class="q">"${esc(reply.line)}"</span> ${badge(reply.source)}${lie ? ' <span class="badge lie" title="The ledger logged this statement as false">lie</span>' : ""}`;
    this.push(el);
  }

  sys(text) {
    const el = document.createElement("div");
    el.className = "logline sys";
    el.textContent = text;
    this.push(el);
  }

  push(el) {
    const log = $("log");
    log.appendChild(el);
    while (log.children.length > 80) log.firstChild.remove();
    log.scrollTop = log.scrollHeight;
  }

  clearLog() { $("log").innerHTML = ""; }

  /** A reading of your words put to you before anything is done: each chip is the button it names. */
  ask(readings) {
    this.clearAsk();
    const el = document.createElement("div");
    el.className = "logline ask";
    el.id = "ask";
    el.innerHTML = `<span>Did you mean:</span>${readings.map((r, i) => `<button class="chipbtn" data-i="${i}">${esc(readingLabel(r.act))}</button>`).join("")}<button class="chipbtn plain" data-plain>Never mind</button>`;
    el.onclick = (e) => {
      const b = e.target.closest("button");
      if (!b || this.busy) return;
      this.clearAsk();
      if (b.dataset.plain === undefined) this.onAct(readings[+b.dataset.i].act);
    };
    this.push(el);
  }

  clearAsk() { $("ask")?.remove(); }

  // --- buttons ---------------------------------------------------------------------------------------

  setBusy(b) {
    this.busy = b;
    for (const el of document.querySelectorAll("#actions .act")) el.disabled = b || el.dataset.enabled !== "1";
  }

  render(verbs, state, { pulse } = {}) {
    this.verbs = verbs;
    const rows = [
      ["Ask", verbs.filter((v) => v.verb === "ask"), (v) => name(v.target)],
      ["Vane", verbs.filter((v) => v.verb === "request_questioning" || v.verb === "accuse"),
        (v) => (v.verb === "accuse" ? `Accuse ${name(v.target)}` : `Question ${name(v.target)}`)],
      ["Go", verbs.filter((v) => v.verb === "move"), (v) => roomName(v.target, { cap: true })],
    ].filter(([, vs]) => vs.length).map(([lbl, vs, label]) => {
      const btns = vs.map((v) => {
        const i = verbs.indexOf(v);
        const cls = ["act", v.ends_phase ? "ends" : "", v.verb === "accuse" ? "accuse" : "", pulse && pulse(v) ? "pulse" : ""].join(" ");
        const tip = v.enabled ? (v.verb === "move" ? `${v.label}. Takes until the next part of the day` : v.label) : v.reason || "Not now";
        return `<button class="${cls}" data-i="${i}" data-enabled="${v.enabled ? 1 : 0}" title="${esc(tip)}" ${v.enabled && !this.busy ? "" : "disabled"}>${esc(label(v))}</button>`;
      }).join("");
      return `<div class="arow"><span class="lbl">${lbl}</span>${btns}</div>`;
    }).join("");
    const box = $("actions");
    box.innerHTML = state.status === "playing" ? rows : '<div class="muted">The case is closed.</div>';
    box.onclick = (e) => {
      const b = e.target.closest(".act");
      if (!b || b.disabled) return;
      this.click(verbs[+b.dataset.i], b);
    };
  }

  click(v, el) {
    if (v.verb === "ask") return this.askPop(v, el);
    if (v.verb === "accuse") return this.accusePop(v, el);
    this.closePop();
    this.onAct({ verb: v.verb, target: v.target });
  }

  // --- popovers --------------------------------------------------------------------------------------

  openPop(html, el) {
    const pop = $("pop");
    pop.innerHTML = html;
    pop.hidden = false;
    const stage = $("stage").getBoundingClientRect();
    const r = el.getBoundingClientRect();
    const k = stage.width / 1280;
    pop.style.left = `${Math.min(1280 - 420, (r.left - stage.left) / k)}px`;
    pop.style.top = `${(r.top - stage.top) / k - pop.offsetHeight - 10}px`;
    return pop;
  }

  closePop() { $("pop").hidden = true; }

  askPop(v, el) {
    const who = esc(name(v.target));
    const pop = this.openPop(`<h4>Ask ${who} about...</h4>
      <div class="row">${v.args.topics.map((t) => `<button class="act" data-topic="${esc(t.id)}">${esc(topicName(t.id))}</button>`).join("")}</div>
      <form class="row"><input maxlength="200" placeholder="...or in your own words" autocomplete="off" /><button class="act" style="flex:none">Say</button></form>
      <div class="count">Asking is free: it never moves the clock on. Your own words are read as one of the buttons, or not at all.</div>`, el);
    pop.querySelectorAll("[data-topic]").forEach((b) => (b.onclick = () => {
      this.closePop();
      this.onAct({ verb: "ask", target: v.target, topic: b.dataset.topic });
    }));
    const input = pop.querySelector("input");
    pop.querySelector("form").onsubmit = (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return input.focus();
      this.closePop();
      this.onSay(v.target, text);
    };
  }

  accusePop(v, el) {
    const who = esc(name(v.target));
    const pop = this.openPop(`<h4>Accuse ${who}?</h4>
      <div class="preview">This ends the case. Lady Vane decides on what she believes now, not on what you know.</div>
      <div class="row"><button class="act ends" data-go>Accuse ${who}</button><button class="act" data-no>Not yet</button></div>`, el);
    pop.querySelector("[data-go]").onclick = () => { this.closePop(); this.onAct({ verb: "accuse", target: v.target }); };
    pop.querySelector("[data-no]").onclick = () => this.closePop();
  }
}
