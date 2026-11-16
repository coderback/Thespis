# Coldwater Landing, the whole town in Blender, rendered pixel style.
# Run: MODE=town|walk SPRITES=<dir> blender -b --factory-startup --python build_town.py -- <out.png> <anchors.json> [blend]
# Layout follows the three.js town: three (x, z) -> Blender (x, -z), fronts face -Y.
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
WALK = MODE == "walk"

random.seed(1898)
bpy.ops.wm.read_factory_settings(use_empty=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coldwater_lib as L  # noqa: E402
from coldwater_lib import box, cabin, cyl, finish, lin, plain, point, sphere  # noqa: E402

S = bpy.context.scene
def P(x, z):
    return (x, -z)  # three.js ground coordinates to Blender

PW, PD, PH = 34.0, 27.0, 4.6

# ---------------------------------------------------------------- plinth, desk, ground, river
box("plinth", (PW, PD, PH), (0, 0, -PH / 2), L.STRATA)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=300, y_subdivisions=240, size=1, location=(0, 0, 0.02))
g = bpy.context.active_object
g.scale = (PW, PD, 1)
bpy.ops.object.transform_apply(scale=True)
for p in g.data.polygons:
    p.use_smooth = True
tex = bpy.data.textures.new("snowlumps", "CLOUDS")
tex.noise_scale = 1.4
md = g.modifiers.new("lumps", "DISPLACE")
md.texture = tex
md.strength = 0.05
finish(g, "ground", L.SNOW)
box("desk", (400, 400, 0.2), (0, 0, -PH - 0.1), L.DESK)
box("river", (PW, 5.8, 0.06), (0, 3.6, 0.035), L.ICE)
# the river in section on the east face: ice over black water
box("ice_section", (0.04, 5.8, 0.9), (PW / 2 + 0.02, 3.6, -0.45), plain("icecut", "#cfe0ee", 0.3))
box("water_section", (0.04, 5.8, 1.9), (PW / 2 + 0.02, 3.6, -1.7), plain("water", "#24405e", 0.3))
TRODDEN = plain("trodden", "#b9c4d3", 0.9)
box("street", (33.4, 2.2, 0.02), (0, -7.6, 0.035), TRODDEN, bevel=0.3, segs=3)
box("lane", (0.8, 4.4, 0.02), (0.15, -4.25, 0.035), TRODDEN, bevel=0.2, segs=3)

TAKEN = [(0.6, 7.2), (0.15, 6.2), (0.12, 4.6), (0.15, 2.6), (0.2, 1.0), (0.25, -0.9), (1.4, -2.0), (3.4, -3.0), (5.3, -4.9), (7.5, -6.6), (9.0, -7.7), (9.5, -8.0)]
BACKWAY = [(0.6, 7.2), (-1.2, 8.5), (-8, 8.7), (-14.4, 8.0), (-15.6, 5.0), (-15.6, 1.0), (-15.2, -3.6), (-14.4, -7.6), (-10.5, -9.0), (-4.5, -8.7), (1.5, -9.4), (6.5, -9.0), (8.6, -8.4), (9.5, -8.0)]


def near_route(x, z, pts, r):
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        dx, dz = bx - ax, bz - az
        t = max(0, min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz)))
        if math.hypot(x - ax - dx * t, z - az - dz * t) < r:
            return True
    return False


# snowbanks along both banks, and drifts on the ice
for i in range(48):
    x = -16.4 + i * 0.7
    if not (-0.8 < x < 1.2) and not (-16 < x < -14.6):
        sphere("bank", (x + random.uniform(0, 0.3), 0.75 + random.uniform(0, 0.15), 0.02), (random.uniform(0.6, 1.0), random.uniform(0.35, 0.5), random.uniform(0.18, 0.32)), L.SNOW)
    if not (6.6 < x < 8.6) and not (-16 < x < -13.6):
        o = sphere("bank", (x, 6.45 + random.uniform(0, 0.15), 0.02), (random.uniform(0.6, 1.0), random.uniform(0.35, 0.5), random.uniform(0.18, 0.32)), L.SNOW)
