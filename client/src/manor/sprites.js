// The manor's people as 16 x 16 pixel characters, drawn in code like The Crypt Road's (src/sprites.js).
// Legend: . clear, o outline, s skin, e eye, h hair, H hair shade, c cloth, C cloth shade, a trim, b shoes,
// w white (collar, apron, cap, pearls), g gem, k black cloth, K black shade, t hat, T hat brim.

const BASE = { o: "#1b1420", s: "#e8b48a", e: "#1b1420", b: "#3a2a22", w: "#f1ead8", g: "#c0396b", k: "#25212b", K: "#151219" };

export const SPRITES = {
  player: { // a detective: brown hat and coat, red scarf
    pal: { t: "#5a3e2b", T: "#3f2a1c", c: "#9a7a4e", C: "#73583a", a: "#b8433a" },
    px: [
      "................",
      ".....tttttt.....",
      "....tttttttt....",
      "...oTTTTTTTTo...",
      "....osesesso....",
      "....ossssso.....",
      "...oaaaaaaao....",
      "..occcccccccco..",
      "..osccccccccso..",
      "..osCccccccCso..",
      "...oCccccccCo...",
      "...oCcccoccCo...",
      "....oCCooCCo....",
      "....obboobbo....",
      "...obbbo.obbbo..",
      "................",
    ],
  },
  vane: { // Lady Vane: grey updo, pearls, a purple gown with gold trim
    pal: { h: "#c9c3d3", H: "#8f88a0", c: "#6b3d8f", C: "#4a2766", a: "#d8b04a" },
    px: [
      "................",
      "......oooo......",
      ".....ohhhho.....",
      "....ohHhhHho....",
      "....ohsesesho...",
      "....ohsssssho...",
      ".....owgwgwo....",
      "....occaaacco...",
      "...occcccccco...",
      "...osCccccCso...",
      "...oCcccccccCo..",
      "..oCcccccccccCo.",
      "..oCcacccccacCo.",
      ".oCcccccccccccCo",
      ".oooooooooooooo.",
      "................",
    ],
  },
  pell: { // the butler: black tailcoat, white collar, a dark bow tie
    pal: { h: "#5d5866", a: "#2b1d33" },
    px: [
      "................",
      "......oooo......",
      ".....ohhhho.....",
      "....ohhhhhho....",
      "....osesesso....",
      "....ossssso.....",
      "...okkwawkko....",
      "..okkkwwwkkko...",
      "..oskkkwkkkso...",
      "..oskkkwkkkso...",
      "...okkkkkkko....",
      "...oKkkokkKo....",
      "...oKKo.oKKo....",
      "....obbo.obbo...",
      "...obbbo.obbbo..",
      "................",
    ],
  },
  sable: { // the maid: white cap and apron over a black dress
    pal: { h: "#6b4527" },
    px: [
      "................",
      "......wwww......",
      ".....owwwwo.....",
      "....ohhhhhho....",
      "....ohesesho....",
      "....ohssssho....",
      ".....osssso.....",
      "....okkwwkko....",
      "...oskwwwwkso...",
      "...oskwwwwkso...",
      "...okkwwwwkko...",
      "..okkkwwwwkkko..",
      "..oKkkkkkkkkKo..",
      "...ooooooooo....",
      "....obo..obo....",
      "................",
    ],
  },
};

const cache = new Map();

/** An offscreen 16x16 canvas for a character; ghost=true gives a pale dashed silhouette for "last seen". */
export function sprite(id, { ghost = false } = {}) {
  const key = `${id}:${ghost}`;
  if (cache.has(key)) return cache.get(key);
  const def = SPRITES[id];
  const c = document.createElement("canvas");
  c.width = c.height = 16;
  const g = c.getContext("2d");
  const pal = { ...BASE, ...def.pal };
  def.px.forEach((row, y) => {
    for (let x = 0; x < 16; x++) {
      const ch = row[x] || ".";
      if (ch === ".") continue;
      if (ghost) {
        if (ch !== "o" || (x + y) % 2) continue; // every other outline pixel: a dashed outline
        g.fillStyle = "#e6e0d0";
      } else g.fillStyle = pal[ch] || "#ff00ff";
      g.fillRect(x, y, 1, 1);
    }
  });
  cache.set(key, c);
  return c;
}
