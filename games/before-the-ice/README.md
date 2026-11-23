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
| `assets/fonts/` | The period faces the canvas sets the paper in, each with its licence: Old Standard TT, IM Fell English SC and Cedarville Cursive (SIL Open Font License), Special Elite (Apache 2.0), from [google/fonts](https://github.com/google/fonts). `scripts/fonts.gd` loads them |
| `assets/portraits/` | Half-length conversation portraits, all nine, made with an image model and restored to their pixel grid (`art/before-the-ice/portraits/ai/`). Anyone without one is shown by their figure, scaled up |
| `scripts/main.gd` | The screen: the town rendered at 960x540 and scaled up by whole pixels, the paper on top at full size |
| `scripts/town.gd` | Stages the model: the toon material on every surface, the desk lamp and the small lamps, sprites, smoke, the camera from the river, the outline pass. The townsfolk stand where the session says they are, on spots out in the open at each place; when the town moves, each one who moved walks to the new place along the street (and down the landing to the ice), and anyone going downriver fades from the model |
| `scripts/paper.gd` | The cartouche, the prompt, and a flag pinned to each place |
| `scripts/walk.gd` | Pick a flag and Anton walks there: red behind him, dashed ahead, click to skip |
| `shaders/toon.gdshader` | The Blender look, live: the desk lamp's light cut into bands (cold blue to warm), falling off with distance and at the edge of its cone; each surface's colour a noise ramp in its own space, as the Blender materials are |
| `shaders/outline.gdshader` | One-pixel ink lines on silhouettes and creases, as Freestyle draws them |
| `shaders/dim.gdshader` | The town behind a conversation: zoomed in on the place, darkened, washed out and softly blurred |
| `coldwater.toml` | The minds: the nine people, what each keeps quiet, the town's ties, Gilchrist's evening questions, rounds and steamer, the player's words. `thespis check coldwater.toml` checks it |
| `case.json` | The world's side, which the game and `tests/test_coldwater.py` both play: the days, the night of the fire as the observations the minds start from, how Tamás remembers, who sees each way, and what the seed varies (`week`: draws with weighted options, and the rules every week keeps), and the pressure director (`director`: how pressure is measured, the target by day, and the incidents it may bring out) |
| `scripts/case.gd` | The rules: the clock, who is where, what Anton's acts do and who sees them, Gilchrist's rounds and evenings, Tamás's memory, the steamer and the Notebook |
| `scripts/journal.gd` | A playtest's record of the week, written when the ice goes out (or the window closes): what the seed drew; each phase, what Anton did and heard and what was said where he wasn't; each morning, what Gilchrist believed and whom the town still trusted; the ending and the Notebook. JSON and a Markdown page, in `user://playtest` ([the playtest kit](../../docs/before-the-ice-playtest.md)) |
| `scripts/talk.gd` | A conversation, as the canvas's ConversationDesk draws it: the town zoomed and dimmed behind, the place card, a half-length portrait with a pinned name tag, what they say on a sheet, numbered answers that say what they may cost (keys 1 to 4), a ruled line for Anton's own words (read by `understand`), the note of what they have from him with the red string of who they told, and the way out. Four answers a visit |
| `addons/thespis/` | The Godot addon, a copy of [sdk/godot/addons/thespis](../../sdk/godot/addons/thespis) (a test keeps the two the same) |
| `tools/week.tscn` | Plays a whole week headless through a sidecar and checks it holds, that the weeks seeds 1 to 500 make keep the rules, and that the week's record is kept and written (CI runs it) |
| `tools/sweep.tscn` | The seed sweep: plays whole weeks headless, ten fixed ways of playing (lie low, an alibi, blame Ashby, the true thing, the watchman's lamp, blame Otto, blame Billy, pay Billy, lose Věra, confess) over many seeds, and counts how each ended, by way of playing and by each thing the seed drew, whether the seed moves each way's ending, and how far Gilchrist's case against Anton got (what he believed, whether he warned and searched, whether he went to ask Otto and Billy), and the director: the pressure each morning against its target, and what it brought out. Does every ending stay reachable; does one way always win? About six seconds a week |
| `tools/tour.tscn` | A playthrough of the real screens: loads the game and plays a week the way a player would (flags, walks, answers, typed words, leaving, the evenings at the post, the ending and the Notebook), saving a screenshot and the screen's text at each step. Needs a window. Run it before a playtest, or after changing a screen |
| `tools/shot.py` | Saves what the game draws, to compare with the Blender renders |

## Run it

Open the folder in Godot 4.7 and press Play, or:

```
godot --path games/before-the-ice                       # a new week; -- --seed=7 for a given one; --log=<dir> or none for its record
godot --headless --path games/before-the-ice res://tools/week.tscn -- --seed=7   # a whole week, checked
godot --path games/before-the-ice res://tools/tour.tscn -- --seed=19 --out=<dir>        # the screens, played through
godot --headless --path games/before-the-ice res://tools/sweep.tscn -- --seeds=24 [--only=alibi,confess] [--out=sweep.json]
python games/before-the-ice/tools/shot.py --godot <Godot 4.7 console build>                       # shots/town.png
python games/before-the-ice/tools/shot.py --godot <...> --out shots/walk.png --walk=dest --at=0.5  # mid-walk
godot --path games/before-the-ice -- --seed=7 --talk=maggies --answer=2 --shot=talk.png          # a conversation
```

Thespis runs as a sidecar the addon starts: the packaged runtime as `thespis/` beside the game's executable, else
`python -m thespis`. From a clone, point it at your Python and the repository:

```
THESPIS_SIDECAR='["<python>", "-m", "thespis"]' PYTHONPATH=<repo> godot --path games/before-the-ice
```

On Windows, `play.cmd` (double-click) or `play.ps1 -Seed 19` does this for a playtest: it finds the Python and
Godot, asks for the seed, and shows where the week's record was saved (`-Editor` opens the editor set up the same way).

With no model the town speaks the game file's own lines and plays the same; `thespis/sidecar/model` in Project
Settings gives it a local one. Without Thespis at all the town still draws and Anton still walks.

### In a browser

The demo server plays it in a browser, for playtests: <https://thespis-production.up.railway.app/ice/?seed=19> (the
link's `seed` picks the week). The Dockerfile exports the game with `export_presets.cfg`'s "Web" preset, and
`games/ice/api.py` serves the build at `/ice/`, the Thespis it talks to at `/thespis` (this game loaded, no model,
nobody may put another game on it), and takes the week's record at `/ice/record`, sent each phase and at the steamer.
The admin token lists and fetches the records (`GET /ice/records`, `GET /ice/records/<name>.md`).

A browser draws with Godot's Compatibility renderer (`rendering_method.web` in `project.godot`), not Forward+. The
shaders keep the town's look on both: the outlines work out a surface's facing from the depth around it where there's
no normal buffer, and the toon shader corrects the light bands, lamp colour and windows, which Compatibility hands it
unconverted, and its lamps, which arrive pi times stronger. `--rendering-method gl_compatibility` shows it on the
desktop. To try the web build locally: export it (`godot --headless --path games/before-the-ice --export-release Web
build/web/index.html`, with the 4.7.2 web templates installed), copy `build/web` to `games/ice/web`, and run
`uvicorn games.crypt_road.app:app`; then open `http://127.0.0.1:8000/ice/?seed=19`.

## How a week plays

Each day has a morning, an afternoon and an evening. Pick a flag and Anton walks there: whoever has that way in
view sees him go (Front Street from the landing, the porch, the post and the infirmary; the lane only from the
store and Maggie's kitchen; the ice from the landing). At the place, speak to whoever is there, in your own words
or with the acts: ask about that night, tell them something, give money, comfort, threaten, confess. **Let the day
go on** moves the town a phase: people walk, news passes along the ties, Gilchrist makes his rounds. Each evening
ends at the post with Gilchrist's question, and after the fifth the ice goes out and he boards the steamer.

## Changing the town

The model is built in Blender by [`art/before-the-ice/blender/build_town.py`](../../art/before-the-ice/blender/build_town.py).
After changing it, export again and copy both files here (Blender reads `SPRITES` from its own folder, so give it in full):

```
EXPORT=<dir> MODE=town SPRITES=<absolute path to art/before-the-ice/sprites> blender -b --factory-startup --python art/before-the-ice/blender/build_town.py -- unused.png unused.json
```

The Blender render is the reference for the look; the Godot picture should match it band for band. Two things are
done differently: the desk lamp is a directional light (for its shadows) with the spot's falloff and cone worked
in the shader, and coloured light (the forge) is drawn as warm pools, because the bands keep only brightness.
