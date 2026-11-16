# Maggie Doyle, half-length pixel portrait (64x80), with an ink outline and a paper-white cut-out edge.
import sys

from PIL import Image, ImageDraw, ImageFilter

W, H = 64, 80
OUT = (26, 18, 14, 255)
C = dict(
    skin=(239, 198, 160), skin_sh=(206, 152, 118), skin_hi=(250, 222, 192), blush=(222, 138, 118),
    hair=(156, 74, 34), hair_sh=(108, 46, 22), hair_hi=(196, 108, 54),
    dress=(122, 48, 48), dress_sh=(84, 32, 34), dress_hi=(152, 66, 60),
    apron=(232, 222, 204), apron_sh=(196, 184, 164),
    shawl=(58, 76, 96), shawl_sh=(38, 50, 66), shawl_hi=(84, 104, 126),
    eye=(36, 26, 22), white=(236, 228, 214), lip=(168, 86, 76), lip_sh=(132, 62, 56),
    tin=(150, 156, 162), tin_sh=(98, 104, 112), tin_hi=(206, 212, 216), coffee=(52, 32, 20), steam=(214, 218, 222),
)
C = {k: v + (255,) for k, v in C.items()}

im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
def P(pts, c):
    return d.polygon(pts, fill=C[c])

def E(box, c):
    return d.ellipse(box, fill=C[c])

def R(box, c):
    return d.rectangle(box, fill=C[c])

def px(x, y, c):
    return d.point((x, y), fill=C[c])


# body: dress, light from the left
P([(13, 51), (21, 45), (30, 44), (36, 44), (44, 45), (52, 51), (57, 80), (7, 80)], "dress")
P([(44, 46), (52, 51), (57, 80), (46, 80), (47, 60)], "dress_sh")
P([(13, 51), (17, 48), (14, 66), (10, 80), (7, 80)], "dress_hi")
# apron bib and skirt front
P([(25, 60), (39, 60), (41, 80), (23, 80)], "apron")
P([(36, 60), (39, 60), (41, 80), (37, 80)], "apron_sh")
R((25, 72, 40, 72), "apron_sh")
# neck and collar
R((28, 35, 35, 44), "skin")
R((33, 35, 35, 44), "skin_sh")
R((28, 38, 35, 39), "skin_sh")
P([(26, 43), (31, 46), (37, 43), (38, 45), (31, 48), (25, 45)], "apron")
# the shawl over her shoulders, knotted at the front
P([(11, 52), (20, 44), (27, 44), (31, 49), (36, 44), (44, 44), (53, 52), (55, 64), (45, 58), (38, 66), (32, 70), (26, 66), (19, 58), (9, 64)], "shawl")
P([(44, 44), (53, 52), (55, 64), (47, 59), (46, 50)], "shawl_sh")
P([(11, 52), (20, 44), (24, 44), (16, 53), (11, 60), (9, 64)], "shawl_hi")
for (x0, y0, x1, y1) in [(20, 50, 26, 60), (40, 49, 36, 59), (15, 55, 19, 61)]:
    d.line((x0, y0, x1, y1), fill=C["shawl_sh"])
E((28, 62, 36, 70), "shawl")
E((29, 63, 33, 67), "shawl_hi")
P([(29, 69), (27, 76), (30, 76), (32, 70)], "shawl_sh")
P([(33, 69), (36, 75), (38, 74), (35, 69)], "shawl")
# her hand and a tin mug of coffee, held out
E((41, 66, 49, 75), "skin")
R((46, 70, 49, 74), "skin_sh")
R((46, 64, 55, 77), "tin")
R((52, 64, 55, 77), "tin_sh")
R((47, 65, 48, 76), "tin_hi")
R((46, 63, 55, 64), "tin_hi")
R((47, 63, 54, 63), "coffee")
R((56, 67, 57, 73), "tin_sh")
# head: hair behind, bun, face, bangs
E((18, 7, 44, 30), "hair")
E((15, 3, 26, 13), "hair")
E((17, 4, 22, 8), "hair_hi")
E((21, 12, 41, 37), "skin")
P([(36, 16), (41, 21), (40, 31), (36, 37), (35, 28)], "skin_sh")
E((23, 15, 27, 19), "skin_hi")
P([(20, 15), (24, 11), (32, 10), (40, 12), (43, 18), (41, 22), (37, 16), (30, 16), (24, 18), (21, 24)], "hair")
P([(24, 11), (32, 10), (36, 11), (28, 13), (23, 16)], "hair_hi")
P([(39, 13), (43, 18), (42, 26), (40, 20)], "hair_sh")
P([(18, 16), (22, 15), (22, 31), (19, 28)], "hair")
R((19, 18, 19, 26), "hair_sh")
# a wary face: brows low at the middle, eyes sliding right, mouth set
for (x, y) in [(24, 21), (25, 21), (26, 22), (27, 22), (33, 22), (34, 22), (35, 21), (36, 21)]:
    px(x, y, "hair_sh")
R((25, 24, 27, 25), "white")
R((27, 24, 27, 25), "eye")
R((26, 24, 26, 24), "eye")
R((33, 24, 35, 25), "white")
R((35, 24, 35, 25), "eye")
R((34, 24, 34, 24), "eye")
px(25, 26, "skin_sh")
px(33, 26, "skin_sh")
for (x, y) in [(31, 26), (31, 27), (31, 28), (30, 29)]:
    px(x, y, "skin_sh")
px(32, 29, "skin_sh")
for (x, y) in [(24, 29), (25, 29), (25, 28), (36, 29), (37, 29), (37, 28)]:
    px(x, y, "blush")
for (x, y) in [(26, 27), (28, 28), (34, 27)]:
    px(x, y, "skin_sh")
R((29, 32, 32, 32), "lip")
px(28, 33, "lip_sh")
px(33, 33, "lip_sh")
R((29, 33, 32, 33), "skin_sh")

# ink outline, then a thick paper-white cut-out edge (the bottom stays cut flat)
a = im.split()[3]
grow1 = a.filter(ImageFilter.MaxFilter(3))
outline = Image.new("RGBA", (W, H), OUT)
outline.putalpha(grow1)
pad = 6
big = Image.new("RGBA", (W + pad * 2, H + pad), (0, 0, 0, 0))
mask = Image.new("L", (W + pad * 2, H + pad), 0)
mask.paste(grow1, (pad, pad))
paper = mask.filter(ImageFilter.MaxFilter(7))
edge = Image.new("RGBA", big.size, (240, 232, 214, 255))
edge.putalpha(paper)
big.alpha_composite(edge)
big.alpha_composite(outline, (pad, pad))
big.alpha_composite(im, (pad, pad))
big = big.crop((0, 0, big.width, H + pad))
scale = int(sys.argv[2]) if len(sys.argv) > 2 else 5
big.resize((big.width * scale, big.height * scale), Image.NEAREST).save(sys.argv[1])
print(big.size)