for i in range(26):
    x, z = random.uniform(-15, 15), -1.4 - random.random() * 4.4
    if math.hypot(x - 4.6, z + 3.8) > 1.6 and not near_route(x, z, TAKEN, 0.7) and not (-12.8 < x < -2.5 and z > -3.8):
        sphere("icedrift", (x, -z, 0.05), (random.uniform(0.5, 1.4), random.uniform(0.2, 0.5), random.uniform(0.04, 0.08)), L.SNOW)

# ---------------------------------------------------------------- buildings
def F(u0, u1, z0, z1, kind="window"):
    return ("front", u0, u1, z0, z1, kind)

def D(u0, u1):
    return ("front", u0, u1, 0.0, 1.6, "door")

# Maggie Doyle's roadhouse, with its false front and a shallow porch over the boardwalk
RX, RY = P(-6, 3.8)
RW, RD = 3.6, 2.6
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


def text(name, body, size, loc, mat, rot=(math.pi / 2, 0, 0)):
    c = bpy.data.curves.new(name, "FONT")
    c.body, c.size, c.extrude, c.align_x, c.align_y = body, size, 0.012, "CENTER", "CENTER"
    if font:
        c.font = font
    o = bpy.data.objects.new(name, c)
    o.location, o.rotation_euler = loc, rot
    o.data.materials.append(mat)
    S.collection.objects.link(o)
    return o


text("sign_text", "ROADHOUSE", 0.42, (RX, y0 - 0.085, FH - 0.55), L.CREAM)
for u in (-1.1, 1.1):
    wd, z0, z1 = 0.75, 0.95, 1.85
    for side in (u - wd / 2 - 0.05, u + wd / 2 + 0.05):
        box("fw_frame", (0.1, 0.08, z1 - z0 + 0.1), (RX + side, y0 - 0.05, (z0 + z1) / 2), L.TRIM)
    box("fw_head", (wd + 0.3, 0.12, 0.12), (RX + u, y0 - 0.06, z1 + 0.08), L.TRIM)
    box("fw_sillsnow", (wd + 0.26, 0.16, 0.07), (RX + u, y0 - 0.1, z0 + 0.0), L.SNOW, bevel=0.03, segs=3)
    box("fw_glass", (wd, 0.02, z1 - z0), (RX + u, y0 - 0.02, (z0 + z1) / 2), L.GLASS)
    box("fw_mull", (0.035, 0.05, z1 - z0), (RX + u, y0 - 0.04, (z0 + z1) / 2), L.TRIM)
    box("fw_mull", (wd, 0.05, 0.035), (RX + u, y0 - 0.04, (z0 + z1) / 2), L.TRIM)
    point("fw_spill", (RX + u, y0 - 0.7, 1.4), 22, radius=0.3)
for i in range(4):
    box("rd_door", (0.95 / 4 - 0.012, 0.05, 2.0), (RX - 0.475 + (i + 0.5) * 0.95 / 4, y0 - 0.05, 0.15 + 1.0), L.PLANK_Z)
box("rd_doorhead", (1.3, 0.12, 0.12), (RX, y0 - 0.07, 2.23), L.TRIM)
PDp = 1.2
for sx in (-1, 1):
    box("post", (0.13, 0.13, 2.3), (RX + sx * (FW / 2 - 0.05), y0 - PDp + 0.1, 0.13 + 1.15), L.PLANK_Z)
