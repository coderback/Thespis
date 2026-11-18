# Coldwater Landing to the town plan, seen from the river, rendered pixel style.
# Run: MODE=town|walk SPRITES=<dir> blender -b --factory-startup --python build_town.py -- <out.png> <anchors.json> [blend]
# Blender X runs west to east, Y south to north (the river is north of the town). Buildings face the river (+Y).
import json
import math
import os
import random
import sys
import time

import bpy
from mathutils import Vector

t0 = time.time()
argv = sys.argv[sys.argv.index("--") + 1:]
OUT, ANCH = argv[0], argv[1]
BLEND = argv[2] if len(argv) > 2 else None
MODE = os.environ.get("MODE", "town")
SPRITES = os.environ["SPRITES"]
EXPORT = os.environ.get("EXPORT")  # a folder: write town.glb and town.json for the Godot game, then stop
WALK = MODE == "walk"

random.seed(1898)
bpy.ops.wm.read_factory_settings(use_empty=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coldwater_lib as L  # noqa: E402
from coldwater_lib import box, cabin, cyl, finish, lin, plain, point, sphere  # noqa: E402

S = bpy.context.scene
PW, PD, PH = 34.0, 27.0, 4.6
FRONT = -1.0      # building fronts
S_BANK, N_BANK = 2.3, 6.6


class turned:
    """Everything built inside the block is turned about (cx, cy) by `ang` radians."""

    def __init__(self, cx, cy, ang):
        self.cx, self.cy, self.ang = cx, cy, ang

    def __enter__(self):
        self.before = {o.name for o in S.objects}
        self.ci = len(L.CHIMNEYS)
        return self

    def __exit__(self, *exc):
        new = [o for o in S.objects if o.name not in self.before and o.parent is None]
        e = bpy.data.objects.new("pivot", None)
        e.location = (self.cx, self.cy, 0)
        S.collection.objects.link(e)
        bpy.context.view_layer.update()
        for o in new:
            o.parent = e
            o.matrix_parent_inverse = e.matrix_world.inverted()
        e.rotation_euler = (0, 0, self.ang)
        bpy.context.view_layer.update()
        ca, sa = math.cos(self.ang), math.sin(self.ang)
        for i in range(self.ci, len(L.CHIMNEYS)):
            x, y, z = L.CHIMNEYS[i]
            dx, dy = x - self.cx, y - self.cy
            L.CHIMNEYS[i] = (self.cx + dx * ca - dy * sa, self.cy + dx * sa + dy * ca, z)


def bench_z(y):
    return 0.0 if y > -5 else 1.3 * ((-y - 5) / 8.5) ** 1.2


# ---------------------------------------------------------------- plinth, desk, ground with the bench rising behind
box("plinth", (PW, PD, PH), (0, 0, -PH / 2), L.STRATA)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=300, y_subdivisions=240, size=1, location=(0, 0, 0.02))
g = bpy.context.active_object
g.scale = (PW, PD, 1)
bpy.ops.object.transform_apply(scale=True)
for v in g.data.vertices:
    v.co.z += bench_z(v.co.y)
for p in g.data.polygons:
    p.use_smooth = True
tex = bpy.data.textures.new("snowlumps", "CLOUDS")
tex.noise_scale = 1.4
md = g.modifiers.new("lumps", "DISPLACE")
md.texture = tex
md.strength = 0.05
finish(g, "ground", L.SNOW)
box("desk", (400, 400, 0.2), (0, 0, -PH - 0.1), L.DESK)
box("river", (PW, N_BANK - S_BANK, 0.06), (0, (S_BANK + N_BANK) / 2, 0.035), L.ICE)
box("ice_section", (0.04, N_BANK - S_BANK, 0.9), (PW / 2 + 0.02, (S_BANK + N_BANK) / 2, -0.45), plain("icecut", "#cfe0ee", 0.3))
box("water_section", (0.04, N_BANK - S_BANK, 1.9), (PW / 2 + 0.02, (S_BANK + N_BANK) / 2, -1.7), plain("water", "#24405e", 0.3))
TRODDEN = plain("trodden", "#b9c4d3", 0.9)
box("street", (33.4, 1.2, 0.02), (0, 0.4, 0.035), TRODDEN, bevel=0.3, segs=3)
box("landing", (5.0, 1.3, 0.02), (1.6, 1.65, 0.035), TRODDEN, bevel=0.3, segs=3)
box("backlane", (31.0, 0.7, 0.02), (0, -4.4, 0.035), TRODDEN, bevel=0.2, segs=3)

# the spruce point: a spit of land into the river at the west end, hiding the bend
pt = [(-17, S_BANK - 0.05), (-12.4, S_BANK - 0.05), (-12.9, 3.0), (-13.8, 3.8), (-14.9, 4.25), (-16.0, 4.1), (-17, 3.7)]
me = bpy.data.meshes.new("point")
me.from_pydata([(x, y, 0.16) for x, y in pt], [], [tuple(range(len(pt)))])
o = bpy.data.objects.new("spruce_point", me)
S.collection.objects.link(o)
sol = o.modifiers.new("solid", "SOLIDIFY")
sol.thickness = 0.2
sol.material_offset_rim = 1
o.data.materials.append(L.SNOW)
o.data.materials.append(plain("earthbank", "#4a3a2c", 1.0))
for (ax, ay), (bx, by) in zip(pt[1:], pt[2:]):
    n = max(2, int(math.hypot(bx - ax, by - ay) / 0.45))
    for k in range(n):
        t = (k + 0.5) / n
        x, y = ax + (bx - ax) * t, ay + (by - ay) * t
        sphere("pointbank", (x, y, 0.1), (0.5, 0.5, 0.1), L.SNOW)
CRACK = plain("crackline", "#24364a", 0.9)
cr = [(-15.2, 4.5), (-15.6, 4.9), (-15.3, 5.3), (-15.8, 5.7), (-15.5, 6.1), (-15.9, 6.45)]
# the creek, up to the north edge
CREEK = [(-2.4, N_BANK), (-2.6, 8.4), (-3.6, 10.2), (-4.2, 11.8), (-5.6, 13.4)]


def strip(name, pts, width, mat, z):
    vs, fs = [], []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        nx, ny = -dy / ln * width / 2, dx / ln * width / 2
        k = len(vs)
        vs += [(ax - nx, ay - ny, z), (ax + nx, ay + ny, z), (bx + nx, by + ny, z), (bx - nx, by - ny, z)]
        fs.append((k, k + 1, k + 2, k + 3))
    m = bpy.data.meshes.new(name)
    m.from_pydata(vs, [], fs)
    m.update()
    ob = bpy.data.objects.new(name, m)
    S.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


strip("creek", CREEK, 0.7, L.ICE, 0.06)
strip("crack", cr, 0.08, CRACK, 0.072)
strip("crack2", [(-15.6, 4.9), (-15.0, 5.0), (-14.6, 5.25)], 0.05, CRACK, 0.072)


def near(x, y, pts, r):
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        if math.hypot(x - ax - dx * t, y - ay - dy * t) < r:
            return True
    return False


# snowbanks along both banks, gaps at the landing, the creek mouth and the bend crossing
for i in range(48):
    x = -16.4 + i * 0.7
    if not (-0.4 < x < 2.4) and not (x < -15.4) and not (-14.8 < x < -12.4):
        sphere("bank", (x + random.uniform(0, 0.3), S_BANK + random.uniform(0, 0.12), 0.02), (random.uniform(0.6, 1.0), random.uniform(0.3, 0.45), random.uniform(0.16, 0.28)), L.SNOW)
    if not (-3.3 < x < -1.6) and not (x < -15.4):
        sphere("bank", (x + random.uniform(0, 0.3), N_BANK - random.uniform(0, 0.12), 0.02), (random.uniform(0.6, 1.0), random.uniform(0.3, 0.45), random.uniform(0.16, 0.28)), L.SNOW)
