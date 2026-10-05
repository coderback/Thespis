// The manor on the map: the house, its people, fog over the rooms you aren't in, the light of the afternoon, typed
// speech bubbles, Sable's nerves, a stamp when a lie is logged and an arc when someone testifies. Drawn at 3x onto the
// 864 x 576 canvas with no smoothing, like The Crypt Road's map (src/map.js). All game logic stays in the engine.

import { CAST, ROOMS, name, roomName, visitedRooms, moodIcons } from "./model.js";
import { sprite } from "./sprites.js";
import { paintHouse, W, FLOOR_Y, ROOM_SPAN, ROOM_X, LAMPS, FIRE } from "./house.js";

const S = 3;
const SLOT = { player: -20, vane: 12, pell: 14, sable: 16 }; // where each stands in a room, from its middle
const GUEST_X = ROOM_X.hall + 32; // where someone called in to be questioned stands
const ROOM_MS = 1000; // to walk one room's width
const FOG = 0.74;
const PIXEL = "'Press Start 2P', monospace";
const SPEECH = "'VT323', monospace";
// Sky (top, bottom) and a light tint, by phase: noon when you arrive, evening when the constable is sent for.
const LIGHT = {
  2: { sky: ["#6fa9dc", "#bfe0f5"], tint: [255, 255, 230, 0] },
  3: { sky: ["#77acd8", "#c9dff0"], tint: [255, 240, 205, 0.04] },
  4: { sky: ["#8aa9cc", "#e2d6c0"], tint: [255, 215, 150, 0.08] },
  5: { sky: ["#8c8fb8", "#f0b878"], tint: [255, 175, 95, 0.15] },
  6: { sky: ["#5b5a92", "#e8875a"], tint: [255, 125, 65, 0.22] },
  7: { sky: ["#151a3d", "#33316a"], tint: [24, 28, 72, 0.46] },
};

const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
const lerp = (a, b, t) => a + (b - a) * t;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const light = (phase) => LIGHT[Math.max(2, Math.min(7, phase))];
const roomAt = (x) => ROOMS.find((id) => x >= ROOM_SPAN[id][0] - 3 && x <= ROOM_SPAN[id][1] + 3) || "hall";

export class ManorView {
  constructor(canvas) {
    this.cv = canvas;
    this.g = canvas.getContext("2d");
    this.house = paintHouse();
    this.state = null;
    this.walks = new Map(); // id -> {from, to, t0, ms}
    this.arrivals = {}; // id -> when it arrived, for the squash
    this.guests = new Set(); // NPCs called into the hall for questioning
    this.fog = Object.fromEntries(ROOMS.map((r) => [r, { from: FOG, to: FOG, t0: 0 }])); // per room, eased over time
    this.sky = { from: light(2), to: light(2), t0: 0 };
    this.bubbles = []; // {id, text, t0, hold}
    this.bursts = []; // {id, kind, t0}
    this.arcs = []; // testimony {a, b, t0}
    this.stars = Array.from({ length: 40 }, (_, i) => [(i * 73) % W, (i * 37) % 30, (i % 3) + 1]);
    requestAnimationFrame(this.frame);
  }

  setState(state, { instant = false } = {}) {
    const prev = this.state?.phase;
    this.state = state;
    if (prev !== state.phase) {
      const now = performance.now();
      this.sky = { from: instant || prev == null ? light(state.phase) : this.lightNow(now), to: light(state.phase), t0: now };
    }
    if (instant) for (const r of ROOMS) { const v = r === state.player.loc ? 0 : FOG; this.fog[r] = { from: v, to: v, t0: 0 }; }
  }

  /** How dark a room is now: it eases over half a second, by the clock rather than by frames, so a page whose frames
   *  are throttled (a background tab) still draws the right moment when it does draw. */
  fogAt(room, now) {
    const f = this.fog[room];
    return lerp(f.from, f.to, Math.max(0, Math.min(1, (now - f.t0) / 500)));
  }

  /** Light the room the player is heading for and darken the rest, starting at `at`. */
  fadeTo(room, at) {
    for (const r of ROOMS) {
      const to = r === room ? 0 : FOG;
      if (this.fog[r].to !== to) this.fog[r] = { from: this.fogAt(r, at), to, t0: at };
    }
  }

