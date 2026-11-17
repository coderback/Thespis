# Run: python kit_sheet.py <kit dir> <town render, 960x540> <out dir>
# Pairs each kit close-up with the same piece cropped from the game render (pixel for pixel, scaled up), one card each.
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

KIT, GAME, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
crops = json.load(open(os.path.join(KIT, "crops.json"), encoding="utf-8"))
game = Image.open(GAME).convert("RGB")  # 960x540 native


def font(names, size):
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default()


f = font(["C:/Windows/Fonts/GeorgiaPro-Bold.ttf", "georgiab.ttf", "DejaVuSerif-Bold.ttf"], 22)
g = font(["C:/Windows/Fonts/GeorgiaPro-Regular.ttf", "georgia.ttf", "DejaVuSerif.ttf"], 15)
os.makedirs(OUT, exist_ok=True)
for key, c in crops.items():
    det = Image.open(os.path.join(KIT, key + ".png")).convert("RGB")
    x0, y0, x1, y1 = c["box"]
    s = 960 / 1280
    box = (max(0, int(x0 * s)), max(0, int(y0 * s)), min(960, int(x1 * s)), min(540, int(y1 * s)))
    crop = game.crop(box)
    k = max(1, min(480 // max(1, crop.width), 360 // max(1, crop.height)))
    crop = crop.resize((crop.width * k, crop.height * k), Image.NEAREST)
    card = Image.new("RGB", (640 + 24 + 480 + 40, 540), (239, 230, 208))
    d = ImageDraw.Draw(card)
    d.text((20, 14), c["label"], fill=(42, 33, 26), font=f)
    card.paste(det, (20, 50))
    card.paste(crop, (684, 50))
    d.text((20, 510), "close up (kit)", fill=(90, 74, 54), font=g)
    d.text((684, 50 + crop.height + 8), f"in the game render, at {k}x", fill=(90, 74, 54), font=g)
    card.save(os.path.join(OUT, key + ".png"))
print("cards:", len(crops))
