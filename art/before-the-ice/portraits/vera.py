# Věra Holub, at her cabin at the creek mouth: a red wool headscarf tied under the chin, the black of mourning at her
# collar under a blue-grey coat, a tin enamel mug held in both hands, and the look of a sister who knows more than
# she's saying. Practical, dry, loyal.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(226, 184, 147), skin_sh=(188, 142, 110), skin_hi=(242, 208, 176), cheek=(212, 146, 120),
    hair=(66, 44, 32), hair_sh=(44, 28, 22),
    eye=(36, 30, 28), white=(230, 222, 206), lip=(164, 98, 84), lip_sh=(132, 74, 64),
    scarf=(154, 59, 42), scarf_sh=(110, 38, 28), scarf_hi=(190, 92, 66),
    coat=(63, 90, 107), coat_sh=(42, 62, 76), coat_hi=(92, 122, 140),
    black=(36, 32, 38), jet=(90, 84, 96),
    mug=(66, 96, 148), mug_sh=(44, 66, 108), rim=(226, 222, 214), chip=(30, 30, 34),
))

# the coat, light from the left
s.poly([(11, 52), (20, 46), (29, 45), (35, 45), (44, 46), (53, 52), (56, 80), (8, 80)], "coat")
s.poly([(44, 47), (53, 52), (56, 80), (46, 80), (47, 60)], "coat_sh")
s.poly([(11, 52), (16, 49), (13, 66), (10, 80), (8, 80)], "coat_hi")
# the black dress of mourning in the coat's opening, a jet brooch at the collar
s.poly([(26, 47), (32, 52), (38, 47), (39, 80), (25, 80)], "black")
s.px([(32, 50), (31, 51), (33, 51), (32, 52)], "jet")
s.poly([(20, 46), (26, 47), (31, 60), (24, 62)], "coat_hi")
s.poly([(44, 46), (38, 47), (33, 60), (40, 62)], "coat_sh")
# neck
s.rect((28, 37, 35, 46), "skin")
s.rect((33, 37, 35, 46), "skin_sh")
# the mug in both hands, held to her for the warmth
s.rect((24, 60, 38, 74), "mug")
s.rect((34, 60, 38, 74), "mug_sh")
s.rect((24, 60, 38, 61), "rim")
s.px([(27, 66), (36, 70), (30, 72)], "chip")
s.poly([(38, 63), (42, 63), (42, 70), (38, 70), (38, 68), (40, 68), (40, 65), (38, 65)], "mug_sh")
s.oval((16, 62, 27, 74), "skin")
s.rect((16, 69, 22, 74), "skin_sh")
s.oval((37, 64, 47, 75), "skin")
s.rect((42, 69, 47, 75), "skin_sh")
for x in (19, 22):
    s.line([(x, 65), (x, 70)], "skin_sh")
# head
s.oval((21, 13, 41, 38), "skin")
s.poly([(36, 17), (41, 22), (40, 31), (36, 38), (35, 28)], "skin_sh")
s.oval((23, 18, 27, 22), "skin_hi")
# dark hair parted under the scarf
s.poly([(22, 18), (25, 14), (31, 14), (31, 17), (26, 18), (23, 22)], "hair")
s.poly([(31, 14), (37, 14), (40, 18), (39, 22), (36, 18), (31, 17)], "hair_sh")
# the headscarf, over her head and down her cheeks, knotted under the chin
s.poly([(17, 22), (19, 11), (25, 5), (32, 4), (39, 5), (44, 11), (45, 22), (44, 33), (41, 36), (40, 24), (37, 15),
        (31, 13), (25, 15), (22, 24), (22, 36), (19, 34)], "scarf")
s.poly([(39, 5), (44, 11), (45, 22), (44, 33), (41, 36), (40, 24), (38, 13)], "scarf_sh")
s.poly([(19, 11), (25, 5), (29, 5), (22, 11), (19, 20)], "scarf_hi")
s.poly([(22, 36), (27, 38), (31, 40), (35, 38), (41, 36), (40, 41), (32, 44), (23, 41)], "scarf")
s.poly([(29, 40), (34, 40), (35, 44), (32, 46), (29, 44)], "scarf_sh")  # the knot
s.poly([(30, 45), (27, 52), (30, 52), (32, 46)], "scarf")  # its ends
s.poly([(33, 45), (36, 51), (34, 52), (32, 46)], "scarf_sh")
for p in [(21, 14), (26, 9), (33, 7), (38, 9), (42, 16), (20, 28), (43, 26), (24, 39), (38, 39)]:
    s.px([p], "scarf_sh")
# one brow a touch higher: she has her doubts about you
s.px([(24, 21), (25, 20), (26, 20), (27, 20)], "hair_sh")
s.px([(34, 21), (35, 21), (36, 21), (37, 21)], "hair_sh")
s.rect((25, 23, 27, 24), "white")
s.rect((34, 24, 36, 24), "white")
s.rect((26, 23, 26, 24), "eye")
s.rect((35, 24, 35, 24), "eye")
s.px([(34, 23), (35, 23), (36, 23)], "skin_sh")  # a heavier lid on that side
s.px([(25, 26), (36, 26), (24, 25)], "skin_sh")
# nose, cold-pink cheeks
s.px([(31, 25), (31, 26), (31, 27), (31, 28), (30, 29), (32, 29)], "skin_sh")
s.px([(24, 28), (25, 28), (36, 28), (37, 28), (25, 29)], "cheek")
# mouth set, a dry line
s.rect((29, 32, 33, 32), "lip")
s.rect((29, 33, 32, 33), "lip_sh")
s.px([(34, 31)], "skin_sh")

finish(s)
