# The townsfolk as they stand in the model: 32x48 pixel figures, each given by a few traits (coat, hat, skin...)
# and drawn by one routine, with a 1-pixel ink outline. A port of drawPerson in prototype/desk-render.html, which
# drew the first seven; this draws them the same, pixel for pixel, and the three added since.
#   python sprites/people.py <out dir> [who ...]
import math
import os
import sys

from PIL import Image, ImageDraw

W, H = 32, 48
OUT = "#0e0d0c"
BOOT = "#2a1d16"

PEOPLE = {
    "anton": dict(coat="#4f5d3b", hat="earflap", hatC="#4a3524", skin="#e2b893", legs="#2c2a30", check=True, scarf="#8a6a3a", lantern=True),
    "maggie": dict(coat="#7a3030", skirt=True, skirtC="#5a2424", apron="#e6dccb", shawl="#3a4a5c", hat="bun", hatC="#9c4a22", skin="#efc6a0"),
    "sandor": dict(coat="#3d4a5c", hat="cap", hatC="#55585e", skin="#d9a882", legs="#2c2a30", beard="#3a2a1e", buttons="#1d2430"),
    "gilchrist": dict(coat="#b0261f", hat="fur", hatC="#3a2a1e", skin="#e8bf9a", legs="#1d2333", stripe="#c9a14a", belt="#c9a14a",
                      buttons="#e8c97a", tallBoots=True, bootC="#4a2e1a", mitt="#3a2616"),
    "billy": dict(coat="#6e5a3a", hat="cap", hatC="#3b3b3b", skin="#e8bf9a", legs="#3a3226", scarf="#a33a2a"),
    "ashby": dict(coat="#2c2c30", long=True, shirt="#d8d2c4", hat="brim", hatC="#151517", skin="#dcae88", legs="#26262a"),
    "vera": dict(coat="#3f5a6b", skirt=True, skirtC="#2a3540", hat="scarf", hatC="#9a3b2a", skin="#e2b893"),
    # the three the portraits came first for (portraits/), in the same colours
    # Tamás: the grey infirmary blanket round him over his nightshirt, the bandage, a grey moustache, bare-headed
    "tamas": dict(coat="#6c6c66", skin="#e2b696", legs="#d6ccb8", bootC="#3a2e26", hat="bandage", hatC="#faf7ee",
                  hair="#9e9c96", moustache="#9e9c96", blanket="#802c28", mitt="#e2b696"),
    # Otto: a long merchant's coat over the waistcoat and chain, a bowler, his whiskers
    "otto": dict(coat="#404840", long=True, vest="#84622c", chain="#dcb248", hat="bowler", hatC="#3a2a20", skin="#e8bc9c",
                 legs="#2a2622", moustache="#463428", whiskers="#463428", ledger="#602a22"),
    # Martha: the print dress, the kerchief over her hair, the glove she's sewing in her hand
    "martha": dict(coat="#405646", skirt=True, skirtC="#2e4236", dots="#8c9c80", hat="scarf", hatC="#2e3a5c", hatDots="#cec4a0",
                   skin="#b27c5a", glove="#c4965c"),
}


def rgb(c):
    if isinstance(c, tuple):
        return c
    n = int(c[1:], 16)
    return (n >> 16, (n >> 8) & 255, n & 255)


def shade(c, f):
    def one(v):
        x = v + (255 - v) * (f - 1) if f > 1 else v * f
        return max(0, min(255, math.floor(x + 0.5)))  # as JavaScript's Math.round
    return tuple(one(v) for v in rgb(c))


def Lt(c):
    return shade(c, 1.22)


def Dk(c):
    return shade(c, 0.7)


