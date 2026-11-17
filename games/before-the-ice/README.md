# Before the Ice Goes Out (Godot)

The Godot game from [the design](../../docs/before-the-ice-goes-out.md). Godot 4.7, Forward+. The town on the desk,
drawn live in the pixel style, with the paper over it and Anton's walk; and the week, played through Thespis: nine
people who believe what they saw and what they're told, an Inspector whose questions and choices follow what he
believes, and the steamer at the end.

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
| `coldwater.toml` | The minds: the nine people, what each keeps quiet, the town's ties, Gilchrist's evening questions, rounds and steamer, the player's words. `thespis check coldwater.toml` checks it |
| `case.json` | The world's side, which the game and `tests/test_coldwater.py` both play: the week, the night of the fire as the observations the minds start from, how Tamás remembers, who sees each way |
| `scripts/case.gd` | The rules: the clock, who is where, what Anton's acts do and who sees them, Gilchrist's rounds and evenings, Tamás's memory, the steamer and the Notebook |
| `scripts/talk.gd` | The talk panel: whom Anton speaks to, what they say, his own words (read by `understand`) and the acts as buttons |
| `addons/thespis/` | The Godot addon, a copy of [sdk/godot/addons/thespis](../../sdk/godot/addons/thespis) (a test keeps the two the same) |
| `tools/week.tscn` | Plays a whole week headless through a sidecar and checks it holds (CI runs it) |
| `tools/shot.py` | Saves what the game draws, to compare with the Blender renders |

## Run it

Open the folder in Godot 4.7 and press Play, or:

```
godot --path games/before-the-ice                       # a new week; -- --seed=7 for a given one
godot --headless --path games/before-the-ice res://tools/week.tscn -- --seed=7   # a whole week, checked
python games/before-the-ice/tools/shot.py --godot <Godot 4.7 console build>                       # shots/town.png
python games/before-the-ice/tools/shot.py --godot <...> --out shots/walk.png --walk=dest --at=0.5  # mid-walk
```

Thespis runs as a sidecar the addon starts: the packaged runtime as `thespis/` beside the game's executable, else
`python -m thespis`. From a clone, point it at your Python and the repository:

```
THESPIS_SIDECAR='["<python>", "-m", "thespis"]' PYTHONPATH=<repo> godot --path games/before-the-ice
```

With no model the town speaks the game file's own lines and plays the same; `thespis/sidecar/model` in Project
Settings gives it a local one. Without Thespis at all the town still draws and Anton still walks.

## How a week plays

Each day has a morning, an afternoon and an evening. Pick a flag and Anton walks there: whoever has that way in
view sees him go (Front Street from the landing, the porch, the post and the infirmary; the lane only from the
store and Maggie's kitchen; the ice from the landing). At the place, speak to whoever is there, in your own words
or with the acts: ask about that night, tell them something, give money, comfort, threaten, confess. **Let the day
go on** moves the town a phase: people walk, news passes along the ties, Gilchrist makes his rounds. Each evening
ends at the post with Gilchrist's question, and after the fifth the ice goes out and he boards the steamer.

## Changing the town

The model is built in Blender by [`art/before-the-ice/blender/build_town.py`](../../art/before-the-ice/blender/build_town.py).
After changing it, export again and copy both files here:

```
EXPORT=<dir> MODE=town SPRITES=art/before-the-ice/sprites blender -b --factory-startup --python art/before-the-ice/blender/build_town.py -- unused.png unused.json
```

The Blender render is the reference for the look; the Godot picture should match it band for band. Two things are
done differently: the desk lamp is a directional light (for its shadows) with the spot's falloff and cone worked
in the shader, and coloured light (the forge) is drawn as warm pools, because the bands keep only brightness.
