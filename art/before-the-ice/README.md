# Before the Ice Goes Out: art drafts

Working art for the town-on-a-desk direction in [the design](../../docs/before-the-ice-goes-out.md). These are
drafts and stand-ins, not final art. Nothing here is imported by Thespis or its tests.

## The town in Blender (`blender/`)

`build_town.py` builds Coldwater Landing to the town plan in [the design](../../docs/before-the-ice-goes-out.md) and
looks at it from the river: the ice with the tripod and the steamer laid up in front, the landing, Front Street with
every building facing the river (your cabin, Maggie's roadhouse, Brand's burned store, the forge, the Mounted Police
post, the mission), spruce on the bench behind, and Věra's cabin and claim across the ice at the creek mouth. It renders
pixel style: EEVEE at 960x540, light in bands (warm lamplight, cold blue shadow), 1-pixel ink outlines, the townsfolk as
camera-facing sprites. It also writes the screen positions of places and people, which the screens use to pin flags.

```
MODE=town SPRITES=<path to sprites> blender -b --factory-startup --python blender/build_town.py -- town.png town-anchors.json [town.blend]
MODE=walk SPRITES=<path to sprites> blender -b --factory-startup --python blender/build_town.py -- walk.png walk-anchors.json
python blender/pixelate.py town.png town-960.png town-1080.png
```

`MODE=walk` moves Anton onto the ice and draws his route: solid behind him, dashed ahead, the back way faint.
Optional settings: `RES` (render width, default 960), `ORTHO` (camera width in scene units, default 46), `CAMX`
(camera position along the river), `LAMP` (desk lamp watts), `BAND_SCALE` (where the light bands fall).
`pixelate.py` takes the render down to 128 colours and doubles it by whole pixels for a 1920x1080 screen.

**Piece by piece.** With `KIT=<dir>` the script renders each part of the town on its own instead (your cabin, the
roadhouse, the store, the forge, the post, the mission, the landing, the steamer, the tripod, the spruce point, Věra's
claim, the bench, the street, the people), close up at 640x480 from the same angle, and writes where each sits in
the game view. `KITONLY=forge,store` renders just those. `kit_sheet.py` pairs each close-up with the same piece cut
from the game render, so detail can be checked at both sizes:

```
KIT=kit MODE=town SPRITES=<path to sprites> blender -b --factory-startup --python blender/build_town.py -- unused.png unused.json
python blender/kit_sheet.py kit town-960.png kit/cards
```

**For the game.** With `EXPORT=<dir>` the script writes the town as `town.glb` and, in `town.json`, what the Godot
game needs to stage it (each material's colours and grain, the lamps, people, chimneys, places, routes, the camera)
instead of rendering. The game is in [`games/before-the-ice`](../../games/before-the-ice/README.md).

- `coldwater_lib.py`: materials, primitives and the log-cabin builder the town uses (logs, gables, snow on the roof,
  icicles, doors and lit windows, an open forge door with the fire in it, woodpiles).
- `build_test.py`: the first test, Maggie's roadhouse and one cabin, rendered in Cycles. Run with `STYLE=toon` or
  `STYLE=pixel` and `--python stylize.py` after it for the cel-shaded and pixel versions.

Made with Blender 5.2. Building the town takes about six minutes, most of it the spruce and the logs; each render,
seconds.

## Sprites and portraits

- `sprites/`: the ten townsfolk, 32x48 each, drawn by `sprites/people.py` from a few traits apiece (coat, hat,
  skin...): `python sprites/people.py sprites [who ...]`. It's a port of the prototype's `drawPerson` and draws the
  first seven exactly as the prototype did; Tamás, Otto and Martha were added after, in their portraits' colours.
  They stand in the Blender town as camera-facing cut-outs. Copy them to `games/before-the-ice/assets/sprites/`.
- `portraits/`: half-length conversation portraits, 64x80 with an ink outline and a paper-white cut-out edge, each
  drawn pixel by pixel by its own script: `python portraits/<who>.py <who>.png 5`. Maggie Doyle with a mug of coffee;
  Tamás Kovács in the infirmary blanket, his head bandaged and the back of his hand burned; Otto Brand with a scorched
  ledger; Martha Matthias sewing a hide glove. `kit.py` is what the later three share.
- `portraits/ai/`: the portraits the game uses now, all nine, made with an image model from the prompts in
  [`portraits/ai/PROMPTS.md`](portraits/ai/PROMPTS.md) (the record for store disclosure), kept here restored to their
  own 74x99 grid. `python portraits/from_ai.py <model's image> games/before-the-ice/assets/portraits/<who>.png
  portraits/ai/<who>.png` restores one, cuts it out and frames it x4 for the conversation screen. The hand-drawn
  portraits above stay as the fallback.

## The earlier prototype (`prototype/`)

`desk-render.html` is the three.js version of the town that came before Blender. It draws the first seven sprites, and
`?dump` prints screen positions.
