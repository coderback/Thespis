# Before the Ice Goes Out (Godot)

The Godot game from [the design](../../docs/before-the-ice-goes-out.md). Godot 4.7, Forward+. This is the first
step of the build: the town on the desk, drawn live in the pixel style, with the paper over it and Anton's walk.
Thespis isn't wired in yet; the game file comes next.

## What's here

| Path | What it is |
| --- | --- |
| `assets/town.glb`, `assets/town.json` | The town, exported from the Blender builder, and what Godot needs to stage it: each material's colours and grain, the lamps, the people, chimneys, places, routes, the camera |
| `assets/sprites/` | The townsfolk, 32x48 (from [art/before-the-ice](../../art/before-the-ice/README.md)) |
| `scripts/main.gd` | The screen: the town rendered at 960x540 and scaled up by whole pixels, the paper on top at full size |
| `scripts/town.gd` | Stages the model: the toon material on every surface, the desk lamp and the small lamps, sprites, smoke, the camera from the river, the outline pass |
| `scripts/paper.gd` | The cartouche, the prompt, and a flag pinned to each place |
| `scripts/walk.gd` | Pick a flag and Anton walks there: red behind him, dashed ahead, click to skip |
| `shaders/toon.gdshader` | The Blender look, live: the desk lamp's light cut into bands (cold blue to warm), falling off with distance and at the edge of its cone; each surface's colour a noise ramp in its own space, as the Blender materials are |
| `shaders/outline.gdshader` | One-pixel ink lines on silhouettes and creases, as Freestyle draws them |
| `tools/shot.py` | Saves what the game draws, to compare with the Blender renders |

## Run it

Open the folder in Godot 4.7 and press Play, or:

```
godot --path games/before-the-ice
python games/before-the-ice/tools/shot.py --godot <Godot 4.7 console build>                       # shots/town.png
python games/before-the-ice/tools/shot.py --godot <...> --out shots/walk.png --walk=dest --at=0.5  # mid-walk
```

## Changing the town

The model is built in Blender by [`art/before-the-ice/blender/build_town.py`](../../art/before-the-ice/blender/build_town.py).
After changing it, export again and copy both files here:

```
EXPORT=<dir> MODE=town SPRITES=art/before-the-ice/sprites blender -b --factory-startup --python art/before-the-ice/blender/build_town.py -- unused.png unused.json
```

The Blender render is the reference for the look; the Godot picture should match it band for band. Two things are
done differently: the desk lamp is a directional light (for its shadows) with the spot's falloff and cone worked
in the shader, and coloured light (the forge) is drawn as warm pools, because the bands keep only brightness.