box("beam", (FW + 0.2, 0.14, 0.16), (RX, y0 - PDp + 0.1, 2.48), L.PLANK_Z)
a2 = math.atan2(0.28, PDp)
mid = Vector((RX, y0 - PDp / 2 - 0.05, 2.62))
nrm = Vector((0, -math.sin(a2), math.cos(a2)))
box("porchroof", (FW + 0.5, PDp + 0.35, 0.06), mid, L.PLANK_Y, rot=(a2, 0, 0))
box("porchsnow", (FW + 0.56, PDp + 0.4, 0.22), mid + nrm * 0.14, L.SNOW, rot=(a2, 0, 0), bevel=0.1, segs=4)
edge = mid + Vector((0, -(PDp + 0.35) / 2 * math.cos(a2), -(PDp + 0.35) / 2 * math.sin(a2)))
x = -FW / 2 - 0.2
while x < FW / 2 + 0.2:
    ln = random.uniform(0.1, 0.45)
    cyl("icicle", 0.035, ln, (RX + x, edge.y + 0.02, edge.z - 0.06 - ln / 2), (math.pi, 0, 0), L.ICICLE, verts=6, r2=0.0)
    x += random.uniform(0.1, 0.22)
box("lantern", (0.16, 0.16, 0.22), (RX + 0.75, y0 - 0.3, 2.0), L.GLASS)
point("lanternlight", (RX + 0.75, y0 - 0.5, 1.9), 30, radius=0.12)

cabin("cabin_w1", *P(-10, 3.6), 2.4, 2.2, 1.9, openings=[D(-0.85, -0.15), F(0.3, 0.9, 0.85, 1.45)])
cabin("cabin_w2", *P(-13.2, 4.2), 2.2, 2.0, 1.8, openings=[D(-0.8, -0.1), F(0.25, 0.8, 0.85, 1.4, "dark")], woodpile=True)
cabin("cabin_e1", *P(1.6, 3.9), 2.4, 2.2, 2.0, openings=[D(-0.85, -0.15), F(0.3, 0.9, 0.85, 1.45)])
cabin("cabin_e2", *P(4.6, 4.4), 2.2, 2.0, 1.9, openings=[D(-0.8, -0.1), F(0.25, 0.8, 0.85, 1.4, "dark")], pipe=False)
PX, PY = P(8.4, 3.9)
cabin("police", PX, PY, 3.4, 2.6, 2.3, openings=[F(-1.35, -0.75, 0.85, 1.5), D(-0.35, 0.35), F(0.75, 1.35, 0.85, 1.5)])
cyl("flagpole", 0.05, 5.0, (PX + 2.1, PY - 1.7, 2.5), (0, 0, 0), L.METAL, verts=8)
box("flag", (1.0, 0.03, 0.6), (PX + 2.62, PY - 1.7, 4.65), plain("flagred", "#b3262b", 0.9))
IX, IY = P(12.4, 8.6)
cabin("infirmary", IX, IY, 3.4, 2.2, 2.0, openings=[F(-1.3, -0.7, 0.8, 1.4), D(-0.3, 0.3), F(0.7, 1.3, 0.8, 1.4)], white=True)
box("cross_v", (0.09, 0.09, 0.75), (IX, IY, 2.0 + 2.2 * 0.3 + 0.6), L.METAL)
box("cross_h", (0.46, 0.09, 0.09), (IX, IY, 2.0 + 2.2 * 0.3 + 0.72), L.METAL)
VX, VY = P(10, -10.2)
cabin("vera", VX, VY, 2.2, 2.0, 1.8, openings=[D(-0.8, -0.1), F(0.25, 0.8, 0.85, 1.4)], woodpile=True)

# boardwalk along the town front
for i in range(128):
    x = -15.2 + i * 0.2
    if -15.2 <= x <= 10.4:
        box("bw", (0.185, 1.0, 0.07), (x, -5.95, 0.11 + random.uniform(-0.006, 0.006)), L.PLANK_Y)
box("bw_joist", (25.6, 0.12, 0.1), (-2.4, -5.5, 0.05), L.PLANK_Y)
box("bw_joist", (25.6, 0.12, 0.1), (-2.4, -6.4, 0.05), L.PLANK_Y)

