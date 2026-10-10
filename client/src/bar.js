// The bottom bar: the dialogue log and the buttons built from GET /allowed, with the "Say or do..." box and the
// three-dropdown claim builder for Tell... What you type is read as one of the buttons, or as talk (POST /say).

import { $, esc, badge } from "./dom.js";
import { name, claimText, readingLabel } from "./model.js";

export class Bar {
  constructor({ onAct, onSay, onLine }) {
    this.onAct = onAct; // (body, opts) => Promise
    this.onSay = onSay; // (target, text) => Promise
    this.onLine = onLine; // (decisionId) => void, opens the why-chain
    this.busy = false;
    this.verbs = [];
    $("log").addEventListener("click", (e) => {
      const l = e.target.closest("[data-decision]");
      if (l) this.onLine(l.dataset.decision);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.closePop(); });
  }

  // --- log -------------------------------------------------------------------------------------------

  line(reply) {
    const el = document.createElement("div");
    el.className = "logline";
    el.dataset.decision = reply.decision;
    el.title = "Click to see why they said it";
    el.innerHTML = `<span class="who ${esc(reply.npc)}">${esc(name(reply.npc))}</span><span class="q">"${esc(reply.line)}"</span> ${badge(reply.source)}`;
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
    while (log.children.length > 60) log.firstChild.remove();
    log.scrollTop = log.scrollHeight;
  }

  clearLog() { $("log").innerHTML = ""; }

