// "Watch the 60-second story": the demo route (frame Kael, seed 1) played through the real API, with captions.

import { $, sleep } from "./dom.js";

const DEMO_SEED = 1;

const STEPS = [
  { cap: "<b>The Crypt Road.</b> Race your rival Kael to the relic in the crypt.", wait: 2600 },
  { cap: "Insult Kael in the tavern. <b>He will remember.</b>", act: { verb: "insult", target: "kael" } },
  { cap: "Challenge him to a duel...", act: { verb: "challenge", target: "kael" } },
  { cap: "...and humiliate him: take his purse. <b>Mags and Odo saw everything.</b>", act: { verb: "humiliate", target: "kael" }, tab: "minds" },
  { cap: "Kael has left the tavern. Out of sight, but <b>not out of mind</b>.", act: { verb: "talk", target: "mags", text: "Where did Kael go?" } },
  { cap: "You only see your own stop. <b>Ghosts</b> mark where you last saw everyone.", act: { verb: "move" } },
  { cap: "At the gate, Captain Brenna is waiting. <b>Kael told her what you did.</b>", act: { verb: "move" }, chain: "brenna" },
  { cap: "The <b>why-chain</b>: her line rests on Kael's report, which rests on what you really did.", wait: 4200 },
  { cap: "A fine paid in coin smooths most trouble. <b>Kael's own coins.</b>", act: { verb: "bribe", target: "brenna", amount: 20 }, tab: "minds" },
  { cap: "Twice. Brenna trusts you again.", act: { verb: "bribe", target: "brenna", amount: 20 } },
  { cap: "Now <b>frame Kael</b>: tell Brenna he robbed Odo. A lie, and the ledger knows it.", act: { verb: "tell_claim", target: "brenna", claim: { pred: "robbed", a: "kael", b: "odo" } }, tab: "beliefs" },
  { cap: "Brenna believes you. <b>Kael is detained.</b> The gate opens.", act: { verb: "move" } },
  { cap: "Across the bridge...", act: { verb: "move" } },
  { cap: "The relic is yours.", act: { verb: "take_relic" } },
];

export async function runAutoplay(game) {
  game.autoplaying = true;
  const t0 = performance.now();
  try {
    await game.newSession(DEMO_SEED);
    for (const step of STEPS) {
      if (!game.autoplaying) return;
      game.caption(step.cap);
      if (step.tab) game.inspector.show(step.tab);
      if (step.act) {
        const res = await game.act(step.act);
        if (!res) throw new Error(`The demo route stopped at ${step.act.verb}`);
        if (step.chain) {
          const r = res.replies.find((x) => x.npc === step.chain);
          if (r) game.inspector.openChain(r.decision);
        }
        await sleep(700);
      } else {
        await sleep(step.wait);
      }
    }
  } catch (e) {
    game.toast(e.message || String(e));
  } finally {
    game.autoplaying = false;
    game.caption(null);
    console.info(`autoplay finished in ${((performance.now() - t0) / 1000).toFixed(1)} s`);
    $("hint").hidden = true;
  }
}
