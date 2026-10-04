// The map: world, characters, fog of war, phase lighting, speech bubbles and the mind icons.
// Draws at 3x onto a 864 x 576 canvas with no smoothing. All game logic stays in the engine.

import { STOP_TILE_X, STOP_NAMES, STOPS, name, moodIcons } from "./model.js";
import { sprite } from "./sprites.js";
import { paintWorld, TILE, ROAD_Y, WINDOWS, TORCH } from "./world.js";

const S = 3;
const FEET_Y = ROAD_Y * TILE + 13;
const SLOT = { player: [0, 2], kael: [14, 2], odo: [-14, 2], mags: [-8, -11], brenna: [10, -10] };
const TINTS = [
  [255, 196, 140, 0.16], // morning
  [255, 255, 230, 0.0], // noon
  [255, 120, 40, 0.24], // evening
  [16, 24, 70, 0.55], // night
];
const WALK_MS = 900;
const PIXEL = "'Press Start 2P', monospace";
const SPEECH = "'VT323', monospace";

const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
const lerp = (a, b, t) => a + (b - a) * t;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class MapView {
  constructor(canvas) {
    this.cv = canvas;
    this.g = canvas.getContext("2d");
    this.world = paintWorld();
    this.state = null;
    this.walks = new Map(); // id -> {from, to, t0}
    this.arrivals = {}; // id -> time of arrival, for the squash
    this.tint = { from: TINTS[0], to: TINTS[0], t0: 0 };
    this.fog = { from: 1, to: 1, t0: 0, ms: 0 };
    this.bubbles = []; // {id, text, t0, hold}
    this.bursts = []; // {id, kind, t0}
    this.links = []; // gossip lines {a, b, t0}
    this.dice = null;
    requestAnimationFrame(this.frame);
  }

  setState(state, { instant = false } = {}) {
    const prevPhase = this.state?.phase;
    this.state = state;
    if (prevPhase !== state.phase) this.setTint(state.phase % 4, instant || prevPhase == null);
  }

  setTint(i, instant) {
    const now = performance.now();
    this.tint = { from: instant ? TINTS[i] : this.currentTint(now), to: TINTS[i], t0: now };
  }

  currentTint(now) {
    const t = Math.min(1, (now - this.tint.t0) / 800);
    return this.tint.from.map((v, k) => lerp(v, this.tint.to[k], t));
  }

  setFog(v, ms = 1200) {
    const now = performance.now();
    this.fog = { from: this.fogNow(now), to: v, t0: now, ms };
  }

  fogNow(now) {
    const f = this.fog;
    return f.ms ? lerp(f.from, f.to, Math.min(1, (now - f.t0) / f.ms)) : f.to;
  }

  /** Walk everyone in `moves` from stop to stop, then adopt `next`. */
  async animateMoves(moves, next) {
    const now = performance.now();
    for (const m of moves) this.walks.set(m.who, { from: m.from, to: m.to, t0: now });
    if (moves.length) await sleep(WALK_MS + 60);
    const end = performance.now();
    for (const m of moves) this.arrivals[m.who] = end;
    this.walks.clear();
    this.setState(next);
  }

  /** A typed-out speech bubble over a character. Resolves once it has been read. */
  async say(id, text) {
    this.bubbles = []; // one speaker at a time keeps it readable
    const hold = 1400 + text.length * 32;
    this.bubbles.push({ id, text, t0: performance.now(), hold });
    await sleep(Math.min(hold, 900 + text.length * 22));
  }

  clearBubbles() { this.bubbles = []; }

  burst(id, kind) { this.bursts.push({ id, kind, t0: performance.now() }); }

  gossip(a, b) { this.links.push({ a, b, t0: performance.now() }); }

  async rollDice(win) {
    this.dice = { win, t0: performance.now() };
    await sleep(1900);
    this.dice = null;
  }

  stopX(loc) { return STOP_TILE_X[loc] * TILE + 8; }

  /** World-px position of a character; bobs while walking. */
  pos(id, now) {
    const [dx, dy] = SLOT[id] || [0, 0];
    const w = this.walks.get(id);
    if (w) {
      const t = Math.min(1, (now - w.t0) / WALK_MS);
      const x = lerp(this.stopX(w.from), this.stopX(w.to), ease(t)) + dx;
      return { x, y: FEET_Y + dy - Math.abs(Math.sin(t * Math.PI * 4)) * 2 };
    }
    const loc = id === "player" ? this.state.player.loc : this.state.npcs.find((n) => n.id === id)?.loc;
    return { x: this.stopX(loc) + dx, y: FEET_Y + dy };
  }

  /** 1 when a character is at the player's stop, fading to 0 as it walks out of the light. */
  visibility(x, px, fog) {
    const d = Math.abs(x - px);
    const v = 1 - Math.max(0, Math.min(1, (d - 16) / 20));
    return Math.max(v, 1 - fog);
  }

  frame = (now) => {
    requestAnimationFrame(this.frame);
    if (!this.state) return;
    const g = this.g;
    g.setTransform(1, 0, 0, 1, 0, 0); // start every frame clean, so nothing a failed draw left behind can stick
    g.globalAlpha = 1;
    g.imageSmoothingEnabled = false;
    g.drawImage(this.world, 0, 0, this.world.width * S, this.world.height * S);

    const fog = this.fogNow(now);
    const player = this.pos("player", now);
    const ids = ["player", ...this.state.npcs.map((n) => n.id)];
    const figs = ids.map((id) => {
      const p = this.pos(id, now);
      return { id, ...p, vis: id === "player" ? 1 : this.visibility(p.x, player.x, fog) };
    }).sort((a, b) => a.y - b.y);

    this.drawGhosts(figs);
    for (const f of figs) this.drawFigure(f, now);
    this.drawFog(player.x, fog);
    this.drawTint(now);
    this.drawStopNames(player.x, fog);
    this.bursts = this.bursts.filter((b) => now - b.t0 < 1800);
    for (const f of figs) if (f.vis > 0.5) this.drawIcons(f, now);
    this.drawLinks(figs, now);
    for (const f of figs) if (f.vis > 0.3) this.drawBubble(f, now);
    if (this.dice) this.drawDice(now);
  };

  /** A dashed "last seen" ghost for anyone out of sight. */
  drawGhosts(figs) {
    const g = this.g;
    for (const n of this.state.npcs) {
      const f = figs.find((x) => x.id === n.id);
      if (!n.last_seen || f.vis > 0.95 || this.walks.has(n.id)) continue;
      const [dx, dy] = SLOT[n.id];
      const gx = this.stopX(n.last_seen.loc) + dx;
      g.globalAlpha = 0.6 * (1 - f.vis);
      g.drawImage(sprite(n.id, { ghost: true }), (gx - 8) * S, (FEET_Y + dy - 14) * S, 16 * S, 16 * S);
      this.label(gx, FEET_Y + dy - 25, `${name(n.id)}?`, "#cfc6b0");
      g.globalAlpha = 1;
    }
  }

  drawFigure(f, now) {
    if (f.vis <= 0.02) return;
    const g = this.g;
    g.globalAlpha = f.vis;
    g.fillStyle = "rgba(0,0,0,0.28)";
    g.beginPath();
    g.ellipse(f.x * S, (f.y + 1) * S, 6 * S, 2 * S, 0, 0, Math.PI * 2);
    g.fill();
    let sx = 1, sy = 1; // a small squash on arrival
    const t = (now - (this.arrivals[f.id] ?? -1e9)) / 240;
    if (t < 1) { sy = 1 - 0.16 * Math.sin(t * Math.PI); sx = 1 + 0.12 * Math.sin(t * Math.PI); }
    const w = 16 * S * sx, h = 16 * S * sy;
    g.drawImage(sprite(f.id), f.x * S - w / 2, f.y * S - h + 2 * S, w, h);
    this.label(f.x, f.y, name(f.id), f.id === "player" ? "#9fe08a" : "#f3ead2");
    g.globalAlpha = 1;
  }

  label(x, y, text, color) {
    const g = this.g;
    g.font = `8px ${PIXEL}`;
    g.textAlign = "center";
    g.textBaseline = "top";
    g.lineWidth = 3;
    g.strokeStyle = "rgba(20,14,18,0.85)";
    g.strokeText(text, x * S, (y + 3) * S);
    g.fillStyle = color;
    g.fillText(text, x * S, (y + 3) * S);
  }

  drawFog(px, fog) {
    if (fog <= 0.01) return;
    const g = this.g, W = this.cv.width, H = this.cv.height;
    const cx = px * S, inner = 26 * S, outer = 40 * S;
    const a = 0.7 * fog;
    const at = (x) => Math.max(0, Math.min(1, x / W));
    const grad = g.createLinearGradient(0, 0, W, 0);
    grad.addColorStop(0, `rgba(10,8,16,${a})`);
    grad.addColorStop(at(cx - outer), `rgba(10,8,16,${a})`);
    grad.addColorStop(at(cx - inner), "rgba(10,8,16,0)");
    grad.addColorStop(at(cx + inner), "rgba(10,8,16,0)");
    grad.addColorStop(at(cx + outer), `rgba(10,8,16,${a})`);
    grad.addColorStop(1, `rgba(10,8,16,${a})`);
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H);
  }

  drawTint(now) {
    const g = this.g;
    const [r, gr, b, a] = this.currentTint(now);
    if (a > 0.01) {
      g.fillStyle = `rgba(${r | 0},${gr | 0},${b | 0},${a})`;
      g.fillRect(0, 0, this.cv.width, this.cv.height);
    }
    const k = Math.min(1, (now - this.tint.t0) / 800);
    const night = this.tint.to === TINTS[3] ? k : this.tint.from === TINTS[3] ? 1 - k : 0;
    if (night <= 0) return;
    g.globalAlpha = night;
    for (const [x, y, w, h] of WINDOWS) {
      g.fillStyle = "#f6c25a";
      g.fillRect(x * S, y * S, w * S, h * S);
      const cx = (x + w / 2) * S, cy = (y + h / 2) * S;
      const glow = g.createRadialGradient(cx, cy, 2, cx, cy, 16 * S);
      glow.addColorStop(0, "rgba(246,194,90,0.35)");
      glow.addColorStop(1, "rgba(246,194,90,0)");
      g.fillStyle = glow;
      g.fillRect(cx - 16 * S, cy - 16 * S, 32 * S, 32 * S);
    }
    const flick = 1 + Math.sin(now / 90) * 0.06 + Math.sin(now / 37) * 0.04;
    const tx = TORCH.x * S, ty = TORCH.y * S;
    const torch = g.createRadialGradient(tx, ty, 2, tx, ty, 34 * S * flick);
    torch.addColorStop(0, "rgba(255,170,70,0.55)");
    torch.addColorStop(1, "rgba(255,170,70,0)");
    g.fillStyle = torch;
    g.fillRect(tx - 40 * S, ty - 40 * S, 80 * S, 80 * S);
    g.fillStyle = "#ffd27a";
    g.fillRect(tx - S, ty - 3 * S, 2 * S, 2 * S);
    g.globalAlpha = 1;
  }

  drawStopNames(px, fog) {
    const g = this.g;
    g.font = `7px ${PIXEL}`;
    g.textAlign = "center";
    g.textBaseline = "top";
    g.strokeStyle = "rgba(20,14,18,0.8)";
    g.lineWidth = 3;
    for (const s of STOPS) {
      const x = this.stopX(s);
      const lit = Math.abs(x - px) < 20 || fog < 0.5;
      g.fillStyle = lit ? "rgba(243,234,210,0.95)" : "rgba(243,234,210,0.4)";
      const text = s === "tavern" ? "The Lantern" : STOP_NAMES[s];
      g.strokeText(text, x * S, (ROAD_Y * TILE + 31) * S);
      g.fillText(text, x * S, (ROAD_Y * TILE + 31) * S);
    }
  }

  drawIcons(f, now) {
    const n = this.state.npcs.find((x) => x.id === f.id);
    const icons = (n ? moodIcons(this.state, n) : []).map((kind) => ({ kind }));
    const all = [...icons, ...this.bursts.filter((b) => b.id === f.id)];
    const g = this.g;
    all.forEach((ic, i) => {
      const x = f.x * S + (i - (all.length - 1) / 2) * 24;
      const pop = ic.t0 ? Math.min(1, (now - ic.t0) / 180) : 1;
      const hop = ic.t0 ? Math.sin(Math.min(1, (now - ic.t0) / 400) * Math.PI) * 6 : Math.sin(now / 300 + i) * 1.5;
      g.save();
      g.translate(x, (f.y - 20) * S - hop);
      g.scale(pop, pop);
      drawIcon(g, ic.kind, now);
      g.restore();
    });
  }

  drawLinks(figs, now) {
    const g = this.g;
    this.links = this.links.filter((l) => now - l.t0 < 1000);
    for (const l of this.links) {
      const a = figs.find((f) => f.id === l.a), b = figs.find((f) => f.id === l.b);
      if (!a || !b || a.vis < 0.5 || b.vis < 0.5) continue;
      const t = (now - l.t0) / 1000;
      g.strokeStyle = `rgba(246,214,120,${1 - t})`;
      g.lineWidth = 2;
      g.setLineDash([6, 5]);
      g.lineDashOffset = -now / 30;
      g.beginPath();
      g.moveTo(a.x * S, (a.y - 10) * S);
      g.quadraticCurveTo(((a.x + b.x) / 2) * S, (Math.min(a.y, b.y) - 24) * S, b.x * S, (b.y - 10) * S);
      g.stroke();
      g.setLineDash([]);
    }
  }

  drawBubble(f, now) {
    const b = this.bubbles.find((x) => x.id === f.id);
    if (!b) return;
    const age = now - b.t0;
    if (age > b.hold + 2600) { this.bubbles = this.bubbles.filter((x) => x !== b); return; }
    const g = this.g;
    g.font = `20px ${SPEECH}`;
    const lines = wrap(g, b.text, 250);
    let left = Math.floor(age / 22); // characters typed so far
    const w = Math.max(...lines.map((l) => g.measureText(l).width)) + 20;
    const h = lines.length * 19 + 14;
    const x = Math.max(6, Math.min(this.cv.width - w - 6, f.x * S - w / 2));
    const y = Math.max(4, (f.y - 22) * S - h - 8);
    const fade = age > b.hold + 2200 ? 1 - (age - b.hold - 2200) / 400 : 1;
    g.globalAlpha = Math.max(0, fade);
    g.fillStyle = "#f6f0de";
    g.strokeStyle = "#1b1420";
    g.lineWidth = 3;
    roundRect(g, x, y, w, h, 6);
    g.fill(); g.stroke();
    const tx = Math.max(x + 12, Math.min(x + w - 12, f.x * S));
    g.beginPath();
    g.moveTo(tx - 7, y + h); g.lineTo(tx, y + h + 10); g.lineTo(tx + 7, y + h);
    g.fill(); g.stroke();
    g.fillRect(tx - 6, y + h - 3, 12, 3);
    g.fillStyle = "#1b1420";
    g.textAlign = "left";
    g.textBaseline = "top";
    lines.forEach((l, i) => {
      if (left <= 0) return;
      g.fillText(l.slice(0, left), x + 10, y + 7 + i * 19);
      left -= l.length + 1;
    });
    g.globalAlpha = 1;
  }

  drawDice(now) {
    const g = this.g, W = this.cv.width, H = this.cv.height;
    // The frame's timestamp can fall just before the roll began: a negative t made face 0, which has no pips, and the
    // throw left the canvas translated and rotated for the rest of the game.
    const t = Math.max(0, now - this.dice.t0);
    const rolling = t < 1000;
    const face = rolling ? 1 + (Math.floor(t / 70) % 6) : this.dice.win ? 6 : 1;
    g.fillStyle = "rgba(10,8,16,0.45)";
    g.fillRect(0, 0, W, H);
    g.save();
    g.translate(W / 2, H / 2 - 20);
    if (rolling) g.rotate(Math.sin(t / 60) * 0.4);
    g.fillStyle = "#f6f0de";
    g.strokeStyle = "#1b1420";
    g.lineWidth = 4;
    roundRect(g, -40, -40, 80, 80, 12);
    g.fill(); g.stroke();
    g.fillStyle = "#1b1420";
    for (const [px, py] of PIPS[face]) { g.beginPath(); g.arc(px * 20, py * 20, 7, 0, Math.PI * 2); g.fill(); }
    g.restore();
    if (rolling) return;
    g.font = `22px ${PIXEL}`;
    g.textAlign = "center";
    g.textBaseline = "top";
    g.lineWidth = 6;
    g.strokeStyle = "#1b1420";
    const text = this.dice.win ? "YOU WIN THE DUEL" : "KAEL WINS THE DUEL";
    g.strokeText(text, W / 2, H / 2 + 40);
    g.fillStyle = this.dice.win ? "#f6c25a" : "#e06a5a";
    g.fillText(text, W / 2, H / 2 + 40);
  }
}

