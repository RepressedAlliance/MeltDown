"""Rin as a relightable cut-out card inside the 3D scenes.

The card is an emission shader fed by the processed layers in assets/char/<pose>/:
  colour * (ambient + stepped key light) + stepped rim light
Key and rim follow a pseudo normal map, so the light direction and colours can be
set per shot to match the set (sodium orange, plasma blue, dawn gold) with
hard anime-style terminators. Every control is an object custom property read by
Attribute nodes, so shots can keyframe them:
  key_dir (vec, card space: +x right, +y up, +z toward camera), key_col, amb_col,
  rim_dir, rim_col, outline_col, key_soft, exposure, dissolve (0..1), dissolve_col, sway, alpha
"""
import json
import math
from pathlib import Path

import bpy

from common import ROOT, frame_value_node, link, node_tree

CHAR = ROOT / "assets" / "char"


def _img(path, colorspace="sRGB"):
    im = bpy.data.images.load(str(path), check_existing=True)
    im.colorspace_settings.name = colorspace
    im.alpha_mode = "STRAIGHT"
    return im


def _attr(N, name, kind="Fac"):
    a = N.new("ShaderNodeAttribute")
    a.attribute_type = "OBJECT"
    a.attribute_name = name
    return a.outputs[kind]


def card_material(pose):
    d = CHAR / pose
    mat = bpy.data.materials.new(f"Card_{pose}")
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    tc = N.new("ShaderNodeTexCoord")
    # hair sway: a slow, smooth warp of the drawing weighted by hair_soft.png (no geometry change).
    # The weights change gradually everywhere (hair_weights.py), so lines bend instead of tearing; the
    # motion is a breeze, about one sway every three seconds with a slower second wave on top (times
    # sway_rate: below 1 slows it, for floating).
    hair = N.new("ShaderNodeTexImage")
    soft = d / "hair_soft.png"
    hair.image = _img(soft if soft.exists() else d / "hair.png", "Non-Color")
    hair.interpolation = "Cubic"
    L.new(tc.outputs["UV"], hair.inputs["Vector"])
    t = frame_value_node(nt, "time")
    rate = N.new("ShaderNodeAttribute")
    rate.attribute_type = "OBJECT"
    rate.attribute_name = "sway_rate"
    sepuv = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["UV"], sepuv.inputs[0])

    def mm(op, a, b=None, bv=None, cv=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        L.new(a, n.inputs[0])
        if b is not None:
            L.new(b, n.inputs[1])
        elif bv is not None:
            n.inputs[1].default_value = bv
        if cv is not None:
            n.inputs[2].default_value = cv
        return n.outputs[0]

    tt = mm("MULTIPLY", t.outputs[0], rate.outputs["Fac"])
    w1 = mm("SINE", mm("ADD", mm("MULTIPLY", tt, bv=2.07), mm("MULTIPLY", sepuv.outputs["Y"], bv=5.0)))
    w2 = mm("SINE", mm("ADD", mm("MULTIPLY", tt, bv=1.19),
                       mm("MULTIPLY_ADD", sepuv.outputs["Y"], bv=9.0, cv=1.3)))
    wx = mm("MULTIPLY", mm("ADD", w1, mm("MULTIPLY", w2, bv=0.45)), bv=1 / 1.45)
    wy = mm("MULTIPLY", mm("SINE", mm("ADD", mm("MULTIPLY", tt, bv=1.7),
                                      mm("MULTIPLY", sepuv.outputs["X"], bv=4.0))), bv=0.35)
    sway = N.new("ShaderNodeAttribute")
    sway.attribute_type = "OBJECT"
    sway.attribute_name = "sway"
    gain = mm("MULTIPLY", sway.outputs["Fac"], hair.outputs["Color"])
    off = N.new("ShaderNodeCombineXYZ")
    L.new(mm("MULTIPLY", wx, gain), off.inputs["X"])
    L.new(mm("MULTIPLY", wy, gain), off.inputs["Y"])
    uvs = N.new("ShaderNodeVectorMath")
    uvs.operation = "ADD"
    L.new(tc.outputs["UV"], uvs.inputs[0])
    L.new(off.outputs[0], uvs.inputs[1])

    class _UV:  # keeps the rest of the graph reading `uv.outputs["UV"]`
        outputs = {"UV": uvs.outputs[0]}
    uv = _UV()
    col = N.new("ShaderNodeTexImage")
    col.image = _img(d / "color.png")
    col.interpolation = "Cubic"
    nrm = N.new("ShaderNodeTexImage")
    nrm.image = _img(d / "normal.png", "Non-Color")
    edge = N.new("ShaderNodeTexImage")
    edge.image = _img(d / "edge.png", "Non-Color")
    L.new(uv.outputs["UV"], edge.inputs["Vector"])
    L.new(uv.outputs["UV"], col.inputs["Vector"])
    L.new(uv.outputs["UV"], nrm.inputs["Vector"])
    color_out, alpha_out = col.outputs["Color"], col.outputs["Alpha"]
    if (d / "color_blink.png").exists():
        colb = N.new("ShaderNodeTexImage")
        colb.image = _img(d / "color_blink.png")
        colb.interpolation = "Cubic"
        L.new(uv.outputs["UV"], colb.inputs["Vector"])
        bl = _attr(N, "blink")
        mixc = N.new("ShaderNodeMix")
        mixc.data_type = "RGBA"
        L.new(bl, mixc.inputs["Factor"])
        L.new(col.outputs["Color"], mixc.inputs["A"])
        L.new(colb.outputs["Color"], mixc.inputs["B"])
        color_out = mixc.outputs["Result"]

    def vm(op, a, b=None, bv=None):
        n = N.new("ShaderNodeVectorMath")
        n.operation = op
        L.new(a, n.inputs[0])
        if b is not None:
            L.new(b, n.inputs[1])
        elif bv is not None:
            n.inputs[1].default_value = bv
        return n

    def m(op, a, b=None, bv=None, av=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        if a is not None:
            L.new(a, n.inputs[0])
        else:
            n.inputs[0].default_value = av
        if b is not None:
            L.new(b, n.inputs[1])
        elif bv is not None:
            n.inputs[1].default_value = bv
        return n.outputs[0]

    # normal: [0,1] -> [-1,1]
    nn = vm("MULTIPLY_ADD", nrm.outputs["Color"], bv=(2, 2, 2))
    nn.inputs[2].default_value = (-1, -1, -1)
    n_vec = vm("NORMALIZE", nn.outputs[0]).outputs[0]

    key_dir = vm("NORMALIZE", _attr(N, "key_dir", "Vector")).outputs[0]
    ndl = vm("DOT_PRODUCT", n_vec, key_dir).outputs["Value"]
    soft = _attr(N, "key_soft")
    lo = m("SUBTRACT", None, soft, av=0.05)
    hi = m("ADD", None, soft, av=0.05)
    step = N.new("ShaderNodeMapRange")
    step.interpolation_type = "SMOOTHSTEP"
    L.new(ndl, step.inputs["Value"])
    L.new(lo, step.inputs["From Min"])
    L.new(hi, step.inputs["From Max"])
    key = step.outputs["Result"]
    # key_wash 1: no new terminator across the drawing (on a face it reads as a grey sheet laid over the
    # drawn cel shading); the key light becomes a broad gradient across the whole figure instead
    kd = N.new("ShaderNodeSeparateXYZ")
    L.new(key_dir, kd.inputs[0])
    kd2 = N.new("ShaderNodeCombineXYZ")
    L.new(kd.outputs["X"], kd2.inputs["X"])
    L.new(kd.outputs["Y"], kd2.inputs["Y"])
    d2 = vm("NORMALIZE", kd2.outputs[0]).outputs[0]
    pc = vm("SUBTRACT", uv.outputs["UV"], bv=(0.5, 0.5, 0.0)).outputs[0]
    g = vm("DOT_PRODUCT", pc, d2).outputs["Value"]
    wash = N.new("ShaderNodeMapRange")
    wash.interpolation_type = "SMOOTHSTEP"
    wash.inputs["From Min"].default_value = -0.55
    wash.inputs["From Max"].default_value = 0.55
    L.new(g, wash.inputs["Value"])
    kmix = N.new("ShaderNodeMix")
    kmix.data_type = "FLOAT"
    L.new(_attr(N, "key_wash"), kmix.inputs["Factor"])
    L.new(key, kmix.inputs["A"])
    L.new(wash.outputs["Result"], kmix.inputs["B"])
    key = kmix.outputs["Result"]

    key_col = _attr(N, "key_col", "Color")
    amb_col = _attr(N, "amb_col", "Color")
    light = N.new("ShaderNodeMix")
    light.data_type = "RGBA"
    light.blend_type = "ADD"
    L.new(key, light.inputs["Factor"])
    L.new(amb_col, light.inputs["A"])
    L.new(key_col, light.inputs["B"])
    lit = N.new("ShaderNodeMix")
    lit.data_type = "RGBA"
    lit.blend_type = "MULTIPLY"
    lit.inputs["Factor"].default_value = 1.0
    L.new(color_out, lit.inputs["A"])
    L.new(light.outputs["Result"], lit.inputs["B"])

    # rim: only inside the narrow edge band, on the side facing rim_dir, stepped
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(n_vec, sep.inputs[0])
    nxy = N.new("ShaderNodeCombineXYZ")
    L.new(sep.outputs["X"], nxy.inputs["X"])
    L.new(sep.outputs["Y"], nxy.inputs["Y"])
    nxy_n = vm("NORMALIZE", nxy.outputs[0]).outputs[0]
    rim_dir = vm("NORMALIZE", _attr(N, "rim_dir", "Vector")).outputs[0]
    rd = vm("DOT_PRODUCT", nxy_n, rim_dir).outputs["Value"]
    rim_raw = m("MULTIPLY", edge.outputs["Color"], m("MAXIMUM", rd, bv=0.0))
    # only the outermost few pixels on the lit side: a thin line, not a halo around the cut-out
    rstep = N.new("ShaderNodeMapRange")
    rstep.interpolation_type = "SMOOTHSTEP"
    rstep.inputs["From Min"].default_value = 0.5
    rstep.inputs["From Max"].default_value = 0.64
    L.new(rim_raw, rstep.inputs["Value"])
    rim_col = _attr(N, "rim_col", "Color")
    rim = N.new("ShaderNodeMix")
    rim.data_type = "RGBA"
    rim.blend_type = "ADD"
    L.new(rstep.outputs["Result"], rim.inputs["Factor"])
    L.new(lit.outputs["Result"], rim.inputs["A"])
    L.new(rim_col, rim.inputs["B"])
    # outline: the same thin outermost line all the way round, whatever the light: dark clothes keep their
    # silhouette against a dark set (her black boots in the reactor printed as one ink with the background)
    ostep = N.new("ShaderNodeMapRange")
    ostep.interpolation_type = "SMOOTHSTEP"
    ostep.inputs["From Min"].default_value = 0.5
    ostep.inputs["From Max"].default_value = 0.64
    L.new(edge.outputs["Color"], ostep.inputs["Value"])
    outline = N.new("ShaderNodeMix")
    outline.data_type = "RGBA"
    outline.blend_type = "ADD"
    L.new(ostep.outputs["Result"], outline.inputs["Factor"])
    L.new(rim.outputs["Result"], outline.inputs["A"])
    L.new(_attr(N, "outline_col", "Color"), outline.inputs["B"])

    # dissolve: noise threshold with a glowing edge
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 9.0
    nz.inputs["Detail"].default_value = 4.0
    L.new(uv.outputs["UV"], nz.inputs["Vector"])
    diss = _attr(N, "dissolve")
    # threshold sweeps the noise range (mostly 0.2..0.8): 0 = intact, 1 = gone
    thr = m("ADD", m("MULTIPLY", diss, bv=0.75), bv=0.15)
    alive = m("GREATER_THAN", nz.outputs["Fac"], thr)
    edge_band = m("SUBTRACT", m("GREATER_THAN", nz.outputs["Fac"], m("SUBTRACT", thr, bv=0.035)), alive)
    dcol = _attr(N, "dissolve_col", "Color")
    glow = N.new("ShaderNodeMix")
    glow.data_type = "RGBA"
    glow.blend_type = "ADD"
    L.new(m("MULTIPLY", edge_band, m("GREATER_THAN", diss, bv=0.001)), glow.inputs["Factor"])
    L.new(outline.outputs["Result"], glow.inputs["A"])
    L.new(dcol, glow.inputs["B"])

    expo = _attr(N, "exposure")
    em = N.new("ShaderNodeEmission")
    L.new(glow.outputs["Result"], em.inputs["Color"])
    L.new(expo, em.inputs["Strength"])
    alpha = m("MULTIPLY", alpha_out, _attr(N, "alpha"))
    vis = m("MAXIMUM", alive, m("MULTIPLY", edge_band, bv=1.0))
    no_diss = m("LESS_THAN", diss, bv=0.001)
    vis = m("MAXIMUM", vis, no_diss)
    alpha = m("MULTIPLY", alpha, vis)
    tr = N.new("ShaderNodeBsdfTransparent")
    mix = N.new("ShaderNodeMixShader")
    L.new(alpha, mix.inputs[0])
    L.new(tr.outputs[0], mix.inputs[1])
    L.new(em.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "DITHERED"
    # never wrap: a bust drawing is opaque along its bottom edge, and a repeating texture sampled at the
    # top edge of the card blends that row in, drawing a thin dark line across the canvas top in frame
    for node in N:
        if node.type == "TEX_IMAGE":
            node.extension = "EXTEND"
    return mat


DEFAULTS = {
    "key_dir": (0.6, 0.5, 0.6), "key_col": (0.55, 0.5, 0.45), "amb_col": (0.45, 0.47, 0.55),
    "rim_dir": (-0.8, 0.3, 0.0), "rim_col": (0.0, 0.0, 0.0), "key_soft": 0.06, "exposure": 1.0,
    "dissolve": 0.0, "dissolve_col": (1.0, 0.8, 0.4), "sway": 0.0, "sway_rate": 1.0, "alpha": 1.0, "blink": 0.0,
    "key_wash": 1.0,
    "outline_col": (0.0, 0.0, 0.0),
}


def add_card(pose, height=1.5, location=(0, 0, 0), rotation=(math.radians(90), 0, 0), coll=None,
             name=None, **props):
    """A vertical card (faces -Y by default) sized to the pose image; origin at bottom centre."""
    meta = json.loads((CHAR / pose / "meta.json").read_text(encoding="utf-8"))
    w_px, h_px = meta["size"]
    width = height * w_px / h_px
    me = bpy.data.meshes.new(name or f"Rin_{pose}")
    hw = width / 2
    me.from_pydata([(-hw, 0, 0), (hw, 0, 0), (hw, 0, height), (-hw, 0, height)], [], [(0, 1, 2, 3)])
    uvl = me.uv_layers.new(name="UVMap")
    for loop, uvv in zip(me.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uvl.data[loop.index].uv = uvv
    ob = bpy.data.objects.new(me.name, me)
    link(ob, coll)
    ob.location = location
    ob.rotation_euler = (rotation[0] - math.radians(90), rotation[1], rotation[2])
    me.materials.append(card_material(pose))
    for k, v in {**DEFAULTS, **props}.items():
        ob[k] = list(v) if isinstance(v, tuple) else v
    ob.visible_shadow = False
    return ob


def key_props(ob, frame, **props):
    for k, v in props.items():
        ob[k] = list(v) if isinstance(v, tuple) else v
        ob.keyframe_insert(f'["{k}"]', frame=frame)