  /** A reading that wasn't sure enough to act on, put to you: each chip is the button it names. */
  ask(target, text, readings) {
    this.clearAsk();
    const el = document.createElement("div");
    el.className = "logline ask";
    el.id = "ask";
    el.innerHTML = `<span>Did you mean:</span>${readings.map((r, i) => `<button class="chipbtn" data-i="${i}">${esc(readingLabel(r.act))}</button>`).join("")}<button class="chipbtn plain" data-plain>Just say it</button>`;
    el.onclick = (e) => {
      const b = e.target.closest("button");
      if (!b || this.busy) return;
      this.clearAsk();
      if (b.dataset.plain !== undefined) this.onAct({ verb: "talk", target, text }, { quiet: true });
      else this.onAct(readings[+b.dataset.i].act);
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
    const groups = new Map();
    for (const v of verbs) {
      // Humiliate and spare only matter right after a duel win; hide them otherwise to keep the bar calm.
      if ((v.verb === "humiliate" || v.verb === "spare") && state.pending !== "duel_won") continue;
      if (state.pending && !v.enabled) continue; // after a duel win only the two choices matter
      if (v.verb === "take_relic" && state.player.loc !== "crypt" && !v.enabled) continue;
      const key = v.target || "_";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(v);
    }
    const rows = [...groups.entries()].sort(([a], [b]) => (a === "_") - (b === "_")).map(([target, vs]) => {
      const btns = vs.map((v) => {
        const i = verbs.indexOf(v);
        const label = target === "_" ? v.label : shortLabel(v);
        const cls = ["act", v.ends_phase ? "ends" : "", pulse && pulse(v) ? "pulse" : ""].join(" ");
        const tip = v.enabled ? (v.ends_phase ? `${v.label}. Ends the phase` : v.label) : v.reason || "Not now";
        return `<button class="${cls}" data-i="${i}" data-enabled="${v.enabled ? 1 : 0}" title="${esc(tip)}" ${v.enabled && !this.busy ? "" : "disabled"}>${esc(label)}</button>`;
      }).join("");
      return `<div class="arow"><span class="lbl">${target === "_" ? "Road" : esc(name(target))}</span>${btns}</div>`;
    }).join("");
    const box = $("actions");
    box.innerHTML = rows || '<div class="muted">The race is over.</div>';
    box.onclick = (e) => {
      const b = e.target.closest(".act");
      if (!b || b.disabled) return;
      this.click(verbs[+b.dataset.i], b);
    };
  }

  click(v, el) {
    if (v.verb === "talk") return this.sayPop(v, el);
    if (v.verb === "tell_claim") return this.tellPop(v, el);
    if (v.verb === "bribe") return this.bribePop(v, el);
    const body = { verb: v.verb };
    if (v.target) body.target = v.target;
    this.onAct(body);
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

  sayPop(v, el) {
    const max = v.args?.max_len ?? 200;
    const who = esc(name(v.target));
    const pop = this.openPop(`<h4>Say or do... <span class="muted">to ${who}</span></h4>
      <form class="row"><input id="talk-text" maxlength="${max}" placeholder="Say it, or do it in words..." autocomplete="off" /><button class="act" style="flex:none">Say</button></form>
      <div class="count"><span id="talk-n">0</span> / ${max}. Words can do what the buttons do: an insult, a claim, an offer of coins. Anything else is talk, which is free.</div>`, el);
    const input = pop.querySelector("input");
    input.focus();
    input.oninput = () => { $("talk-n").textContent = input.value.length; };
    pop.querySelector("form").onsubmit = (e) => {
      e.preventDefault();
      const text = input.value.trim() || "Hello.";
      this.closePop();
      this.onSay(v.target, text);
    };
  }

  bribePop(v, el) {
    const { amount = 20, min = 1, max = amount } = v.args || {};
    const who = esc(name(v.target));
    const pop = this.openPop(`<h4>Bribe ${who}</h4>
      <form class="row"><input id="bribe-amount" type="number" min="${min}" max="${max}" step="1" value="${amount}" aria-label="Coins to offer" /><button class="act" style="flex:none">Offer</button></form>
      <div class="count">You have ${max} coins. Offer too little and ${who} names a price, or turns you away for the phase.</div>`, el);
    const input = pop.querySelector("input");
    input.focus();
    input.select();
    pop.querySelector("form").onsubmit = (e) => {
      e.preventDefault();
      const n = Math.round(Number(input.value));
      if (!(n >= min && n <= max)) return input.focus();
      this.closePop();
      this.onAct({ verb: "bribe", target: v.target, amount: n });
    };
  }

  tellPop(v, el) {
    const preds = v.args?.preds || ["robbed", "beat", "insulted", "spared", "lied"];
    const subs = v.args?.subjects || ["player", "kael", "brenna", "mags", "odo"];
    const opt = (list, sel, fmt) => list.map((x) => `<option value="${esc(x)}" ${x === sel ? "selected" : ""}>${esc(fmt(x))}</option>`).join("");
    const pop = this.openPop(`<h4>Tell ${esc(name(v.target))}...</h4>
      <div class="row">
        <select id="tell-a">${opt(subs, "kael", (x) => name(x))}</select>
        <select id="tell-p">${opt(preds, "robbed", (x) => x)}</select>
        <select id="tell-b">${opt(subs, "odo", (x) => name(x))}</select>
      </div>
      <div class="preview" id="tell-preview"></div>
      <div class="row"><button class="act ends" id="tell-go" style="flex:1">Tell ${esc(name(v.target))}</button></div>`, el);
    const claim = () => ({ pred: $("tell-p").value, a: $("tell-a").value, b: $("tell-b").value });
    const preview = () => {
      $("tell-preview").innerHTML = `"${esc(claimText(claim()))}." ${esc(name(v.target))} will believe it as much as they trust you. The ledger records the truth.`;
    };
    pop.querySelectorAll("select").forEach((s) => (s.onchange = preview));
    preview();
    $("tell-go").onclick = () => { this.closePop(); this.onAct({ verb: "tell_claim", target: v.target, claim: claim() }); };
  }
}

function shortLabel(v) {
  return { talk: "Say...", insult: "Insult", challenge: "Challenge", humiliate: "Humiliate", spare: "Spare", tell_claim: "Tell...", bribe: "Bribe..." }[v.verb] || v.label;
}
