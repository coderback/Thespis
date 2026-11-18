# Tamás Kovács, the watchman, sitting up in the mission infirmary: an old smith with a burned hand and a bandaged
# head, a grey blanket round his shoulders, looking past you for something he can't yet see.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(226, 182, 150), skin_sh=(186, 136, 108), skin_hi=(240, 206, 178), sick=(206, 168, 150),
    rim=(196, 120, 110), scar=(214, 128, 116), scar_hi=(232, 160, 146),
    hair=(158, 156, 150), hair_sh=(112, 110, 106), hair_hi=(196, 194, 188), stubble=(184, 150, 132),
    eye=(40, 32, 28), white=(230, 222, 206),
    linen=(250, 247, 238), linen_sh=(206, 200, 184), lint=(226, 220, 204),
    shirt=(222, 214, 196), shirt_sh=(184, 174, 154),
    blanket=(108, 108, 102), blanket_sh=(76, 76, 72), blanket_hi=(140, 140, 132), stripe=(128, 44, 40),
))

# the nightshirt, open at the throat
s.poly([(14, 52), (22, 45), (30, 44), (36, 44), (44, 45), (52, 52), (54, 80), (10, 80)], "shirt")
s.poly([(40, 46), (52, 52), (54, 80), (44, 80)], "shirt_sh")
# neck, with a thick old man's throat
s.rect((26, 34, 37, 45), "skin")
s.rect((34, 34, 37, 45), "skin_sh")
s.rect((26, 39, 37, 40), "skin_sh")
s.poly([(27, 44), (32, 51), (37, 44)], "skin")
s.poly([(33, 46), (32, 51), (35, 46)], "skin_sh")
s.line([(27, 44), (31, 50)], "shirt_sh")
s.line([(37, 44), (33, 50)], "shirt_sh")
# the infirmary blanket round his shoulders, a dark red stripe along its edge
s.poly([(8, 56), (14, 48), (22, 44), (27, 46), (25, 58), (22, 80), (6, 80)], "blanket")
s.poly([(56, 56), (50, 48), (42, 44), (37, 46), (40, 58), (43, 80), (58, 80)], "blanket")
s.poly([(50, 48), (56, 56), (58, 80), (50, 80), (48, 60)], "blanket_sh")
s.poly([(8, 56), (14, 48), (18, 46), (12, 56), (9, 68), (6, 72)], "blanket_hi")
s.line([(25, 50), (23, 80)], "stripe")
s.line([(26, 50), (24, 80)], "stripe")
s.line([(39, 50), (41, 80)], "stripe")
s.line([(40, 50), (42, 80)], "stripe")
for (x0, y0, x1, y1) in [(15, 56, 13, 66), (19, 54, 18, 64), (46, 56, 48, 66)]:
    s.line([(x0, y0), (x1, y1)], "blanket_sh")
# his right hand holds the blanket shut: a smith's hand, the back of it burned
s.oval((24, 60, 38, 72), "skin")
s.rect((26, 60, 36, 62), "skin_hi")
s.poly([(33, 61), (38, 64), (37, 71), (32, 72)], "skin_sh")
s.oval((26, 63, 32, 68), "scar")
s.px([(27, 64), (28, 64), (29, 65)], "scar_hi")
for x in (27, 30, 33):
    s.line([(x, 69), (x, 72)], "skin_sh")
# head: a broad face, the hair gone from the crown, grey at the sides
s.oval((19, 10, 43, 39), "skin")
s.poly([(37, 16), (43, 22), (42, 32), (37, 38), (36, 28)], "skin_sh")
s.oval((22, 13, 28, 17), "skin_hi")
s.poly([(17, 18), (21, 14), (22, 30), (19, 31)], "hair")
s.poly([(45, 18), (41, 14), (41, 30), (43, 31)], "hair_sh")
s.poly([(17, 18), (19, 16), (19, 26), (17, 24)], "hair_hi")
# ears
s.oval((16, 22, 21, 30), "skin")
s.oval((41, 22, 46, 30), "skin_sh")
# the bandage round his head, knotted at the side, a tail hanging
s.poly([(19, 15), (25, 11), (37, 11), (43, 15), (43, 19), (37, 16), (25, 16), (19, 20)], "linen")
s.poly([(37, 12), (43, 15), (43, 19), (37, 16)], "linen_sh")
s.line([(21, 17), (27, 14)], "lint")
s.line([(30, 13), (36, 13)], "lint")
s.oval((42, 14, 47, 19), "linen")
s.poly([(45, 18), (48, 26), (46, 27), (44, 19)], "linen_sh")
s.line([(19, 20), (25, 16), (37, 16), (43, 19)], "linen_sh")
s.px([(29, 11), (30, 11), (31, 11)], "sick")
# brows lifted and drawn together: straining to see something
s.px([(23, 21), (24, 20), (25, 20), (26, 20), (27, 21), (35, 21), (36, 20), (37, 20), (38, 20), (39, 21)], "hair_sh")
s.px([(28, 20), (34, 20)], "hair")
# eyes looking up and away to his right, red at the rims
s.rect((24, 23, 27, 25), "white")
s.rect((35, 23, 38, 25), "white")
s.rect((24, 23, 25, 24), "eye")
s.rect((35, 23, 36, 24), "eye")
s.px([(24, 26), (25, 26), (26, 26), (27, 26), (35, 26), (36, 26), (37, 26), (38, 26)], "rim")
s.px([(23, 27), (28, 27), (34, 27), (39, 27)], "skin_sh")
# a big nose, sunken cheeks
s.px([(31, 24), (31, 25), (31, 26), (31, 27), (30, 28), (32, 29), (30, 29)], "skin_sh")
s.px([(24, 29), (25, 30), (38, 29), (37, 30)], "sick")
# the moustache: grey, heavy, drooping past the corners of his mouth
s.poly([(25, 31), (30, 30), (31, 31), (32, 30), (37, 31), (39, 35), (37, 36), (34, 33), (28, 33), (25, 36), (23, 35)], "hair")
s.poly([(32, 30), (37, 31), (39, 35), (37, 36), (34, 33)], "hair_sh")
s.px([(27, 31), (28, 31)], "hair_hi")
# the mouth just showing under it, and grey stubble on the jaw
s.rect((29, 34, 33, 34), "rim")
s.px([(24, 36), (26, 37), (28, 38), (31, 38), (34, 37), (36, 36), (38, 35), (27, 36), (35, 35)], "stubble")

finish(s)