# Brand's store: burned out, its false front fallen face-up
SX0, SY0 = P(-1.9, 3.9)
CHAR = plain("char", "#151312", 1.0)
cyl("soot", 2.4, 0.02, (SX0, SY0, 0.04), (0, 0, 0), plain("soot", "#2b2a2a", 1.0), verts=32).scale = (1.25, 0.95, 1)
for (x, hh, z, tilt) in [(-1.5, 1.1, 1.0, 0), (1.3, 1.1, 0.9, 0.25), (-1.5, 1.1, -1.1, -0.15), (1.3, 0.7, -1.1, 0.4), (-0.2, 0.4, 0.9, 0)]:
    box("charpost", (0.22, 0.22, hh * 2), (SX0 + x, SY0 - z, hh), CHAR, rot=(0, tilt, 0))
box("charbeam", (3.2, 0.22, 0.22), (SX0 - 0.2, SY0 - 0.1, 0.35), CHAR, rot=(0.18, -0.1, -0.4))
box("charwall", (0.25, 2.2, 1.2), (SX0 - 1.55, SY0, 0.6), CHAR)
box("fallenfront", (2.6, 1.5, 0.1), (SX0 - 0.6, SY0 - 1.55, 0.1), plain("charred", "#2a221c", 1.0), rot=(0.04, -0.06, 0.25))
text("fallen_text", "BRAND · GEN", 0.3, (SX0 - 0.7, SY0 - 1.55, 0.17), plain("ash", "#8f877a", 1.0), rot=(0.04, -0.06, 0.25))

# the landing: dock, crates, barrels, the clock post, the tripod and its line
DX, DY = P(0.2, 0.4)
box("dock", (1.4, 3.2, 0.15), (DX, DY, 0.09), L.PLANK_Y)
for (x, z) in [(-0.65, -1.15), (1.05, -1.15), (-0.65, 0.5), (1.05, 0.5)]:
    cyl("dockpost", 0.08, 0.6, (x, -z, 0.2), (0, 0, 0), L.LOGS[0], verts=8)
    sphere("dockpostsnow", (x, -z, 0.5), (0.11, 0.11, 0.05), L.SNOW)
for (x, z, s) in [(-1.3, 1.6, 0.55), (-1.9, 1.85, 0.5), (1.55, 1.9, 0.5)]:
    box("crate", (s, s, s), (x, -z, s / 2), L.PLANK_Z, rot=(0, 0, random.random()))
    box("cratesnow", (s + 0.02, s + 0.02, 0.07), (x, -z, s + 0.03), L.SNOW, bevel=0.03, segs=3)
for (x, z) in [(1.4, 1.25), (1.85, 1.45)]:
    cyl("barrel", 0.2, 0.55, (x, -z, 0.28), (0, 0, 0), L.LOGS[1], verts=14)
    sphere("barrelsnow", (x, -z, 0.56), (0.19, 0.19, 0.05), L.SNOW)
box("clockpost", (0.16, 0.16, 2.0), (1.15, -1.4, 1.0), L.PLANK_Z)
cyl("clockface", 0.22, 0.04, (1.15, -1.49, 1.75), (math.pi / 2, 0, 0), L.CREAM, verts=20)
TT = Vector((4.6, 3.8, 2.3))
for (dx, dz) in [(-0.8, 0.5), (0.8, 0.4), (0.05, -0.9)]:
    foot = Vector((4.6 + dx, 3.8 - dz, 0))
    v = TT - foot
    o = cyl("tripodleg", 0.05, v.length, (foot + TT) / 2, (0, 0, 0), L.LOGS[0], verts=6)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = v.to_track_quat("Z", "Y")
box("pennant", (0.4, 0.02, 0.25), (4.82, 3.8, 2.3), plain("pennant", "#1b2a4a", 0.9))


def tube(name, pts, radius, mat):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    o = bpy.data.objects.new(name, cu)
    S.collection.objects.link(o)
    o.data.materials.append(mat)
    return o


def qbez(a, m, b, n=40):
    return [tuple(a * (1 - t) ** 2 + m * 2 * t * (1 - t) + b * t * t) for t in (i / n for i in range(n + 1))]


tube("clockline", qbez(TT, Vector((2.8, 1.2, 1.0)), Vector((1.15, -1.4, 1.9))), 0.012, plain("line", "#1a1714", 0.8))

