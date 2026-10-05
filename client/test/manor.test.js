// The manor client's pure helpers, on state shaped like GET /manor/state (games/manor/views.py).

import { test } from "node:test";
import assert from "node:assert/strict";
import { actionText, bursts, caseNote, isLie, memory, moodIcons, spokenLines, visitedRooms } from "../src/manor/model.js";
import { SPRITES } from "../src/manor/sprites.js";
import { STEPS } from "../src/manor/autoplay.js";

const event = (id, verb, actor, target, extra = {}) => ({ id, phase: 2, verb, actor, target, loc: "hall", text: `${actor} ${verb}`, claim: null, truth: true, ...extra });
const ALIBI = "Sable was in the kitchen at mid-morning";

function noon() {
  return {
    phase: 2, clock: "Noon", status: "playing", player: { loc: "hall", asked: [] },
    npcs: [{ id: "vane", loc: "hall", drives: {}, trust_in: { pell: 3, sable: 2, player: 0 } },
      { id: "pell", loc: "study", drives: {}, trust_in: {} }, { id: "sable", loc: "kitchen", drives: { fear: 1 }, trust_in: {} }],
    beliefs: [{ id: "b0004", npc: "vane", claim: ALIBI, conf: 0.9, status: "active", truth: false, evidence: [] }],
    ledger: [event("e0003", "tell", "sable", "vane", { phase: 1, claim: ALIBI, truth: false })],
    decisions: [],
  };
}

test("rooms you have stood in", () => {
  const s = noon();
  assert.deepEqual([...visitedRooms(s)], ["hall"]);
  s.ledger.push(event("e0005", "move", "player", "kitchen"), event("e0007", "move", "player", "study"));
  assert.deepEqual([...visitedRooms(s)].sort(), ["hall", "kitchen", "study"]);
});

test("Sable sweats once she is frightened enough to lie", () => {
  assert.deepEqual(moodIcons({ drives: { fear: 1 } }), []);
  assert.deepEqual(moodIcons({ drives: { fear: 3 } }), ["sweat"]);
  assert.deepEqual(moodIcons({ drives: {} }), []);
});

test("bursts: a lie logged false, a testimony, and a belief dropped", () => {
  const prev = noon();
  const next = noon();
  next.beliefs[0] = { ...next.beliefs[0], status: "retracted" };
  const events = [
    event("e0006", "tell", "sable", "player", { claim: ALIBI, truth: false }),
    event("e0011", "testify", "pell", "vane", { claim: "Sable was in the study at mid-morning", truth: true }),
  ];
  assert.deepEqual(bursts(prev, next, events), [
    { npc: "sable", kind: "lie" }, { npc: "pell", kind: "testify", to: "vane" }, { npc: "vane", kind: "retract" },
  ]);
  assert.deepEqual(bursts(prev, prev, [event("e0005", "move", "player", "kitchen")]), []);
});

test("case notes flag what the ledger logged false", () => {
  const note = caseNote([event("e0005", "move", "player", "kitchen"), event("e0006", "tell", "sable", "player", { claim: ALIBI, truth: false })], "Early afternoon");
  assert.equal(note.when, "Early afternoon");
  assert.deepEqual(note.items.map((i) => i.lie), [false, true]);
  assert.equal(caseNote([], "Noon"), null); // asking alone writes nothing to the ledger
});

test("lies, spoken lines and what the house remembers", () => {
  const s = noon();
  s.ledger.push(event("e0006", "tell", "sable", "player", { claim: ALIBI, truth: false }));
  s.decisions.push({ id: "d0001", npc: "sable", line: "The kitchen, sir.", source: "llm", asserted: "e0006" },
    { id: "d0002", npc: "vane", line: null, source: "fallback" });
  assert.equal(isLie(s, s.decisions[0]), true);
  assert.equal(isLie(s, s.decisions[1]), false);
  assert.deepEqual(spokenLines(s), [{ decision: "d0001", npc: "sable", line: "The kitchen, sir.", source: "llm" }]);
  const m = memory(s);
  assert.ok(m[0].startsWith("Lady Vane believes Sable was in the kitchen") && m[0].endsWith("(a lie)"));
  assert.ok(m.includes("2 lies told, every one in the ledger"));
});

test("the player's own lines", () => {
  assert.equal(actionText({ verb: "ask", target: "sable", topic: "morning" }), "You ask Sable about this morning.");
  assert.equal(actionText({ verb: "move", target: "study" }), "You walk to the study.");
  assert.equal(actionText({ verb: "request_questioning", target: "pell" }), "You ask Lady Vane to question Pell.");
  assert.equal(actionText({ verb: "accuse", target: "sable" }), "You accuse Sable before Lady Vane.");
});

test("every sprite is 16 x 16", () => {
  for (const [id, def] of Object.entries(SPRITES)) {
    assert.equal(def.px.length, 16, id);
    for (const row of def.px) assert.equal(row.length, 16, `${id}: ${row}`);
  }
});

test("the Watch route is the solve: kitchen, study, hall, then accuse Sable", () => {
  const acts = STEPS.filter((s) => s.act).map((s) => s.act);
  assert.deepEqual(acts.filter((a) => a.verb === "move").map((a) => a.target), ["kitchen", "study", "hall"]);
  assert.deepEqual(acts.at(-1), { verb: "accuse", target: "sable" });
  assert.ok(acts.some((a) => a.verb === "request_questioning" && a.target === "pell"));
});
