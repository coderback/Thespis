// The Thespis inspector: a read-only view of a runtime's sessions, through the /v1 API of the server that serves it.
// It calls only GET routes and the POSTs that change nothing (explain, trace). The token comes from the page's
// fragment (#token=...), which a browser never sends to a server, or from the form; it is kept in this tab only.
// Everything a game wrote (names, places, claims) is set as text, never parsed as HTML.
"use strict";

const API = new URL("../v1/", location.href).pathname;
const POLL_MS = 2000;
const LEDGER_SHOWN = 300;

const state = {
  token: new URLSearchParams(location.hash.slice(1)).get("token") || sessionStorageGet("thespis.token") || "",
  sid: new URLSearchParams(location.hash.slice(1)).get("session") || "",
  overview: null,
  npc: "",
  tab: "mind",
  events: [],
  verb: "",
  traced: null,
  timer: 0,
  busy: false,
};

function sessionStorageGet(k) { try { return sessionStorage.getItem(k); } catch { return null; } }
function sessionStorageSet(k, v) { try { sessionStorage.setItem(k, v); } catch { /* private window */ } }

const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of children.flat()) {
    if (c === undefined || c === null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function fill(el, ...children) { el.replaceChildren(...children.flat().filter((c) => c !== null && c !== undefined)); }

// What each panel last showed. A panel is drawn again only when what it shows has changed, so polling doesn't
// replace a button under the pointer, or close a list someone has open.
let drawn = {};
function changed(panel, ...what) {
  const now = JSON.stringify(what);
  if (drawn[panel] === now) return false;
  drawn[panel] = now;
  return true;
}

class ApiError extends Error {
  constructor(status, body) {
    super((body && (body.reason || body.error)) || `HTTP ${status}`);
    this.status = status;
  }
}

async function api(path, body) {
  const headers = { Accept: "application/json" };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const r = await fetch(API + path, {
    method: body === undefined ? "GET" : "POST", headers, cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, data);
  return data;
}

function status(text, bad) {
  const el = $("status");
  el.textContent = text;
  el.className = bad ? "bad" : "";
}

// ---------------------------------------------------------------- names and claims

function nameOf(id) {
  if (!id) return "";
  const o = state.overview;
  if (o) {
    for (const n of o.npcs) if (n.id === id) return n.name;
    for (const p of o.players) if (p.id === id) return p.name;
    if (o.places[id]) return o.places[id];
  }
  return id;
}

function claimText(c) {
  if (!c) return "";
  const args = [c.a, c.b].filter(Boolean).map(nameOf).join(", ");
  let s = `${c.neg ? "not " : ""}${c.pred}(${args})`;
  if (c.place) s += ` at ${nameOf(c.place)}`;
  if (c.at !== undefined && c.at !== null) s += ` in phase ${c.at}`;
  return s;
}

function sure(x) { return typeof x === "number" ? x.toFixed(2) : ""; }

function evidenceText(e) {
  const who = e.source === "self" || e.source === "witnessed" ? `saw it (${e.event})` : `${nameOf(e.source)} (${e.event})`;
  const origin = e.origin && e.origin.length ? `, first from ${e.origin.map(nameOf).join(" via ")}` : "";
  return `${e.against ? "against: " : ""}${who}, phase ${e.phase}, ${sure(e.conf)}${origin}`;
}

// ---------------------------------------------------------------- sessions and the cast

async function loadSessions() {
  const rows = await api("sessions");
  const select = $("session");
  if (!rows.some((r) => r.session === state.sid)) state.sid = rows.length ? rows[0].session : "";
  if (changed("sessions", rows.map((r) => [r.session, r.game]), state.sid)) {
    fill(select, rows.length ? rows.map((r) => h("option", { value: r.session }, `${r.game} · ${r.session}`)) :
      [h("option", { value: "" }, "no sessions yet")]);
    select.value = state.sid;
  }
}

async function loadOverview() {
  if (!state.sid) { state.overview = null; renderOverview(); return; }
  state.overview = await api(`sessions/${encodeURIComponent(state.sid)}`);
  if (!state.overview.npcs.some((n) => n.id === state.npc)) state.npc = "";
  if (changed("overview", state.overview, state.npc)) renderOverview();
}

function renderOverview() {
  const o = state.overview;
  $("game").textContent = o ? o.name : "No session";
  $("phase").textContent = o ? `${o.game} · phase ${o.phase} · ${o.events} events` : "";
  fill($("cast"), o ? o.npcs.map((n) => h("li", {},
    h("button", {
      type: "button", class: n.id === state.npc ? "picked" : "", "aria-pressed": n.id === state.npc ? "true" : "false",
      onclick: () => { state.npc = n.id; renderOverview(); showTab(state.tab === "why" ? "why" : "mind"); },
    },
    h("span", { class: "name" }, n.name, n.gone ? h("span", { class: "tag" }, "gone") : null),
    h("span", { class: "muted" }, `${n.id} · ${nameOf(n.loc) || "nowhere"} · ${n.beliefs} belief${n.beliefs === 1 ? "" : "s"}`
      + (n.retracted ? `, ${n.retracted} let go` : ""))))) : []);
  fill($("players"), o ? o.players.map((p) => h("li", {}, `${p.name} `, h("span", { class: "muted" },
    `${p.id} · ${nameOf(p.loc) || "nowhere"}`))) : []);
  fill($("ties"), o && o.ties.length ? o.ties.map((t) => h("li", {}, `${nameOf(t.between[0])} – ${nameOf(t.between[1])} `,
    h("span", { class: "muted" }, `${t.kind}${t.made === "play" ? ", made in play" : ""}`))) :
    [h("li", { class: "muted" }, "none")]);
  renderWhyPickers();
}

// ---------------------------------------------------------------- one mind

async function loadMind() {
  if (!state.npc) { $("mind").hidden = true; $("mind-empty").hidden = false; return; }
  const m = await api(`sessions/${encodeURIComponent(state.sid)}/npcs/${encodeURIComponent(state.npc)}`);
  if (!changed("mind", m, state.npc, $("retracted").checked, state.overview && state.overview.npcs.map((x) => x.name))) return;
  $("mind").hidden = false;
  $("mind-empty").hidden = true;
  $("mind-name").textContent = `${nameOf(state.npc)}${m.npc.gone ? " (gone)" : ""}`;
  const n = m.npc;
  const pairs = (o) => Object.entries(o || {}).map(([k, v]) => `${nameOf(k)} ${typeof v === "object" ? JSON.stringify(v) : v}`).join(", ") || "none";
  fill($("mind-state"),
    h("dt", {}, "At"), h("dd", {}, nameOf(n.loc) || "nowhere"),
    h("dt", {}, "Drives"), h("dd", {}, pairs(n.drives)),
    h("dt", {}, "Trusts"), h("dd", {}, pairs(n.trust_in)),
    h("dt", {}, "Flags"), h("dd", {}, pairs(n.flags)),
    n.kind ? [h("dt", {}, "Kind"), h("dd", {}, n.kind)] : null);
  const all = $("retracted").checked;
  const shown = m.beliefs.filter((b) => all || b.status === "active");
  fill($("beliefs"), shown.length ? shown.map((b) => h("tr", { class: b.status === "active" ? "" : "faded" },
    h("td", {}, claimText(b.claim)),
    h("td", { class: "num", title: `belief ${b.opinion.b}, disbelief ${b.opinion.d}, uncertainty ${b.opinion.u}` }, sure(b.opinion.b)),
    h("td", {}, b.status),
    h("td", {}, h("ul", { class: "plain" }, b.evidence.map((e) => h("li", {}, evidenceText(e))))),
    h("td", {}, h("button", { type: "button", onclick: () => { state.traced = b.claim; showTab("trace"); } }, "Trace")))) :
    [h("tr", {}, h("td", { colspan: 5, class: "muted" }, "Believes nothing yet."))]);
}

// ---------------------------------------------------------------- why

function renderWhyPickers() {
  const o = state.overview;
  const npcs = o ? o.npcs.filter((n) => n.moments.length) : [];
  const npcSel = $("why-npc");
  const keep = state.npc && npcs.some((n) => n.id === state.npc) ? state.npc : npcSel.value;
  fill(npcSel, npcs.length ? npcs.map((n) => h("option", { value: n.id }, n.name)) :
    [h("option", { value: "" }, "nobody has choices")]);
  if (npcs.some((n) => n.id === keep)) npcSel.value = keep;
  renderMoments();
}

function renderMoments() {
  const o = state.overview;
  const n = o && o.npcs.find((x) => x.id === $("why-npc").value);
  const sel = $("why-moment");
  const keep = sel.value;
  fill(sel, (n ? n.moments : []).map((m) => h("option", { value: m }, m)));
  if (n && n.moments.includes(keep)) sel.value = keep;
}

function bindings(text) {
  const out = {};
  for (const part of text.split(",")) {
    const [k, ...rest] = part.split("=");
    if (!k.trim()) continue;
    const v = rest.join("=").trim();
    out[k.trim()] = v === "true" ? true : v === "false" ? false : v !== "" && !isNaN(Number(v)) ? Number(v) : v;
  }
  return out;
}

async function loadWhy() {
  const npc = $("why-npc").value, moment = $("why-moment").value;
  if (!npc || !moment) { fill($("why")); return; }
  const rows = await api(`sessions/${encodeURIComponent(state.sid)}/explain`,
    { npc, moment, bindings: bindings($("why-bindings").value) });
  if (!changed("why", rows, npc, moment)) return;
  fill($("why"), rows.map((c) => h("tr", { class: c.chosen ? "chosen" : c.open ? "" : "faded" },
    h("td", {}, c.chosen ? "▶" : ""),
    h("td", {}, c.do),
    h("td", {}, c.open ? "yes" : "no"),
    h("td", {}, c.blocked || ""),
    h("td", { class: "num" }, String(c.utility)),
    h("td", {}, c.terms.join("; ")))));
}

// ---------------------------------------------------------------- ledger

async function loadLedger(fresh) {
  const verb = state.verb ? `&verb=${encodeURIComponent(state.verb)}` : "";
  if (fresh) state.events = [];
  const last = state.events.length ? state.events[state.events.length - 1].id : "";
  const rows = await api(`sessions/${encodeURIComponent(state.sid)}/events?${last ? `after=${encodeURIComponent(last)}` : ""}${verb}`);
  state.events = state.events.concat(rows).slice(-5000);
  if (!fresh && !rows.length) return;
  const shown = state.events.slice(-LEDGER_SHOWN).reverse();
  $("ledger-count").textContent = `${state.events.length} events${state.verb ? ` of ${state.verb}` : ""}, newest first`
    + (state.events.length > LEDGER_SHOWN ? `; the latest ${LEDGER_SHOWN} shown` : "");
  fill($("ledger"), shown.map((e) => h("tr", { class: e.verb === "caught" ? "caught" : "" },
    h("td", {}, e.id),
    h("td", { class: "num" }, String(e.phase)),
    h("td", {}, nameOf(e.actor)),
    h("td", {}, e.verb + (e.amount !== null && e.amount !== undefined ? ` ${e.amount}` : "")),
    h("td", {}, nameOf(e.target)),
    h("td", {}, nameOf(e.loc)),
    h("td", {}, claimText(e.claim)),
    h("td", {}, e.truth ? "yes" : "no"))));
}

// ---------------------------------------------------------------- trace

async function loadTrace() {
  if (!state.traced) { $("trace").hidden = true; $("trace-empty").hidden = false; return; }
  const t = await api(`sessions/${encodeURIComponent(state.sid)}/trace`, state.traced);
  if (!changed("trace", t, state.traced)) return;
  $("trace").hidden = false;
  $("trace-empty").hidden = true;
  $("trace-claim").textContent = claimText(state.traced);
  fill($("holders"), t.holders.length ? t.holders.map((x) => h("tr", { class: x.status === "active" ? "" : "faded" },
    h("td", {}, nameOf(x.npc)), h("td", { class: "num" }, sure(x.conf)), h("td", {}, x.status),
    h("td", {}, h("ul", { class: "plain" }, (x.from || []).map((e) => h("li", {}, evidenceText(e))))))) :
    [h("tr", {}, h("td", { colspan: 4, class: "muted" }, "Nobody."))]);
  fill($("next"), t.next.length ? t.next.map((x) => h("tr", {},
    h("td", {}, nameOf(x.teller)), h("td", {}, nameOf(x.listener)), h("td", { class: "num" }, sure(x.conf)),
    h("td", {}, x.how || ""))) : [h("tr", {}, h("td", { colspan: 4, class: "muted" }, "Nothing: it goes no further next tick."))]);
  fill($("stopped"), t.stopped.length ? t.stopped.map((x) => h("tr", {},
    h("td", {}, nameOf(x.npc) + (x.listener ? ` → ${nameOf(x.listener)}` : "")), h("td", {}, x.why))) :
    [h("tr", {}, h("td", { colspan: 2, class: "muted" }, "Nowhere."))]);
}

// ---------------------------------------------------------------- tabs and refreshing

function showTab(tab) {
  state.tab = tab;
  drawn = { sessions: drawn.sessions, overview: drawn.overview };
  for (const b of document.querySelectorAll("[role=tab]")) b.setAttribute("aria-selected", String(b.dataset.tab === tab));
  for (const p of document.querySelectorAll("[role=tabpanel]")) p.hidden = p.id !== `tab-${tab}`;
  refreshTab();
}

async function refreshTab(fresh) {
  if (!state.sid) return;
  try {
    if (state.tab === "mind") await loadMind();
    else if (state.tab === "why") await loadWhy();
    else if (state.tab === "ledger") await loadLedger(fresh);
    else if (state.tab === "trace") await loadTrace();
  } catch (e) { failed(e); }
}

function failed(e) {
  if (e instanceof ApiError && e.status === 401) {
    $("login").hidden = false;
    $("main").hidden = true;
    status("wants a token", true);
    stop();
  } else {
    status(e.message || String(e), true);
  }
}

async function refresh(fresh) {
  if (state.busy) return;
  state.busy = true;
  if (fresh) drawn = {};
  try {
    await loadSessions();
    await loadOverview();
    $("login").hidden = true;
    $("main").hidden = false;
    await refreshTab(fresh);
    if (!$("status").classList.contains("bad")) status(`updated ${new Date().toLocaleTimeString()}`);
  } catch (e) {
    failed(e);
  } finally {
    state.busy = false;
  }
}

function stop() { clearInterval(state.timer); state.timer = 0; }

function start() {
  stop();
  if ($("live").checked) state.timer = setInterval(() => { status(""); refresh(false); }, POLL_MS);
}

document.addEventListener("DOMContentLoaded", () => {
  for (const b of document.querySelectorAll("[role=tab]")) b.addEventListener("click", () => showTab(b.dataset.tab));
  $("session").addEventListener("change", (ev) => {
    state.sid = ev.target.value; state.npc = ""; state.traced = null; state.events = [];
    refresh(true);
  });
  $("refresh").addEventListener("click", () => { status(""); refresh(true); });
  $("live").addEventListener("change", start);
  $("retracted").addEventListener("change", () => refreshTab());
  $("why-npc").addEventListener("change", () => { renderMoments(); refreshTab(); });
  $("why-moment").addEventListener("change", () => refreshTab());
  $("why-form").addEventListener("submit", (ev) => { ev.preventDefault(); status(""); refreshTab(); });
  $("ledger-form").addEventListener("submit", (ev) => {
    ev.preventDefault(); state.verb = $("ledger-verb").value.trim(); status(""); refreshTab(true);
  });
  $("login").addEventListener("submit", (ev) => {
    ev.preventDefault();
    state.token = $("token").value.trim();
    sessionStorageSet("thespis.token", state.token);
    status("");
    refresh(true).then(start);
  });
  if (state.token) sessionStorageSet("thespis.token", state.token);
  refresh(true).then(start);
});
