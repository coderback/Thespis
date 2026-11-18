# Billy Tuck, the wood boy, about thirteen: a man's coat too big for him, sleeves rolled, a red muffler, a cap pushed
# back, and an armful of split cordwood that isn't his. Freckled, quick, cheeky, and looking off to one side, in case
# it's the police.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(232, 191, 154), skin_sh=(196, 150, 116), skin_hi=(246, 214, 186), freckle=(196, 132, 96), cheek=(222, 150, 124),
    hair=(150, 92, 52), hair_sh=(110, 64, 34),
    eye=(36, 30, 28), white=(232, 224, 208), lip=(170, 102, 88), tooth=(236, 230, 214),
    coat=(110, 90, 58), coat_sh=(78, 62, 38), coat_hi=(140, 118, 80), patch=(92, 100, 76),
    cap=(59, 59, 59), cap_sh=(38, 38, 40), cap_hi=(88, 88, 90),
    scarf=(163, 58, 42), scarf_sh=(118, 38, 28), scarf_hi=(196, 90, 70),
    wood=(150, 112, 70), wood_sh=(108, 78, 46), ring=(206, 172, 120), bark=(80, 60, 44),
))

# the coat, a man's, hanging off narrow shoulders
s.poly([(13, 53), (22, 47), (30, 46), (34, 46), (42, 47), (51, 53), (55, 80), (9, 80)], "coat")
s.poly([(42, 48), (51, 53), (55, 80), (45, 80), (46, 62)], "coat_sh")
s.poly([(13, 53), (18, 50), (15, 66), (11, 80), (9, 80)], "coat_hi")
s.rect((14, 70, 20, 76), "patch")  # a patch on the elbow
s.px([(14, 70), (16, 70), (18, 70), (20, 72), (20, 74), (14, 74)], "coat_sh")
# neck, and the red muffler wound round it
s.rect((28, 37, 35, 46), "skin")
s.rect((33, 37, 35, 46), "skin_sh")
s.poly([(24, 43), (32, 46), (40, 43), (41, 48), (32, 51), (23, 48)], "scarf")
s.poly([(32, 46), (40, 43), (41, 48), (32, 51)], "scarf_sh")
s.poly([(25, 48), (29, 49), (28, 60), (24, 59)], "scarf")  # the end hanging down
s.px([(24, 44), (27, 45), (25, 52), (26, 56)], "scarf_hi")
# an armful of split cordwood carried across him: long sticks, bark on their backs, the split faces pale
for y, x0, x1 in [(57, 10, 50), (62, 8, 52), (67, 11, 54), (72, 9, 51)]:
    s.poly([(x0, y), (x1, y - 1), (x1 + 1, y + 3), (x0 + 1, y + 4)], "wood")
    s.line([(x0, y), (x1, y - 1)], "ring")  # the split face catching the light
    s.line([(x0 + 1, y + 4), (x1 + 1, y + 3)], "bark")
    s.px([(x0 + 8, y + 2), (x0 + 19, y + 1), (x0 + 30, y + 2)], "wood_sh")
    s.poly([(x1, y - 1), (x1 + 3, y), (x1 + 3, y + 3), (x1 + 1, y + 3)], "ring")  # the sawn end
    s.px([(x1 + 2, y + 1)], "wood_sh")
s.oval((4, 60, 13, 71), "skin")  # one hand under the load
s.px([(7, 62), (10, 62)], "skin_sh")
s.oval((26, 74, 35, 80), "skin_sh")  # the other arm round it
# head, round and young
s.oval((21, 14, 42, 39), "skin")
s.poly([(37, 18), (42, 23), (41, 32), (37, 39), (36, 29)], "skin_sh")
s.oval((23, 19, 27, 23), "skin_hi")
s.oval((17, 22, 23, 31), "skin")  # ears that stick out
s.oval((40, 22, 46, 31), "skin_sh")
s.px([(19, 25), (19, 26)], "skin_sh")
# ginger hair from under the cap
s.poly([(20, 20), (23, 14), (27, 18), (24, 22), (21, 24)], "hair")
s.poly([(43, 20), (40, 14), (36, 18), (39, 21), (42, 24)], "hair_sh")
s.px([(28, 17), (30, 18), (33, 17)], "hair")
# the cap, pushed back
s.poly([(19, 15), (21, 8), (27, 4), (35, 4), (41, 7), (44, 13), (43, 17), (38, 14), (30, 13), (22, 15)], "cap")
s.poly([(36, 4), (41, 7), (44, 13), (43, 17), (39, 11)], "cap_sh")
s.poly([(21, 8), (27, 4), (30, 5), (23, 9), (21, 13)], "cap_hi")
s.poly([(22, 15), (30, 13), (38, 14), (36, 16), (30, 15), (24, 17)], "cap_sh")  # the short peak
# eyes slid to one side: is that the Mountie?
s.px([(24, 21), (25, 20), (26, 20), (27, 21)], "hair_sh")
s.px([(34, 21), (35, 20), (36, 20), (37, 21)], "hair_sh")
s.rect((24, 23, 27, 25), "white")
s.rect((34, 23, 37, 25), "white")
s.rect((26, 23, 27, 25), "eye")
s.rect((36, 23, 37, 25), "eye")
# freckles across the nose, cold cheeks
s.px([(31, 26), (31, 27), (31, 28), (30, 29), (32, 29)], "skin_sh")
s.px([(26, 27), (28, 28), (27, 29), (34, 28), (35, 27), (36, 29), (29, 27), (33, 27)], "freckle")
s.px([(24, 30), (25, 30), (37, 30), (38, 30)], "cheek")
# a lopsided grin with a gap in it
s.poly([(28, 33), (35, 32), (34, 34), (29, 34)], "lip")
s.rect((29, 33, 33, 33), "tooth")
s.px([(31, 33)], "lip")
s.px([(36, 31)], "skin_sh")

finish(s)
