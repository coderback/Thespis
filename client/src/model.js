// Pure helpers over the engine's state: names, text, fog and the why-chain. No DOM, so node --test covers them.

export const STOPS = ["tavern", "market", "guard_post", "bridge", "crypt"];
export const STOP_NAMES = {
  tavern: "The Lantern & Last Coin",
  market: "Market",
  guard_post: "Guard Post",
  bridge: "Bridge",
  crypt: "Crypt",
};
export const STOP_SHORT = { tavern: "the tavern", market: "the market", guard_post: "the guard post", bridge: "the bridge", crypt: "the crypt" };
export const STOP_TILE_X = { tavern: 2, market: 5, guard_post: 9, bridge: 12, crypt: 15 };
export const PHASE_NAMES = ["Morning", "Noon", "Evening", "Night"];
export const NAMES = { player: "You", kael: "Kael", brenna: "Brenna", mags: "Mags", odo: "Odo" };
export const CAST = ["kael", "brenna", "odo", "mags"];
export const REPORT_VERBS = new Set(["accuse", "gossip", "testify", "tell_claim"]);
export const ACTION_LINE = 0.5; // beliefs under this are stored and shown but never acted on

export function name(id, { lower = false } = {}) {
  if (id === "player") return lower ? "you" : "You";
  return NAMES[id] || id;
}

export function clock(state) {
  const p = state.phase;
  return `Day ${Math.floor(p / 4) + 1} · ${PHASE_NAMES[p % 4]}`;
}

const CLAIM_VERBS = { robbed: "robbed", beat: "beat", insulted: "insulted", spared: "spared", lied: "lied about" };

export function claimText(claim, { lower = false } = {}) {
  if (!claim) return "";
  const a = name(claim.a, { lower });
  const b = claim.b === "player" ? "you" : name(claim.b);
  return `${a} ${CLAIM_VERBS[claim.pred] || claim.pred} ${b}`;
}

export function claimKey(c) {
  return c ? `${c.pred}(${c.a},${c.b})` : "";
}

export function eventText(e) {
  const who = name(e.actor);
  const whom = e.target ? name(e.target, { lower: true }) : "";
  const c = e.claim ? claimText(e.claim, { lower: true }) : "";
  switch (e.verb) {
    case "move": return `${who} walked from ${STOP_SHORT[e.loc]} to ${STOP_SHORT[e.target]}`;
    case "insult": return `${who} insulted ${whom}`;
    case "challenge": return `${who} challenged ${whom} to a duel`;
    case "beat": return `${who} beat ${whom} in a duel`;
    case "humiliate": return `${who} humiliated ${whom} and took his purse`;
    case "spare": return `${who} spared ${whom}`;
    case "tell_claim": return `${who} told ${whom}: "${c}"`;
    case "bribe": return `${who} paid ${whom} a fine`;
    case "block": return `${who} blocked ${whom} at the gate`;
    case "accuse": return `${who} told ${whom}: "${c}"`;
    case "detain": return `${who} detained ${whom}`;
    case "release": return `${who} released ${whom}`;
    case "gossip": return `${who} gossiped to ${whom}: "${c}"`;
    case "testify": return `${who} testified to ${whom}: not "${c}"`;
    case "take_relic": return `${who} took the relic`;
    default: return `${who} ${e.verb}${whom ? " " + whom : ""}`;
  }
}

/** NPCs on the map: visible ones at their stop, the rest as last-seen ghosts (or not at all if never seen). */
export function mapFigures(state) {
  const out = [];
  for (const n of state.npcs) {
    if (n.loc === state.player.loc) out.push({ id: n.id, loc: n.loc, ghost: false });
    else if (n.last_seen) out.push({ id: n.id, loc: n.last_seen.loc, ghost: true, phase: n.last_seen.phase });
  }
  return out;
}

export function npc(state, id) {
  return state.npcs.find((n) => n.id === id);
}

export function isFrozen(state, n) {
  return n.frozen_until != null && n.frozen_until >= state.phase;
}

/** Icons above a head, from drive numbers and status. */
export function moodIcons(state, n) {
  const d = n.drives || {};
  const icons = [];
  if ((d.grudge ?? 0) >= 5) icons.push("angry");
  if ((d.fear ?? 0) >= 4) icons.push("sweat");
  if ((d.respect ?? 0) >= 4) icons.push("star");
  if (isFrozen(state, n)) icons.push("chains");
  return icons;
}

