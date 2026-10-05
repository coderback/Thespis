// The manor, painted once into a 288 x 192 offscreen canvas and shown at 3x: a cutaway of three rooms side by side,
// the study, the hall and the kitchen, with doorways between them. The sky is left clear (above the roof and in the
// windows) so the scene can paint the time of day behind it.

export const W = 288;
export const H = 192;
export const FLOOR_Y = 160; // where feet stand
export const ROOM_SPAN = { study: [10, 94], hall: [100, 188], kitchen: [194, 278] };
export const ROOM_X = { study: 52, hall: 144, kitchen: 236 };
export const WINDOWS = [[42, 50, 22, 30], [106, 44, 14, 48], [168, 44, 14, 48], [206, 48, 22, 28]];
export const LAMPS = [
  { x: 86, y: 129, r: 30 }, // the green desk lamp in the study
  { x: 144, y: 47, r: 46 }, // the hall's chandelier
  { x: 214, y: 105, r: 30 }, // a lamp on the kitchen shelf
];
export const FIRE = { x: 144, y: 150 };

const C = {
  roof: "#3b3346", roof2: "#2c2636", roofHi: "#4d4459", stone: "#77705f", stone2: "#5f594c", stoneHi: "#8d8674",
  beam: "#3a2416", wood: "#6b4527", wood2: "#4a3020", woodHi: "#8a5d36", floor: "#7a5634", floor2: "#5e4127",
  study: "#2f4a3a", study2: "#36553f", hall: "#5a2430", hall2: "#682a38", plaster: "#cdbf9f", plaster2: "#c2b392",
  tile: "#b3a684", tile2: "#a3956f", gold: "#d8b04a", gold2: "#a8832e", iron: "#2a2730", iron2: "#3a3640",
  copper: "#b8733a", copper2: "#8c5426", rug: "#8c2f3a", rug2: "#6e2430", green: "#2f7a4a", dark: "#1a1214",
  grass: "#3f5a2c", grass2: "#35502a", frame: "#6b4a2e",
};

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function paintHouse() {
  const cv = document.createElement("canvas");
  cv.width = W;
  cv.height = H;
  const g = cv.getContext("2d");
  const r = rng(11);
  const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };

  // Grounds below the house.
  rect(0, 166, W, H - 166, C.grass);
  for (let i = 0; i < 260; i++) rect(Math.floor(r() * W), 168 + Math.floor(r() * 24), 1, 1, C.grass2);

  // Roof and chimneys.
  for (const x of [36, 238]) { rect(x, 2, 12, 16, C.stone2); rect(x - 1, 2, 14, 3, C.stoneHi); }
  for (let y = 10; y < 30; y++) {
    const inset = Math.max(0, 30 - y) * 0.6;
    rect(4 + inset, y, W - 8 - inset * 2, 1, y % 4 === 0 ? C.roof2 : C.roof);
  }
  rect(2, 28, W - 4, 3, C.roofHi);

  // Outer walls, the ceiling beam, the floor and the foundation.
  rect(4, 31, 6, 135, C.stone);
  rect(W - 10, 31, 6, 135, C.stone);
  rect(10, 31, W - 20, 4, C.beam);
  rect(4, 166, W - 8, 8, C.stone2);
  for (let x = 6; x < W - 6; x += 10) rect(x, 166 + ((x / 10) % 2) * 4, 1, 4, C.stone);

  // The three rooms' walls.
  room(g, rect, "study", C.study, C.study2, 128);
  room(g, rect, "hall", C.hall, C.hall2, 132);
  room(g, rect, "kitchen", C.plaster, C.plaster2, 118);
  for (let y = 118; y < FLOOR_Y; y += 6) for (let x = 194; x < 278; x += 6) rect(x, y, 6, 6, (x / 6 + y / 6) % 2 ? C.tile : C.tile2);

  // Floors: boards in the study and hall, a checked floor in the kitchen.
  rect(10, FLOOR_Y, 178, 6, C.floor);
  for (let x = 10; x < 188; x += 14) rect(x, FLOOR_Y, 1, 6, C.floor2);
  for (let x = 194; x < 278; x += 4) for (let y = FLOOR_Y; y < 166; y += 3) rect(x, y, 4, 3, (x / 4 + y / 3) % 2 ? "#d8d0bc" : "#a59a82");

  // Inner walls with doorways.
  for (const x of [94, 188]) {
    rect(x, 35, 6, 93, C.stone);
    rect(x, 35, 1, 93, C.stoneHi);
    rect(x - 1, 126, 8, 3, C.wood2);
    rect(x, 129, 6, 31, C.dark);
    rect(x, FLOOR_Y, 6, 6, C.floor2);
  }

  windows(g, rect);
  study(g, rect, r);
  hall(g, rect);
  kitchen(g, rect);
  return cv;
}