# the sternwheeler, laid up for the winter and frozen in
SX1, SY1 = P(-8, -2.45)
hull_pts = [(-3.8, -1), (2.9, -1), (3.6, -0.75), (4.1, 0), (3.6, 0.75), (2.9, 1), (-3.8, 1)]
me = bpy.data.meshes.new("hull")
me.from_pydata([(SX1 + x, SY1 + y, -0.15) for x, y in hull_pts], [], [tuple(range(len(hull_pts)))])
hull = bpy.data.objects.new("hull", me)
S.collection.objects.link(hull)
sol = hull.modifiers.new("solid", "SOLIDIFY")
sol.thickness = -0.6
sol.offset = 1
hull.data.materials.append(plain("hull", "#3b2b22", 0.9))
WHITEP = plain("steamerwhite", "#e2dccf", 0.85)
box("deck", (6.0, 1.8, 0.85), (SX1 - 0.4, SY1, 0.82), WHITEP)
for i in range(14):
    box("deckwin", (0.18, 0.02, 0.32), (SX1 - 3.1 + i * 0.4, SY1 - 0.91, 0.9), L.DARKGLASS)
box("deckroof", (6.6, 2.2, 0.08), (SX1 - 0.4, SY1, 1.29), WHITEP)
box("deckroofsnow", (6.6, 2.2, 0.14), (SX1 - 0.4, SY1, 1.38), L.SNOW, bevel=0.05, segs=3)
box("texas", (3.4, 1.3, 0.6), (SX1 + 0.4, SY1, 1.75), WHITEP)
box("texassnow", (3.7, 1.55, 0.14), (SX1 + 0.4, SY1, 2.12), L.SNOW, bevel=0.05, segs=3)
box("pilothouse", (0.9, 0.9, 0.6), (SX1 + 1.5, SY1, 2.45), WHITEP)
box("pilotsnow", (1.1, 1.1, 0.14), (SX1 + 1.5, SY1, 2.81), L.SNOW, bevel=0.05, segs=3)
for dz in (0.36, -0.36):
    cyl("stack", 0.11, 2.6, (SX1 + 2.5, SY1 + dz, 2.6), (0, 0, 0), L.METAL, verts=10)
    cyl("stackcrown", 0.17, 0.18, (SX1 + 2.5, SY1 + dz, 3.95), (0, 0, 0), L.METAL, verts=10, r2=0.13)
WHEEL = plain("wheel", "#6a2a1e", 0.9)
for i in range(10):
    box("paddle", (0.08, 1.7, 1.5), (SX1 - 4.3, SY1, 0.55), WHEEL, rot=(0, i * math.pi / 10, 0))

# street lanterns
for (x, z) in [(-8.2, 6.9), (-3.6, 6.9), (3.2, 6.9), (6.2, 6.9), (10.6, 7.6)]:
    cyl("lpost", 0.05, 1.6, (x, -z, 0.8), (0, 0, 0), L.PLANK_Z, verts=8)
    box("lglass", (0.22, 0.22, 0.28), (x, -z, 1.72), L.GLASS)
    cyl("lcap", 0.2, 0.14, (x, -z, 1.93), (0, 0, math.pi / 4), L.METAL, verts=4, r2=0.02)
    point("streetlight", (x, -z, 1.6), 40, radius=0.12)

# ---------------------------------------------------------------- black spruce: three shapes, shared meshes
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
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    o = bpy.context.active_object
    o.name = "spruce_proto%d" % k
    o.location = (0, 0, -50)
    return o.data


protos = [spruce_mesh(k) for k in range(3)]
count = 0
for i in range(560):
    x, z = (random.random() - 0.5) * (PW - 1.6), (random.random() - 0.5) * (PD - 1.6)
    in_river = -7.3 < z < 0.3
    in_town = -15 < x < 15.5 and 0 < z < 12.2
    near_vera = math.hypot(x - 10, z + 10) < 3.2
    if in_river or in_town or near_vera or near_route(x, z, BACKWAY, 0.75):
        continue
    o = bpy.data.objects.new("spruce", random.choice(protos))
    s = random.uniform(0.6, 1.25)
    o.location, o.scale, o.rotation_euler = (x, -z, 0), (s, s, s * random.uniform(0.9, 1.15)), (0, 0, random.uniform(0, 6.28))
    S.collection.objects.link(o)
    count += 1

