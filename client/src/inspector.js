// The inspector: Minds, Beliefs, Ledger and Why tabs, and the why-chain from a line down to the ledger.

import { $, esc, badge } from "./dom.js";
import { CAST, STOP_SHORT, ACTION_LINE, name, claimText, eventText, whyChain, isFrozen, fmtTrust, heardText } from "./model.js";

const DRIVES = [["grudge", "#e0574a"], ["fear", "#7fc3ec"], ["respect", "#f6c25a"], ["ambition", "#c98ad8"]];

export class Inspector {
  constructor() {
    this.tab = "minds";
    this.state = null;
    this.prev = null;
    this.chainId = null; // the decision whose why-chain is open
    this.highlight = null; // an id to outline in the ledger or beliefs
    this.editing = null; // the NPC whose persona is being edited (#39)
    this.onPersona = null; // set by the game: (npc, text) => save it; "" goes back to the default
    this.words = []; // what you typed this session and how each was read (POST /say), newest last
    for (const b of document.querySelectorAll("#tabs button")) {
      b.addEventListener("click", () => { this.highlight = null; this.show(b.dataset.tab); });
    }
    $("panel").addEventListener("click", (e) => {
      if (e.target.closest("[data-close-chain]")) { this.chainId = null; return this.render(); }
      const edit = e.target.closest("[data-edit-persona]");
      if (edit) { this.editing = edit.dataset.editPersona; return this.render(); }
      if (e.target.closest("[data-cancel-persona]")) { this.editing = null; return this.render(); }
      const save = e.target.closest("[data-save-persona], [data-reset-persona]");
      if (save) {
        const npc = save.dataset.savePersona || save.dataset.resetPersona;
        const text = save.dataset.savePersona ? $("persona-text").value : "";
        this.editing = null;
        return this.onPersona?.(npc, text);
      }
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
      ledger: (this.state.ledger_tail?.length || 0) !== (this.prev.ledger_tail?.length || 0),
      why: (this.state.decisions_tail?.length || 0) !== (this.prev.decisions_tail?.length || 0),
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

  /** Something you typed, and how the engine read it: shown at the top of the Why tab. */
  heard(entry) {
    this.words = [...this.words, entry].slice(-6);
    if (this.tab !== "why") document.querySelector('#tabs [data-tab="why"]').classList.add("flash");
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
    const s = this.state;
    return CAST.map((id) => {
      const n = s.npcs.find((x) => x.id === id);
      if (!n) return "";
      const drives = DRIVES.filter(([k]) => n.drives[k] !== undefined).map(([k, col]) => `
        <div class="drive"><span>${k}</span><div class="meter"><i style="width:${(n.drives[k] / 10) * 100}%;background:${col}"></i></div><b>${n.drives[k]}</b></div>`).join("");
      const trust = Object.entries(n.trust_in || {}).map(([who, t]) => {
        const w = (Math.abs(t) / 5) * 50;
        const left = t >= 0 ? 50 : 50 - w;
        return `<div class="drive"><span>trust ${esc(name(who, { lower: true }))}</span><div class="meter trust"><i style="left:${left}%;width:${w}%;background:${t >= 0 ? "var(--good)" : "var(--bad)"}"></i></div><b>${fmtTrust(t)}</b></div>`;
      }).join("");
      const frozen = isFrozen(s, n) ? `<div class="frozen">Detained until the end of phase ${n.frozen_until}</div>` : "";
      return `<div class="npc"><h4><span class="who ${id}">${name(id)}</span><span class="where">at ${STOP_SHORT[n.loc]}</span></h4>${drives}${trust}${frozen}${this.persona(id, n)}</div>`;
    }).join("");
  }

  // Live persona editing (#39): the model voices this NPC with the edited persona from its next line.
  persona(id, n) {
    if (!n.persona) return "";
    if (this.editing === id) {
      return `<div class="persona edit"><textarea id="persona-text" maxlength="300" aria-label="${esc(name(id))}'s persona">${esc(n.persona)}</textarea>
        <div class="row"><button data-save-persona="${id}">Save</button><button data-reset-persona="${id}">Default</button><button data-cancel-persona>Cancel</button></div></div>`;
    }
    const edited = n.persona_edited ? '<span class="edited">edited</span>' : "";
    return `<div class="persona"><q>${esc(n.persona)}</q> <button class="persona-edit" data-edit-persona="${id}" title="Change the persona the model voices">edit</button>${edited}</div>`;
  }

  beliefs() {
    const s = this.state;
    const old = new Set((this.prev?.beliefs || []).map((b) => b.id));
    const groups = CAST.map((id) => {
      const list = s.beliefs.filter((b) => b.npc === id);
      if (!list.length) return "";
      return `<div class="group"><h5><span class="who ${id}">${name(id)}</span> believes</h5>${list.map((b) => this.beliefRow(b, this.prev && !old.has(b.id))).join("")}</div>`;
    }).join("");
    return groups || '<div class="empty">No one believes anything yet. Give them something to talk about.</div>';
  }

  beliefRow(b, isNew) {
    const mark = b.status !== "retracted" && b.conf < ACTION_LINE ? ["q", "?", "Below the 0.5 action line: stored, never acted on"]
      : b.truth ? ["t", "✓", "True: the ledger shows it happened"] : ["f", "✗", "False: the ledger shows it never happened"];
    const how = (ev) => ev.source === "witnessed" ? "saw it" : ev.source === "self" ? "it happened to them" : "from " + esc(name(ev.source));
    const src = (b.evidence || []).map((ev) => `<span class="chip${ev.against ? " against" : ""}">${ev.against ? "against, " : ""}${how(ev)} · ${ev.conf.toFixed(1)}</span><span class="chip id" data-id="${esc(ev.event)}">${esc(ev.event)}</span>`).join(" ");
    const cls = ["belief", b.status === "retracted" ? "retracted" : "", isNew ? "new" : "", this.highlight === b.id ? "ev hl" : ""].join(" ");
    return `<div class="${cls}" data-b="${esc(b.id)}">
      <span class="mark ${mark[0]}" title="${mark[2]}">${mark[1]}</span>
      <span class="claim">${esc(claimText(b.claim))}${b.status === "retracted" ? ' <span class="badge offline">retracted</span>' : ""}</span>
      <div class="meter" title="confidence ${b.conf}${b.opinion && b.opinion.d > 0 ? `, doubt ${b.opinion.d}` : ""}"><i style="width:${b.conf * 100}%;background:${b.conf >= ACTION_LINE ? "var(--accent)" : "var(--muted)"}"></i>${b.opinion && b.opinion.d > 0 ? `<i class="dis" style="width:${b.opinion.d * 100}%"></i>` : ""}</div>
      <div class="src"><span class="chip id" data-id="${esc(b.id)}">${esc(b.id)}</span> ${src}</div>
    </div>`;
  }

  ledger() {
    const s = this.state;
    const old = new Set((this.prev?.ledger_tail || []).map((e) => e.id));
    let lastPhase = -1;
    const rows = (s.ledger_tail || []).map((e) => {
      const head = e.phase !== lastPhase ? `<div class="phase-h">Day ${Math.floor(e.phase / 4) + 1} · ${["morning", "noon", "evening", "night"][e.phase % 4]} (phase ${e.phase})</div>` : "";
      lastPhase = e.phase;
      const truth = e.claim ? (e.truth ? '<span class="mark t" title="The claim is true">✓</span>' : '<span class="mark f" title="The claim is false">✗</span>') : "<span></span>";
      const cls = ["ev", this.prev && !old.has(e.id) ? "new" : "", this.highlight === e.id ? "hl" : ""].join(" ");
      return `${head}<div class="${cls}" data-ev="${esc(e.id)}"><span class="id">${esc(e.id)}</span><span>${esc(eventText(e))}</span>${truth}</div>`;
    }).join("");
    return rows || '<div class="empty">The ledger is empty. Nothing has happened yet.</div>';
  }

  why() {
    const s = this.state;
    const chain = this.chainId ? this.chainHtml(this.chainId) : "";
    const cards = [...(s.decisions_tail || [])].reverse().map((d) => `
      <div class="dcard" data-decision="${esc(d.id)}">
        <div class="head"><span class="who ${d.npc}">${name(d.npc)}</span><span>${esc(d.id)} · phase ${d.phase} · ${esc(d.trigger)}</span>${badge(d.source)}</div>
        ${d.kind === "decide" ? `<div>${(d.allowed || []).map((a) => `<span class="chip ${a === d.chosen ? "chosen" : ""}">${esc(a)}</span>`).join("")}</div>` : ""}
        ${d.line ? `<div class="line">"${esc(d.line)}"</div>` : '<div class="meta">(no line)</div>'}
        <div class="meta">cites ${(d.cites || []).map((c) => `<span class="chip id" data-id="${esc(c)}">${esc(c)}</span>`).join("") || "nothing"} · ${esc(d.reason || "")}</div>
      </div>`).join("");
    const intro = chain ? "" : '<div class="empty">Click any spoken line, here or in the dialogue log, to trace it to the ledger.</div>';
    const words = [...this.words].reverse().map((h) => {
      const r = heardText(h.understood);
      return `<div class="dcard heard">
        <div class="head"><span class="who player">You</span><span>to ${esc(name(h.target))} · your words</span><span class="badge ${r.verdict}">${r.verdict}</span></div>
        <div class="line">"${esc(h.text)}"</div>
        <div class="meta"><b>${esc(r.what)}</b><br>${esc(r.how)}</div>
      </div>`;
    }).join("");
    return `${chain}${intro}${words}${cards}`;
  }

  chainHtml(id) {
    const c = whyChain(this.state, id);
    if (!c) return "";
    const d = c.decision;
    const nodes = [];
    const chip = (x) => `<span class="chip id" data-id="${esc(x)}">${esc(x)}</span>`;
    const node = (cls, k, body, sub = "") => nodes.push(
      `<div class="node ${cls}" style="animation-delay:${nodes.length * 0.15}s"><div class="k">${k}</div><div class="body">${body}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`);
    const how = (e) => e.source === "witnessed" ? "saw it" : e.source === "self" ? "it happened to them" : "told by " + esc(name(e.source));

    node("line", `<span class="who ${d.npc}">${name(d.npc)}</span> said ${badge(d.source)}`, `"${esc(d.line || "(no line)")}"`);
    node("", `Decision ${chip(d.id)} · ${d.kind}`,
      d.kind === "decide"
        ? `Chose <span class="chip chosen">${esc(d.chosen)}</span> from ${(d.allowed || []).map((a) => `<span class="chip">${esc(a)}</span>`).join("")}`
        : `Reacted to <b>${esc(d.trigger)}</b>`,
      `Reason: ${esc(d.reason || "-")} · phase ${d.phase}`);
    for (const l of c.links) {
      if (l.kind === "belief") {
        const b = l.belief;
        const ev = l.evidence.map((e) => `${how(e)} in ${chip(e.event.id)}${e.event.verb ? ": " + esc(eventText(e.event)) : ""} (${e.conf.toFixed(1)})`).join("<br>");
        node("", `Belief ${chip(b.id)} · confidence ${b.conf}${b.opinion && b.opinion.d > 0 ? `, doubt ${b.opinion.d}` : ""}${b.status === "retracted" ? ' · <span class="badge offline">retracted</span>' : ""}`,
          `${esc(name(b.npc))} believes <b>${esc(claimText(b.claim, { lower: true }))}</b>`, ev);
      } else if (l.kind === "event") {
        node("", `Event ${chip(l.id)} · phase ${l.event.phase}`, esc(eventText(l.event)), `at ${STOP_SHORT[l.event.loc] || esc(l.event.loc)}`);
      } else {
        node("", `Cited ${esc(l.id)}`, '<span class="muted">Not in the current snapshot</span>');
      }
    }
    for (const r of c.roots) {
      const t = r.truth ? "t" : "f";
      node(`root ${t}`, `Ledger root ${chip(r.event.id)} · phase ${r.event.phase}<span class="verdict ${t}">${r.truth ? "✓ TRUE" : "✗ FALSE"}</span>`,
        esc(eventText(r.event)),
        r.truth ? "This really happened. The ledger is the ground truth." : "Nothing in the ledger backs this claim: it was a lie.");
    }
    return `<div class="chain"><h3>Why-chain<button class="ghost" data-close-chain>Close</button></h3>${nodes.join("")}</div>`;
  }
}
