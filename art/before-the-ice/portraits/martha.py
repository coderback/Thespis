# Martha Matthias, in Maggie's kitchen with her sewing: a cotton kerchief over her hair, a print trade-cloth dress,
# a smoked-hide glove half-sewn in her hand, and a level look straight back at whoever's asking.
# Kept to what the record shows women in town wearing in 1898 (store cloth, a kerchief) and the work she sells; no
# beadwork patterns or anything ceremonial (docs/before-the-ice-han-1898.md). A Hän reader sees her before release.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(178, 124, 90), skin_sh=(142, 94, 66), skin_hi=(202, 152, 116), cheek=(170, 104, 80),
    hair=(34, 28, 28), hair_sh=(20, 16, 18), hair_hi=(70, 62, 64),
    eye=(26, 20, 18), white=(226, 216, 200), lip=(140, 78, 66), lip_sh=(112, 60, 52),
    scarf=(46, 58, 92), scarf_sh=(30, 38, 64), scarf_hi=(70, 86, 124), dot=(206, 196, 168),
    dress=(64, 86, 70), dress_sh=(42, 60, 50), dress_hi=(88, 114, 92), print=(206, 196, 160),
    collar=(226, 216, 196), collar_sh=(188, 176, 156),
    hide=(196, 150, 92), hide_sh=(158, 114, 66), hide_hi=(222, 182, 126), thread=(240, 232, 214), steel=(186, 192, 198),
))

# the dress, light from the left, a small print in the cloth
s.poly([(12, 51), (21, 45), (30, 44), (36, 44), (44, 45), (52, 51), (56, 80), (8, 80)], "dress")
s.poly([(44, 46), (52, 51), (56, 80), (46, 80), (47, 60)], "dress_sh")
s.poly([(12, 51), (17, 48), (14, 66), (10, 80), (8, 80)], "dress_hi")
for y in range(50, 80, 5):
    for x in range(11 + (y // 5) % 2 * 2, 54, 5):
        s.px([(x, y)], "print")
s.line([(32, 50), (32, 80)], "dress_sh")  # the bodice seam
s.px([(31, 54), (31, 60), (31, 66)], "collar")  # buttons
# neck and a plain band collar
s.rect((28, 35, 35, 45), "skin")
s.rect((33, 35, 35, 45), "skin_sh")
s.rect((28, 38, 35, 39), "skin_sh")
s.poly([(26, 43), (32, 46), (38, 43), (38, 46), (32, 49), (26, 46)], "collar")
s.poly([(32, 46), (38, 43), (38, 46), (32, 49)], "collar_sh")
# her hands at work: a smoked-hide glove, half-sewn, the needle drawn up on its thread
s.poly([(17, 61), (23, 63), (23, 73), (16, 75)], "hide_sh")  # the cuff
s.rect((23, 63, 31, 73), "hide")  # the back of the glove
s.poly([(25, 63), (27, 58), (30, 57), (31, 63)], "hide")  # the thumb
s.px([(28, 58), (29, 58)], "hide_hi")
for y in (63, 66, 69):
    s.rect((32, y, 39, y + 2), "hide")
    s.px([(32, y + 2), (39, y + 2)], "hide_sh")
s.rect((32, 72, 37, 73), "hide_sh")
s.rect((24, 64, 30, 65), "hide_hi")
s.px([(24, 70), (26, 70), (28, 70), (30, 70)], "thread")  # the seam she's sewing
s.oval((10, 64, 20, 75), "skin")  # left hand, holding it by the cuff
s.rect((10, 71, 15, 75), "skin_sh")
s.oval((38, 56, 46, 64), "skin")  # right hand, drawing the thread
s.rect((42, 59, 46, 63), "skin_sh")
s.line([(31, 70), (35, 66), (39, 62)], "thread")
s.line([(44, 56), (46, 52)], "steel")
# head: hair parted in the middle, drawn back under the kerchief
s.oval((21, 12, 41, 37), "skin")
s.poly([(36, 16), (41, 21), (40, 31), (36, 37), (35, 28)], "skin_sh")
s.oval((23, 17, 27, 21), "skin_hi")
s.poly([(20, 16), (24, 12), (31, 12), (31, 16), (25, 17), (22, 22), (21, 28), (19, 24)], "hair")
s.poly([(31, 12), (38, 12), (42, 17), (43, 24), (41, 28), (40, 22), (37, 17), (31, 16)], "hair_sh")
s.px([(24, 15), (26, 14)], "hair_hi")
# the kerchief over her head, knotted at the nape, its ends behind her shoulder
s.poly([(18, 18), (21, 9), (27, 5), (35, 5), (41, 8), (44, 14), (44, 20), (40, 15), (34, 12), (28, 12), (22, 15), (19, 21)], "scarf")
s.poly([(35, 5), (41, 8), (44, 14), (44, 20), (40, 14), (36, 10)], "scarf_sh")
s.poly([(21, 9), (27, 5), (30, 6), (24, 9), (20, 14)], "scarf_hi")
s.poly([(43, 18), (47, 22), (48, 30), (45, 34), (43, 28)], "scarf")
s.poly([(46, 26), (49, 36), (46, 40), (45, 32)], "scarf_sh")
for p in [(24, 8), (29, 7), (34, 7), (39, 10), (42, 14), (22, 13), (27, 10), (32, 10), (37, 12), (46, 27)]:
    s.px([p], "dot")
# level brows, eyes straight at you: she has nothing she means to hide
s.px([(24, 21), (25, 21), (26, 21), (27, 21), (34, 21), (35, 21), (36, 21), (37, 21)], "hair")
s.rect((25, 24, 27, 25), "white")
s.rect((34, 24, 36, 25), "white")
s.rect((26, 24, 26, 25), "eye")
s.rect((35, 24, 35, 25), "eye")
s.px([(25, 23), (26, 23), (27, 23), (34, 23), (35, 23), (36, 23)], "skin_sh")
s.px([(25, 26), (35, 26)], "skin_sh")
# nose, high cheekbones
s.px([(31, 25), (31, 26), (31, 27), (31, 28), (30, 29), (32, 29)], "skin_sh")
s.px([(24, 28), (25, 28), (36, 28), (37, 28)], "cheek")
# mouth closed and even
s.rect((29, 32, 33, 32), "lip")
s.rect((29, 33, 33, 33), "lip_sh")
s.px([(28, 32), (34, 32)], "skin_sh")

finish(s)