for i in range(24):
    x, y = random.uniform(-12, 15), random.uniform(S_BANK + 0.6, N_BANK - 0.6)
    if math.hypot(x - 4.6, y - 4.4) > 1.4 and not (-6.5 < x < -1.2 and y < 3.6) and not (-3.5 < x < 1.6 and y > 3.2) and x > -11:
        sphere("icedrift", (x, y, 0.05), (random.uniform(0.5, 1.3), random.uniform(0.2, 0.45), random.uniform(0.04, 0.08)), L.SNOW)

# ---------------------------------------------------------------- buildings
F = lambda u0, u1, z0, z1, kind="window": ("front", u0, u1, z0, z1, kind)  # noqa: E731
Rd = lambda u0, u1: ("right", u0, u1, 0.0, 1.6, "door")  # noqa: E731
Rw = lambda u0, u1, kind="window": ("right", u0, u1, 0.85, 1.4, kind)  # noqa: E731


def gable_front(name, x, w, depth, h, openings, front_y=FRONT, faces="north", **kw):
    """A gable-fronted log cabin: built with its gable on +X, turned so the gable faces the street (or the town)."""
    cy = front_y - depth / 2 if faces == "north" else front_y + depth / 2
    with turned(x, cy, math.pi / 2 if faces == "north" else -math.pi / 2):
        cabin(name, x, cy, depth, w, h, openings=openings, **kw)
    return cy


gable_front("your_cabin", -13.4, 2.2, 2.6, 1.9, [Rd(-0.4, 0.4), Rw(0.55, 0.95)], woodpile="side")
gable_front("cabin_w", -10.6, 2.0, 2.4, 1.8, [Rd(-0.4, 0.4), Rw(0.5, 0.9, "dark")])
gable_front("cabin_e", 5.9, 2.0, 2.4, 1.8, [Rd(-0.4, 0.4), Rw(-0.9, -0.5)])
gable_front("forge", 2.8, 1.8, 2.2, 1.7, [("right", -0.45, 0.45, 0.0, 1.6, "firedoor"), Rw(0.55, 0.85)], pipe=False)
box("forge_chimney", (0.45, 0.45, 2.9), (2.15, FRONT - 1.5, 1.45), plain("stone", "#6b6660", 0.95), bevel=0.03)

# Maggie Doyle's roadhouse: logs behind a board false front, porch over the boardwalk; built facing -Y, turned
RX, RW, RD = -6.6, 3.6, 2.6
RY = FRONT - RD / 2 - 0.2
with turned(RX, RY, math.pi):
    rh_h, rh_rh = cabin("roadhouse", RX, RY, RW, RD, 2.6, openings=[("right", -0.5, 0.3, 0.95, 1.6, "window")], front_logs=False, woodpile=True)
    y0 = RY - RD / 2 - 0.2
    FW, FH = RW + 0.4, rh_h + rh_rh + 1.0
    n = int(FW / 0.2)
    for i in range(n):
        box("ff_board", (0.19, 0.05, FH + random.uniform(-0.015, 0.015)), (RX - FW / 2 + 0.1 + i * FW / n, y0, FH / 2), L.PAINT)
    for sx in (-1, 1):
        box("ff_trim", (0.14, 0.09, FH), (RX + sx * (FW / 2 - 0.02), y0 - 0.03, FH / 2), L.TRIM)
    box("ff_cornice", (FW + 0.3, 0.3, 0.16), (RX, y0 + 0.03, FH + 0.05), L.TRIM, bevel=0.02)
    box("ff_snow", (FW + 0.32, 0.34, 0.14), (RX, y0 + 0.03, FH + 0.2), L.SNOW, bevel=0.06, segs=4)
    box("sign", (FW - 0.5, 0.06, 0.62), (RX, y0 - 0.05, FH - 0.55), L.TRIM)
    font = None
    for path in ("C:/Windows/Fonts/GeorgiaPro-Bold.ttf", "C:/Windows/Fonts/georgiab.ttf"):
        try:
            font = bpy.data.fonts.load(path)
            break
        except Exception:
            pass
    c = bpy.data.curves.new("sign_text", "FONT")
    c.body, c.size, c.extrude, c.align_x, c.align_y = "ROADHOUSE", 0.42, 0.012, "CENTER", "CENTER"
    if font:
        c.font = font
    st = bpy.data.objects.new("sign_text", c)
    st.location, st.rotation_euler = (RX, y0 - 0.085, FH - 0.55), (math.pi / 2, 0, 0)
    st.data.materials.append(L.CREAM)
    S.collection.objects.link(st)
    for u in (-1.1, 1.1):
        wd, z0, z1 = 0.75, 0.95, 1.85
        for side in (u - wd / 2 - 0.05, u + wd / 2 + 0.05):
            box("fw_frame", (0.1, 0.08, z1 - z0 + 0.1), (RX + side, y0 - 0.05, (z0 + z1) / 2), L.TRIM)
        box("fw_head", (wd + 0.3, 0.12, 0.12), (RX + u, y0 - 0.06, z1 + 0.08), L.TRIM)
        box("fw_glass", (wd, 0.02, z1 - z0), (RX + u, y0 - 0.02, (z0 + z1) / 2), L.GLASS)
        box("fw_mull", (0.035, 0.05, z1 - z0), (RX + u, y0 - 0.04, (z0 + z1) / 2), L.TRIM)
        box("fw_mull", (wd, 0.05, 0.035), (RX + u, y0 - 0.04, (z0 + z1) / 2), L.TRIM)
        point("fw_spill", (RX + u, y0 - 0.7, 1.4), 22, radius=0.3)
    for i in range(4):
        box("rd_door", (0.95 / 4 - 0.012, 0.05, 2.0), (RX - 0.475 + (i + 0.5) * 0.95 / 4, y0 - 0.05, 0.15 + 1.0), L.PLANK_Z)
    PDp = 0.85
    for sx in (-1, 1):
        box("post", (0.13, 0.13, 2.3), (RX + sx * (FW / 2 - 0.05), y0 - PDp + 0.1, 0.13 + 1.15), L.PLANK_Z)
    a2 = math.atan2(0.24, PDp)
    mid = Vector((RX, y0 - PDp / 2 - 0.05, 2.62))
    nrm = Vector((0, -math.sin(a2), math.cos(a2)))
    box("porchroof", (FW + 0.5, PDp + 0.35, 0.06), mid, L.PLANK_Y, rot=(a2, 0, 0))
    box("porchsnow", (FW + 0.56, PDp + 0.4, 0.22), mid + nrm * 0.14, L.SNOW, rot=(a2, 0, 0), bevel=0.1, segs=4)
    edge = mid + Vector((0, -(PDp + 0.35) / 2 * math.cos(a2), -(PDp + 0.35) / 2 * math.sin(a2)))
    xx = -FW / 2 - 0.2
    while xx < FW / 2 + 0.2:
        ln = random.uniform(0.1, 0.45)
        cyl("icicle", 0.035, ln, (RX + xx, edge.y + 0.02, edge.z - 0.06 - ln / 2), (math.pi, 0, 0), L.ICICLE, verts=6, r2=0.0)
        xx += random.uniform(0.1, 0.22)
    box("lantern", (0.16, 0.16, 0.22), (RX + 0.75, y0 - 0.3, 2.0), L.GLASS)
    point("lanternlight", (RX + 0.75, y0 - 0.5, 1.9), 30, radius=0.12)

# Brand's store, burned: charred posts and the fallen front, the cordwood stack out back
SX0, SY0 = 0.0, FRONT - 1.2
CHAR = plain("char", "#151312", 1.0)
SOOT = plain("soot", "#2b2a2a", 1.0)
for (dx, dy, r, sx, sy) in [(0, 0, 1.5, 1.2, 0.85), (-0.9, 0.5, 0.8, 1, 0.8), (1.0, -0.4, 0.8, 1, 0.9), (0.6, 0.8, 0.6, 1.2, 0.8), (-0.8, -0.6, 0.7, 1.1, 0.8), (1.6, 0.4, 0.45, 1, 1)]:
    cyl("soot", r, 0.02, (SX0 + dx, SY0 + dy, 0.045), (0, 0, random.uniform(0, 3)), SOOT, verts=9).scale = (sx, sy, 1)
