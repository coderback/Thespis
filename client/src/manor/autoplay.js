// "Watch the case solved": the solve played through the real API with a caption per beat. tools/manor_solve.py plays
// the same steps as its "Watch route", to check them and warm the model cache after a deploy.

import { sleep } from "../dom.js";

export const STEPS = [
  { cap: "<b>The Manor Mystery.</b> Lady Vane's signet ring vanished from the study this morning, before you arrived.", wait: 3000 },
  { cap: "Ask Lady Vane about the ring.", act: { verb: "ask", target: "vane", topic: "ring" } },
  { cap: "And about this morning. <b>She believes Sable</b>: the kitchen, all morning.", act: { verb: "ask", target: "vane", topic: "morning" }, tab: "beliefs" },
  { cap: "Down to the kitchen. You only see the room you're in.", act: { verb: "move", target: "kitchen" } },
  { cap: "Ask Sable where she was. Frightened, <b>she lies</b>, and the ledger logs it false.", act: { verb: "ask", target: "sable", topic: "morning" }, chain: "sable" },
  { cap: "The <b>why-chain</b>: her line, the lie she chose over dodging, and what she really knew.", wait: 5200 },
  { cap: "Pell was in the study all morning. Ask him.", act: { verb: "move", target: "study" } },
  { cap: "Pell never lies. <b>He saw Sable leave the study.</b>", act: { verb: "ask", target: "pell", topic: "morning" } },
  { cap: "Back to the hall, to Lady Vane.", act: { verb: "move", target: "hall" } },
  { cap: "Have her question Pell. Two places at once can't both be true...", act: { verb: "request_questioning", target: "pell" }, tab: "beliefs" },
  { cap: "...so she drops the word of the one she trusts less. <b>The alibi is broken.</b>", wait: 4200 },
  { cap: "Now accuse Sable.", act: { verb: "accuse", target: "sable" } },
];

export async function runAutoplay(game) {
  game.autoplaying = true;
  const t0 = performance.now();
  try {
    await game.newSession();
    for (const step of STEPS) {
      if (!game.autoplaying) return;
      game.caption(step.cap);
      if (step.tab) game.inspector.show(step.tab);
      if (step.act) {
        const res = await game.act(step.act);
        if (!res) throw new Error(`The case stopped at ${step.act.verb}`);
        if (step.chain) {
          const said = res.replies.find((r) => r.npc === step.chain);
          if (said) game.inspector.openChain(said.decision);
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
  }
}
