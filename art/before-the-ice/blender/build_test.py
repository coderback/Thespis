# Coldwater Landing, Blender test: Maggie Doyle's roadhouse and one cabin on a corner of the plinth.
# Run: blender -b --factory-startup --python build_test.py -- <out.png> <out.blend> [samples]
import math
import os
import random
import sys
import time

import bpy
from mathutils import Vector

random.seed(1898)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "test.png"
BLEND = argv[1] if len(argv) > 1 else None
SAMPLES = int(argv[2]) if len(argv) > 2 else 160
t0 = time.time()

bpy.ops.wm.read_factory_settings(use_empty=True)
S = bpy.context.scene


def lin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))


# ---------------------------------------------------------------- materials
def new_mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    return m, m.node_tree, m.node_tree.nodes.get("Principled BSDF")


def ramp(nt, stops):
    r = nt.nodes.new("ShaderNodeValToRGB")
    els = r.color_ramp.elements
    els[0].position, els[0].color = stops[0][0], (*lin(stops[0][1]), 1)
    els[1].position, els[1].color = stops[-1][0], (*lin(stops[-1][1]), 1)
    for pos, c in stops[1:-1]:
        e = els.new(pos)
        e.color = (*lin(c), 1)
    return r


def textured(name, stops, scale=(1, 1, 1), noise=4.0, detail=8.0, rough=0.85, bump=0.3, wave=None, metal=0.0):
    m, nt, b = new_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    if wave:
        t = nt.nodes.new("ShaderNodeTexWave")
        t.wave_type = wave.get("type", "BANDS")
        for attr in ("bands_direction", "rings_direction"):
            try:
                setattr(t, attr, wave.get("dir", "X"))
            except Exception:
                pass
        t.inputs["Scale"].default_value = wave.get("scale", 3)
        t.inputs["Distortion"].default_value = wave.get("distortion", 6)
        t.inputs["Detail"].default_value = 6
    else:
        t = nt.nodes.new("ShaderNodeTexNoise")
        t.inputs["Scale"].default_value = noise
        t.inputs["Detail"].default_value = detail
    nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
    r = ramp(nt, stops)
    nt.links.new(t.outputs["Fac"], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = bump
    nt.links.new(t.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def plain(name, hexc, rough=0.8, metal=0.0, emit=None, strength=0.0):
    m, nt, b = new_mat(name)
    b.inputs["Base Color"].default_value = (*lin(hexc), 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*lin(emit), 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def snow_mat():
    m, nt, b = new_mat("snow")
    b.inputs["Base Color"].default_value = (*lin("#eef3f9"), 1)
    b.inputs["Roughness"].default_value = 0.55
    b.inputs["Subsurface Weight"].default_value = 0.35
    b.inputs["Subsurface Radius"].default_value = (0.5, 0.7, 1.0)
    b.inputs["Subsurface Scale"].default_value = 0.06
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 45
    n.inputs["Detail"].default_value = 4
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.12
    nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def strata_mat():
    m, nt, b = new_mat("strata")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    ma = nt.nodes.new("ShaderNodeMath")
    ma.operation = "MULTIPLY_ADD"
    ma.inputs[1].default_value = 1 / 1.8
    ma.inputs[2].default_value = 0.5
    nt.links.new(sep.outputs["Z"], ma.inputs[0])
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3
    n.inputs["Detail"].default_value = 6
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY_ADD"
    mul.inputs[1].default_value = 0.08
    nt.links.new(n.outputs["Fac"], mul.inputs[0])
    nt.links.new(ma.outputs[0], mul.inputs[2])
    r = ramp(nt, [(0, "#3a3028"), (0.2, "#5d6f84"), (0.34, "#8a9bb0"), (0.38, "#5a4430"), (0.6, "#7a6248"), (0.7, "#a08a6a"), (0.74, "#6a5038"), (0.86, "#4a3626"), (0.9, "#e4ebf2"), (1, "#f2f6fa")])
    nt.links.new(mul.outputs[0], r.inputs["Fac"])
    nt.links.new(r.outputs["Color"], b.inputs["Base Color"])
    v = nt.nodes.new("ShaderNodeTexVoronoi")
    v.inputs["Scale"].default_value = 14
    nt.links.new(tc.outputs["Object"], v.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.5
    nt.links.new(v.outputs["Distance"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.95
    return m


SNOW = snow_mat()
LOGS = [textured("log%d" % i, st, scale=(9, 9, 0.5), noise=3.5, rough=0.9, bump=0.45) for i, st in enumerate([
    [(0, "#2a1f17"), (0.45, "#56412e"), (0.7, "#76644f"), (1, "#9a8b77")],
    [(0, "#2e2219"), (0.5, "#5e4733"), (0.75, "#806b54"), (1, "#a39380")],
    [(0, "#261c15"), (0.4, "#4e3b2a"), (0.7, "#6d5a46"), (1, "#8c7c68")],
])]
CHINK = plain("chink", "#3b342b", 1.0)
PLANK_Z = textured("plankZ", [(0, "#2c2016"), (0.5, "#5a4433"), (1, "#7d6550")], scale=(14, 14, 0.6), rough=0.9, bump=0.3)
PLANK_Y = textured("plankY", [(0, "#2c2016"), (0.5, "#5a4433"), (1, "#7d6550")], scale=(14, 0.6, 14), rough=0.9, bump=0.3)
PAINT = textured("paint", [(0, "#3e3024"), (0.36, "#4a3a2c"), (0.42, "#b39a74"), (1, "#cfbf9c")], scale=(6, 6, 0.8), noise=2.5, detail=10, rough=0.8, bump=0.25)
TRIM = textured("trim", [(0, "#1e231d"), (0.6, "#2b3329"), (1, "#3d463a")], scale=(10, 10, 1), rough=0.7, bump=0.1)
CREAM = plain("cream", "#e6d8b8", 0.6)
METAL = plain("metal", "#1c1a19", 0.45, 0.7)
GLASS = plain("glass", "#2a1a0a", 0.2, 0, emit="#ffb35a", strength=9)
ICE = textured("ice", [(0, "#8fb0cc"), (0.5, "#b4cadd"), (1, "#e6eef6")], scale=(2, 2, 2), noise=3, rough=0.12, bump=0.08)
STRATA = strata_mat()
DESK = textured("walnut", [(0, "#1c120b"), (0.5, "#2c1b10"), (1, "#3c2616")], scale=(0.08, 2.5, 1), noise=6, detail=12, rough=0.3, bump=0.02)
SPRUCE = textured("spruce", [(0, "#0f1d16"), (0.5, "#1d3328"), (1, "#2c4a3a")], scale=(4, 4, 4), noise=6, rough=0.95, bump=0.6)


# ---------------------------------------------------------------- primitives
def finish(o, name, mat):
    o.name = name
    if mat:
        o.data.materials.append(mat)
    return o


def box(name, size, loc, mat, rot=(0, 0, 0), bevel=0.0, segs=2):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        md = o.modifiers.new("bevel", "BEVEL")
        md.width = bevel
        md.segments = segs
        if segs > 2:
            for p in o.data.polygons:
                p.use_smooth = True
    return finish(o, name, mat)


def cyl(name, r, L, loc, rot, mat, verts=16, r2=None, smooth=True):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r2 is None else r2, depth=L, location=loc)
    o = bpy.context.active_object
    o.rotation_mode = "ZYX"
    o.rotation_euler = rot
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = abs(p.normal.z) < 0.5
    return finish(o, name, mat)


def sphere(name, loc, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, radius=1, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    for p in o.data.polygons:
        p.use_smooth = True
    return finish(o, name, mat)


def point(name, loc, watts, color="#ffa64d", radius=0.1):
    d = bpy.data.lights.new(name, "POINT")
    d.energy = watts
    d.color = lin(color)
    d.shadow_soft_size = radius
    o = bpy.data.objects.new(name, d)
    o.location = loc
    S.collection.objects.link(o)
    return o


def ALONG_X(spin=0.0):
    return (0, math.pi / 2, spin)

def ALONG_Y(spin=0.0):
    return (math.pi / 2, 0, spin)



def cut(segs, a, b):
    out = []
    for s0, s1 in segs:
        if b <= s0 or a >= s1:
            out.append((s0, s1))
        else:
            if a > s0:
                out.append((s0, a))
            if b < s1:
                out.append((b, s1))
    return out


# ---------------------------------------------------------------- a log cabin
R, STEP = 0.12, 0.235


def cabin(name, cx, cy, w, d, h, openings=(), rh_ratio=0.3, front_logs=True, pipe=True, woodpile=False):
    rows = int(h / STEP)
    h = rows * STEP
    rh = d * rh_ratio
    box(name + "_core", (w - 0.14, d - 0.14, h + 0.05), (cx, cy, h / 2), CHINK)

    def wall_pos(wall, u, z, depth):
        return (cx + u, cy - d / 2 - depth, z) if wall == "front" else (cx + w / 2 + depth, cy + u, z)

    def wall_size(wall, su, sd, sz):
        return (su, sd, sz) if wall == "front" else (sd, su, sz)

    for k in range(rows):
        z = R + k * STEP
        # front and back walls: logs along X
        for s in (-1, 1):
            segs = [(-w / 2 - 0.24, w / 2 + 0.24)]
            if s == -1:
                if not front_logs:
                    segs = []
                for (wall, u0, u1, z0, z1, _kind) in openings:
                    if wall == "front" and z + R * 0.6 > z0 and z - R * 0.6 < z1:
                        segs = cut(segs, u0, u1)
            for a, b in segs:
                if b - a > 0.12:
                    cyl(name + "_log", R * random.uniform(0.92, 1.06), b - a, (cx + (a + b) / 2, cy + s * d / 2, z), ALONG_X(random.uniform(0, 6.28)), random.choice(LOGS))
        # side walls: logs along Y, half a course up so the corners interlock
        for s in (-1, 1):
            segs = [(-d / 2 - 0.24, d / 2 + 0.24)]
            zz = z + STEP / 2
            if s == 1:
                for (wall, u0, u1, z0, z1, _kind) in openings:
                    if wall == "right" and zz + R * 0.6 > z0 and zz - R * 0.6 < z1:
                        segs = cut(segs, u0, u1)
            for a, b in segs:
                if b - a > 0.12:
                    cyl(name + "_log", R * random.uniform(0.92, 1.06), b - a, (cx + s * w / 2, cy + (a + b) / 2, zz), ALONG_Y(random.uniform(0, 6.28)), random.choice(LOGS))
    # gables: logs along Y, shortening toward the ridge
    k = 0
    while True:
        zz = h + STEP / 2 + k * STEP
        half = (d / 2) * (1 - (zz - h) / rh)
        if half < 0.18:
            break
        for s in (-1, 1):
            cyl(name + "_gable", R * random.uniform(0.92, 1.04), 2 * half + 0.05, (cx + s * w / 2, cy, zz), ALONG_Y(random.uniform(0, 6.28)), random.choice(LOGS))
        k += 1
    # ridge pole and purlins, their ends showing past the gables
    cyl(name + "_ridge", 0.12, w + 0.9, (cx, cy, h + rh - 0.04), ALONG_X(), LOGS[2])
    for s in (-1, 1):
        cyl(name + "_purlin", 0.1, w + 0.85, (cx, cy + s * d / 4, h + rh / 2 - 0.02), ALONG_X(), LOGS[0])

    # roof: boards, a thick rounded layer of snow, a snow lip at the eave, icicles
    a = math.atan2(rh, d / 2)
    ov, gov = 0.38, 0.42
    for s in (-1, 1):
        run = d / 2 + ov
        L = run / math.cos(a)
        top = h + rh + 0.1
        ridge = Vector((cx, cy, top))
        eave = Vector((cx, cy + s * run, top - run * math.tan(a)))
        mid = (ridge + eave) / 2
        th = -s * a
        nrm = Vector((0, -math.sin(th), math.cos(th)))
        box(name + "_roof", (w + 2 * gov, L, 0.06), mid, PLANK_Y, rot=(th, 0, 0), bevel=0.01)
        box(name + "_roofsnow", (w + 2 * gov + 0.08, L + 0.06, 0.26), mid + nrm * 0.16, SNOW, rot=(th, 0, 0), bevel=0.11, segs=5)
        lip = eave + nrm * 0.1 + Vector((0, s * 0.03, -0.02))
        o = cyl(name + "_lip", 0.13, w + 2 * gov + 0.02, lip, ALONG_X(), SNOW, verts=20)
        rb = o.modifiers.new("round", "BEVEL")
        rb.width = 0.1
        rb.segments = 5
        rb.limit_method = "ANGLE"
        if s == -1:
            x = -w / 2 - gov + 0.05
            while x < w / 2 + gov - 0.05:
                ln = random.uniform(0.08, 0.42) if random.random() < 0.7 else random.uniform(0.02, 0.1)
                cyl(name + "_icicle", 0.03, ln, (cx + x, lip.y + 0.03, lip.z - 0.1 - ln / 2), (math.pi, 0, 0), plain("icicle", "#dbe8f5", 0.05) if False else ICICLE, verts=6, r2=0.0)
                x += random.uniform(0.09, 0.2)
    sph = cyl(name + "_ridgesnow", 0.17, w + 2 * gov - 0.02, (cx, cy, h + rh + 0.3), ALONG_X(), SNOW, verts=20)
    sph.scale = (1, 1, 0.6)
    rb = sph.modifiers.new("round", "BEVEL")
    rb.width = 0.12
    rb.segments = 5
    rb.limit_method = "ANGLE"

    # openings: frames through the log wall, plank doors, lit windows with mullions and snow on the sill
    for (wall, u0, u1, z0, z1, kind) in openings:
        uc, wd, ht = (u0 + u1) / 2, u1 - u0, z1 - z0
        depth = 0.32
        for side in (u0 - 0.04, u1 + 0.04):
            box(name + "_frame", wall_size(wall, 0.08, depth, ht + 0.08), wall_pos(wall, side, z0 + ht / 2, 0), PLANK_Z, bevel=0.01)
        box(name + "_lintel", wall_size(wall, wd + 0.2, depth, 0.1), wall_pos(wall, uc, z1 + 0.05, 0), PLANK_Z, bevel=0.01)
        if kind == "door":
            n = 4
            for i in range(n):
                box(name + "_door", wall_size(wall, wd / n - 0.012, 0.05, ht - 0.02), wall_pos(wall, u0 + (i + 0.5) * wd / n, z0 + ht / 2, 0.02), PLANK_Z, bevel=0.006)
            box(name + "_doorbatten", wall_size(wall, wd - 0.05, 0.04, 0.09), wall_pos(wall, uc, z0 + ht * 0.7, 0.06), PLANK_Z)
            box(name + "_doorbatten", wall_size(wall, wd - 0.05, 0.04, 0.09), wall_pos(wall, uc, z0 + ht * 0.25, 0.06), PLANK_Z)
            box(name + "_step", wall_size(wall, wd + 0.5, 0.45, 0.12), wall_pos(wall, uc, 0.06, 0.32), PLANK_Y, bevel=0.01)
        else:
            box(name + "_sill", wall_size(wall, wd + 0.22, depth + 0.12, 0.07), wall_pos(wall, uc, z0 - 0.035, 0.06), PLANK_Z, bevel=0.01)
            box(name + "_sillsnow", wall_size(wall, wd + 0.18, 0.2, 0.08), wall_pos(wall, uc, z0 + 0.03, 0.14), SNOW, bevel=0.035, segs=4)
            box(name + "_glass", wall_size(wall, wd, 0.02, ht), wall_pos(wall, uc, z0 + ht / 2, -0.02), GLASS)
            box(name + "_mull", wall_size(wall, 0.035, 0.05, ht), wall_pos(wall, uc, z0 + ht / 2, 0.0), PLANK_Z)
            box(name + "_mull", wall_size(wall, wd, 0.05, 0.035), wall_pos(wall, uc, z0 + ht / 2, 0.0), PLANK_Z)
            point(name + "_spill", wall_pos(wall, uc, z0 + ht / 2, 0.55), 18, radius=0.25)

    if pipe:
        px, py, pz = cx + w * 0.25, cy + d * 0.22, h + rh * 0.55
        cyl(name + "_pipe", 0.07, 1.4, (px, py, pz + 0.55), (0, 0, 0), METAL)
        cyl(name + "_cap", 0.15, 0.12, (px, py, pz + 1.3), (0, 0, 0), METAL, r2=0.03)
    # drifts banked against the back and sides
    for _ in range(5):
        side = random.choice(["back", "left", "right"])
        if side == "back":
            loc, sc = (cx + random.uniform(-w / 2, w / 2), cy + d / 2 + 0.15, 0), (random.uniform(0.6, 1.1), 0.4, random.uniform(0.3, 0.5))
        else:
            sx = -1 if side == "left" else 1
            loc, sc = (cx + sx * (w / 2 + 0.15), cy + random.uniform(-d / 2, d / 2), 0), (0.4, random.uniform(0.6, 1.0), random.uniform(0.25, 0.45))
        sphere(name + "_drift", loc, sc, SNOW)
    for sx in (-1, 1):
        sphere(name + "_cornerdrift", (cx + sx * (w / 2 + 0.2), cy - d / 2 - 0.2, 0), (0.45, 0.4, 0.3), SNOW)
    if woodpile:
        bx, by = cx + w / 2 + 0.6, cy - d / 2 + 0.35
        for row in range(4):
            for i in range(6 - row):
                cyl(name + "_wood", 0.075, 0.55, (bx, by + i * 0.16 + row * 0.08, 0.08 + row * 0.135), ALONG_X(random.uniform(0, 6)), random.choice(LOGS), verts=9)
        sphere(name + "_woodsnow", (bx, by + 0.4, 0.6), (0.34, 0.5, 0.1), SNOW)
    return h, rh


ICICLE = plain("icicle", "#dbe8f5", 0.05)
try:
    ICICLE.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.85
except Exception:
    pass

# ---------------------------------------------------------------- the plinth, desk and river
box("plinth", (13, 8.5, 1.8), (0, 0.75, -0.9), STRATA)
bpy.ops.mesh.primitive_grid_add(x_subdivisions=200, y_subdivisions=130, size=1, location=(0, 0.75, 0.02))
g = bpy.context.active_object
g.scale = (13, 8.5, 1)
bpy.ops.object.transform_apply(scale=True)
for p in g.data.polygons:
    p.use_smooth = True
tex = bpy.data.textures.new("snowlumps", "CLOUDS")
tex.noise_scale = 1.1
md = g.modifiers.new("lumps", "DISPLACE")
md.texture = tex
md.strength = 0.07
finish(g, "ground", SNOW)
box("desk", (400, 400, 0.2), (0, 0, -1.9), DESK)
box("river", (13, 1.3, 0.04), (0, 4.35, 0.03), ICE)
for i in range(22):
    x = -6.3 + i * 0.6 + random.uniform(-0.1, 0.1)
    sphere("bank", (x, 3.62, 0.02), (random.uniform(0.4, 0.7), 0.3, random.uniform(0.12, 0.22)), SNOW)

# ---------------------------------------------------------------- Maggie Doyle's roadhouse
RX, RY, RW, RD = -2.6, 0.7, 4.2, 3.4
rh_h, rh_rh = cabin("roadhouse", RX, RY, RW, RD, 2.6, openings=[("right", -0.55, 0.25, 0.95, 1.65, "window")], front_logs=False, woodpile=False)
y0 = RY - RD / 2 - 0.2
FW, FH = RW + 0.5, rh_h + rh_rh + 1.05
n = int(FW / 0.2)
for i in range(n):
    box("ff_board", (0.19, 0.05, FH + random.uniform(-0.015, 0.015)), (RX - FW / 2 + 0.1 + i * FW / n, y0 + random.uniform(-0.004, 0.004), FH / 2), PAINT, bevel=0.006)
for sx in (-1, 1):
    box("ff_trim", (0.14, 0.09, FH), (RX + sx * (FW / 2 - 0.02), y0 - 0.03, FH / 2), TRIM, bevel=0.01)
box("ff_cornice", (FW + 0.34, 0.32, 0.16), (RX, y0 + 0.03, FH + 0.05), TRIM, bevel=0.02)
box("ff_snow", (FW + 0.36, 0.36, 0.14), (RX, y0 + 0.03, FH + 0.2), SNOW, bevel=0.06, segs=4)
box("sign", (FW - 0.7, 0.06, 0.62), (RX, y0 - 0.05, FH - 0.58), TRIM, bevel=0.01)
font = None
for path in ("C:/Windows/Fonts/GeorgiaPro-Bold.ttf", "C:/Windows/Fonts/georgiab.ttf"):
    try:
        font = bpy.data.fonts.load(path)
        break
    except Exception:
        pass


def text(name, body, size, loc, mat):
    c = bpy.data.curves.new(name, "FONT")
    c.body = body
    c.size = size
    c.extrude = 0.012
    c.align_x = "CENTER"
    c.align_y = "CENTER"
    if font:
        c.font = font
    o = bpy.data.objects.new(name, c)
    o.location = loc
    o.rotation_euler = (math.pi / 2, 0, 0)
    o.data.materials.append(mat)
    S.collection.objects.link(o)
    return o


text("sign_text", "ROADHOUSE", 0.4, (RX, y0 - 0.085, FH - 0.58), CREAM)
text("sign_small", "MEALS · BEDS · M. DOYLE", 0.19, (RX, y0 - 0.04, FH - 1.12), TRIM)


def facade_window(u, z0, z1, wd, lit=True):
    ht = z1 - z0
    for side in (u - wd / 2 - 0.05, u + wd / 2 + 0.05):
        box("fw_frame", (0.1, 0.08, ht + 0.1), (RX + side, y0 - 0.05, z0 + ht / 2), TRIM, bevel=0.01)
    box("fw_head", (wd + 0.36, 0.12, 0.12), (RX + u, y0 - 0.06, z1 + 0.08), TRIM, bevel=0.01)
    box("fw_sill", (wd + 0.3, 0.16, 0.06), (RX + u, y0 - 0.08, z0 - 0.04), TRIM, bevel=0.01)
    box("fw_sillsnow", (wd + 0.26, 0.16, 0.07), (RX + u, y0 - 0.1, z0 + 0.02), SNOW, bevel=0.03, segs=4)
    box("fw_glass", (wd, 0.02, ht), (RX + u, y0 - 0.02, z0 + ht / 2), GLASS if lit else plain("darkglass", "#1a1a20", 0.1))
    box("fw_mull", (0.035, 0.05, ht), (RX + u, y0 - 0.04, z0 + ht / 2), TRIM)
    box("fw_mull", (wd, 0.05, 0.035), (RX + u, y0 - 0.04, z0 + ht / 2), TRIM)
    if lit:
        point("fw_spill", (RX + u, y0 - 0.7, z0 + ht / 2), 22, radius=0.3)


facade_window(-1.35, 0.95, 1.9, 0.8)
facade_window(1.35, 0.95, 1.9, 0.8)
dw, dh = 0.95, 2.0
for i in range(4):
    box("rd_door", (dw / 4 - 0.012, 0.05, dh), (RX - dw / 2 + (i + 0.5) * dw / 4, y0 - 0.05, 0.15 + dh / 2), PLANK_Z, bevel=0.006)
for side in (-dw / 2 - 0.06, dw / 2 + 0.06):
    box("rd_doorframe", (0.1, 0.09, dh + 0.1), (RX + side, y0 - 0.06, 0.15 + dh / 2), TRIM, bevel=0.01)
box("rd_doorhead", (dw + 0.36, 0.12, 0.12), (RX, y0 - 0.07, 0.15 + dh + 0.08), TRIM, bevel=0.01)

# the porch: boardwalk deck, two posts, a shed roof heavy with snow and icicles, a lantern by the door
PD = 1.75
n = int((FW + 0.4) / 0.2)
for i in range(n):
    box("deck", (0.185, PD, 0.06), (RX - (FW + 0.4) / 2 + 0.1 + i * (FW + 0.4) / n, y0 - PD / 2, 0.13 + random.uniform(-0.006, 0.006)), PLANK_Y, bevel=0.005)
for sx in (-1, 1):
    box("joist", (0.12, PD, 0.1), (RX + sx * (FW / 2 + 0.05), y0 - PD / 2, 0.05), PLANK_Y)
for sx in (-1, 1):
    box("post", (0.13, 0.13, 2.35), (RX + sx * (FW / 2 - 0.05), y0 - PD + 0.1, 0.16 + 2.35 / 2), PLANK_Z, bevel=0.01)
box("beam", (FW + 0.2, 0.14, 0.16), (RX, y0 - PD + 0.1, 2.55), PLANK_Z, bevel=0.01)
a2 = math.atan2(0.32, PD)
mid = Vector((RX, y0 - PD / 2 - 0.05, 2.7))
nrm = Vector((0, -math.sin(a2), math.cos(a2)))
box("porchroof", (FW + 0.5, PD + 0.35, 0.06), mid, PLANK_Y, rot=(a2, 0, 0), bevel=0.01)
box("porchsnow", (FW + 0.56, PD + 0.4, 0.22), mid + nrm * 0.14, SNOW, rot=(a2, 0, 0), bevel=0.1, segs=5)
edge = mid + Vector((0, -(PD + 0.35) / 2 * math.cos(a2), -(PD + 0.35) / 2 * math.sin(a2)))
pl = cyl("porchlip", 0.12, FW + 0.54, edge + nrm * 0.1, ALONG_X(), SNOW, verts=20)
rb = pl.modifiers.new("round", "BEVEL")
rb.width = 0.1
rb.segments = 5
rb.limit_method = "ANGLE"
x = -FW / 2 - 0.2
while x < FW / 2 + 0.2:
    ln = random.uniform(0.1, 0.5) if random.random() < 0.7 else random.uniform(0.03, 0.1)
    cyl("icicle", 0.032, ln, (RX + x, edge.y + 0.02, edge.z - 0.06 - ln / 2), (math.pi, 0, 0), ICICLE, verts=6, r2=0.0)
    x += random.uniform(0.08, 0.18)
box("lantern", (0.16, 0.16, 0.22), (RX + 0.78, y0 - 0.32, 2.05), GLASS)
cyl("lanterncap", 0.14, 0.1, (RX + 0.78, y0 - 0.32, 2.21), (0, 0, 0), METAL, verts=4, r2=0.02)
point("lanternlight", (RX + 0.78, y0 - 0.5, 1.95), 30, radius=0.12)
for sx in (-1, 1):
    sphere("porchdrift", (RX + sx * (FW / 2 + 0.3), y0 - PD + 0.2, 0.05), (0.55, 0.7, 0.35), SNOW)
for i in range(3):
    cyl("barrel", 0.22, 0.6, (RX + FW / 2 - 0.45 - i * 0.48, y0 - 0.3, 0.46), (0, 0, 0), plain("barrel", "#4a3322", 0.85) if i == 0 else LOGS[i % 3], verts=18)
    sphere("barrelsnow", (RX + FW / 2 - 0.45 - i * 0.48, y0 - 0.3, 0.77), (0.2, 0.2, 0.05), SNOW)

# ---------------------------------------------------------------- a cabin
cabin("cabin", 2.7, 1.1, 3.0, 2.6, 2.1, openings=[("front", -0.95, -0.15, 0.0, 1.75, "door"), ("front", 0.35, 1.05, 0.85, 1.55, "window"), ("right", -0.35, 0.35, 0.85, 1.5, "window")], woodpile=True)

# ---------------------------------------------------------------- a hand sled by the cabin door
SX, SY = 0.9, -0.6
for sx in (-0.22, 0.22):
    cyl("runner", 0.025, 1.3, (SX + sx, SY, 0.06), ALONG_Y(), METAL, verts=8)
    for yy in (-0.4, 0.0, 0.4):
        box("stanchion", (0.04, 0.04, 0.2), (SX + sx, SY + yy, 0.16), PLANK_Z)
for i in range(6):
    box("slat", (0.56, 0.1, 0.03), (SX, SY - 0.5 + i * 0.2, 0.27), PLANK_Y, bevel=0.005)
sphere("sledsnow", (SX, SY + 0.1, 0.3), (0.26, 0.45, 0.06), SNOW)
box("sledbox", (0.4, 0.4, 0.3), (SX, SY - 0.3, 0.44), PLANK_Z, bevel=0.01)
box("sledboxsnow", (0.42, 0.42, 0.06), (SX, SY - 0.3, 0.62), SNOW, bevel=0.025, segs=3)

# ---------------------------------------------------------------- a street lantern and spruce
cyl("lpost", 0.06, 1.9, (1.0, -2.7, 0.95), (0, 0, 0), PLANK_Z, verts=8)
box("lglass", (0.22, 0.22, 0.3), (1.0, -2.7, 2.02), GLASS)
cyl("lcap", 0.2, 0.14, (1.0, -2.7, 2.24), (0, 0, math.pi / 4), METAL, verts=4, r2=0.02)
point("streetlight", (1.0, -2.7, 1.95), 45, radius=0.12)


def spruce(x, y, s):
    tiers = 8
    for k in range(tiers):
        r = (0.95 * (1 - k / (tiers + 0.5)) + 0.08) * s
        z = (0.45 + k * 0.42) * s
        cyl("spruce", r, 0.75 * s, (x, y, z), (0, 0, random.uniform(0, 6)), SPRUCE, verts=9, r2=0.0, smooth=False)
        cyl("sprucesnow", r * 0.8, 0.32 * s, (x, y, z + 0.2 * s), (0, 0, random.uniform(0, 6)), SNOW, verts=9, r2=0.0, smooth=False)
    cyl("trunk", 0.08 * s, 0.6 * s, (x, y, 0.3 * s), (0, 0, 0), LOGS[0], verts=8)


for (x, y, s) in [(-5.6, 2.9, 1.25), (-4.6, 3.3, 0.95), (5.4, 3.0, 1.3), (5.9, 1.6, 1.0), (-5.9, -1.6, 0.9), (4.6, 3.4, 0.8)]:
    spruce(x, y, s)

# ---------------------------------------------------------------- light: one desk lamp, the cold, windows
W = S.world or bpy.data.worlds.new("World")
S.world = W
try:
    W.use_nodes = True
except Exception:
    pass
bg = W.node_tree.nodes.get("Background")
bg.inputs["Color"].default_value = (*lin("#13203a"), 1)
bg.inputs["Strength"].default_value = 0.9
lamp = bpy.data.lights.new("desklamp", "SPOT")
lamp.energy = 13000
lamp.color = lin("#ffd8ad")
lamp.spot_size = math.radians(78)
lamp.spot_blend = 0.7
lamp.shadow_soft_size = 1.2
lo = bpy.data.objects.new("desklamp", lamp)
lo.location = (-15, -9, 17)
S.collection.objects.link(lo)
lo.rotation_euler = (Vector((0, 0.5, 0)) - lo.location).to_track_quat("-Z", "Y").to_euler()
moon = bpy.data.lights.new("moon", "SUN")
moon.energy = 1.6
moon.color = lin("#8aa6cf")
moon.angle = math.radians(3)
mo = bpy.data.objects.new("moon", moon)
mo.rotation_euler = (math.radians(55), 0, math.radians(150))
S.collection.objects.link(mo)

# ---------------------------------------------------------------- camera: leaning over the model
cam = bpy.data.cameras.new("cam")
cam.lens = 38
co = bpy.data.objects.new("cam", cam)
S.collection.objects.link(co)
co.location = (13.5, -15.5, 10.0)
target = Vector((0.0, 0.5, 0.6))
co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
S.camera = co
foc = bpy.data.objects.new("focus", None)
foc.location = (-0.6, -0.9, 1.2)
S.collection.objects.link(foc)
cam.dof.use_dof = True
cam.dof.focus_object = foc
cam.dof.aperture_fstop = 1.1

# ---------------------------------------------------------------- render
S.render.engine = "CYCLES"
S.cycles.samples = SAMPLES
try:
    S.cycles.use_adaptive_sampling = True
    S.cycles.use_denoising = True
except Exception:
    pass
dev = "CPU"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type == kind]
            if gpus:
                for d in prefs.devices:
                    d.use = d.type == kind
                S.cycles.device = "GPU"
                dev = kind
                break
        except Exception:
            continue
except Exception as e:
    print("no gpu:", e)
S.render.resolution_x, S.render.resolution_y = 1920, 1080
S.render.resolution_percentage = 100
try:
    S.view_settings.view_transform = "AgX"
    S.view_settings.look = "AgX - Medium High Contrast"
except Exception:
    pass
S.view_settings.exposure = 0.0
S.render.filepath = OUT
print("built in %.1fs, %d objects, device %s" % (time.time() - t0, len(S.objects), dev))

if os.environ.get("STYLE", "photo") == "photo":
    if BLEND:
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    bpy.ops.render.render(write_still=True)
    print("rendered in %.1fs" % (time.time() - t0))