for (x, hh, y, tilt) in [(-1.4, 1.1, -0.9, 0), (1.3, 1.1, -0.8, 0.25), (-1.4, 1.1, 0.9, -0.15), (1.3, 0.7, 0.9, 0.4), (0.1, 0.45, -0.9, 0)]:
    box("charpost", (0.22, 0.22, hh * 2), (SX0 + x, SY0 + y, hh), CHAR, rot=(0, tilt, 0))
box("charbeam", (3.0, 0.22, 0.22), (SX0 + 0.1, SY0 + 0.1, 0.35), CHAR, rot=(0.18, -0.1, 0.4))
box("charwall", (0.25, 2.0, 1.1), (SX0 - 1.45, SY0, 0.55), CHAR)
box("fallenfront", (2.4, 1.3, 0.1), (SX0 + 0.3, SY0 + 1.0, 0.1), plain("charred", "#2a221c", 1.0), rot=(-0.04, 0.06, -0.2))
IRON = plain("castiron", "#26262a", 0.6, 0.6)
box("stove", (0.55, 0.42, 0.5), (SX0 - 0.5, SY0 - 0.1, 0.3), IRON, bevel=0.03)
for (dx, dy) in [(-0.22, -0.16), (0.22, -0.16), (-0.22, 0.16), (0.22, 0.16)]:
    box("stoveleg", (0.06, 0.06, 0.06), (SX0 - 0.5 + dx, SY0 - 0.1 + dy, 0.04), IRON)
cyl("stovepipe", 0.07, 0.8, (SX0 - 0.42, SY0 - 0.05, 0.85), (0.35, 0.2, 0), IRON, verts=10)
SAFE = plain("safegreen", "#2f3a33", 0.6, 0.4)
box("safe", (0.6, 0.55, 0.7), (SX0 + 0.75, SY0 - 0.45, 0.38), SAFE, rot=(0, 0, 0.12), bevel=0.02)
box("safedoor", (0.5, 0.06, 0.6), (SX0 + 0.9, SY0 + 0.1, 0.38), SAFE, rot=(0, 0, -0.9), bevel=0.015)
box("safedark", (0.46, 0.02, 0.56), (SX0 + 0.72, SY0 - 0.17, 0.38), plain("safeinside", "#0d0d0e", 1.0), rot=(0, 0, 0.12))
for (x, y, ln, rz) in [(-0.9, 0.4, 2.2, 1.57), (-0.3, 0.35, 2.4, 1.6), (0.4, 0.2, 1.6, 1.45), (1.0, 0.45, 1.2, 1.7)]:
    box("joist", (0.14, ln, 0.12), (SX0 + x, SY0 + y, 0.1), CHAR, rot=(0, 0, rz - 1.57))
for _ in range(16):
    box("debris", (random.uniform(0.15, 0.5), random.uniform(0.06, 0.12), random.uniform(0.05, 0.1)),
        (SX0 + random.uniform(-1.3, 1.3), SY0 + random.uniform(-0.8, 0.9), 0.07), CHAR, rot=(0, random.uniform(-0.2, 0.2), random.uniform(0, 3.14)))
for (x, y, sx, sy) in [(-1.1, -0.6, 0.5, 0.35), (0.9, 0.7, 0.45, 0.3), (-0.2, 0.9, 0.4, 0.25)]:
    sphere("ruinsnow", (SX0 + x, SY0 + y, 0.02), (sx, sy, 0.07), L.SNOW)
for row in range(4):
    for i in range(9 - row):
        cyl("cordwood", 0.08, 0.6, (SX0 - 0.6 + i * 0.17 + row * 0.085, FRONT - 3.0, 0.09 + row * 0.15), (math.pi / 2, 0, random.uniform(0, 6)), random.choice(L.LOGS), verts=8)
sphere("cordsnow", (SX0 + 0.08, FRONT - 3.0, 0.63), (0.55, 0.3, 0.05), L.SNOW)

# the Mounted Police post: a picket stockade, the barracks inside, the flag; built facing -Y, turned
PX, PY, PWID, PDEP = 9.6, FRONT - 1.7, 4.4, 3.2
with turned(PX, PY, math.pi):
    cabin("barracks", PX - 0.3, PY + 0.2, 3.0, 1.8, 1.9, openings=[F(-1.1, -0.6, 0.85, 1.4), F(-0.25, 0.35, 0.0, 1.6, "door"), F(0.7, 1.2, 0.85, 1.4)])
    for i in range(int(PWID / 0.14)):
        x = PX - PWID / 2 + i * 0.14
        if abs(x - PX) > 0.5:
            box("picket", (0.09, 0.09, 1.0 + random.uniform(-0.04, 0.04)), (x, PY - PDEP / 2, 0.5), L.LOGS[i % 3])
        box("picket", (0.09, 0.09, 1.0), (x, PY + PDEP / 2, 0.5), L.LOGS[(i + 1) % 3])
    for i in range(int(PDEP / 0.14)):
        y = PY - PDEP / 2 + i * 0.14
        for sx in (-1, 1):
            box("picket", (0.09, 0.09, 1.0), (PX + sx * PWID / 2, y, 0.5), L.LOGS[i % 3])
    cyl("flagpole", 0.05, 5.0, (PX + 1.6, PY - 1.0, 2.5), (0, 0, 0), L.METAL, verts=8)
    box("flag", (1.0, 0.03, 0.6), (PX + 2.12, PY - 1.0, 4.65), plain("flagred", "#b3262b", 0.9))

# the mission: the church with its belfry, and the infirmary, at the east end
CHX = 13.0
cy = gable_front("church", CHX, 1.5, 2.6, 2.2, [Rd(-0.35, 0.35), ("right", -0.13, 0.13, 1.85, 2.15, "window"),
                 F(-0.95, -0.7, 0.6, 1.75), F(-0.15, 0.1, 0.6, 1.75), F(0.6, 0.85, 0.6, 1.75)], white=True, pipe=False)
box("belfry", (0.6, 0.6, 0.9), (CHX, FRONT - 0.3, 2.2 + 1.5 * 0.3 + 0.55), plain("belfrywhite", "#e8e6df", 0.9))
cyl("spire", 0.48, 1.0, (CHX, FRONT - 0.3, 2.2 + 1.5 * 0.3 + 1.5), (0, 0, math.pi / 4), plain("spiretin", "#4a4e55", 0.5, 0.5), verts=4, r2=0.0)
box("cross_v", (0.06, 0.06, 0.55), (CHX, FRONT - 0.3, 2.2 + 1.5 * 0.3 + 2.25), L.METAL)
box("cross_h", (0.32, 0.06, 0.06), (CHX, FRONT - 0.3, 2.2 + 1.5 * 0.3 + 2.35), L.METAL)
IX, IW, ID = 15.4, 2.6, 2.0
IY = FRONT - ID / 2
with turned(IX, IY, math.pi):
    cabin("infirmary", IX, IY, IW, ID, 1.9, openings=[F(-1.05, -0.55, 0.8, 1.4), F(-0.3, 0.3, 0.0, 1.6, "door"), F(0.55, 1.05, 0.8, 1.4)], white=True)

# Věra's cabin across the ice at the creek mouth, its gable to the town
VX = -4.1
VY = gable_front("vera", VX, 2.0, 2.2, 1.8, [Rd(-0.4, 0.4), Rw(0.5, 0.9)], front_y=N_BANK + 0.5, faces="south", woodpile="side")

# boardwalk along the fronts
for i in range(160):
    x = -15.0 + i * 0.2
    if x < 16.6:
        box("bw", (0.185, 0.7, 0.07), (x, FRONT + 0.4, 0.11 + random.uniform(-0.006, 0.006)), L.PLANK_X if hasattr(L, "PLANK_X") else L.PLANK_Y)

