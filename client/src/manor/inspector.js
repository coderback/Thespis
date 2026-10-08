// The manor's inspector: Minds, Beliefs, Ledger and Why, drawn with The Crypt Road's classes so the two games read
// the same. The why-chain runs from a line to its decision, to the claim it stated and what the speaker really knew,
// down to the ledger.

import { $, esc, badge } from "../dom.js";
import { ARRIVAL, CAST, name, roomName, fmtTrust, isLie } from "./model.js";

const DRIVES = [["fear", "#7fc3ec"]];
const TRIGGERS = {
  asked_morning: "asked about this morning", asked_ring: "asked about the ring", testify: "questioned by Lady Vane",
  questioned: "after Pell's testimony", questioned_sable: "after questioning Sable", accused_sable: "on the accusation",
  accused_pell: "on the accusation", constable: "at evening",
};
export const trigger = (t) => TRIGGERS[t] || t.replace(/_/g, " ");

export class Inspector {
  constructor() {
    this.tab = "minds";
    this.state = null;
    this.prev = null;
    this.chainId = null;
    this.highlight = null;
    for (const b of document.querySelectorAll("#tabs button")) {
      b.addEventListener("click", () => { this.highlight = null; this.show(b.dataset.tab); });
    }
    $("panel").addEventListener("click", (e) => {
      if (e.target.closest("[data-close-chain]")) { this.chainId = null; return this.render(); }
      const chip = e.target.closest("[data-id]");
      if (chip) return this.follow(chip.dataset.id);
      const card = e.target.closest("[data-decision]");
      if (card) this.openChain(card.dataset.decision);
    });
    this.show("minds");
  }

  update(state) {
    this.prev = this.state;
    this.state = state;
    if (this.prev) this.flashTabs();
    this.render();
  }

  flashTabs() {
    const changed = {
      beliefs: this.state.beliefs.length !== this.prev.beliefs.length ||
        this.state.beliefs.some((b, i) => this.prev.beliefs[i]?.status !== b.status),
      ledger: this.state.ledger.length !== this.prev.ledger.length,
      why: this.state.decisions.length !== this.prev.decisions.length,
    };
    for (const [tab, on] of Object.entries(changed)) {
      if (on && tab !== this.tab) document.querySelector(`#tabs [data-tab="${tab}"]`).classList.add("flash");
    }
  }

  show(tab) {
    this.tab = tab;
    for (const b of document.querySelectorAll("#tabs button")) {
      b.setAttribute("aria-selected", String(b.dataset.tab === tab));
      if (b.dataset.tab === tab) b.classList.remove("flash");
    }
    this.render();
  }

  openChain(decisionId) {
    this.chainId = decisionId;
    this.show("why");
    $("panel").scrollTop = 0;
  }

  follow(id) {
    this.highlight = id;
    if (id.startsWith("e")) this.show("ledger");
    else if (id.startsWith("b")) this.show("beliefs");
    else if (id.startsWith("d")) return this.openChain(id);
    document.querySelector(`[data-ev="${id}"], [data-b="${id}"]`)?.scrollIntoView({ block: "center" });
  }

  render() {
    if (!this.state) return;
    const html = { minds: () => this.minds(), beliefs: () => this.beliefs(), ledger: () => this.ledger(), why: () => this.why() }[this.tab]();
    const panel = $("panel");
    const top = panel.scrollTop;
    panel.innerHTML = html;
    if (this.tab === "ledger" && !this.highlight) panel.scrollTop = panel.scrollHeight;
    else if (!(this.tab === "why" && this.chainId)) panel.scrollTop = top;
  }

  minds() {
    return CAST.map((id) => {
      const n = this.state.npcs.find((x) => x.id === id);
      if (!n) return "";
      const drives = DRIVES.filter(([k]) => n.drives[k] !== undefined).map(([k, col]) => `
        <div class="drive"><span>${k}</span><div class="meter"><i style="width:${(n.drives[k] / 10) * 100}%;background:${col}"></i></div><b>${n.drives[k]}</b></div>`).join("");
      const trust = Object.entries(n.trust_in || {}).map(([who, t]) => {
        const w = (Math.abs(t) / 5) * 50;
        const left = t >= 0 ? 50 : 50 - w;
        return `<div class="drive"><span>trust ${esc(name(who, { lower: true }))}</span><div class="meter trust"><i style="left:${left}%;width:${w}%;background:${t >= 0 ? "var(--good)" : "var(--bad)"}"></i></div><b>${fmtTrust(t)}</b></div>`;
      }).join("");
      return `<div class="npc"><h4><span class="who ${id}">${name(id)}</span><span class="where">in ${roomName(n.loc)}</span></h4>${drives}${trust}
        <div class="persona"><q>${esc(n.persona)}</q></div></div>`;
    }).join("");
  }

