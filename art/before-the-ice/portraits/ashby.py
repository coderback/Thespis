# The man who calls himself Jack Ashby, at the landing: a long dark coat with the collar turned up, a wide-brimmed
# hat worn low, a collarless shirt, a week's stubble, and an unlit match in the corner of his mouth. Easy-going, and
# watching everything from under the brim. The name isn't his.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(220, 174, 136), skin_sh=(180, 134, 102), skin_hi=(238, 202, 168), stubble=(150, 120, 96),
    hair=(46, 38, 34), hair_sh=(28, 22, 20),
    eye=(30, 26, 24), white=(226, 218, 202), lip=(156, 94, 80),
    coat=(44, 44, 48), coat_sh=(28, 28, 32), coat_hi=(70, 70, 76),
    shirt=(216, 210, 196), shirt_sh=(176, 168, 152), button=(120, 112, 100),
    hat=(21, 21, 23), hat_sh=(10, 10, 12), hat_hi=(48, 48, 52), band=(90, 64, 44),
    match=(226, 206, 160), head=(176, 52, 40),
))

# the long coat, collar up, light from the left
s.poly([(10, 52), (19, 45), (29, 44), (35, 44), (45, 45), (54, 52), (57, 80), (7, 80)], "coat")
s.poly([(45, 46), (54, 52), (57, 80), (47, 80), (48, 60)], "coat_sh")
s.poly([(10, 52), (16, 48), (13, 66), (9, 80), (7, 80)], "coat_hi")
# the shirt in the opening, no collar, a button undone
s.poly([(26, 46), (32, 50), (38, 46), (37, 80), (27, 80)], "shirt")
s.poly([(33, 49), (38, 46), (37, 80), (34, 80)], "shirt_sh")
s.px([(32, 56), (32, 63), (32, 70)], "button")
# the turned-up collar, standing either side of his jaw
s.poly([(18, 37), (24, 40), (27, 48), (30, 58), (24, 60), (19, 48)], "coat_hi")
s.poly([(46, 37), (40, 40), (37, 48), (34, 58), (40, 60), (45, 48)], "coat_sh")
# neck
s.rect((27, 35, 36, 46), "skin")
s.rect((33, 35, 36, 46), "skin_sh")
s.px([(28, 39), (30, 40), (33, 39), (29, 42)], "stubble")
# hands in the coat pockets: only the pocket flaps show
s.line([(12, 66), (21, 64)], "coat_sh")
s.line([(43, 64), (52, 66)], "hat_sh")
s.px([(14, 67), (16, 67)], "skin_sh")  # a knuckle at the pocket's edge
# head, long in the face
s.oval((21, 11, 42, 38), "skin")
s.poly([(36, 16), (42, 21), (41, 31), (36, 38), (35, 28)], "skin_sh")
s.oval((17, 20, 22, 28), "skin")
s.oval((40, 20, 45, 28), "skin_sh")
s.poly([(20, 17), (24, 15), (24, 22), (21, 24)], "hair")
s.poly([(43, 17), (39, 15), (39, 22), (42, 24)], "hair_sh")
# a week of stubble on the jaw and lip
for p in [(23, 29), (24, 31), (25, 33), (27, 35), (29, 36), (31, 37), (33, 36), (35, 35), (37, 33), (38, 31), (39, 29),
          (26, 31), (28, 33), (34, 33), (36, 31), (28, 30), (30, 30), (32, 30), (34, 30), (24, 34), (38, 34), (30, 35)]:
    s.px([p], "stubble")
# the hat: a wide brim, worn low, its crown dented
s.poly([(12, 16), (20, 13), (31, 12), (42, 13), (50, 16), (46, 18), (31, 17), (16, 18)], "hat")
s.poly([(31, 17), (46, 18), (50, 16), (42, 15)], "hat_sh")
s.poly([(20, 13), (21, 6), (25, 2), (31, 3), (37, 2), (41, 6), (42, 13), (31, 12)], "hat")
s.poly([(37, 2), (41, 6), (42, 13), (38, 12)], "hat_sh")
s.poly([(21, 6), (25, 2), (27, 3), (23, 7), (22, 12)], "hat_hi")
s.line([(28, 3), (31, 6), (34, 3)], "hat_sh")  # the dent
s.rect((21, 10, 41, 12), "band")
s.poly([(16, 18), (31, 17), (46, 18), (42, 20), (31, 19), (20, 20)], "hat_sh")  # its shadow on his brow
# eyes narrowed, looking off to the side from under the brim
s.rect((24, 23, 27, 23), "white")
s.rect((34, 23, 37, 23), "white")
s.rect((24, 23, 25, 23), "eye")
s.rect((34, 23, 35, 23), "eye")
s.px([(24, 22), (25, 22), (26, 22), (27, 22), (34, 22), (35, 22), (36, 22), (37, 22)], "hair_sh")
s.px([(24, 24), (25, 24), (36, 24), (37, 24)], "skin_sh")
# nose, long
s.px([(31, 23), (31, 24), (31, 25), (31, 26), (31, 27), (32, 28), (30, 28)], "skin_sh")
# an easy half-smile, and the match in the corner of it
s.line([(28, 32), (33, 32)], "lip")
s.px([(34, 31)], "lip")
s.line([(34, 32), (41, 35)], "match")
s.px([(41, 35), (42, 35)], "head")

finish(s)