# ---------------------------------------------------------------- the landing: dock, clock post, tent, steamer; the tripod on the ice
DX0 = 1.0
box("dock", (1.3, 2.6, 0.15), (DX0, S_BANK + 0.5, 0.09), L.PLANK_Y)
for (x, y) in [(DX0 - 0.6, S_BANK + 1.7), (DX0 + 0.6, S_BANK + 1.7), (DX0 - 0.6, S_BANK + 0.2), (DX0 + 0.6, S_BANK + 0.2)]:
    cyl("dockpost", 0.08, 0.6, (x, y, 0.2), (0, 0, 0), L.LOGS[0], verts=8)
    sphere("dockpostsnow", (x, y, 0.5), (0.11, 0.11, 0.05), L.SNOW)
box("clockpost", (0.16, 0.16, 2.0), (2.1, 1.5, 1.0), L.PLANK_Z)
cyl("clockface", 0.22, 0.04, (2.1, 1.59, 1.75), (math.pi / 2, 0, 0), L.CREAM, verts=20)
TT = Vector((4.6, 4.4, 2.3))
for (dx, dy) in [(-0.8, -0.5), (0.8, -0.4), (0.05, 0.9)]:
    foot = Vector((4.6 + dx, 4.4 + dy, 0))
    v = TT - foot
    o = cyl("tripodleg", 0.05, v.length, (foot + TT) / 2, (0, 0, 0), L.LOGS[0], verts=6)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = v.to_track_quat("Z", "Y")
box("pennant", (0.4, 0.02, 0.25), (4.82, 4.4, 2.3), plain("pennant", "#1b2a4a", 0.9))
for (x, y, z) in [(3.6, 1.7, 0.0)]:  # Ashby's wall tent
    t = bpy.data.meshes.new("tent")
    t.from_pydata([(x - 0.6, y - 0.5, 0.05), (x + 0.6, y - 0.5, 0.05), (x + 0.6, y + 0.5, 0.05), (x - 0.6, y + 0.5, 0.05), (x - 0.6, y, 0.95), (x + 0.6, y, 0.95)],
                  [], [(0, 1, 5, 4), (3, 2, 5, 4), (0, 3, 4), (1, 2, 5)])
    to = bpy.data.objects.new("tent", t)
    S.collection.objects.link(to)
    to.data.materials.append(plain("canvas", "#cfc3a6", 0.95))


def tube(name, pts, radius, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    ob = bpy.data.objects.new(name, cu)
    S.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


def qbez(a, m, b, n=40):
    return [tuple(a * (1 - t) ** 2 + m * 2 * t * (1 - t) + b * t * t) for t in (i / n for i in range(n + 1))]


tube("clockline", qbez(TT, Vector((3.4, 2.6, 1.0)), Vector((2.1, 1.5, 1.9))), 0.012, plain("line", "#1a1714", 0.8))

# the sternwheeler, laid up in the ice west of the landing, bow upstream
SX1, SY1 = -3.9, S_BANK + 0.75
hull_pts = [(-3.0, -0.8), (2.3, -0.8), (2.9, -0.6), (3.3, 0), (2.9, 0.6), (2.3, 0.8), (-3.0, 0.8)]
me = bpy.data.meshes.new("hull")
me.from_pydata([(SX1 - x, SY1 + y, -0.15) for x, y in hull_pts], [], [tuple(range(len(hull_pts)))])
hull = bpy.data.objects.new("hull", me)
S.collection.objects.link(hull)
sol = hull.modifiers.new("solid", "SOLIDIFY")
sol.thickness = -0.55
sol.offset = 1
hull.data.materials.append(plain("hull", "#3b2b22", 0.9))
WHITEP = plain("steamerwhite", "#e2dccf", 0.85)
box("deck", (4.8, 1.45, 0.75), (SX1 + 0.3, SY1, 0.75), WHITEP)
for i in range(11):
    box("deckwin", (0.16, 0.02, 0.28), (SX1 - 1.8 + i * 0.4, SY1 - 0.735, 0.82), L.DARKGLASS)
box("deckroof", (5.3, 1.8, 0.08), (SX1 + 0.3, SY1, 1.17), WHITEP)
box("deckroofsnow", (5.3, 1.8, 0.14), (SX1 + 0.3, SY1, 1.26), L.SNOW, bevel=0.05, segs=3)
box("texas", (2.7, 1.05, 0.5), (SX1 - 0.3, SY1, 1.58), WHITEP)
box("texassnow", (2.95, 1.25, 0.12), (SX1 - 0.3, SY1, 1.9), L.SNOW, bevel=0.05, segs=3)
box("pilothouse", (0.75, 0.75, 0.5), (SX1 - 1.2, SY1, 2.2), WHITEP)
box("pilotsnow", (0.9, 0.9, 0.12), (SX1 - 1.2, SY1, 2.52), L.SNOW, bevel=0.05, segs=3)
for dz in (0.3, -0.3):
    cyl("stack", 0.09, 2.2, (SX1 - 2.0, SY1 + dz, 2.3), (0, 0, 0), L.METAL, verts=10)
WHEEL = plain("wheel", "#6a2a1e", 0.9)
for i in range(10):
    box("paddle", (0.07, 1.4, 1.2), (SX1 + 3.45, SY1, 0.45), WHEEL, rot=(0, i * math.pi / 10, 0))

# street lanterns along the boardwalk's edge
for x in (-12.0, -8.6, -3.3, 3.9, 7.0, 12.0):
    cyl("lpost", 0.05, 1.6, (x, FRONT + 0.85, 0.8), (0, 0, 0), L.PLANK_Z, verts=8)
    box("lglass", (0.22, 0.22, 0.28), (x, FRONT + 0.85, 1.72), L.GLASS)
    cyl("lcap", 0.2, 0.14, (x, FRONT + 0.85, 1.93), (0, 0, math.pi / 4), L.METAL, verts=4, r2=0.02)
    point("streetlight", (x, FRONT + 0.85, 1.6), 40, radius=0.12)


# ---------------------------------------------------------------- props: what makes a miniature feel lived in (refs 9, 11, 14, 20, 45)
BARREL = plain("barrel", "#4a3322", 0.85)
ROCK = plain("rock", "#6d7178", 0.95)


def barrel(x, y, z=0.0):
    cyl("barrel", 0.2, 0.55, (x, y, z + 0.28), (0, 0, 0), BARREL, verts=14)
    for hz in (0.1, 0.46):
        cyl("hoop", 0.205, 0.04, (x, y, z + hz), (0, 0, 0), L.METAL, verts=14)
    sphere("barrelsnow", (x, y, z + 0.56), (0.19, 0.19, 0.05), L.SNOW)


def crate(x, y, sz=0.5, z=0.0, rot=0.0):
    box("crate", (sz, sz, sz), (x, y, z + sz / 2), L.PLANK_Z, rot=(0, 0, rot), bevel=0.01)
    box("cratesnow", (sz + 0.02, sz + 0.02, 0.06), (x, y, z + sz + 0.03), L.SNOW, rot=(0, 0, rot), bevel=0.025, segs=3)


def rock(x, y, r):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=r, location=(x, y, r * 0.25))
    o = bpy.context.active_object
    o.scale = (random.uniform(0.9, 1.3), random.uniform(0.8, 1.2), random.uniform(0.5, 0.8))
    o.rotation_euler = (random.uniform(0, 0.4), random.uniform(0, 0.4), random.uniform(0, 6))
    finish(o, "rock", ROCK)
    sphere("rocksnow", (x, y, r * 0.25 + r * 0.55), (r * 0.8, r * 0.7, r * 0.22), L.SNOW)


def rail_fence(x0, x1, y, z=0.0):
    x = x0
    while x <= x1 + 0.01:
        cyl("fencepost", 0.05, 0.8, (x, y, z + 0.4), (0, 0, 0), L.LOGS[1], verts=6)
        x += 1.4
    for hz in (0.35, 0.65):
        cyl("rail", 0.035, x1 - x0, ((x0 + x1) / 2, y, z + hz), (0, math.pi / 2, 0), L.LOGS[0], verts=6)


def stump(x, y, z=0.0):
    cyl("stump", 0.16, 0.3, (x, y, z + 0.15), (0, 0, 0), L.LOGS[2], verts=10)
    sphere("stumpsnow", (x, y, z + 0.31), (0.15, 0.15, 0.04), L.SNOW)