  lightNow(now) {
    const t = Math.min(1, (now - this.sky.t0) / 1400);
    const mix = (a, b) => a.map((v, i) => (typeof v === "number" ? lerp(v, b[i], t) : t < 0.5 ? v : b[i]));
    return { sky: t < 0.5 ? this.sky.from.sky : this.sky.to.sky, tint: mix(this.sky.from.tint, this.sky.to.tint), t };
  }

  home(id) {
    if (id === "player") return ROOM_X[this.state.player.loc] + SLOT.player;
    if (this.guests.has(id)) return GUEST_X;
    const n = this.state.npcs.find((x) => x.id === id);
    return ROOM_X[n.loc] + SLOT[id];
  }

  /** Walk someone to an x on the floor; resolves when they arrive. */
  async walkTo(id, x, from = null) {
    const start = from ?? this.pos(id, performance.now()).x;
    const ms = Math.max(500, (Math.abs(x - start) / 90) * ROOM_MS);
    this.walks.set(id, { from: start, to: x, t0: performance.now(), ms });
    await sleep(ms + 40);
    this.walks.delete(id);
    this.arrivals[id] = performance.now();
  }

  /** The player walks to the room in `next`, then the view adopts it. */
  async walkPlayer(next) {
    const now = performance.now();
    const from = this.pos("player", now).x, to = ROOM_X[next.player.loc] + SLOT.player;
    this.fadeTo(next.player.loc, now + Math.max(500, (Math.abs(to - from) / 90) * ROOM_MS) - 450); // as they reach the door
    await this.walkTo("player", to, from);
    this.setState(next);
  }

  /** Lady Vane sends for someone: they walk into the hall to be questioned. */
  async summon(id) {
    const from = this.home(id);
    this.guests.add(id);
    await this.walkTo(id, GUEST_X, from);
  }

  /** ...and back to their own room afterwards. */
  async dismiss(id) {
    if (!this.guests.has(id)) return;
    this.guests.delete(id);
    await this.walkTo(id, this.home(id), GUEST_X);
  }

  /** A typed-out speech bubble over a character. Resolves once it has been read. */
  async say(id, text) {
    this.bubbles = [];
    const hold = 1400 + text.length * 32;
    this.bubbles.push({ id, text, t0: performance.now(), hold });
    await sleep(Math.min(hold, 900 + text.length * 22));
  }

  clearBubbles() { this.bubbles = []; }

  burst(id, kind) { this.bursts.push({ id, kind, t0: performance.now() }); }

  testify(a, b) { this.arcs.push({ a, b, t0: performance.now() }); }

  pos(id, now) {
    const w = this.walks.get(id);
    if (w) {
      const t = Math.min(1, (now - w.t0) / w.ms);
      return { x: lerp(w.from, w.to, ease(t)), y: FLOOR_Y - Math.abs(Math.sin(t * Math.PI * 5)) * 2 };
    }
    return { x: this.home(id), y: FLOOR_Y };
  }

  frame = (now) => {
    requestAnimationFrame(this.frame);
    if (!this.state) return;
    const g = this.g;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalAlpha = 1;
    g.imageSmoothingEnabled = false;
    const lit = this.lightNow(now);
    this.drawSky(lit, now);
    g.drawImage(this.house, 0, 0, this.house.width * S, this.house.height * S);
    this.drawFire(now);
    this.drawLamps(now);

    const here = this.state.player.loc;
    const figs = ["player", ...CAST].map((id) => {
      const p = this.pos(id, now);
      return { id, ...p, vis: id === "player" ? 1 : 1 - this.fogAt(roomAt(p.x), now) / FOG };
    });
    for (const f of figs) this.drawFigure(f, now);
    this.drawFog(now);
    this.drawGhosts(figs); // over the fog, so "last seen" stays readable in a dark room
    this.drawTint(lit.tint);
    this.drawRoomNames(here);
    this.bursts = this.bursts.filter((b) => now - b.t0 < 2400);
    for (const f of figs) if (f.vis > 0.5) this.drawIcons(f, now);
    this.drawArcs(figs, now);
    for (const f of figs) if (f.vis > 0.3) this.drawBubble(f, now);
    for (const b of this.bursts) {
      const f = figs.find((x) => x.id === b.id);
      if (b.kind === "lie" && f && f.vis > 0.5) this.drawStamp(f, now - b.t0); // last, so no bubble covers it
    }
  };

