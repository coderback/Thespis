# Runs after build_test.py in the same Blender session (STYLE=toon|pixel): cel-shades every material,
# adds outlines and the pixel townsfolk, and renders with EEVEE.
import math
import os
import sys
import time

import bpy
from mathutils import Vector

STYLE = os.environ.get("STYLE", "toon")
argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
SPRITES = os.environ["SPRITES"]
S = bpy.context.scene
t0 = time.time()


def lin(h):
    h = h.lstrip("#")
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))


# light bands: deep shadow is cold blue, lamplight is warm; positions are diffuse light levels
BANDS = [(0.0, "#2c3658"), (0.05, "#55638a"), (0.22, "#a9a9b8"), (0.6, "#f2e2c8"), (1.6, "#fff4e0")]
SCALE = float(os.environ.get("BAND_SCALE", "1.0"))


def toonify(m):
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    out = nt.nodes.get("Material Output")
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
    diff.inputs["Color"].default_value = (1, 1, 1, 1)
    s2r = nt.nodes.new("ShaderNodeShaderToRGB")
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    sc = nt.nodes.new("ShaderNodeMath")
    sc.operation = "MULTIPLY"
    sc.inputs[1].default_value = 1.0 / (BANDS[-1][0] * SCALE)
    nt.links.new(s2r.outputs["Color"], sc.inputs[0])
    r = nt.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.interpolation = "CONSTANT"
    els = r.color_ramp.elements
    top = BANDS[-1][0]
    els[0].position, els[0].color = 0.0, (*lin(BANDS[0][1]), 1)
    els[1].position, els[1].color = 1.0, (*lin(BANDS[-1][1]), 1)
    for pos, c in BANDS[1:]:
        e = els.new(min(pos / top, 0.999))
        e.color = (*lin(c), 1)
    nt.links.new(sc.outputs[0], r.inputs["Fac"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 1.0
    nt.links.new(src, mix.inputs[6])
    nt.links.new(r.outputs["Color"], mix.inputs[7])
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(mix.outputs[2], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])


for m in list(bpy.data.materials):
    if m.name.startswith("glass"):
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 3.0
        continue
    toonify(m)

# harder shadows read better in a drawn style
for light in bpy.data.lights:
    if light.type == "SPOT":
        light.shadow_soft_size = 0.35

# ---------------------------------------------------------------- the townsfolk as camera-facing cut-outs
coll = bpy.data.collections.new("sprites")
S.collection.children.link(coll)
cam = S.camera


def sprite(name, x, y, z, height=1.75):
    img = bpy.data.images.load(os.path.join(SPRITES, name + ".png"))
    m = bpy.data.materials.new("sprite_" + name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(n)
    out = nt.nodes.get("Material Output")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    t.interpolation = "Closest"
    em = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(t.outputs["Color"], em.inputs["Color"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(t.outputs["Alpha"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(em.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, y, z))
    o = bpy.context.active_object
    for v in o.data.vertices:
        v.co.y += 0.5
    o.scale = (height * 32 / 48, height, 1)
    d = cam.location - Vector((x, y, z))
    o.rotation_euler = (math.pi / 2, 0, math.atan2(d.x, -d.y))
    o.data.materials.append(m)
    o.name = "sprite_" + name
    for c in o.users_collection:
        c.objects.unlink(o)
    coll.objects.link(o)
    # a soft contact shadow
    bpy.ops.mesh.primitive_circle_add(vertices=24, radius=0.36, fill_type="NGON", location=(x, y, z + 0.012))
    s = bpy.context.active_object
    s.scale = (1.2, 0.8, 1)
    sm = bpy.data.materials.new("shadow_" + name)
    try:
        sm.use_nodes = True
    except Exception:
        pass
    snt = sm.node_tree
    for n in list(snt.nodes):
        if n.type != "OUTPUT_MATERIAL":
            snt.nodes.remove(n)
    e2 = snt.nodes.new("ShaderNodeEmission")
    e2.inputs["Color"].default_value = (*lin("#1a2238"), 1)
    t2 = snt.nodes.new("ShaderNodeBsdfTransparent")
    m2 = snt.nodes.new("ShaderNodeMixShader")
    m2.inputs["Fac"].default_value = 0.45
    snt.links.new(t2.outputs[0], m2.inputs[1])
    snt.links.new(e2.outputs[0], m2.inputs[2])
    snt.links.new(m2.outputs[0], snt.nodes.get("Material Output").inputs["Surface"])
    s.data.materials.append(sm)
    for c in s.users_collection:
        c.objects.unlink(s)
    coll.objects.link(s)


RX, y0 = -2.6, -1.2
sprite("maggie", RX + 0.35, -1.75, 0.16)
sprite("anton", 0.15, -2.95, 0.03)
sprite("sandor", 2.1, -0.95, 0.03)

# ---------------------------------------------------------------- engine, outlines, camera
for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):
    try:
        S.render.engine = eng
        break
    except Exception:
        continue
try:
    S.eevee.taa_render_samples = 16 if STYLE == "pixel" else 48
except Exception:
    pass
S.view_settings.view_transform = "Standard"
S.view_settings.look = "None"

pixel = STYLE == "pixel"
try:
    S.render.use_freestyle = True
    S.render.line_thickness_mode = "ABSOLUTE"
    S.render.line_thickness = 1.0 if pixel else 2.6
    vl = S.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    ls = fs.linesets[0] if len(fs.linesets) else fs.linesets.new("outline")
    ls.select_by_visibility = True
    ls.select_silhouette = True
    ls.select_border = True
    ls.select_crease = True
    fs.crease_angle = math.radians(140)
    ls.select_by_collection = True
    ls.collection = coll
    ls.collection_negation = "EXCLUSIVE"
    if ls.linestyle is None:
        ls.linestyle = bpy.data.linestyles.new("ink")
    ls.linestyle.color = lin("#1a120c")
    ls.linestyle.thickness = 1.0 if pixel else 1.6
except Exception as e:
    print("freestyle unavailable:", e)

if pixel:
    c = cam.data
    c.type = "ORTHO"
    c.ortho_scale = 18.5
    c.shift_y = 0.05
    c.dof.use_dof = False
    S.render.resolution_x, S.render.resolution_y = 480, 270
    try:
        S.render.filter_size = 0.0
    except Exception:
        pass
else:
    cam.data.dof.aperture_fstop = 2.0
    S.render.resolution_x, S.render.resolution_y = 1920, 1080
S.render.resolution_percentage = 100
S.render.filepath = OUT
print("stylized (%s) in %.1fs with %s" % (STYLE, time.time() - t0, S.render.engine))
bpy.ops.render.render(write_still=True)
print("rendered in %.1fs" % (time.time() - t0))