# the Kovács forge's yard: anvil on its stump, the quench barrel, the coal heap, the fire showing in the door
cyl("anvilstump", 0.2, 0.42, (4.3, FRONT - 0.6, 0.21), (0, 0, 0), L.LOGS[2], verts=12)
box("anvilbody", (0.15, 0.34, 0.14), (4.3, FRONT - 0.6, 0.49), IRON)
box("anvilface", (0.18, 0.46, 0.07), (4.3, FRONT - 0.6, 0.59), IRON, bevel=0.01)
cyl("anvilhorn", 0.06, 0.2, (4.3, FRONT - 0.28, 0.59), (-math.pi / 2, 0, 0), IRON, verts=8, r2=0.0)
barrel(4.3, FRONT - 1.3)
cyl("quench", 0.17, 0.01, (4.3, FRONT - 1.3, 0.555), (0, 0, 0), plain("quenchwater", "#1d2a38", 0.2), verts=14)
bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.36, depth=0.28, location=(4.3, FRONT - 2.05, 0.14))
finish(bpy.context.active_object, "coal", plain("coal", "#121214", 0.9))
# the fire's light: out of the open door onto the boardwalk, and round the east jamb over the yard
point("forgeglow", (2.8, FRONT + 0.3, 0.8), 60, color="#ff7a2a", radius=0.3)
point("forgeglow_yard", (3.95, FRONT + 0.3, 0.75), 110, color="#ff8a3a", radius=0.35)
for (x, y, ang) in [(4.2, FRONT - 0.15, 0.3), (4.42, FRONT - 0.13, -0.2)]:
    box("tongs", (0.03, 0.03, 0.5), (x, y, 0.3), IRON, rot=(0.25, ang, 0))

# the landing: freight waiting for the boats, and a sled
for (x, y, sz, r) in [(-0.9, 1.95, 0.5, 0.2), (-1.4, 1.85, 0.45, -0.1), (-1.15, 1.9, 0.4, 0.5)]:
    crate(x, y, sz, 0.45 if (x, y) == (-1.15, 1.9) else 0.0, r)
for (x, y) in [(2.75, 1.95), (3.05, 2.05), (2.6, 1.15)]:
    barrel(x, y)
for sx in (-0.2, 0.2):
    cyl("runner", 0.025, 1.2, (-2.4 + sx, 1.45, 0.06), (math.pi / 2, 0, 0), L.METAL, verts=8)
for i in range(5):
    box("slat", (0.5, 0.1, 0.03), (-2.4, 0.97 + i * 0.22, 0.25), L.PLANK_X if hasattr(L, "PLANK_X") else L.PLANK_Y)
crate(-2.4, 1.3, 0.35, 0.27, 0.0)
# Maggie's porch and the boardwalk
barrel(RX - 2.15, FRONT + 0.35, 0.15)
barrel(RX + 2.2, FRONT + 0.3, 0.15)
crate(RX + 2.6, FRONT + 0.2, 0.4, 0.15, 0.3)
barrel(5.9 + 1.3, FRONT + 0.35, 0.15)
# your cabin's chopping block and axe
cyl("block", 0.22, 0.4, (-12.0, FRONT - 0.3, 0.2), (0, 0, 0), L.LOGS[1], verts=10)
box("axehandle", (0.04, 0.04, 0.55), (-11.96, FRONT - 0.3, 0.6), L.PLANK_Z, rot=(0.3, 0.2, 0))
box("axehead", (0.16, 0.03, 0.08), (-11.9, FRONT - 0.36, 0.84), L.METAL, rot=(0.3, 0.2, 0))
# rocks along both banks
for (x, y, r) in [(-12.85, 2.75, 0.2), (-13.65, 3.6, 0.22), (-15.4, 4.1, 0.2), (-11.2, 2.25, 0.25), (-10.6, 2.35, 0.18), (-8.6, 2.3, 0.22), (5.8, 2.3, 0.24), (7.2, 2.25, 0.2), (9.4, 2.35, 0.27), (12.8, 2.3, 0.2),
                  (14.6, 2.35, 0.24), (-9.0, 6.65, 0.24), (-6.6, 6.6, 0.2), (0.6, 6.7, 0.26), (3.4, 6.65, 0.2), (7.8, 6.6, 0.25), (11.6, 6.7, 0.22), (15.2, 6.6, 0.2)]:
    rock(x, y, r)
# split-rail fences along the back lane
rail_fence(-14.6, -8.2, -5.0)
rail_fence(4.2, 7.0, -5.0)
rail_fence(13.0, 16.4, -5.0)
# stumps where the bench was cut for firewood
for (x, y) in [(-12.4, -5.6), (-9.0, -5.9), (-5.2, -5.5), (-1.0, -5.8), (2.6, -5.6), (8.4, -5.9), (11.0, -5.5)]:
    stump(x, y, bench_z(y))

# Věra's claim up the creek: the windlass over the shaft, the gravel dump, the sluice on trestles, the path from her door
CL = (-7.2, 10.6)
GRAVEL = plain("gravel", "#8a8076", 1.0)
for (dx, dy, sx, sy, sz) in [(1.4, 0.3, 1.0, 0.8, 0.5), (0.8, 0.0, 0.6, 0.55, 0.35), (2.0, 0.6, 0.7, 0.6, 0.38), (1.7, -0.2, 0.6, 0.5, 0.3), (1.0, 0.7, 0.55, 0.45, 0.3)]:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=(CL[0] + dx, CL[1] + dy, 0.0))
    o = bpy.context.active_object
    o.scale = (sx, sy, sz)
    for v in o.data.vertices:
        v.co *= random.uniform(0.9, 1.08)
    finish(o, "dump", GRAVEL)
for _ in range(14):
    rock(CL[0] + random.uniform(0.2, 2.6), CL[1] + random.uniform(-0.7, 1.1), random.uniform(0.06, 0.12))
for (dx, dy, r, z) in [(0.7, -0.1, 0.32, 0.3), (1.9, 0.6, 0.28, 0.32), (1.5, 0.9, 0.22, 0.42), (2.2, 0.1, 0.25, 0.22), (1.1, 0.5, 0.2, 0.5)]:
    sphere("dumpsnow", (CL[0] + dx, CL[1] + dy, z), (r, r * 0.8, 0.09), L.SNOW)
box("shaftcollar", (0.9, 0.9, 0.14), (CL[0], CL[1], 0.07), L.PLANK_Y)
box("shafthole", (0.6, 0.6, 0.02), (CL[0], CL[1], 0.15), plain("shaft", "#141110", 1.0))
for sx in (-0.5, 0.5):
    box("windlasspost", (0.1, 0.1, 1.1), (CL[0] + sx, CL[1], 0.55), L.LOGS[0])
cyl("windlassdrum", 0.1, 1.0, (CL[0], CL[1], 0.95), (0, math.pi / 2, 0), L.LOGS[1], verts=10)
box("crank", (0.05, 0.05, 0.35), (CL[0] + 0.58, CL[1], 0.82), L.METAL)
cyl("rope", 0.012, 0.75, (CL[0] + 0.1, CL[1], 0.55), (0, 0, 0), plain("rope", "#8a7a5c", 0.9), verts=5)
cyl("bucket", 0.12, 0.18, (CL[0] + 0.1, CL[1], 0.2), (0, 0, 0), L.METAL, verts=10)
for i in range(3):  # the sluice box down toward the creek
    x0 = CL[0] + 2.6 + i * 0.9
    for sx in (-0.15, 0.15):
        box("trestle", (0.06, 0.06, 0.55 - i * 0.1), (x0, CL[1] - 0.6 - i * 0.25 + sx, 0.27 - i * 0.05), L.LOGS[2])