# ---------------------------------------------------------------- shading: light bands, cold shadows, warm lamplight
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
    for pos, c in BANDS[1:]:
        e = els.new(min(pos / top, 0.999))
        e.color = (*lin(c), 1)
    nt.links.new(sc.outputs[0], r.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(src, mix.inputs[6])
    nt.links.new(r.outputs["Color"], mix.inputs[7])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])


for m in list(bpy.data.materials):
    if m.name.startswith("glass"):
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
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
    return m


# ---------------------------------------------------------------- camera
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
cam.ortho_scale = float(os.environ.get("ORTHO", "50"))
co = bpy.data.objects.new("cam", cam)
S.collection.objects.link(co)
co.location = Vector((37, -45, 27))
target = Vector((1.0, -0.6, -1.4))
co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
S.camera = co
FWD = (target - co.location).normalized()

# ---------------------------------------------------------------- the townsfolk
SPR = bpy.data.collections.new("sprites")
S.collection.children.link(SPR)
HEAD = {}
PERSON_H = 2.6


def sprite(name, x, z, y=0.03, k=1.0):
    bx, by = P(x, z)
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
    bpy.ops.mesh.primitive_plane_add(size=1, location=(bx, by, y))
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
    HEAD[name] = Vector((bx, by, y)) + up * h * 0.92
    bpy.ops.mesh.primitive_circle_add(vertices=20, radius=0.42, fill_type="NGON", location=(bx, by, y + 0.03))
    s = bpy.context.active_object
    s.scale = (1.2, 0.85, 1)
    s.data.materials.append(unlit("shadow_" + name, "#1a2238", 0.45))
    for c in s.users_collection:
        c.objects.unlink(s)
    SPR.objects.link(s)


ANTON = (3.4, -3.0) if WALK else (0.6, 7.2)
sprite("anton", *ANTON, y=0.06 if WALK else 0.03)
sprite("maggie", -6.2, 5.75, y=0.15)
sprite("sandor", -2.4, 6.9)
sprite("gilchrist", 12.0, 10.4)
sprite("billy", -1.7, -1.5, y=0.06, k=0.8)
sprite("ashby", 5.9, -2.5, y=0.06)
sprite("vera", 10.1, -8.6)
ax, ay = P(*ANTON)
point("antonlantern", (ax + 0.5, ay - 0.3, 0.9), 60 if WALK else 35, radius=0.1)

# ---------------------------------------------------------------- red: the thread in town, the route on the walk
RED = unlit("red", "#c0262b")
if not WALK:
    a, b = HEAD["maggie"], HEAD["sandor"]
    m = (a + b) / 2 + Vector((0, 0, 1.6))
    tube("thread", qbez(a, m, b), 0.085, RED)


