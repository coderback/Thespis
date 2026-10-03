// The static map, painted once into an 18 x 12 tile (288 x 192 px) offscreen canvas.
// Road left to right, a river under the bridge, one building per stop.

export const TILE = 16;
export const COLS = 18;
export const ROWS = 12;
export const ROAD_Y = 7; // the road's tile row; characters stand on it

const C = {
  grass: "#5b7a3a", grass2: "#4f6c33", grass3: "#6a8a44", flower: "#d8c25a", flower2: "#c96f8a",
  road: "#a88a5c", road2: "#97794d", roadEdge: "#7d6440",
  water: "#3d6d8c", water2: "#335c78", waterHi: "#6f9fbd", bank: "#6b5634",
  wood: "#7a5232", wood2: "#5e3e25", woodHi: "#93673f", roof: "#8c3b2a", roof2: "#6e2c1f",
  stone: "#8a8a80", stone2: "#6c6c64", stoneHi: "#a5a59a", dark: "#1f1a1c", window: "#2a2430",
  awning: "#b8433a", awning2: "#efe4cf", trunk: "#5a3e24", leaf: "#3f6a2c", leaf2: "#34582a", leafHi: "#53843a",
};

export const WINDOWS = []; // [x, y, w, h] in world px, lit at night
export const TORCH = { x: 10 * TILE + 3, y: 5 * TILE + 4 };

function rng(seed) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