box("sluice", (2.8, 0.36, 0.18), (CL[0] + 3.5, CL[1] - 0.85, 0.5), L.PLANK_Y, rot=(0, 0.12, -0.25))
box("sluicesnow", (2.8, 0.38, 0.05), (CL[0] + 3.5, CL[1] - 0.85, 0.61), L.SNOW, rot=(0, 0.12, -0.25))
strip("claimpath", [(VX + 0.6, N_BANK + 0.4), (VX + 0.2, 8.4), (CL[0] + 1.6, 9.6), (CL[0] + 0.4, CL[1] - 0.6)], 0.5, TRODDEN, 0.04)
strip("icepath", [(VX + 0.6, N_BANK + 0.5), (-3.0, N_BANK + 0.15), (-2.6, N_BANK - 0.1)], 0.5, TRODDEN, 0.045)
for (x, y) in [(CL[0] - 1.2, CL[1] + 1.4), (CL[0] + 2.8, CL[1] + 1.2), (-9.6, 9.0), (6.0, 9.6), (2.4, 11.0)]:
    stump(x, y)
for (x, y, r) in [(-1.0, 9.8, 0.3), (3.6, 8.6, 0.26), (8.8, 11.2, 0.3), (-11.8, 11.6, 0.28)]:
    rock(x, y, r)

# ---------------------------------------------------------------- black spruce: shared meshes; on the bench, the far bank, the point
def spruce_mesh(k):
    objs = []
    tiers = 7
    for t in range(tiers):
        r = 0.95 * (1 - t / (tiers + 0.5)) + 0.1
        z = 0.5 + t * 0.48
        objs.append(cyl("t", r, 0.85, (0, 0, z), (0, 0, random.uniform(0, 6)), L.SPRUCE, verts=8, r2=0.0, smooth=False))
        objs.append(cyl("t", r * 0.78, 0.36, (0, 0, z + 0.22), (0, 0, random.uniform(0, 6)), L.SNOW, verts=8, r2=0.0, smooth=False))
    objs.append(cyl("t", 0.09, 0.6, (0, 0, 0.3), (0, 0, 0), L.LOGS[0], verts=6))
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = "spruce_proto%d" % k
    ob.location = (0, 0, -50)
    return ob.data


protos = [spruce_mesh(k) for k in range(3)]
TAKEN = [(-13.4, -0.9), (-13.4, 0.3), (-8, 0.4), (-2, 0.4), (0.7, 0.6), (1.0, 1.8), (1.0, 3.4), (0.2, 4.4), (-1.0, 5.4), (-2.0, 6.3), (-2.8, 6.8), (-3.5, 6.85)]
BACKWAY = [(-13.4, -0.9), (-13.6, 0.3), (-15.4, 0.4), (-16.2, 1.6), (-16.3, 3.5), (-16.2, 5.6), (-15.6, 7.3), (-12, 7.7), (-8, 7.5), (-5.6, 7.1), (-4.7, 6.95)]


def plant(x, y, s):
    o = bpy.data.objects.new("spruce", random.choice(protos))
    o.location, o.scale, o.rotation_euler = (x, y, bench_z(y)), (s, s, s * random.uniform(0.9, 1.15)), (0, 0, random.uniform(0, 6.28))
    S.collection.objects.link(o)


count = 0
for i in range(700):
    x, y = (random.random() - 0.5) * (PW - 1.4), (random.random() - 0.5) * (PD - 1.4)
    bench = y < -5.2
    far = y > N_BANK + 0.6
    if not (bench or far):
        continue
    if far and (math.hypot(x - VX, y - (VY)) < 2.6 or math.hypot(x - CL[0] - 1.5, y - CL[1]) < 3.4 or near(x, y, CREEK, 1.0) or near(x, y, BACKWAY, 0.8)):
        continue
    if far and (-10 < x < 9 or y < 9.2 or random.random() < 0.5):
        continue  # keep the near bank low and open: the ice and the town must read from the river
    if bench and random.random() < 0.35:
        continue
    plant(x, y, random.uniform(0.6, 1.25) if bench else random.uniform(0.5, 0.8))
    count += 1
for (x, y, s) in [(-14.3, 3.3, 0.8), (-15.3, 3.4, 0.72), (-16.2, 3.0, 0.78), (-13.6, 2.7, 0.62), (-15.0, 2.7, 0.85)]:
    o = bpy.data.objects.new("spruce", random.choice(protos))
    o.location, o.scale, o.rotation_euler = (x, y, 0.16), (s, s, s * 1.05), (0, 0, random.uniform(0, 6.28))
    S.collection.objects.link(o)
    count += 1

# ---------------------------------------------------------------- shading: light bands, cold shadows, warm lamplight
SMOKE_POS = list(L.CHIMNEYS)
BANDS = [(0.0, "#2c3658"), (0.05, "#55638a"), (0.22, "#a9a9b8"), (0.6, "#f2e2c8"), (1.6, "#fff4e0")]
BAND_SCALE = float(os.environ.get("BAND_SCALE", "0.45"))


def toonify(m):
    nt = m.node_tree
    b, out = nt.nodes.get("Principled BSDF"), nt.nodes.get("Material Output")
    if not b or not out:
        return
    bc = b.inputs["Base Color"]
    if bc.is_linked:
        src = bc.links[0].from_socket
    else:
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = bc.default_value
        src = rgb.outputs[0]
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    sc = nt.nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    sc.inputs[1].default_value = 1.0 / (BANDS[-1][0] * BAND_SCALE)
    nt.links.new(s2r.outputs["Color"], sc.inputs[0])
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.interpolation = "CONSTANT"
    els, top = r.color_ramp.elements, BANDS[-1][0]
    els[0].position, els[0].color = 0.0, (*lin(BANDS[0][1]), 1)
    els[1].position, els[1].color = 1.0, (*lin(BANDS[-1][1]), 1)
    for pos, cc in BANDS[1:]:
        e = els.new(min(pos / top, 0.999))
        e.color = (*lin(cc), 1)
    nt.links.new(sc.outputs[0], r.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(src, mix.inputs[6])
    nt.links.new(r.outputs["Color"], mix.inputs[7])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])


for m in [] if EXPORT else list(bpy.data.materials):  # Godot shades the exported town itself
    if m.name.startswith("glass"):
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
    elif m.name.startswith("fire_"):
        pass  # the forge fire: flat emissive colour, no bands
    else:
        toonify(m)


def unlit(name, hexc, alpha=1.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(nd)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(hexc), 1)
    if alpha < 1:
        tr, mx = nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeMixShader")
        mx.inputs["Fac"].default_value = alpha
        nt.links.new(tr.outputs[0], mx.inputs[1])
        nt.links.new(em.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], nt.nodes.get("Material Output").inputs["Surface"])
    else:
        nt.links.new(em.outputs[0], nt.nodes.get("Material Output").inputs["Surface"])
    L.MATSPEC[m.name] = {"kind": "unlit", "color": hexc, "alpha": alpha}
    return m


# chimney smoke (unlit, drawn after shading so it stays soft and pale)
SPR = bpy.data.collections.new("sprites")
S.collection.children.link(SPR)
SMOKE = unlit("smoke", "#c3cad4")
for (x, y, z) in SMOKE_POS:
    for i in range(7):
        u = i / 7
        r = 0.09 + u * 0.2
        o = sphere("smoke", (x - u * 0.9 + random.uniform(-0.04, 0.04), y + u * 0.2, z + 0.08 + u * 1.15), (r, r, r * 0.8), SMOKE)
        try:
            o.visible_shadow = False
        except Exception:
            pass
        for c in o.users_collection:
            c.objects.unlink(o)
        SPR.objects.link(o)

# the forge's firelight: the cel bands keep only brightness, so the fire's colour is laid down as warm pools,
# the way pixel scenes draw lamplight; an inner and an outer ring on the boardwalk and over the yard
GLOWS = []
for (x, y, z, rx, ry, col) in [(2.8, FRONT + 0.4, 0.15, 0.62, 0.34, "#7a4022"), (2.75, FRONT + 0.3, 0.152, 0.36, 0.2, "#a8582a"),
                               (4.25, FRONT - 0.5, 0.09, 0.42, 0.85, "#e7a978"), (4.2, FRONT - 0.25, 0.092, 0.3, 0.5, "#f6c590")]:
    GLOWS.append({"pos": [x, y, z], "radii": [rx, ry], "color": col})
    o = cyl("fireglow", 1.0, 0.004, (x, y, z), (0, 0, 0.2), unlit("fireglow_" + col[1:], col), verts=10)
    o.scale = (rx, ry, 1)
    for c in o.users_collection:
        c.objects.unlink(o)
    SPR.objects.link(o)

