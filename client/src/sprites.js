// 16 x 16 pixel characters, drawn in code so the client ships with no image files.
// Legend: . clear, o outline, s skin, e eye, h hair/hood, H hood shade, c cloth, C cloth shade,
// a belt/trim, b boots, m metal, M metal shade, w apron, p pack, P pack shade, r cloak, R cloak shade.

const BASE = {
  o: "#1b1420", s: "#e8b48a", e: "#1b1420", b: "#4a3226", a: "#c99a3c",
  m: "#c9d1d9", M: "#7d8a99", w: "#f1ead8", p: "#9a6b3f", P: "#6b4527",
};

const SPRITES = {
  player: {
    pal: { h: "#3f7d3a", H: "#2a5527", c: "#4f9446", C: "#326b2d" },
    px: [
      "................",
      "......oooo......",
      ".....ohhhho.....",
      "....ohhhhhho....",
      "....ohHseHho....",
      "....ohHsesho....",
      "...ohhhsshhho...",
      "...occcaaccco...",
      "..osccccccccso..",
      "..osCccccccCso..",
      "...oaaaaaaaao...",
      "...oCccccccCo...",
      "....oCCooCCo....",
      "....obboobbo....",
      "...obbbo.obbbo..",
      "................",
    ],
  },
  kael: {
    pal: { h: "#2b1d16", r: "#b8322c", R: "#7d1f1c", c: "#5d5a66", C: "#3f3d47" },
    px: [
      "................",
      "......oooo......",
      ".....ohhhho.....",
      "....ohhhhhho.m..",
      "....ohseseho.m..",
      "....osssssso.m..",
      "......osso...m..",
      "...orrrmmrrrom..",
      "..orrrrmmrrrrao.",
      "..osRrccccrRso..",
      "...oaaaaaaaao...",
      "...oRccccccRo...",
      "....oCCooCCo....",
      "....obboobbo....",
      "...obbbo.obbbo..",
      "................",
    ],
  },
  brenna: {
    pal: { c: "#3a6ab8", C: "#28487f", h: "#8a5a2b" },
    px: [
      ".m..............",
      "mmm...oooo......",
      ".m...oMmmMo.....",
      ".m..oMmmmmMo....",
      ".m..oMseseMo....",
      ".m..oMssssMo....",
      ".m..ooosssoo....",
      ".m.ommccccmmo...",
      ".mosmccmmccmso..",
      ".mosCcccccccso..",
      ".m.oaaaaaaaao...",
      ".m.oCccccccCo...",
      ".m..oMMooMMo....",
      ".m..obboobbo....",
      ".m.obbbo.obbbo..",
      "................",
    ],
  },
  mags: {
    pal: { h: "#a8452a", c: "#7a4f8a", C: "#563766" },
    px: [
      "................",
      ".......oo.......",
      "......ohho......",
      ".....ohhhho.....",
      "....ohhhhhho....",
      "....ohseseho....",
      "....ohssssho....",
      "...occwwwwcco...",
      "..osccwwwwccso..",
      "..oscwwwwwwcso..",
      "...ocwwwwwwco...",
      "...ocwwwwwwco...",
      "...oCCCCCCCCo...",
      "....oCCCCCCo....",
      ".....obbobbo....",
      "................",
    ],
  },
  odo: {
    pal: { h: "#6b5b3a", c: "#c48a2c", C: "#8f6420" },
    px: [
      "................",
      "......oooo......",
      ".....ohhhho.....",
      "...ohhhhhhhho...",
      "....osesesso....",
      "....osssssso....",
      "..oo..osso......",
      ".opPocccccco....",
      ".opPoscccccso...",
      ".opPocccccco....",
      ".opPoaaaaaao....",
      ".oPPocccccco....",
      "..oo.oCCoCCo....",
      ".....obboobbo...",
      "....obbbo.obbbo.",
      "................",
    ],
  },
};

const cache = new Map();

/** An offscreen 16x16 canvas for a character; ghost=true gives a pale dashed-looking silhouette. */
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

export const SPRITE_IDS = Object.keys(SPRITES);
export const SPRITE_ROWS = Object.fromEntries(Object.entries(SPRITES).map(([k, v]) => [k, v.px]));
