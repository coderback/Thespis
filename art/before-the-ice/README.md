# Before the Ice Goes Out: art drafts

Working art for the town-on-a-desk direction in [the design](../../docs/before-the-ice-goes-out.md). These are
drafts and stand-ins, not final art. Nothing here is imported by Thespis or its tests.

## The town in Blender (`blender/`)

`build_town.py` builds the whole of Coldwater Landing on its plinth (log cabins, the roadhouse's false front, the
burned store, the steamer frozen in, the landing and tripod, the boardwalk, the spruce, the townsfolk) and renders it
pixel style: EEVEE at 960x540, light in bands (warm lamplight, cold blue shadow), 1-pixel ink outlines. It also
writes the screen positions of places and people, which the screen drafts use to pin flags onto the model.

```
MODE=town  SPRITES=<path to sprites> blender -b --factory-startup --python blender/build_town.py -- town.png town-anchors.json [town.blend]
MODE=walk  SPRITES=<path to sprites> blender -b --factory-startup --python blender/build_town.py -- walk.png walk-anchors.json
```

`MODE=walk` moves Anton onto the ice and draws his route: solid behind him, dashed ahead, the back way faint.
Optional settings: `RES` (render width, default 960), `ORTHO` (camera width in scene units, default 50),
`LAMP` (desk lamp watts), `BAND_SCALE` (where the light bands fall). Scale the 960x540 image up by whole pixels.

- `coldwater_lib.py`: materials, primitives and the log-cabin builder the town uses.
- `build_test.py`: the first test, Maggie's roadhouse and one cabin, rendered in Cycles. Run with `STYLE=toon` or
  `STYLE=pixel` and `--python stylize.py` after it for the cel-shaded and pixel versions.

Made with Blender 5.2. Building the town takes about three minutes; the render itself, seconds.

## Sprites and portraits

- `sprites/`: the seven townsfolk, 32x48 each, drawn in `prototype/desk-render.html` (open it with
  `?mode=town&dump&sprites` to print them as PNG data). They stand in the Blender town as camera-facing cut-outs.
- `portraits/maggie.py`: Maggie Doyle's half-length conversation portrait, 64x80 with an ink outline and a paper-white
  cut-out edge, drawn pixel by pixel: `python portraits/maggie.py maggie.png 5`.

## The earlier prototype (`prototype/`)

`desk-render.html` is the three.js version of the town that came before Blender. It still draws the sprites, and
`?dump` prints screen positions.