# ---------------------------------------------------------------- camera: from the river, the north-east, looking south over the ice
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
cam.ortho_scale = float(os.environ.get("ORTHO", "46"))
co = bpy.data.objects.new("cam", cam)
S.collection.objects.link(co)
co.location = Vector((float(os.environ.get("CAMX", "12")), 50, 38))
target = Vector((0.5, 0.2, -1.0))
co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
S.camera = co
FWD = (target - co.location).normalized()

# ---------------------------------------------------------------- the townsfolk
HEAD = {}
PEOPLE = {}
PERSON_H = 2.6


def sprite(name, x, y, z=0.03, k=1.0):
    PEOPLE[name] = {"pos": [x, y, z], "height": PERSON_H * k}
    img = bpy.data.images.load(os.path.join(SPRITES, name + ".png"))
    m = bpy.data.materials.new("sprite_" + name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for nd in list(nt.nodes):
        if nd.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(nd)
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image, t.interpolation = img, "Closest"
    em, tr, mx = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(t.outputs["Color"], em.inputs["Color"])
    nt.links.new(t.outputs["Alpha"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], nt.nodes.get("Material Output").inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z))
    o = bpy.context.active_object
    for v in o.data.vertices:
        v.co.y += 0.5
    h = PERSON_H * k
    o.scale = (h * 32 / 48, h, 1)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = (-FWD).to_track_quat("Z", "Y")
    o.data.materials.append(m)
    o.name = "sprite_" + name
    try:
        o.visible_shadow = False
    except Exception:
        pass
    for c in o.users_collection:
        c.objects.unlink(o)
    SPR.objects.link(o)
    up = o.rotation_quaternion @ Vector((0, 1, 0))
    HEAD[name] = Vector((x, y, z)) + up * h * 0.92
    bpy.ops.mesh.primitive_circle_add(vertices=20, radius=0.42, fill_type="NGON", location=(x, y, z + 0.03))
    s = bpy.context.active_object
    s.scale = (1.2, 0.85, 1)
    s.data.materials.append(unlit("shadow_" + name, "#1a2238", 0.45))
    for c in s.users_collection:
        c.objects.unlink(s)
    SPR.objects.link(s)


ANTON = (-0.6, 5.0) if WALK else (-2.9, 0.35)
sprite("anton", *ANTON, z=0.06 if WALK else 0.03)
sprite("maggie", RX + 0.5, FRONT + 1.25)  # out in the street: by the wall, the eaves hide her from the camera
sprite("sandor", -4.6, 0.3)
sprite("gilchrist", PX, FRONT + 0.55)
sprite("billy", 0.0, 1.8, k=0.8)
sprite("ashby", 5.5, 3.9, z=0.06)
sprite("vera", VX + 1.55, N_BANK + 0.55)
sprite("tamas", IX - 0.3, FRONT + 1.3)  # outside the infirmary, in his blanket
sprite("otto", SX0 + 1.1, FRONT + 0.6)  # by the ruin of his store
sprite("martha", RX - 1.3, FRONT + 1.3)  # at the roadhouse, along from Maggie
point("antonlantern", (ANTON[0] + 0.5, ANTON[1] + 0.3, 0.9), 60 if WALK else 35, radius=0.1)

# ---------------------------------------------------------------- red: the thread in town, the route on the walk
RED = unlit("red", "#c0262b")
if not WALK:
    a, b = HEAD["maggie"], HEAD["sandor"]
    tube("thread", qbez(a, (a + b) / 2 + Vector((0, 0, 1.6)), b), 0.085, RED)


def ground_z(x, y):
    if abs(x - DX0) < 0.65 and S_BANK - 0.8 < y < S_BANK + 1.8:
        return 0.2
    if FRONT + 0.05 < y < FRONT + 0.75 and -15.1 < x < 16.7:
        return 0.16
    if S_BANK < y < N_BANK:
        return 0.08
    return 0.07


def catmull(pts, n=600):
    P_ = [pts[0]] + list(pts) + [pts[-1]]
    dense = []
    for i in range(1, len(P_) - 2):
        p0, p1, p2, p3 = (Vector(P_[j]) for j in (i - 1, i, i + 1, i + 2))
        for s in range(20):
            t = s / 20
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(Vector(pts[-1]))
    cum = [0.0]
    for p, q in zip(dense, dense[1:]):
        cum.append(cum[-1] + (q - p).length)
    total, out, j = cum[-1], [], 0
    for i in range(n + 1):
        d = total * i / n
        while j < len(cum) - 2 and cum[j + 1] < d:
            j += 1
        f = (d - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append(dense[j].lerp(dense[j + 1], f))
    return out, total


def ribbon(name, pts, width, mat, dash=None, ta0=0.0, ta1=1.0):
    sp, total = catmull(pts)
    N = len(sp) - 1
    vs, fs = [], []
    for i in range(N):
        ta, tb = i / N, (i + 1) / N
        if tb < ta0 or ta > ta1:
            continue
        if dash and int(ta * total / dash) % 2 == 1:
            continue
        p, q = sp[i], sp[i + 1]
        dv = q - p
        if dv.length < 1e-9:
            continue
        nx, ny = -dv.y / dv.length * width / 2, dv.x / dv.length * width / 2
        k = len(vs)
        for (x, y) in [(p.x - nx, p.y - ny), (p.x + nx, p.y + ny), (q.x + nx, q.y + ny), (q.x - nx, q.y - ny)]:
            vs.append((x, y, ground_z(x, y)))
        fs.append((k, k + 1, k + 2, k + 3))
    m = bpy.data.meshes.new(name)
    m.from_pydata(vs, [], fs)
    m.update()
    ob = bpy.data.objects.new(name, m)
    S.collection.objects.link(ob)
    ob.data.materials.append(mat)
    return ob


if WALK:
    sp, total = catmull(TAKEN)
    tA = min(range(len(sp)), key=lambda i: (sp[i] - Vector(ANTON)).length) / (len(sp) - 1)
    ribbon("route_done", TAKEN, 0.2, RED, None, 0, tA)
    ribbon("route_ahead", TAKEN, 0.18, RED, 0.32, tA + 0.012, 1)
    ribbon("route_back", BACKWAY, 0.15, unlit("redfaint", "#9a4a46"), 0.26)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.5, minor_radius=0.07, location=(VX + 0.6, N_BANK + 0.25, 0.08))
    finish(bpy.context.active_object, "destination", RED)

# ---------------------------------------------------------------- light: the desk lamp from the north-west, the cold from the south
W = bpy.data.worlds.new("World")
S.world = W
try:
    W.use_nodes = True
except Exception:
    pass
bg = W.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (*lin("#13203a"), 1)
bg.inputs["Strength"].default_value = 0.9
lamp = bpy.data.lights.new("desklamp", "SPOT")
lamp.energy = float(os.environ.get("LAMP", "52000"))
lamp.color = lin("#ffd8ad")
lamp.spot_size = math.radians(62)
lamp.spot_blend = 0.6
lamp.shadow_soft_size = 0.6
lo = bpy.data.objects.new("desklamp", lamp)
lo.location = (-24, 18, 34)
S.collection.objects.link(lo)
lo.rotation_euler = (Vector((0, 0, -1)) - lo.location).to_track_quat("-Z", "Y").to_euler()
moon = bpy.data.lights.new("moon", "SUN")
moon.energy, moon.color, moon.angle = 1.6, lin("#8aa6cf"), math.radians(3)
mo = bpy.data.objects.new("moon", moon)
mo.rotation_euler = (math.radians(55), 0, math.radians(-30))
S.collection.objects.link(mo)