def draw(p: dict) -> Image.Image:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def px(x, y, w, h, c):
        if w > 0 and h > 0:
            d.rectangle((x, y, x + w - 1, y + h - 1), fill=rgb(c) + (255,))

    def clear(x, y):
        d.point((x, y), fill=(0, 0, 0, 0))

    g = p.get
    hem = 40 if g("long") else 36
    if not g("skirt"):
        px(12, 37, 3, 7, p["legs"])
        px(17, 37, 3, 7, p["legs"])
        px(12, 37, 1, 7, Lt(p["legs"]))
        px(19, 37, 1, 7, Dk(p["legs"]))
        if g("stripe"):
            px(12, 37, 1, 5, p["stripe"])
            px(19, 37, 1, 5, p["stripe"])
        bt = 40 if g("tallBoots") else 43
        bc = g("bootC") or BOOT
        px(11, bt, 4, 46 - bt, bc)
        px(17, bt, 4, 46 - bt, bc)
        px(11, 45, 4, 1, "#140e0b")
        px(17, 45, 4, 1, "#140e0b")
        px(11, bt, 1, 46 - bt - 1, Lt(bc))
    if g("skirt"):
        for y in range(33, 45):
            wd = (y - 33) // 3 + 1
            x0, x1 = 10 - wd, 21 + wd
            px(x0, y, x1 - x0 + 1, 1, p["skirtC"])
            px(x0, y, 2, 1, Lt(p["skirtC"]))
            px(x1 - 1, y, 2, 1, Dk(p["skirtC"]))
            if y % 4 == 1:
                px(x0 + 4, y, 1, 1, Dk(p["skirtC"]))
            if g("dots") and y % 3 == 0:  # a print in the cloth
                for x in range(x0 + 2 + y % 2, x1 - 1, 3):
                    px(x, y, 1, 1, p["dots"])
        px(12, 45, 3, 1, BOOT)
        px(17, 45, 3, 1, BOOT)
    for y in range(19, (33 if g("skirt") else hem) + 1):
        wd = max(0, (y - 30) // 3)
        x0, x1 = 10 - wd, 21 + wd
        px(x0, y, x1 - x0 + 1, 1, p["coat"])
        px(x0, y, 2, 1, Lt(p["coat"]))
        px(x1 - 1, y, 2, 1, Dk(p["coat"]))
    clear(10, 19)
    clear(21, 19)
    if g("long"):
        px(15, 31, 1, hem - 30, Dk(p["coat"]))
    if g("shirt"):
        px(14, 19, 4, 6, p["shirt"])
        px(15, 19, 2, 5, "#1a1a1a")
    if g("vest"):  # the coat open on a waistcoat, a watch chain across it, a white collar and dark tie
        px(13, 19, 6, 12, p["vest"])
        px(16, 19, 3, 12, Dk(p["vest"]))
        px(14, 19, 4, 1, "#e8e0d0")
        px(15, 19, 2, 3, "#1e1a1c")
        px(13, 26, 2, 1, p["chain"])
        px(15, 27, 2, 1, p["chain"])
        px(17, 26, 1, 1, p["chain"])
    if g("blanket"):  # a blanket held round the shoulders, its stripe down the front, the nightshirt between
        px(14, 19, 4, 13, "#ddd2bc")
        px(17, 19, 1, 13, "#b8ac94")
        px(13, 19, 1, 14, p["blanket"])
        px(18, 19, 1, 14, p["blanket"])
    if g("apron"):
        for y in range(25, 43):
            px(13 - (1 if y > 33 else 0), y, 6 + (2 if y > 33 else 0), 1, shade(p["apron"], 0.85) if y == 25 else p["apron"])
    if g("dots"):
        for y in range(21, 33, 3):
            for x in range(11 + y % 2, 21, 3):
                px(x, y, 1, 1, p["dots"])
    if g("belt"):
        px(10, 30, 12, 1, "#3a2616")
        px(15, 30, 2, 1, p["belt"])
        for i in range(9):
            px(11 + i, 20 + i, 1, 1, "#3a2616")
    if g("buttons"):
        for y in (22, 25, 28):
            px(15, y, 1, 1, p["buttons"])
    if g("check"):
        for y in range(20, hem, 3):
            for x in range(11, 21, 3):
                px(x, y, 1, 1, Dk(p["coat"]))
    if g("shawl"):
        for y in range(19, 26):
            wd = 12 - (y - 19) * 2
            if wd > 0:
                px(16 - wd // 2, y, wd, 1, Lt(p["shawl"]) if y == 19 else p["shawl"])
    px(8, 21, 2, 12, Lt(p["coat"]))
    px(22, 21, 2, 12, Dk(p["coat"]))
    px(8, 20, 2, 1, p["coat"])
    px(22, 20, 2, 1, Dk(p["coat"]))
    px(8, 33, 2, 2, g("mitt") or "#5a3b26")
    px(22, 33, 2, 2, g("mitt") or "#5a3b26")
    if g("lantern"):
        px(23, 35, 1, 1, "#2a1d16")
        px(21, 36, 5, 1, "#2a1d16")
        px(21, 37, 5, 4, "#3a2a1a")
        px(22, 37, 3, 3, "#ffc95a")
        px(23, 38, 1, 1, "#fff3c4")
        px(21, 41, 5, 1, "#2a1d16")
    if g("ledger"):  # a ledger under his arm, its top corner burned
        px(22, 29, 4, 6, p["ledger"])
        px(22, 29, 1, 6, "#d6c4a0")
        px(24, 29, 2, 2, "#1e1614")
        px(22, 33, 2, 2, g("mitt") or "#5a3b26")
    if g("glove"):  # the hide glove she's sewing, held up in front of her
        px(13, 27, 6, 4, p["glove"])
        px(13, 26, 2, 1, p["glove"])
        px(16, 26, 1, 1, p["glove"])
        px(18, 26, 1, 1, p["glove"])
        px(13, 30, 6, 1, Dk(p["glove"]))
        px(12, 28, 1, 3, p["skin"])
        px(19, 28, 1, 2, p["skin"])
    px(12, 17, 8, 2, g("scarf") or Dk(p["coat"]))
    if g("scarf"):
        px(17, 19, 2, 6, p["scarf"])
    px(12, 8, 8, 10, p["skin"])
    clear(12, 8)
    clear(19, 8)
    clear(12, 17)
    clear(19, 17)
    px(19, 9, 1, 8, Dk(p["skin"]))
    px(13, 16, 6, 1, shade(p["skin"], 0.88))
    px(11, 12, 1, 2, p["skin"])
    px(20, 12, 1, 2, Dk(p["skin"]))
    px(14, 12, 1, 2, "#1d1410")
    px(17, 12, 1, 2, "#1d1410")
    px(16, 14, 1, 1, Dk(p["skin"]))
    px(13, 14, 1, 1, "#d58f7c")
    px(18, 14, 1, 1, "#c98272")
    px(15, 16, 2, 1, shade(p["skin"], 0.62))
    if g("beard"):
        px(13, 15, 6, 3, p["beard"])
        px(14, 18, 4, 1, p["beard"])
        px(15, 16, 2, 1, Dk(p["beard"]))
    if g("whiskers"):
        px(12, 12, 1, 4, p["whiskers"])
        px(19, 12, 1, 4, Dk(p["whiskers"]))
    if g("moustache"):
        px(14, 15, 4, 1, p["moustache"])
        px(13, 16, 1, 1, p["moustache"])
        px(18, 16, 1, 1, p["moustache"])
    hc = g("hatC")
    hat = g("hat")
    if hat == "fur":
        px(11, 4, 10, 6, hc)
        px(11, 4, 2, 6, Lt(hc))
        px(10, 8, 2, 6, hc)
        px(20, 8, 2, 6, Dk(hc))
        px(15, 6, 2, 2, "#c9a14a")
    if hat == "earflap":
        px(11, 5, 10, 5, hc)
        px(11, 5, 2, 5, Lt(hc))
        px(11, 9, 10, 1, Lt(hc))
        px(11, 10, 2, 6, hc)
        px(19, 10, 2, 6, Dk(hc))
    if hat == "cap":
        px(12, 5, 8, 4, hc)
        px(12, 5, 2, 3, Lt(hc))
        px(11, 8, 11, 1, Dk(hc))
        px(12, 9, 1, 3, g("hair") or "#3a2a1e")
    if hat == "brim":
        px(13, 3, 6, 5, hc)
        px(13, 3, 1, 5, Lt(hc))
        px(13, 7, 6, 1, "#5a2020")
        px(9, 8, 14, 1, hc)
        px(13, 9, 6, 1, Dk(p["skin"]))
    if hat == "bun":
        px(12, 6, 8, 4, hc)
        px(12, 6, 2, 2, Lt(hc))
        px(12, 9, 1, 5, hc)
        px(19, 9, 1, 5, Dk(hc))
        px(14, 3, 4, 3, hc)
        px(16, 6, 1, 2, Dk(hc))
    if hat == "scarf":
        px(11, 6, 10, 5, hc)
        px(11, 10, 2, 7, hc)
        px(19, 10, 2, 7, Dk(hc))
        px(15, 18, 2, 2, hc)
        for (x, y) in [(13, 7), (17, 8), (12, 11), (19, 12)]:
            px(x, y, 1, 1, g("hatDots") or Lt(hc))
    if hat == "bowler":  # a round crown and a narrow brim
        px(12, 4, 8, 4, hc)
        px(13, 3, 6, 1, hc)
        px(12, 4, 2, 3, Lt(hc))
        px(10, 7, 12, 1, hc)
        px(10, 7, 2, 1, Lt(hc))
        px(12, 8, 8, 1, Dk(p["skin"]))
    if hat == "bandage":  # bare-headed, grey at the sides, a linen bandage round the head
        px(12, 6, 8, 3, p["skin"])
        px(12, 6, 2, 2, Lt(p["skin"]))
        px(11, 8, 2, 5, p["hair"])
        px(19, 8, 2, 5, Dk(p["hair"]))
        px(11, 8, 10, 2, hc)
        px(19, 8, 2, 2, Dk(hc))
        px(20, 10, 2, 2, hc)
    # the ink outline round everything drawn
    a = im.load()
    filled = [[a[x, y][3] > 0 for y in range(H)] for x in range(W)]

    def f(x, y):
        return 0 <= x < W and 0 <= y < H and filled[x][y]

    for y in range(H):
        for x in range(W):
            if not f(x, y) and (f(x - 1, y) or f(x + 1, y) or f(x, y - 1) or f(x, y + 1)):
                a[x, y] = rgb(OUT) + (255,)
    return im


if __name__ == "__main__":
    out = sys.argv[1]
    for who in sys.argv[2:] or PEOPLE:
        draw(PEOPLE[who]).save(os.path.join(out, who + ".png"))
        print(who)