/** Changes between two snapshots that deserve a burst: a new belief, or learning of a lie. */
export function beliefBursts(prev, next) {
  const before = new Map((prev?.beliefs || []).map((b) => [b.id, b]));
  const bursts = [];
  for (const b of next.beliefs) {
    const old = before.get(b.id);
    const liedTo = b.claim.pred === "lied" && b.claim.b === b.npc;
    if (!old && liedTo) bursts.push({ npc: b.npc, kind: "liedto" });
    else if (old && old.status !== "retracted" && b.status === "retracted") bursts.push({ npc: b.npc, kind: "liedto" });
    else if (!old) bursts.push({ npc: b.npc, kind: "belief" });
  }
  const seen = new Map(); // one burst per NPC; learning of a lie wins
  for (const b of bursts) if (!seen.has(b.npc) || b.kind === "liedto") seen.set(b.npc, b);
  return [...seen.values()];
}

/**
 * The event a claim rests on. Every event carries the truth of its claim, so a true claim rests on the world
 * event that made it true (not a report of it), and a false one on the first time it was said: the lie.
 */
export function rootEvent(ledger, claim) {
  const key = claimKey(claim);
  const same = ledger.filter((e) => e.claim && claimKey(e.claim) === key);
  return same.find((e) => e.truth && !REPORT_VERBS.has(e.verb)) || same[0] || null;
}

/**
 * The why-chain for a decision: line -> decision -> cited beliefs (with their evidence events)
 * and cited events -> the ledger event at the root, marked true or false.
 */
export function whyChain(state, decisionId) {
  const d = (state.decisions_tail || []).find((x) => x.id === decisionId);
  if (!d) return null;
  const ledger = state.ledger_tail || [];
  const byEvent = new Map(ledger.map((e) => [e.id, e]));
  const byBelief = new Map((state.beliefs || []).map((b) => [b.id, b]));
  const links = [];
  const roots = new Map();
  const addRoot = (claim, fallback) => {
    const r = claim ? rootEvent(ledger, claim) : fallback;
    if (r) roots.set(r.id, { event: r, truth: r.truth !== false });
  };
  for (const id of d.cites || []) {
    if (byBelief.has(id)) {
      const b = byBelief.get(id);
      const evidence = (b.evidence || []).map((ev) => ({ ...ev, event: byEvent.get(ev.event) || { id: ev.event } }));
      links.push({ kind: "belief", id, belief: b, evidence });
      addRoot(b.claim);
    } else if (byEvent.has(id)) {
      const e = byEvent.get(id);
      links.push({ kind: "event", id, event: e });
      addRoot(e.claim, e);
    } else {
      links.push({ kind: "missing", id });
    }
  }
  return { decision: d, links, roots: [...roots.values()] };
}

/** Order replies: lines reacting to the verb come before the moves, greetings in the new phase after. */
export function splitReplies(replies, nextState, prevPhase) {
  const decisions = new Map((nextState.decisions_tail || []).map((d) => [d.id, d]));
  const before = [], after = [];
  for (const r of replies || []) {
    const d = decisions.get(r.decision);
    (d && d.phase > prevPhase ? after : before).push(r);
  }
  return { before, after };
}

/** What the world remembers, for the end card. */
export function worldMemory(state) {
  const kael = npc(state, "kael"), brenna = npc(state, "brenna");
  const lines = [];
  if (kael) lines.push(`Kael's grudge against you: ${kael.drives.grudge ?? 0} / 10`);
  if (brenna) lines.push(`Brenna's trust in you: ${fmtTrust(brenna.trust_in.player ?? 0)}`);
  // Most telling first: exposed lies, then false beliefs still held, then the worst news.
  const weight = { robbed: 4, lied: 4, spared: 3, beat: 2, insulted: 1 };
  const score = (b) => (b.status === "retracted" ? 100 : 0) + (b.truth ? 0 : 50) + (weight[b.claim.pred] || 0) + (b.npc === "brenna" ? 5 : 0);
  const strong = state.beliefs.filter((b) => b.conf >= ACTION_LINE && b.claim.a !== b.npc).sort((a, b) => score(b) - score(a));
  for (const b of strong.slice(0, 5)) {
    const verb = b.status === "retracted" ? "no longer believes" : "believes";
    lines.push(`${name(b.npc)} ${verb} ${claimText(b.claim, { lower: true })}${b.truth ? "" : " (a lie)"}`);
  }
  return lines;
}

export function fmtTrust(t) {
  return t > 0 ? `+${t}` : `${t}`;
}
