# Portraits made with an image model: the prompts

The portraits in this folder were made with Google's Nano Banana (Gemini image) from the prompts below, then put
into the game's format with [`../from_ai.py`](../from_ai.py): the model's large image restored to its own pixel grid
(74x99), background cut out, bottom cut flat, framed and scaled x4 so the conversation screen draws it pixel for pixel.
The restored 74x99 drawings are kept here as `<who>.png`. The hand-drawn kit portraits (`../<who>.py`) stay as a fallback. This file is the record of what was made
with a model, for store disclosure (Steam asks games to disclose AI-generated content).

**How to run one.** Attach two or three finished portraits as style references (`games/before-the-ice/assets/portraits/`:
`gilchrist.png`, `vera.png`, `maggie.png`), start with the style line, then the person's line. Ask for the full
image on a flat slate background (106, 126, 129). Don't ask for a small version: the model's own downscale loses the
props (Billy's logs became boards); `from_ai.py` restores the full image instead.

> **Style:** Pixel-art half-length portrait on a 64×80 pixel grid, shown scaled up with hard square pixels: no
> anti-aliasing, no gradients, flat colour shapes with two or three tones each, light from the left. A 1-pixel
> near-black outline and a thick cream paper cut-out border around the figure, the bottom cut flat, plain flat
> background, facing the viewer. Match the attached reference portraits exactly in style, proportions, pixel size and
> palette. A Klondike gold-rush river town on the Yukon, April 1898.

Each line keeps to the person's town-figure colours (`../../sprites/people.py`), so the portrait and the figure on the
model match.

## Made (18 November 2026)

All nine, from the second round ("Gilchrist style"), whose pixels are a clean 12x12 grid.

1. **Gilchrist.** Inspector Gilchrist of the North-West Mounted Police, a Scot in his forties. Scarlet serge tunic
   with brass buttons and a dark blue stand collar, a brown leather Sam Browne strap across the chest, a round
   dark-brown fur winter cap. Ginger hair going grey at the temples, a full moustache. Patient, slightly hooded eyes.
   He holds a small open notebook and a pencil. Polite, unhurried, missing nothing.
2. **Věra.** Věra Holub, a Czech widow in her mid-thirties, practical and dry. A rust-red wool headscarf tied under
   the chin, dark hair parted beneath it. A blue-grey wool coat over a black mourning dress with a small jet brooch.
   She holds a chipped blue enamel tin mug in both hands. One eyebrow slightly raised; she knows more than she's
   saying.
3. **Sándor.** Sándor Kovács, a young Hungarian-American blacksmith's son, about 24. Broad shoulders, a slate-blue work
   jacket over an open collarless shirt, a brown leather forge apron, a grey flat cap pulled low. A short dark beard.
   His right hand is a clenched fist, the palm and wrist wrapped in a bloodied bandage. Brows drawn down hard; angry,
   wanting someone to pay.
4. **Billy.** Billy Tuck, an orphan wood boy of about 13 from San Francisco. Ginger hair, freckles, ears that stick
   out. A man's brown coat far too big for him, with a patched elbow, and a red wool muffler. A dark cloth cap pushed
   back. He carries an armful of split cordwood across his chest. A cheeky gap-toothed grin, but his eyes slide to one
   side, in case it's the police.
5. **Ashby.** A man who calls himself Jack Ashby, about 35, a drifter. A long dark wool coat with the collar turned
   up, a collarless off-white shirt, a black wide-brimmed hat with a dented crown worn low. A week's stubble, a long
   face. An unlit match in the corner of his mouth. An easy half-smile, eyes narrowed and looking off to the side from
   under the brim.

6. **Maggie.** Maggie Doyle, an Irish roadhouse keeper from Cork, in her forties. Warm but shrewd, the town's quickest
   tongue. Copper-red hair pinned up in a bun, a few freckles, cheeks flushed from the stove. A dark red wool dress, a
   slate-blue shawl crossed over her chest and knotted, a white apron. A tin coffee mug in one hand. A knowing
   half-smile, one eyebrow up, eyes sizing you up.
7. **Tamás.** Tamás Kovács, an old Hungarian blacksmith turned night watchman, about sixty, sitting up in the mission
   infirmary after the fire. White hair under a clean white bandage wound round his head, a big grey moustache, a
   feverish flush. A grey wool blanket with a dark red stripe round his shoulders over a pale nightshirt, his burned
   hand wrapped in a bandage held against his chest. Tired, ashamed eyes looking a little past you, trying to remember.
8. **Otto.** Otto Brand, a German trader and money-lender from Hamburg, about fifty. Dark hair oiled flat with a
   parting, side-whiskers grown into a waxed moustache turned up at the ends. A dark green frock coat over a mustard
   waistcoat with a gold watch chain, a high starched white collar and a dark tie, a signet ring. A scorched,
   leather-bound ledger held against his chest, soot on one cuff. One eyebrow raised, a thin smile: already pricing
   you.
9. **Billy, again** (used for Billy). As 4, but: he carries three or four long split logs in his arms, bark on their backs and pale
   split faces showing, not a stack of boards.
## To make

10. **Anton** (optional; the player, for the ending or the casebook). Anton Holub, a Czech miner about thirty, wiry
    and weathered. A dark olive-green checked mackinaw coat, a brown fur-lined cap with the earflaps up, a mustard
    wool scarf. Dark stubble, dark hair under the cap. He holds an unlit tin lantern at his side. A guarded, tired
    look, straight at you: a decent man with something to hide.

## Martha: made with a model, the Hän reader still to see it

Martha Matthias is the one Hän woman in the game, and the design gives her portrait to a paid Hän sensitivity reader,
from the Tr'ondëk Hwëch'in Heritage department, before release ([before-the-ice-han-1898.md](../../../../docs/before-the-ice-han-1898.md)).
Image models tend to reach for stereotype: beadwork, regalia, feathers, a "noble" pose. The line below keeps
clear of all that. We chose to put the model-made portrait in the game now; it goes before the reader with the rest
of her before release, and if they ask for changes or for the hand-drawn one (`../martha.py`), that's what ships.

11. **Martha.** Martha Matthias, a Hän woman in her thirties from the people building new cabins downriver, plain-spoken
    and fluent in English, her own opinions. Dressed as women in town dressed in 1898, in store cloth: a dark green
    trade-cloth dress with a small pale print and a plain band collar, a navy cotton kerchief with small white dots
    tied at the nape. She's sewing: a half-made smoked-moosehide glove in one hand, needle and thread drawn up in the
    other. Black hair parted under the kerchief. A level look straight back at whoever's asking. No beadwork, no
    jewellery, no feathers, nothing ceremonial or symbolic, and no costume: an ordinary working woman, herself.
