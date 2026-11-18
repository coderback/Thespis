# Sándor "Sandy" Kovács, the watchman's son: a smith's broad shoulders in a blue work jacket over a leather forge
# apron, a flat cap, a short dark beard, and his right hand bandaged from dragging his father out of the fire. Brows
# down, jaw set: he wants someone to pay.
from kit import Sheet, finish

s = Sheet(dict(
    skin=(217, 168, 130), skin_sh=(176, 128, 96), skin_hi=(236, 196, 160), flush=(200, 120, 96),
    beard=(58, 42, 30), beard_sh=(38, 26, 20), beard_hi=(86, 64, 46),
    eye=(30, 24, 22), white=(228, 220, 204), lip=(150, 86, 70),
    coat=(61, 74, 92), coat_sh=(40, 50, 64), coat_hi=(86, 102, 124),
    cap=(85, 88, 94), cap_sh=(58, 60, 66), cap_hi=(112, 116, 122),
    shirt=(200, 192, 176), shirt_sh=(160, 152, 138),
    apron=(112, 72, 44), apron_sh=(80, 50, 30), buckle=(150, 150, 156),
    bandage=(232, 226, 212), bandage_sh=(190, 182, 166), blood=(150, 50, 40), soot=(50, 46, 46),
))

# the jacket, cut for a big man, light from the left
s.poly([(7, 52), (18, 45), (28, 44), (36, 44), (46, 45), (57, 52), (60, 80), (4, 80)], "coat")
s.poly([(46, 46), (57, 52), (60, 80), (48, 80), (49, 60)], "coat_sh")
s.poly([(7, 52), (13, 48), (10, 66), (6, 80), (4, 80)], "coat_hi")
# the open shirt, and the forge apron's bib over it
s.poly([(25, 46), (32, 52), (39, 46), (41, 80), (23, 80)], "shirt")
s.poly([(34, 50), (39, 46), (41, 80), (37, 80)], "shirt_sh")
s.poly([(24, 56), (40, 56), (42, 80), (22, 80)], "apron")
s.poly([(36, 56), (40, 56), (42, 80), (38, 80)], "apron_sh")
s.line([(24, 56), (20, 46)], "apron_sh")  # the neck strap
s.line([(40, 56), (44, 46)], "apron_sh")
s.px([(24, 57), (40, 57)], "buckle")
s.px([(27, 64), (34, 70), (29, 75)], "soot")
s.poly([(18, 45), (25, 46), (28, 56), (22, 58)], "coat_hi")
s.poly([(46, 45), (39, 46), (36, 56), (42, 58)], "coat_sh")
# neck, thick
s.rect((26, 35, 37, 46), "skin")
s.rect((34, 35, 37, 46), "skin_sh")
s.poly([(29, 46), (32, 52), (35, 46)], "skin_sh")
# the bandaged hand, a fist held at his chest: fingers bare, the palm and wrist wrapped
s.rect((40, 70, 49, 78), "coat_sh")  # the cuff
s.poly([(40, 64), (49, 63), (50, 71), (41, 72)], "bandage")  # the wrapped palm and wrist
s.poly([(46, 63), (49, 63), (50, 71), (47, 71)], "bandage_sh")
s.line([(40, 66), (49, 65)], "bandage_sh")
s.line([(41, 69), (50, 68)], "bandage_sh")
s.px([(44, 67), (45, 67)], "blood")
s.oval((38, 56, 49, 66), "skin")  # the fist above it, knuckles to you
s.rect((45, 59, 49, 65), "skin_sh")
for x in (41, 43, 45):
    s.line([(x, 58), (x, 64)], "skin_sh")
s.px([(40, 57), (42, 57), (44, 57)], "skin_hi")
# head, broad in the jaw
s.oval((20, 11, 43, 38), "skin")
s.poly([(37, 16), (43, 22), (42, 32), (37, 38), (36, 28)], "skin_sh")
s.oval((23, 16, 27, 20), "skin_hi")
s.oval((17, 21, 22, 29), "skin")
s.oval((41, 21, 46, 29), "skin_sh")
# a short dark beard along the jaw
s.poly([(20, 24), (22, 24), (24, 33), (31, 36), (38, 33), (40, 24), (43, 24), (42, 34), (37, 40), (31, 41), (25, 40),
        (21, 34)], "beard")
s.poly([(38, 33), (40, 24), (43, 24), (42, 34), (37, 40), (33, 41)], "beard_sh")
s.px([(23, 34), (26, 37), (29, 39)], "beard_hi")
s.poly([(26, 31), (31, 30), (36, 31), (35, 33), (31, 32), (27, 33)], "beard")  # moustache
# the flat cap, pulled down
s.poly([(16, 17), (18, 9), (24, 4), (33, 3), (41, 5), (46, 10), (47, 16), (43, 17), (31, 15), (20, 18)], "cap")
s.poly([(38, 4), (46, 10), (47, 16), (43, 17), (42, 9)], "cap_sh")
s.poly([(18, 9), (24, 4), (28, 4), (21, 10), (18, 15)], "cap_hi")
s.poly([(16, 17), (31, 15), (43, 17), (40, 20), (31, 19), (19, 21)], "cap_sh")  # the peak
s.line([(24, 6), (40, 12)], "cap_sh")  # a seam
# brows drawn down hard
s.px([(23, 20), (24, 21), (25, 21), (26, 22), (27, 22)], "beard_sh")
s.px([(35, 22), (36, 22), (37, 21), (38, 21), (39, 20)], "beard_sh")
s.rect((24, 23, 27, 24), "white")
s.rect((35, 23, 38, 24), "white")
s.rect((25, 23, 26, 24), "eye")
s.rect((36, 23, 37, 24), "eye")
s.px([(24, 25), (37, 25)], "skin_sh")
# nose, broad; a flush of temper
s.px([(31, 24), (31, 25), (31, 26), (31, 27), (32, 28), (30, 28), (33, 28)], "skin_sh")
s.px([(24, 28), (25, 28), (37, 28), (38, 28)], "flush")
# mouth tight under the moustache
s.rect((29, 34, 34, 34), "lip")
s.px([(28, 35), (35, 35)], "beard_sh")

finish(s)