# ---------------------------------------------------------------- render: EEVEE at pixel resolution, ink outlines
S.render.engine = "BLENDER_EEVEE"
S.eevee.taa_render_samples = 16
S.view_settings.view_transform = "Standard"
S.view_settings.look = "None"
RES = int(os.environ.get("RES", "960"))
S.render.resolution_x, S.render.resolution_y = RES, RES * 9 // 16
S.render.resolution_percentage = 100
S.render.filter_size = 0.0
S.render.use_freestyle = True
S.render.line_thickness_mode = "ABSOLUTE"
S.render.line_thickness = 1.0
vl = S.view_layers[0]
vl.use_freestyle = True
fs = vl.freestyle_settings
fs.crease_angle = math.radians(140)
ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("outline")
ls.select_by_visibility = ls.select_silhouette = ls.select_border = ls.select_crease = True
ls.select_by_collection = True
ls.collection = SPR
ls.collection_negation = "EXCLUSIVE"
if ls.linestyle is None:
    ls.linestyle = bpy.data.linestyles.new("ink")
ls.linestyle.color = lin("#1a120c")
ls.linestyle.thickness = 1.0
S.render.filepath = OUT

from bpy_extras.object_utils import world_to_camera_view  # noqa: E402

bpy.context.view_layer.update()


def scr(v):
    cc = world_to_camera_view(S, co, Vector(v))
    return [round(cc.x * 1280), round((1 - cc.y) * 720)]


PLACES = {
    "maggies": (RX, FRONT, FH + 0.3), "store": (SX0, SY0, 1.3), "landing": (DX0, S_BANK + 0.6, 0.3), "ice": tuple(TT),
    "vera": (VX, VY, 2.9), "police": (PX, FRONT - 0.2, 1.2), "infirmary": (IX, IY, 2.7), "church": (CHX, FRONT - 0.3, 4.6),
    "your_cabin": (-13.4, FRONT - 1.3, 2.8), "dest": (VX + 0.6, N_BANK + 0.25, 0.08),
}
A = {k_: scr(v) for k_, v in PLACES.items()}
for k_, v in HEAD.items():
    A["head_" + k_] = scr(v)
json.dump(A, open(ANCH, "w"), indent=0)

# ---------------------------------------------------------------- export: the town as glTF plus what Godot needs to stage it


def godot_xyz(v):
    """Blender is Z-up with Y north; Godot is Y-up with -Z north (what the glTF exporter does to the meshes)."""
    return [round(v[0], 4), round(v[2], 4), round(-v[1], 4)]


def hexs(c):
    return "#%02x%02x%02x" % tuple(round(max(0.0, min(1.0, x)) ** (1 / 2.2) * 255) for x in c[:3])


if EXPORT:
    os.makedirs(EXPORT, exist_ok=True)
    skip = {"thread"}
    keep = []
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(S.objects):
        if o.type in ("CURVE", "FONT") and o.name not in skip and SPR not in o.users_collection:
            bpy.context.view_layer.objects.active = o
            o.select_set(True)
            bpy.ops.object.convert(target="MESH")
            o.select_set(False)
    for o in S.objects:
        if SPR in o.users_collection or o.name.split(".")[0] in skip or o.name.startswith("spruce_proto"):
            continue
        if o.type in ("MESH", "EMPTY"):
            o.select_set(True)
            keep.append(o)
    bpy.ops.export_scene.gltf(filepath=os.path.join(EXPORT, "town.glb"), export_format="GLB", use_selection=True,
                              export_apply=True, export_lights=False, export_cameras=False, export_yup=True)
    used = {s.material.name for o in keep if o.type == "MESH" for s in o.material_slots if s.material}
    lights = [{"pos": godot_xyz(o.location), "color": hexs(o.data.color), "watts": o.data.energy,
               "radius": o.data.shadow_soft_size}
              for o in S.objects if o.type == "LIGHT" and o.data.type == "POINT"]
    data = {
        "camera": {"pos": godot_xyz(co.location), "target": godot_xyz(target), "ortho": cam.ortho_scale,
                   "size": [RES, RES * 9 // 16]},
        "lamp": {"pos": godot_xyz(lo.location), "target": [0, -1, 0], "color": hexs(lamp.color), "energy": lamp.energy},
        "moon": {"color": hexs(moon.color), "energy": moon.energy, "rotation": list(mo.rotation_euler)},
        "world": "#13203a",
        "bands": BANDS, "band_scale": BAND_SCALE,
        "materials": {k_: v for k_, v in L.MATSPEC.items() if k_ in used},
        "lights": lights,
        "chimneys": [godot_xyz(c) for c in SMOKE_POS],
        "glows": [{"pos": godot_xyz(g["pos"]), "radii": g["radii"], "color": g["color"]} for g in GLOWS],
        "people": {k_: {"pos": godot_xyz(v["pos"]), "height": v["height"]} for k_, v in PEOPLE.items()},
        "places": {k_: godot_xyz(v) for k_, v in PLACES.items()},
        "heads": {k_: godot_xyz(v) for k_, v in HEAD.items()},
        "routes": {"taken": [godot_xyz((x, y, ground_z(x, y))) for x, y in TAKEN],
                   "backway": [godot_xyz((x, y, ground_z(x, y))) for x, y in BACKWAY]},
        "screen": A,
    }
    json.dump(data, open(os.path.join(EXPORT, "town.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("exported", len(keep), "objects,", len(used), "materials")
    sys.exit(0)

# ---------------------------------------------------------------- kit mode: every piece rendered on its own, close up
KIT = [
    ("your_cabin", "Your cabin", (-13.4, -2.3, 1.1), 6.0), ("roadhouse", "Maggie's roadhouse", (-6.6, -2.4, 1.6), 7.5),
    ("store", "Brand's store, burned, and the cordwood", (0.0, -2.6, 0.7), 6.5), ("forge", "The Kovács forge", (2.8, -2.2, 1.2), 5.0),
    ("post", "The Mounted Police post", (9.6, -2.7, 1.2), 8.0), ("mission", "The mission: church and infirmary", (14.2, -2.1, 1.6), 8.0),
    ("landing", "The landing: dock, freight, clock post, Ashby's tent", (1.2, 1.6, 0.6), 8.0), ("steamer", "The steamer, laid up", (-3.9, 3.05, 1.1), 8.0),
    ("tripod", "The tripod on the ice", (4.6, 4.4, 1.0), 4.5), ("point", "The spruce point and the crack", (-14.6, 3.6, 0.7), 6.5),
    ("vera", "Věra's cabin and claim", (-5.6, 8.8, 0.8), 9.0), ("bench", "Spruce on the bench", (-2.0, -8.0, 2.0), 9.0),
    ("street", "Boardwalk, lanterns, street", (-3.4, -0.4, 0.9), 4.5), ("people", "Maggie and Sándor on the street", (-5.4, -0.2, 1.3), 5.0),
]
if os.environ.get("KIT"):
    kitdir = os.environ["KIT"]
    os.makedirs(kitdir, exist_ok=True)
    crops = {}
    for key, label, c, sc in KIT:
        cc = Vector(c)
        right = co.matrix_world.to_quaternion() @ Vector((1, 0, 0))
        up = co.matrix_world.to_quaternion() @ Vector((0, 1, 0))
        a0, a1 = scr(cc - right * sc / 2 + up * sc * 0.375), scr(cc + right * sc / 2 - up * sc * 0.375)
        crops[key] = {"label": label, "box": [a0[0], a0[1], a1[0], a1[1]]}
    json.dump(crops, open(os.path.join(kitdir, "crops.json"), "w"), indent=1)
    S.render.resolution_x, S.render.resolution_y = 640, 480
    for key, label, c, sc in KIT:
        if os.environ.get("KITONLY") and key not in os.environ["KITONLY"].split(","):
            continue
        cam.ortho_scale = sc
        co.location = Vector(c) - FWD * 60
        bpy.context.view_layer.update()
        S.render.filepath = os.path.join(kitdir, key + ".png")
        bpy.ops.render.render(write_still=True)
        print("kit", key)
    sys.exit(0)
print("built in %.1fs, %d objects, %d trees" % (time.time() - t0, len(S.objects), count))
if BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
bpy.ops.render.render(write_still=True)
print("rendered in %.1fs" % (time.time() - t0))