  beliefs() {
    const old = new Set((this.prev?.beliefs || []).map((b) => b.id));
    const groups = CAST.map((id) => {
      const list = this.state.beliefs.filter((b) => b.npc === id);
      if (!list.length) return "";
      return `<div class="group"><h5><span class="who ${id}">${name(id)}</span> believes</h5>${list.map((b) => this.beliefRow(b, this.prev && !old.has(b.id))).join("")}</div>`;
    }).join("");
    return `<div class="empty manor-note">✓ and ✗ come from the ledger. The people never see them.</div>${groups}`;
  }

  beliefRow(b, isNew) {
    const mark = b.truth ? ["t", "✓", "True: the ledger shows it happened"] : ["f", "✗", "False: nothing in the ledger makes it true"];
    const how = (ev) => ev.source === "witnessed" ? "saw it" : ev.source === "self" ? "knows first-hand" : "told by " + esc(name(ev.source));
    const src = (b.evidence || []).map((ev) => `<span class="chip${ev.against ? " against" : ""}">${ev.against ? "against, " : ""}${how(ev)} · ${ev.conf.toFixed(1)}</span><span class="chip id" data-id="${esc(ev.event)}">${esc(ev.event)}</span>`).join(" ");
    const cls = ["belief", b.status === "retracted" ? "retracted" : "", isNew ? "new" : "", this.highlight === b.id ? "ev hl" : ""].join(" ");
    return `<div class="${cls}" data-b="${esc(b.id)}">
      <span class="mark ${mark[0]}" title="${mark[2]}">${mark[1]}</span>
      <span class="claim">${esc(b.claim)}${b.status === "retracted" ? ' <span class="badge offline">retracted</span>' : ""}</span>
      <div class="meter" title="confidence ${b.conf}${b.opinion && b.opinion.d > 0 ? `, doubt ${b.opinion.d}` : ""}"><i style="width:${b.conf * 100}%;background:var(--accent)"></i>${b.opinion && b.opinion.d > 0 ? `<i class="dis" style="width:${b.opinion.d * 100}%"></i>` : ""}</div>
      <div class="src"><span class="chip id" data-id="${esc(b.id)}">${esc(b.id)}</span> ${src}</div>
    </div>`;
  }

  ledger() {
    const s = this.state;
    const old = new Set((this.prev?.ledger || []).map((e) => e.id));
    let lastPhase = -1;
    const rows = s.ledger.map((e) => {
      let head = "";
      if (e.phase !== lastPhase) {
        const when = s.clocks?.[e.phase] || `phase ${e.phase}`;
        head = `<div class="phase-h">${esc(when)}${e.phase < ARRIVAL ? " · before you arrived" : ""}</div>`;
      }
      lastPhase = e.phase;
      const truth = e.claim ? (e.truth ? '<span class="mark t" title="True">✓</span>' : '<span class="mark f" title="False: a lie, logged as one">✗</span>') : "<span></span>";
      const cls = ["ev", this.prev && !old.has(e.id) ? "new" : "", this.highlight === e.id ? "hl" : "", e.claim && !e.truth ? "lie" : ""].join(" ");
      return `${head}<div class="${cls}" data-ev="${esc(e.id)}"><span class="id">${esc(e.id)}</span><span>${esc(e.text)}</span>${truth}</div>`;
    }).join("");
    return rows || '<div class="empty">The ledger is empty.</div>';
  }

