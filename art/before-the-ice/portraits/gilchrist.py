# Inspector Gilchrist of the North-West Mounted Police, at the post: the scarlet serge with its brass buttons and
# dark collar, a winter fur cap, the Sam Browne strap across him, and his notebook open, pencil ready. Patient eyes
# under level brows; he'll write it down, if you don't mind.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(232, 191, 154), skin_sh=(194, 148, 116), skin_hi=(246, 214, 186), flush=(214, 140, 116),
    hair=(150, 104, 72), hair_sh=(108, 74, 52), grey=(178, 168, 154),
    eye=(34, 30, 28), white=(232, 224, 208), lip=(160, 96, 82),
    serge=(176, 38, 31), serge_sh=(124, 24, 22), serge_hi=(212, 72, 58),
    navy=(30, 36, 60), brass=(214, 176, 84), brass_sh=(150, 116, 48),
    belt=(122, 82, 46), belt_sh=(86, 56, 32),
    fur=(78, 58, 42), fur_sh=(52, 38, 28), fur_hi=(112, 88, 64),
    cover=(44, 38, 34), pages=(232, 224, 202), pages_sh=(196, 186, 162), writing=(70, 70, 90), pencil=(202, 168, 84),
))

# the scarlet tunic, light from the left
s.poly([(10, 52), (20, 45), (29, 44), (35, 44), (44, 45), (54, 52), (57, 80), (7, 80)], "serge")
s.poly([(44, 46), (54, 52), (57, 80), (46, 80), (47, 60)], "serge_sh")
s.poly([(10, 52), (16, 48), (13, 66), (9, 80), (7, 80)], "serge_hi")
s.line([(32, 50), (32, 80)], "serge_sh")  # the front, buttoned to the throat
for y in (53, 59, 65, 71, 77):
    s.px([(33, y)], "brass")
    s.px([(33, y + 1)], "brass_sh")
s.line([(12, 58), (20, 58)], "serge_sh")  # a breast pocket's flap
s.line([(41, 58), (50, 58)], "serge_sh")
s.px([(16, 59), (45, 59)], "brass")
# the Sam Browne strap from his shoulder across to the hip
s.poly([(41, 45), (45, 47), (21, 80), (16, 80)], "belt")
s.poly([(43, 46), (45, 47), (21, 80), (19, 80)], "belt_sh")
# neck, and the dark stand collar with its badges
s.rect((27, 34, 36, 44), "skin")
s.rect((33, 34, 36, 44), "skin_sh")
s.poly([(25, 42), (32, 45), (39, 42), (39, 47), (32, 50), (25, 47)], "navy")
s.px([(27, 45), (28, 45), (36, 45), (37, 45)], "brass")
# the notebook held open, the pencil in his other hand
s.poly([(11, 63), (31, 61), (32, 74), (12, 76)], "cover")
s.poly([(12, 62), (30, 60), (31, 72), (13, 74)], "pages")
s.line([(21, 61), (22, 73)], "pages_sh")
for y in (64, 66, 68, 70):
    s.line([(14, y + 1), (19, y)], "writing")
s.line([(24, y - 6), (28, y - 7)], "writing")
s.line([(24, 64), (28, 63)], "writing")
s.oval((6, 66, 15, 76), "skin")
s.rect((6, 72, 11, 76), "skin_sh")
s.line([(30, 70), (38, 60)], "pencil")
s.px([(30, 71)], "writing")
s.oval((33, 64, 42, 73), "skin")
s.rect((38, 68, 42, 73), "skin_sh")
# head
s.oval((20, 12, 42, 38), "skin")
s.poly([(36, 17), (42, 22), (41, 32), (36, 38), (35, 28)], "skin_sh")
# ears, and ginger hair going grey at the temples under the cap
s.oval((17, 21, 22, 29), "skin")
s.oval((40, 21, 45, 29), "skin_sh")
s.poly([(19, 16), (22, 14), (23, 22), (21, 24), (19, 21)], "hair")
s.poly([(43, 16), (40, 14), (39, 22), (41, 24), (43, 21)], "hair_sh")
s.px([(20, 19), (21, 21), (42, 19)], "grey")
# the fur cap, round and deep, worn square
s.poly([(17, 15), (18, 6), (22, 2), (31, 1), (40, 2), (44, 6), (45, 15), (40, 14), (31, 13), (22, 14)], "fur")
s.poly([(38, 2), (44, 6), (45, 15), (40, 14), (41, 6)], "fur_sh")
s.poly([(17, 13), (31, 12), (45, 13), (44, 19), (31, 18), (18, 19)], "fur_sh")
for p in [(21, 5), (25, 3), (29, 6), (33, 3), (24, 9), (28, 11), (35, 8), (20, 11), (31, 9), (37, 5)]:
    s.px([p], "fur_hi")
# level brows, eyes a little hooded: patient
s.px([(23, 21), (24, 21), (25, 21), (26, 21), (27, 21), (34, 21), (35, 21), (36, 21), (37, 21), (38, 21)], "hair_sh")
s.rect((24, 23, 27, 24), "white")
s.rect((34, 23, 37, 24), "white")
s.rect((25, 23, 26, 24), "eye")
s.rect((35, 23, 36, 24), "eye")
s.px([(24, 22), (25, 22), (26, 22), (27, 22), (34, 22), (35, 22), (36, 22), (37, 22)], "skin_sh")
s.px([(24, 26), (36, 26)], "skin_sh")
# nose, a weathered flush
s.px([(31, 24), (31, 25), (31, 26), (31, 27), (32, 28), (30, 28)], "skin_sh")
s.px([(24, 28), (25, 28), (37, 28), (38, 28)], "flush")
# a full moustache, ginger gone grey, over a closed mouth
s.poly([(24, 30), (31, 29), (38, 30), (39, 34), (36, 33), (31, 32), (26, 33), (23, 34)], "hair")
s.line([(25, 32), (37, 32)], "hair")
s.px([(29, 30), (34, 30)], "grey")
s.px([(24, 33), (38, 33)], "hair_sh")
s.rect((29, 34, 33, 34), "lip")
s.px([(29, 36), (30, 36), (31, 36), (32, 36)], "skin_sh")

finish(s)