  drawSky(lit, now) {
    const g = this.g;
    const grad = g.createLinearGradient(0, 0, 0, 100 * S);
    grad.addColorStop(0, lit.sky[0]);
    grad.addColorStop(1, lit.sky[1]);
    g.fillStyle = grad;
    g.fillRect(0, 0, this.cv.width, 166 * S);
    if (this.state.phase < 7) return;
    for (const [x, y, s] of this.stars) {
      g.globalAlpha = 0.5 + 0.5 * Math.sin(now / 500 + x);
      g.fillStyle = "#f3ead2";
      g.fillRect(x * S, y * S, s, s);
    }
    g.globalAlpha = 1;
  }

  drawFire(now) {
    const g = this.g;
    const flick = 1 + Math.sin(now / 80) * 0.08 + Math.sin(now / 31) * 0.05;
    const x = FIRE.x * S, y = FIRE.y * S;
    const glow = g.createRadialGradient(x, y, 2, x, y, 30 * S * flick);
    glow.addColorStop(0, "rgba(255,150,60,0.55)");
    glow.addColorStop(1, "rgba(255,150,60,0)");
    g.fillStyle = glow;
    g.fillRect(x - 32 * S, y - 32 * S, 64 * S, 64 * S);
    for (let i = 0; i < 3; i++) {
      const h = (5 + Math.sin(now / (60 + i * 17) + i) * 2) * S;
      g.fillStyle = i === 1 ? "#ffd27a" : "#f08a3a";
      g.fillRect(x + (i - 1) * 4 * S - S, y + 4 * S - h, 2 * S, h);
    }
  }

  drawLamps(now) {
    if (this.state.phase < 6) return; // lamps are lit from teatime
    const g = this.g;
    for (const l of LAMPS) {
      const x = l.x * S, y = l.y * S, rad = l.r * S * (1 + Math.sin(now / 400 + l.x) * 0.03);
      const glow = g.createRadialGradient(x, y, 2, x, y, rad);
      glow.addColorStop(0, "rgba(246,200,110,0.45)");
      glow.addColorStop(1, "rgba(246,200,110,0)");
      g.fillStyle = glow;
      g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
    }
  }

  /** A dashed "last seen" ghost for anyone in a room you have been in but aren't in now. */
  drawGhosts(figs) {
    const g = this.g;
    const seen = visitedRooms(this.state);
    for (const f of figs) {
      if (f.id === "player" || f.vis > 0.9 || this.walks.has(f.id) || this.guests.has(f.id)) continue;
      if (!seen.has(roomAt(f.x))) continue;
      g.globalAlpha = 0.8 * (1 - f.vis);
      g.drawImage(sprite(f.id, { ghost: true }), (f.x - 8) * S, (FLOOR_Y - 14) * S, 16 * S, 16 * S);
      this.label(f.x, FLOOR_Y, `${name(f.id)}?`, "#cfc6b0");
      g.globalAlpha = 1;
    }
  }