def ground_z(x, z):
    if abs(x - 0.2) < 0.7 and -1.2 < z < 2.0:
        return 0.2
    if 5.45 < z < 6.45 and -15.2 < x < 10.4:
        return 0.16
    if -6.5 < z < -0.7:
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
    for a, b in zip(dense, dense[1:]):
        cum.append(cum[-1] + (b - a).length)
    total, out, j = cum[-1], [], 0
    for i in range(n + 1):
        d = total * i / n
        while j < len(cum) - 2 and cum[j + 1] < d:
            j += 1
        f = (d - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
        out.append(dense[j].lerp(dense[j + 1], f))
    return out, total


def ribbon(name, pts, width, mat, dash=None, t0=0.0, t1=1.0):
    sp, total = catmull(pts)
    N = len(sp) - 1
    vs, fs = [], []
    for i in range(N):
        ta, tb = i / N, (i + 1) / N
        if tb < t0 or ta > t1:
            continue
        if dash and int(ta * total / dash) % 2 == 1:
            continue
        a, b = sp[i], sp[i + 1]
        dv = (b - a)
        if dv.length < 1e-9:
            continue
        nx, nz = -dv.y / dv.length * width / 2, dv.x / dv.length * width / 2
        k = len(vs)
        for (x, z) in [(a.x - nx, a.y - nz), (a.x + nx, a.y + nz), (b.x + nx, b.y + nz), (b.x - nx, b.y - nz)]:
            vs.append((x, -z, ground_z(x, z)))
        fs.append((k, k + 1, k + 2, k + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.update()
    o = bpy.data.objects.new(name, me)
    S.collection.objects.link(o)
    o.data.materials.append(mat)
    return o, sp, total


if WALK:
    sp, total = catmull(TAKEN)
    tA = min(range(len(sp)), key=lambda i: (sp[i] - Vector(ANTON)).length) / (len(sp) - 1)
    ribbon("route_done", TAKEN, 0.2, RED, None, 0, tA)
    ribbon("route_ahead", TAKEN, 0.18, RED, 0.32, tA + 0.012, 1)
    ribbon("route_back", BACKWAY, 0.15, unlit("redfaint", "#9a4a46"), 0.26)
    FOOT = unlit("foot", "#5f7290")
    s = 0.4
    k = 0
    while s < tA * total - 0.5:
        i = int(s / total * (len(sp) - 1))
        p, q = sp[i], sp[min(i + 1, len(sp) - 1)]
        tg = (q - p).normalized() if (q - p).length > 0 else Vector((1, 0))
        side = 1 if k % 2 else -1
        x, z = p.x - tg.y * 0.16 * side, p.y + tg.x * 0.16 * side
        if ground_z(x, z) < 0.1:
            o = cyl("foot", 0.07, 0.01, (x, -z, ground_z(x, z) - 0.01), (0, 0, -math.atan2(tg.x, tg.y)), FOOT, verts=10)
            o.scale = (1, 1.7, 1)
        s += 0.32
        k += 1
    bpy.ops.mesh.primitive_torus_add(major_radius=0.5, minor_radius=0.07, location=(9.5, 8.0, 0.08))
    finish(bpy.context.active_object, "destination", RED)

# ---------------------------------------------------------------- light
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
lo.location = (-26, -14, 34)
S.collection.objects.link(lo)
lo.rotation_euler = (Vector((0, 0, -1)) - lo.location).to_track_quat("-Z", "Y").to_euler()
moon = bpy.data.lights.new("moon", "SUN")
moon.energy, moon.color, moon.angle = 1.6, lin("#8aa6cf"), math.radians(3)
mo = bpy.data.objects.new("moon", moon)
mo.rotation_euler = (math.radians(55), 0, math.radians(150))
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

# anchors for the paper overlay, in 1280x720 screen space
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402

bpy.context.view_layer.update()


def scr(v):
    c = world_to_camera_view(S, co, Vector(v))
    return [round(c.x * 1280), round((1 - c.y) * 720)]


A = {
    "maggies": scr((RX, y0, FH + 0.2)), "store": scr((-3.4, -3.0, 1.4)), "landing": scr((-1.0, 1.2, 0.3)), "ice": scr(TT),
    "vera": scr((VX, VY, 3.0)), "police_door": scr((PX, PY - 1.4, 1.0)), "police_roof": scr((PX + 1.2, PY, 3.0)), "inf_roof_e": scr((IX + 1.2, IY, 2.8)),
    "dest": scr((9.5, 8.0, 0.08)), "alt_mid": scr((-15.6, -3, 0.07)),
}
for k_, v in HEAD.items():
    A["head_" + k_] = scr(v)
json.dump(A, open(ANCH, "w"), indent=0)
print("built in %.1fs, %d objects, %d trees" % (time.time() - t0, len(S.objects), count))
if BLEND:
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
bpy.ops.render.render(write_still=True)
print("rendered in %.1fs" % (time.time() - t0))