  why() {
    const s = this.state;
    const chain = this.chainId ? this.chainHtml(this.chainId) : "";
    const cards = [...s.decisions].reverse().filter((d) => d.line).map((d) => `
      <div class="dcard" data-decision="${esc(d.id)}">
        <div class="head"><span class="who ${d.npc}">${name(d.npc)}</span><span>${esc(d.id)} · ${esc(trigger(d.trigger))}</span>${isLie(s, d) ? '<span class="badge lie">lie</span>' : ""}${badge(d.source)}</div>
        ${d.kind === "decide" ? `<div>${(d.allowed || []).map((a) => `<span class="chip ${a === d.chosen ? "chosen" : ""}">${esc(a)}</span>`).join("")}</div>` : ""}
        <div class="line">"${esc(d.line)}"</div>
        <div class="meta">cites ${(d.cites || []).map((c) => `<span class="chip id" data-id="${esc(c)}">${esc(c)}</span>`).join("") || "nothing"}</div>
      </div>`).join("");
    const intro = chain ? "" : '<div class="empty">Click any spoken line, here or in the log, to trace it to the ledger.</div>';
    return `${chain}${intro}${cards}`;
  }

  chainHtml(id) {
    const s = this.state;
    const d = s.decisions.find((x) => x.id === id);
    if (!d) return "";
    const ev = (eid) => s.ledger.find((e) => e.id === eid);
    const bel = (bid) => s.beliefs.find((b) => b.id === bid);
    const nodes = [];
    const chip = (x) => `<span class="chip id" data-id="${esc(x)}">${esc(x)}</span>`;
    const node = (cls, k, body, sub = "") => nodes.push(
      `<div class="node ${cls}" style="animation-delay:${nodes.length * 0.15}s"><div class="k">${k}</div><div class="body">${body}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`);
    const how = (e) => e.source === "witnessed" ? "saw it" : e.source === "self" ? "knows first-hand" : "told by " + esc(name(e.source));
    const root = (e) => {
      const t = e.truth ? "t" : "f";
      node(`root ${t}`, `Ledger ${chip(e.id)}${e.phase < ARRIVAL ? " · before you arrived" : ""}<span class="verdict ${t}">${e.truth ? "✓ TRUE" : "✗ FALSE"}</span>`,
        esc(e.text), e.truth ? "This really happened. The ledger is the ground truth." : "Nothing in the ledger makes this true.");
    };

    node("line", `<span class="who ${d.npc}">${name(d.npc)}</span> said ${badge(d.source)}`, `"${esc(d.line || "(no line)")}"`);
    node("", `Decision ${chip(d.id)} · ${d.kind}`,
      d.kind === "decide"
        ? `Chose <span class="chip chosen">${esc(d.chosen)}</span> from ${(d.allowed || []).map((a) => `<span class="chip">${esc(a)}</span>`).join("")}`
        : `Reacted ${esc(trigger(d.trigger))}`,
      `Reason: ${esc(d.reason || "-")}`);
    const stated = d.asserted && ev(d.asserted);
    if (stated) {
      root(stated);
      const knew = (d.knew || []).map(bel).filter(Boolean);
      for (const b of knew) {
        const roots = b.evidence.map((x) => `${how(x)} in ${chip(x.event)}`).join("<br>");
        node("", `What ${name(d.npc, { lower: false })} knew ${chip(b.id)}`, `<b>${esc(b.claim)}</b>`, roots);
      }
      if (knew.length && !stated.truth) node("lie-k", "So", `${name(d.npc)} stated it <b>knowing it was false</b>: a lie, not a mistake.`);
    }
    for (const c of d.cites || []) {
      if (c === d.asserted) continue;
      const b = bel(c), e = ev(c);
      if (b) {
        const sub = b.evidence.map((x) => `${how(x)} in ${chip(x.event)}: ${esc(ev(x.event)?.text || "")} (${x.conf.toFixed(1)})`).join("<br>");
        node("", `Belief ${chip(b.id)} · confidence ${b.conf}${b.opinion && b.opinion.d > 0 ? `, doubt ${b.opinion.d}` : ""}${b.status === "retracted" ? ' · <span class="badge offline">retracted</span>' : ""}`,
          `${esc(name(b.npc))} believes <b>${esc(b.claim)}</b>`, sub);
        for (const x of b.evidence) { const r = ev(x.event); if (r && r.claim) root(r); }
      } else if (e) {
        e.claim ? root(e) : node("", `Event ${chip(e.id)}`, esc(e.text), `in ${roomName(e.loc)}`);
      }
    }
    return `<div class="chain"><h3>Why-chain<button class="ghost" data-close-chain>Close</button></h3>${nodes.join("")}</div>`;
  }
}