  drawFigure(f, now) {
    if (f.vis <= 0.02) return;
    const g = this.g;
    g.globalAlpha = f.vis;
    g.fillStyle = "rgba(0,0,0,0.3)";
    g.beginPath();
    g.ellipse(f.x * S, (f.y + 1) * S, 6 * S, 2 * S, 0, 0, Math.PI * 2);
    g.fill();
    let sx = 1, sy = 1;
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

  drawFog(now) {
    const g = this.g;
    for (const r of ROOMS) {
      const a = this.fogAt(r, now);
      if (a < 0.01) continue;
      const [x0, x1] = ROOM_SPAN[r];
      g.fillStyle = `rgba(10,8,16,${a})`;
      g.fillRect(x0 * S, 35 * S, (x1 - x0) * S, (FLOOR_Y + 6 - 35) * S);
    }
  }

  drawTint([r, gr, b, a]) {
    if (a < 0.01) return;
    this.g.fillStyle = `rgba(${r | 0},${gr | 0},${b | 0},${a})`;
    this.g.fillRect(0, 0, this.cv.width, this.cv.height);
  }

  drawRoomNames(here) {
    const g = this.g;
    g.font = `8px ${PIXEL}`;
    g.textAlign = "center";
    g.textBaseline = "top";
    g.strokeStyle = "rgba(20,14,18,0.85)";
    g.lineWidth = 3;
    for (const r of ROOMS) {
      const text = roomName(r, { cap: true });
      g.fillStyle = r === here ? "rgba(246,194,90,0.98)" : "rgba(243,234,210,0.45)";
      g.strokeText(text.toUpperCase(), ROOM_X[r] * S, 177 * S);
      g.fillText(text.toUpperCase(), ROOM_X[r] * S, 177 * S);
    }
  }

  drawIcons(f, now) {
    const n = this.state.npcs.find((x) => x.id === f.id);
    const icons = (n ? moodIcons(n) : []).map((kind) => ({ kind }));
    const all = [...icons, ...this.bursts.filter((b) => b.id === f.id && b.kind !== "lie")];
    const g = this.g;
    all.forEach((ic, i) => {
      const x = f.x * S + (i - (all.length - 1) / 2) * 24;
      const pop = ic.t0 ? Math.min(1, (now - ic.t0) / 180) : 1;
      const hop = ic.t0 ? Math.sin(Math.min(1, (now - ic.t0) / 400) * Math.PI) * 6 : Math.sin(now / 300 + i) * 1.5;
      g.save();
      g.translate(x, (f.y - 21) * S - hop);
      g.scale(pop, pop);
      drawIcon(g, ic.kind);
      g.restore();
    });
  }

  /** A red LIE stamp over whoever just stated something the ledger logged false. */
  drawStamp(f, age) {
    const g = this.g;
    const pop = Math.min(1, age / 140);
    const fade = age > 1900 ? 1 - (age - 1900) / 500 : 1;
    g.save();
    g.globalAlpha = Math.max(0, fade);
    g.translate((f.x + 22) * S, (f.y - 8) * S); // beside the liar, clear of the speech bubble above
    g.rotate(-0.22);
    g.scale(2.2 - 1.2 * pop, 2.2 - 1.2 * pop);
    g.strokeStyle = "#e0453a";
    g.lineWidth = 4;
    roundRect(g, -34, -14, 68, 28, 4);
    g.stroke();
    g.font = `14px ${PIXEL}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = "#e0453a";
    g.fillText("LIE", 1, 2);
    g.restore();
  }

  drawArcs(figs, now) {
    const g = this.g;
    this.arcs = this.arcs.filter((l) => now - l.t0 < 1800);
    for (const l of this.arcs) {
      const a = figs.find((f) => f.id === l.a), b = figs.find((f) => f.id === l.b);
      if (!a || !b || a.vis < 0.5 || b.vis < 0.5) continue;
      const t = (now - l.t0) / 1800;
      g.strokeStyle = `rgba(246,214,120,${1 - t})`;
      g.lineWidth = 3;
      g.setLineDash([7, 6]);
      g.lineDashOffset = -now / 30;
      g.beginPath();
      g.moveTo(a.x * S, (a.y - 12) * S);
      g.quadraticCurveTo(((a.x + b.x) / 2) * S, (Math.min(a.y, b.y) - 34) * S, b.x * S, (b.y - 12) * S);
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
    let left = Math.floor(age / 22);
    const w = Math.max(...lines.map((l) => g.measureText(l).width)) + 20;
    const h = lines.length * 19 + 14;
    const x = Math.max(6, Math.min(this.cv.width - w - 6, f.x * S - w / 2));
    const y = Math.max(4, (f.y - 24) * S - h - 8);
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
}

function drawIcon(g, kind) {
  g.lineWidth = 3;
  g.strokeStyle = "#1b1420";
  if (kind === "sweat") {
    g.fillStyle = "#7fc3ec";
    g.beginPath();
    g.moveTo(0, -10); g.quadraticCurveTo(9, 2, 0, 8); g.quadraticCurveTo(-9, 2, 0, -10);
    g.fill(); g.stroke();
    return;
  }
  // "!" when someone changes their mind; testimony shows as an arc, not an icon
  if (kind !== "retract") return;
  g.fillStyle = "#f6c25a";
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
  g.fillText("!", 1, 1);
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