function room(g, rect, id, wall, stripe, wainscot) {
  const [x0, x1] = ROOM_SPAN[id];
  rect(x0, 35, x1 - x0, FLOOR_Y - 35, wall);
  if (id !== "kitchen") for (let x = x0 + 3; x < x1; x += 8) rect(x, 35, 2, wainscot - 35, stripe);
  if (id !== "kitchen") {
    rect(x0, wainscot, x1 - x0, FLOOR_Y - wainscot, C.wood2);
    rect(x0, wainscot, x1 - x0, 2, C.woodHi);
    for (let x = x0 + 6; x < x1 - 6; x += 14) rect(x, wainscot + 6, 10, FLOOR_Y - wainscot - 10, C.wood);
  }
}

function windows(g, rect) {
  for (const [x, y, w, h] of WINDOWS) {
    rect(x - 2, y - 2, w + 4, h + 4, C.frame);
    g.clearRect(x, y, w, h); // the sky shows through
    rect(x + Math.floor(w / 2) - 1, y, 2, h, C.frame);
    rect(x, y + Math.floor(h / 2) - 1, w, 2, C.frame);
    rect(x - 3, y + h + 2, w + 6, 2, C.woodHi);
  }
}

function study(g, rect, r) {
  // A bookshelf of many-coloured spines.
  rect(14, 62, 24, 98, C.wood2);
  const spines = ["#8c2f3a", "#2f5a8c", "#d8b04a", "#3f7a4a", "#6b3d8f", "#b8733a", "#cdbf9f"];
  for (let y = 66; y < 156; y += 15) {
    for (let x = 16; x < 36;) {
      const w = 2 + Math.floor(r() * 2);
      rect(x, y + Math.floor(r() * 3), w, 12 - Math.floor(r() * 3), spines[Math.floor(r() * spines.length)]);
      x += w;
    }
    rect(14, y + 12, 24, 2, C.wood);
  }
  // The desk, the empty ring box on it, and the green lamp.
  rect(56, 140, 34, 4, C.woodHi);
  rect(58, 144, 4, 16, C.wood);
  rect(84, 144, 4, 16, C.wood);
  rect(62, 146, 22, 8, C.wood2);
  rect(70, 136, 7, 4, "#8c1f2a");
  rect(71, 137, 5, 2, "#d9c3a0"); // the cushion, with nothing on it
  rect(70, 133, 7, 3, "#a0283a");
  rect(85, 133, 2, 7, C.gold2);
  rect(81, 128, 10, 5, C.green);
  rect(81, 128, 10, 1, "#4fae6e");
  // A small framed map.
  rect(70, 64, 18, 14, C.gold2);
  rect(72, 66, 14, 10, "#d9c3a0");
  rect(75, 68, 6, 4, "#8a9a6a");
}

function hall(g, rect) {
  // The fireplace, with Lady Vane's portrait above it.
  rect(126, 116, 36, 44, C.stone);
  rect(124, 114, 40, 4, C.wood);
  rect(134, 128, 20, 32, C.dark);
  rect(136, 154, 16, 3, C.wood2);
  rect(132, 64, 24, 32, C.gold);
  rect(134, 66, 20, 28, "#2c2238");
  rect(141, 70, 6, 6, "#e8b48a");
  rect(140, 68, 8, 3, "#c9c3d3");
  rect(138, 77, 12, 17, "#6b3d8f");
  // The chandelier.
  rect(143, 35, 2, 8, C.gold2);
  rect(136, 43, 16, 3, C.gold);
  for (const x of [136, 143, 150]) { rect(x, 40, 2, 3, "#f1ead8"); }
  // A long red rug, and a side table with a vase.
  rect(108, 158, 72, 3, C.rug);
  rect(108, 158, 72, 1, C.gold2);
  rect(170, 146, 12, 2, C.woodHi);
  rect(172, 148, 2, 12, C.wood);
  rect(178, 148, 2, 12, C.wood);
  rect(174, 139, 4, 7, "#2f5a8c");
}

function kitchen(g, rect) {
  // The range, its hood and two copper pots.
  rect(240, 90, 30, 4, C.iron2);
  rect(244, 94, 22, 26, C.iron2);
  rect(236, 124, 38, 36, C.iron);
  rect(236, 124, 38, 3, "#4a4652");
  rect(242, 134, 26, 18, "#1c1a21");
  rect(254, 140, 2, 6, C.gold2);
  rect(240, 115, 12, 9, C.copper);
  rect(240, 115, 12, 2, "#d99a5e");
  rect(256, 118, 12, 6, C.copper2);
  // Hanging pans on a rail.
  rect(198, 80, 34, 2, C.iron);
  for (const [x, rad] of [[203, 4], [214, 5], [226, 4]]) {
    rect(x, 82, 1, 5, C.iron);
    g.fillStyle = C.copper;
    g.beginPath(); g.arc(x + 0.5, 87 + rad, rad, 0, Math.PI * 2); g.fill();
  }
  // A shelf of plates with a lamp, and the table below it.
  rect(198, 106, 34, 2, C.wood);
  for (const x of [200, 207, 214]) rect(x, 99, 6, 7, "#e9e2d0");
  rect(222, 100, 3, 6, C.gold2);
  rect(198, 144, 34, 4, C.woodHi);
  rect(200, 148, 3, 12, C.wood);
  rect(227, 148, 3, 12, C.wood);
  rect(206, 140, 12, 4, "#c99a5e");
}
