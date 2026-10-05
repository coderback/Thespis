// The manor mystery's pure helpers: names and rooms, what the player has seen, the bursts one act sets off, the case
// notes and what the house remembers. No DOM here, so test/manor.test.js can run them under node.

export const CAST = ["vane", "pell", "sable"];
export const ROOMS = ["study", "hall", "kitchen"]; // left to right on the map
export const START_ROOM = "hall";
export const ARRIVAL = 2; // the player arrives at noon; earlier events happened before they came
const NAMES = { vane: "Lady Vane", pell: "Pell", sable: "Sable" };
const ROOM_NAMES = { study: "the study", hall: "the hall", kitchen: "the kitchen" };
const TOPICS = { morning: "this morning", ring: "the ring" };

export function name(id, { lower = false } = {}) {
  if (id === "player") return lower ? "you" : "You";
  return NAMES[id] || id;
}

export function roomName(id, { cap = false } = {}) {
  const n = ROOM_NAMES[id] || id;
  return cap ? n[0].toUpperCase() + n.slice(1) : n;
}

export const topicName = (id) => TOPICS[id] || id;

/** Rooms the player has stood in: where they arrived, and everywhere they have walked since. */
export function visitedRooms(state) {
  const seen = new Set([START_ROOM]);
  for (const e of state.ledger || []) if (e.verb === "move" && e.actor === "player") seen.add(e.target);
  return seen;
}

/** The icons an NPC wears right now: Sable sweats once she is frightened enough to lie. */
export function moodIcons(npc) {
  return (npc.drives?.fear ?? 0) >= 3 ? ["sweat"] : [];
}

/** What one act sets off on the map: a stamp over anyone whose statement the ledger logged false, an arc for each
 *  testimony, and a "!" over anyone who dropped a belief. */
export function bursts(prev, next, events) {
  const out = [];
  for (const e of events) {
    if ((e.verb === "tell" || e.verb === "testify") && e.claim && !e.truth) out.push({ npc: e.actor, kind: "lie" });
    if (e.verb === "testify") out.push({ npc: e.actor, kind: "testify", to: e.target });
  }
  const before = new Map((prev?.beliefs || []).map((b) => [b.id, b.status]));
  for (const b of next.beliefs) {
    if (b.status === "retracted" && before.get(b.id) === "active") out.push({ npc: b.npc, kind: "retract" });
  }
  return out;
}

/** One act's events as a case note, in the server's words; a statement the ledger marks false is flagged. */
export function caseNote(events, clock) {
  const items = events.map((e) => ({ id: e.id, text: e.text, lie: Boolean(e.claim) && !e.truth }));
  return items.length ? { when: clock, items } : null;
}

/** The lines Lady Vane and Sable spoke, rebuilt from a state, for a reload. */
export function spokenLines(state) {
  return state.decisions.filter((d) => d.line).map((d) => ({ decision: d.id, npc: d.npc, line: d.line, source: d.source }));
}

/** Did this decision state something the ledger says is false? */
export function isLie(state, d) {
  const e = d.asserted && state.ledger.find((x) => x.id === d.asserted);
  return Boolean(e) && !e.truth;
}

/** What the house remembers, for the end card. */
export function memory(state) {
  const npc = (id) => state.npcs.find((n) => n.id === id);
  const out = state.beliefs.filter((b) => b.npc === "vane").map((b) =>
    `Lady Vane ${b.status === "retracted" ? "no longer believes" : "believes"} ${b.claim}${b.truth ? "" : " (a lie)"}`);
  const vane = npc("vane");
  if (vane) out.push(`Lady Vane's trust in Sable: ${fmtTrust(vane.trust_in.sable)}, in Pell: ${fmtTrust(vane.trust_in.pell)}`);
  const sable = npc("sable");
  if (sable) out.push(`Sable's fear: ${sable.drives.fear ?? 0} / 10`);
  const lies = state.ledger.filter((e) => e.claim && !e.truth).length;
  out.push(`${lies} ${lies === 1 ? "lie" : "lies"} told, every one in the ledger`);
  return out;
}

export const fmtTrust = (t) => (t > 0 ? `+${t}` : String(t));

/** The player's own line in the log. */
export function actionText(body) {
  switch (body.verb) {
    case "ask": return `You ask ${name(body.target)} about ${topicName(body.topic)}.`;
    case "move": return `You walk to ${roomName(body.target)}.`;
    case "request_questioning": return `You ask Lady Vane to question ${name(body.target)}.`;
    case "accuse": return `You accuse ${name(body.target)} before Lady Vane.`;
    default: return `You ${body.verb.replace("_", " ")}.`;
  }
}
