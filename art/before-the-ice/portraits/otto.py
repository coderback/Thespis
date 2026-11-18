# Otto Brand, trader and lender, back from picking through the ashes of his store: a Hamburg merchant's coat and
# watch chain, soot on his sleeve, a scorched ledger under his hand, and a look that's already pricing you.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(232, 188, 156), skin_sh=(194, 144, 114), skin_hi=(246, 214, 186), flush=(214, 134, 112),
    hair=(70, 52, 40), hair_sh=(44, 32, 26), hair_hi=(108, 84, 64), grey=(140, 128, 118),
    eye=(34, 28, 24), white=(232, 224, 208), lip=(160, 92, 80),
    coat=(64, 72, 64), coat_sh=(42, 48, 44), coat_hi=(92, 102, 90),
    vest=(132, 98, 44), vest_sh=(98, 70, 30), vest_hi=(164, 128, 64),
    collar=(238, 232, 220), collar_sh=(198, 190, 176), tie=(40, 30, 34),
    gold=(220, 178, 72), gold_sh=(160, 120, 40),
    soot=(46, 42, 40),
    ledger=(96, 42, 34), ledger_sh=(64, 28, 24), pages=(214, 196, 160), char=(30, 22, 20), burnt=(120, 82, 50),
))

# the frock coat, broad and well cut, light from the left
s.poly([(10, 52), (20, 45), (29, 44), (35, 44), (44, 45), (54, 52), (57, 80), (7, 80)], "coat")
s.poly([(44, 46), (54, 52), (57, 80), (46, 80), (47, 60)], "coat_sh")
s.poly([(10, 52), (16, 48), (13, 66), (9, 80), (7, 80)], "coat_hi")
# the waistcoat in the opening, a gold chain across it
s.poly([(25, 48), (32, 54), (39, 48), (40, 80), (24, 80)], "vest")
s.poly([(34, 52), (39, 48), (40, 80), (36, 80)], "vest_sh")
s.px([(32, 58), (32, 63), (32, 68), (32, 73)], "vest_hi")
s.line([(25, 62), (28, 64), (32, 65), (35, 64)], "gold")
s.line([(28, 65), (32, 66)], "gold_sh")
s.px([(35, 63), (36, 63)], "gold")
# lapels
s.poly([(20, 45), (25, 46), (32, 56), (26, 62), (22, 52)], "coat_hi")
s.poly([(44, 45), (39, 46), (32, 56), (38, 62), (42, 52)], "coat_sh")
# neck, a high starched collar and a dark tie
s.rect((27, 34, 36, 44), "skin")
s.rect((33, 34, 36, 44), "skin_sh")
s.poly([(25, 42), (32, 46), (39, 42), (39, 46), (32, 50), (25, 46)], "collar")
s.poly([(32, 46), (39, 42), (39, 46), (32, 50)], "collar_sh")
s.poly([(30, 47), (34, 47), (33, 54), (31, 54)], "tie")
# a scorched ledger held against his coat, his hand on it; soot on the cuff
s.poly([(39, 56), (55, 53), (58, 80), (41, 80)], "ledger")
s.poly([(52, 54), (55, 53), (58, 80), (54, 80)], "ledger_sh")
s.poly([(39, 56), (41, 56), (43, 80), (41, 80)], "pages")
s.rect((44, 60, 52, 61), "gold_sh")  # a brass corner band, the title gone
s.poly([(46, 54), (55, 53), (55, 58), (51, 60), (48, 57)], "char")
s.px([(47, 57), (50, 58), (53, 59), (45, 55)], "burnt")
s.poly([(38, 70), (44, 68), (46, 76), (40, 78)], "coat_sh")
s.px([(40, 72), (42, 71), (41, 75)], "soot")
s.oval((43, 68, 52, 77), "skin")
s.rect((48, 71, 52, 76), "skin_sh")
for x in (46, 49):
    s.line([(x, 73), (x, 77)], "skin_sh")
s.px([(51, 69), (52, 69)], "gold")  # a signet ring
# head: hair oiled flat and parted, side-whiskers grown into the moustache
s.oval((20, 10, 42, 38), "skin")
s.poly([(36, 15), (42, 20), (41, 32), (36, 38), (35, 28)], "skin_sh")
s.oval((23, 14, 28, 18), "skin_hi")
s.poly([(19, 21), (20, 13), (25, 8), (33, 7), (40, 9), (44, 15), (43, 21), (40, 21), (39, 14), (28, 13), (22, 16), (22, 21)], "hair")
s.poly([(25, 8), (33, 7), (30, 9), (24, 11)], "hair_hi")
s.line([(28, 8), (27, 13)], "hair_sh")  # the parting
s.poly([(40, 12), (44, 15), (43, 22), (41, 18)], "hair_sh")
s.px([(20, 16), (21, 15), (42, 15)], "grey")
# ears, and side-whiskers grown down into the moustache
s.oval((17, 21, 22, 29), "skin")
s.oval((40, 21, 45, 29), "skin_sh")
s.poly([(21, 22), (23, 22), (24, 31), (23, 33), (21, 29)], "hair")
s.poly([(41, 22), (39, 22), (38, 31), (39, 33), (41, 29)], "hair_sh")
s.px([(22, 25)], "grey")
# one brow up, one down: weighing you
s.px([(24, 20), (25, 19), (26, 19), (27, 20)], "hair_sh")
s.px([(34, 21), (35, 21), (36, 21), (37, 21), (38, 22)], "hair_sh")
s.rect((24, 22, 27, 24), "white")
s.rect((34, 23, 37, 24), "white")
s.rect((25, 22, 26, 24), "eye")
s.rect((35, 23, 36, 24), "eye")
s.px([(23, 25), (34, 25), (37, 25)], "skin_sh")
# nose, a broker's flush on the cheeks
s.px([(31, 24), (31, 25), (31, 26), (31, 27), (32, 28), (30, 28)], "skin_sh")
s.px([(24, 28), (25, 28), (37, 28), (38, 28), (25, 29), (37, 29)], "flush")
# the moustache, waxed and turned up at the ends
s.poly([(25, 30), (31, 29), (37, 30), (38, 32), (35, 33), (31, 32), (27, 33), (24, 32)], "hair")
s.px([(23, 30), (22, 29), (39, 30), (40, 29)], "hair")
s.px([(32, 30), (35, 31)], "hair_sh")
# a thin smile, held a little to one side
s.rect((28, 34, 33, 34), "lip")
s.px([(34, 33)], "lip")
s.px([(29, 36), (30, 36), (31, 36)], "skin_sh")

finish(s)