const PIPS = {
  1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]], 4: [[-1, -1], [1, -1], [-1, 1], [1, 1]],
  5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]], 6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]],
};

function drawIcon(g, kind, now) {
  g.lineWidth = 3;
  g.strokeStyle = "#1b1420";
  if (kind === "angry") {
    for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      g.beginPath();
      g.moveTo(sx * 3, sy * 9); g.lineTo(sx * 3, sy * 3); g.lineTo(sx * 9, sy * 3);
      g.strokeStyle = "#1b1420"; g.lineWidth = 6; g.stroke();
      g.strokeStyle = "#e0453a"; g.lineWidth = 3; g.stroke();
    }
  } else if (kind === "sweat") {
    g.fillStyle = "#7fc3ec";
    g.beginPath();
    g.moveTo(0, -10); g.quadraticCurveTo(9, 2, 0, 8); g.quadraticCurveTo(-9, 2, 0, -10);
    g.fill(); g.stroke();
  } else if (kind === "star") {
    g.fillStyle = "#f6c25a";
    g.beginPath();
    for (let i = 0; i < 10; i++) {
      const r = i % 2 ? 4.5 : 10, a = (i * Math.PI) / 5 - Math.PI / 2;
      g.lineTo(Math.cos(a) * r, Math.sin(a) * r);
    }
    g.closePath(); g.fill(); g.stroke();
  } else if (kind === "chains") {
    for (let i = -1; i <= 1; i++) {
      g.beginPath();
      g.ellipse(i * 8, Math.sin(now / 200 + i), 5, 3.5, i ? 0.6 : -0.6, 0, Math.PI * 2);
      g.strokeStyle = "#1b1420"; g.lineWidth = 5; g.stroke();
      g.strokeStyle = "#c9d1d9"; g.lineWidth = 2.5; g.stroke();
    }
  } else {
    g.fillStyle = kind === "liedto" ? "#e0453a" : "#f6c25a";
    g.beginPath();
    for (let i = 0; i < 16; i++) {
      const r = i % 2 ? 9 : 14, a = (i * Math.PI) / 8;
      g.lineTo(Math.cos(a) * r * 1.15, Math.sin(a) * r);
    }
    g.closePath(); g.fill(); g.stroke();
    g.font = `10px ${PIXEL}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = "#1b1420";
    g.fillText(kind === "liedto" ? "?!" : "!", 1, 1);
  }
}

function roundRect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function wrap(g, text, max) {
  const lines = [];
  let cur = "";
  for (const w of text.split(" ")) {
    const next = cur ? cur + " " + w : w;
    if (g.measureText(next).width > max && cur) { lines.push(cur); cur = w; } else cur = next;
  }
  if (cur) lines.push(cur);
  return lines.length ? lines : [""];
}
