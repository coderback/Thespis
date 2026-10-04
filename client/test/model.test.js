// Checks the client's pure logic against the real fixtures, so a contract change that breaks the client fails here.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { whyChain, mapFigures, splitReplies, beliefBursts, moodIcons, worldMemory, clock, claimText, eventText } from "../src/model.js";
import { FixtureApi, DEMO_ROUTE } from "../src/api.js";

const dir = fileURLToPath(new URL("../../fixtures/", import.meta.url));
const fx = (n) => JSON.parse(readFileSync(dir + n + ".json", "utf8"));

test("Brenna's gate line traces down to the humiliation, marked true", () => {
  const act = fx("act_06_move_to_guard_post");
  const reply = act.replies.find((r) => r.npc === "brenna");
  const chain = whyChain(act.state, reply.decision);
  assert.equal(chain.decision.npc, "brenna");
  const belief = chain.links.find((l) => l.kind === "belief");
  assert.equal(belief.belief.claim.pred, "robbed");
  assert.equal(belief.evidence[0].source, "kael");
  assert.equal(chain.roots.length, 1);
  assert.equal(chain.roots[0].event.verb, "humiliate");
  assert.equal(chain.roots[0].truth, true);
});

test("Brenna's detain line rests on the lie, marked false", () => {
  const act = fx("act_10_move_to_bridge");
  const d = act.tick.decisions.find((x) => x.npc === "brenna");
  const chain = whyChain(act.state, d.id);
  const lie = chain.roots.find((r) => r.event.verb === "tell_claim");
  assert.ok(lie, "the root is the player's tell_claim");
  assert.equal(lie.truth, false);
});

test("fog: after the humiliation Kael is a ghost at the tavern", () => {
  const s = fx("state_p1_after_humiliate");
  const kael = mapFigures(s).find((f) => f.id === "kael");
  assert.deepEqual([kael.ghost, kael.loc], [true, "tavern"]);
  const mags = mapFigures(s).find((f) => f.id === "mags");
  assert.equal(mags.ghost, false);
  assert.ok(!mapFigures(fx("state_p0_start")).find((f) => f.id === "brenna"), "never seen: no ghost at all");
});

test("arrival greetings play after the moves, reactions before", () => {
  const humiliate = fx("act_03_humiliate_kael");
  const a = splitReplies(humiliate.replies, humiliate.state, 0);
  assert.equal(a.before.length, 1);
  const gate = fx("act_06_move_to_guard_post");
  const b = splitReplies(gate.replies, gate.state, 2);
  assert.equal(b.after.length, 2);
});

test("icons and bursts follow the demo beats", () => {
  const prev = fx("act_08_bribe_brenna").state;
  const lie = fx("act_09_tell_brenna_lie").state;
  const kael = lie.npcs.find((n) => n.id === "kael");
  assert.ok(moodIcons(lie, kael).includes("angry"));
  const bursts = beliefBursts(prev, lie);
  assert.ok(bursts.some((b) => b.npc === "kael" && b.kind === "liedto"));
  assert.ok(bursts.some((b) => b.npc === "brenna" && b.kind === "belief"));
  const detained = fx("act_10_move_to_bridge").state;
  assert.ok(moodIcons(detained, detained.npcs.find((n) => n.id === "kael")).includes("chains"));
  const end = fx("state_p7_end");
  assert.ok(beliefBursts(lie, end).some((b) => b.npc === "brenna" && b.kind === "liedto"), "Brenna learns she was lied to");
});

test("text helpers", () => {
  assert.equal(clock({ phase: 3 }), "Day 1 · Night");
  assert.equal(claimText({ pred: "robbed", a: "player", b: "kael" }), "You robbed Kael");
  assert.equal(eventText({ verb: "move", actor: "odo", loc: "market", target: "guard_post" }), "Odo walked from the market to the guard post");
  assert.ok(worldMemory(fx("state_p7_end")).some((l) => l.startsWith("Brenna no longer believes")));
});

test("the fixture backend plays the whole demo route", async () => {
  const names = ["session_new", "allowed_p0_tavern", "allowed_p0_duel_won", "allowed_p3_gate", "allowed_p7_end", "digest_p2", "digest_epilogue",
    ...DEMO_ROUTE.map(([n]) => n)];
  const api = new FixtureApi(Object.fromEntries(names.map((n) => [n, fx(n)])));
  await api.newSession();
  for (const [, req] of DEMO_ROUTE) await api.act({ ...req, text: "hi", amount: 20, claim: { pred: "robbed", a: "kael", b: "odo" } });
  const s = await api.state();
  assert.equal(s.status, "won");
  await assert.rejects(api.act({ verb: "wait" }), (e) => e.status === 409);
});

test("the fixture backend keeps a live persona edit (#39)", async () => {
  const names = ["session_new", ...DEMO_ROUTE.map(([n]) => n)];
  const api = new FixtureApi(Object.fromEntries(names.map((n) => [n, fx(n)])));
  await api.newSession();
  const kael = (s) => s.npcs.find((n) => n.id === "kael");
  const usual = kael(await api.state()).persona;
  assert.equal(kael(await api.state()).persona_edited, false);
  assert.deepEqual(await api.persona("kael", "Speaks only in rhyme."), { npc: "kael", persona: "Speaks only in rhyme.", default: false });
  assert.equal(kael(await api.state()).persona, "Speaks only in rhyme.");
  const [, first] = DEMO_ROUTE[0];
  assert.equal(kael((await api.act(first)).state).persona_edited, true); // kept across actions
  assert.equal((await api.persona("kael", "")).default, true);
  assert.equal(kael(await api.state()).persona, usual);
});