export function paintWorld() {
  const cv = document.createElement("canvas");
  cv.width = COLS * TILE;
  cv.height = ROWS * TILE;
  const g = cv.getContext("2d");
  const r = rng(7);
  const rect = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
  WINDOWS.length = 0;

  // Ground.
  rect(0, 0, cv.width, cv.height, C.grass);
  for (let i = 0; i < 900; i++) rect(Math.floor(r() * cv.width), Math.floor(r() * cv.height), 1, 1 + Math.floor(r() * 2), r() < 0.5 ? C.grass2 : C.grass3);
  for (let i = 0; i < 40; i++) {
    const x = Math.floor(r() * cv.width), y = Math.floor(r() * cv.height);
    if (Math.abs(y - (ROAD_Y * TILE + 8)) > 14) rect(x, y, 1, 1, r() < 0.5 ? C.flower : C.flower2);
  }

  // River: a vertical band under the bridge (tile x 12).
  const rx = 12 * TILE - 2, rw = TILE + 4;
  rect(rx - 2, 0, rw + 4, cv.height, C.bank);
  rect(rx, 0, rw, cv.height, C.water);
  for (let y = 0; y < cv.height; y += 3) {
    rect(rx + Math.floor(r() * (rw - 5)), y, 3 + Math.floor(r() * 3), 1, r() < 0.5 ? C.water2 : C.waterHi);
  }

  // Road.
  const ry = ROAD_Y * TILE;
  rect(0, ry - 1, cv.width, TILE + 2, C.roadEdge);
  rect(0, ry, cv.width, TILE, C.road);
  for (let i = 0; i < 260; i++) rect(Math.floor(r() * cv.width), ry + 1 + Math.floor(r() * (TILE - 2)), 2, 1, C.road2);

  // Bridge planks over the river.
  rect(rx - 6, ry - 4, rw + 12, TILE + 8, C.wood2);
  for (let x = rx - 6; x < rx + rw + 6; x += 3) rect(x, ry - 3, 2, TILE + 6, C.wood);
  rect(rx - 6, ry - 5, rw + 12, 2, C.woodHi);
  rect(rx - 6, ry + TILE + 3, rw + 12, 2, C.wood2);
  for (const px of [rx - 6, rx + rw + 4]) { rect(px, ry - 8, 2, 6, C.wood2); rect(px, ry + TILE + 3, 2, 6, C.wood2); }

  // Tavern (tiles 1..3, rows 3..6).
  const tx = 1 * TILE, ty = 3 * TILE + 4;
  rect(tx - 2, ty - 10, 3 * TILE + 4, 12, C.roof2);
  for (let i = 0; i < 6; i++) rect(tx - 2 + i * 2, ty - 10 - i * 2, 3 * TILE + 4 - i * 4, 2, i % 2 ? C.roof : C.roof2);
  rect(tx, ty, 3 * TILE, 3 * TILE - 6, C.wood);
  for (let y = ty + 3; y < ty + 3 * TILE - 6; y += 4) rect(tx, y, 3 * TILE, 1, C.wood2);
  rect(tx + 20, ty + 22, 8, 20, C.dark); // door
  rect(tx + 21, ty + 23, 6, 19, C.wood2);
  for (const wx of [tx + 5, tx + 35]) { rect(wx, ty + 10, 8, 8, C.window); WINDOWS.push([wx, ty + 10, 8, 8]); rect(wx + 3, ty + 10, 1, 8, C.wood2); }
  rect(tx + 37, ty + 22, 12, 7, C.woodHi); rect(tx + 38, ty + 23, 10, 5, C.wood2); // sign
  rect(tx + 41, ty + 24, 4, 3, "#e3b54a");

  // Market stall (tiles 4..6).
  const mx = 4 * TILE + 2, my = 4 * TILE + 6;
  for (let i = 0; i < 7; i++) rect(mx + i * 6, my, 6, 9, i % 2 ? C.awning2 : C.awning);
  rect(mx, my + 9, 42, 2, C.wood2);
  rect(mx + 2, my + 11, 2, 18, C.wood2); rect(mx + 38, my + 11, 2, 18, C.wood2);
  rect(mx, my + 22, 42, 7, C.wood); rect(mx, my + 22, 42, 1, C.woodHi);
  const goods = ["#d8c25a", "#c94f3a", "#7fb04a", "#e09a3c", "#9a6bb0"];
  for (let i = 0; i < 9; i++) rect(mx + 3 + i * 4, my + 19, 3, 3, goods[i % goods.length]);
  rect(mx + 46, my + 18, 8, 10, C.wood2); rect(mx + 47, my + 19, 6, 8, C.wood); // crate

  // Guard post (tiles 8..9) and the gate at the east edge (tile 10.5).
  const gx = 8 * TILE - 2, gy = 2 * TILE + 6;
  rect(gx, gy, 22, 4 * TILE - 6, C.stone2);
  for (let y = gy; y < gy + 4 * TILE - 6; y += 5) for (let x = gx + ((y / 5) % 2 ? 0 : 3); x < gx + 22; x += 7) rect(x, y, 6, 4, C.stone);
  for (let x = gx - 1; x < gx + 23; x += 5) rect(x, gy - 4, 3, 4, C.stone);
  rect(gx + 7, gy + 12, 7, 9, C.window); WINDOWS.push([gx + 7, gy + 12, 7, 9]);
  rect(gx + 6, gy + 4 * TILE - 20, 10, 14, C.dark);
  rect(gx + 26, gy + 26, 26, 22, C.wood); rect(gx + 26, gy + 24, 26, 3, C.wood2); // barracks hut
  rect(gx + 33, gy + 34, 6, 6, C.window); WINDOWS.push([gx + 33, gy + 34, 6, 6]);
  // gate posts across the road
  const gateX = 10 * TILE + 10;
  rect(gateX, ry - 14, 4, TILE + 18, C.wood2); rect(gateX, ry - 16, 4, 2, C.stoneHi);
  rect(gateX - 1, ry + TILE + 2, 6, 3, C.stone2);
  rect(TORCH.x - 1, TORCH.y, 2, 8, C.wood2);
  rect(TORCH.x - 2, TORCH.y - 3, 4, 3, "#f0a03a");

  // Crypt (tiles 14..16).
  const cx = 14 * TILE, cy = 3 * TILE;
  rect(cx - 2, cy + 6, 3 * TILE + 4, 3 * TILE - 4, C.stone2);
  for (let y = cy + 8; y < cy + 3 * TILE; y += 5) for (let x = cx + ((y / 5) % 2 ? 0 : 4); x < cx + 3 * TILE; x += 8) rect(x, y, 7, 4, C.stone);
  for (let i = 0; i < 5; i++) rect(cx - 2 + i * 5, cy + 6 - i * 3, 3 * TILE + 4 - i * 10, 3, i % 2 ? C.stone : C.stoneHi);
  rect(cx + 18, cy + 26, 12, 24, C.dark); rect(cx + 19, cy + 24, 10, 2, C.dark);
  rect(cx + 22, cy - 9, 4, 10, C.stoneHi); rect(cx + 19, cy - 6, 10, 3, C.stoneHi); // cross on top
  for (const [x, y] of [[13, 9], [15, 10], [17, 9], [16, 1]]) { // gravestones
    rect(x * TILE + 3, y * TILE + 2, 7, 10, C.stone2); rect(x * TILE + 4, y * TILE + 1, 5, 2, C.stone); rect(x * TILE + 3, y * TILE + 12, 8, 2, C.grass2);
  }

  // Trees, kept off the road, river and buildings.
  const spots = [[0, 1], [3, 0], [6, 1], [7, 10], [1, 10], [4, 11], [10, 0], [10, 10], [14, 11], [17, 4], [0, 5], [11, 2], [5, 9]];
  for (const [x, y] of spots) tree(g, x * TILE, y * TILE);

  // Fence along the south of the road.
  for (let x = 0; x < 11 * TILE; x += 6) rect(x, ry + TILE + 6, 2, 6, C.wood2);
  rect(0, ry + TILE + 8, 11 * TILE, 1, C.wood);
  return cv;
}

function tree(g, x, y) {
  const rect = (a, b, w, h, col) => { g.fillStyle = col; g.fillRect(a, b, w, h); };
  rect(x + 6, y + 10, 4, 6, C.trunk);
  rect(x + 2, y + 3, 12, 9, C.leaf);
  rect(x + 4, y + 1, 8, 2, C.leaf);
  rect(x + 3, y + 4, 4, 3, C.leafHi);
  rect(x + 2, y + 10, 12, 2, C.leaf2);
  rect(x + 4, y + 16, 8, 1, "rgba(0,0,0,0.18)");
}
