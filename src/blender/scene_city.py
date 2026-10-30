"""Procedural night city on a bay, with the fusion facility across the water.

One joined mesh holds every building; windows, their on/off state and colour
come from a facade shader keyed by per-building random attributes, so the
whole city can be dimmed or re-lit by animating a single value.
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from citygen import _buildings, _highway_path  # noqa: F401
from common import (add_prim, assign, collection, frame_value_node, link, mat_emission,
                    mat_principled, node_tree)

BLOCK = 78.0
STREET = 16.0
REACTOR_POS = Vector((900.0, -1150.0, 0.0))
REACTOR_R = 170.0


# ---------------------------------------------------------------- buildings

def _box_mesh(name, boxes, rng, coll):
    verts, faces, bid, btype, blit = [], [], [], [], []
    for i, (x, y, w, h, z) in enumerate(boxes):
        b = len(verts)
        x0, x1, y0, y1 = x - w / 2, x + w / 2, y - h / 2, y + h / 2
        verts += [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0),
                  (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
        fs = [(b, b + 1, b + 5, b + 4), (b + 1, b + 2, b + 6, b + 5), (b + 2, b + 3, b + 7, b + 6),
              (b + 3, b, b + 4, b + 7), (b + 4, b + 5, b + 6, b + 7)]
        faces += fs
        r, t = rng.random(), rng.random()
        l = rng.beta(1.1, 4.5) * (0.9 if t > 0.72 else 0.6)
        bid += [r] * 5
        btype += [t] * 5
        blit += [l] * 5
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    for nm, arr in (("bid", bid), ("btype", btype), ("blit", blit)):
        a = me.attributes.new(nm, "FLOAT", "FACE")
        a.data.foreach_set("value", arr)
    me.update()
    return link(bpy.data.objects.new(name, me), coll)


def facade_material(name="Facade", window_strength=4.0):
    mat = bpy.data.materials.new(name)
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    p = N.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (0.018, 0.02, 0.026, 1)
    p.inputs["Roughness"].default_value = 0.55
    p.inputs["Specular IOR Level"].default_value = 0.4

    geo = N.new("ShaderNodeNewGeometry")
    sep_p = N.new("ShaderNodeSeparateXYZ")
    sep_n = N.new("ShaderNodeSeparateXYZ")
    L.new(geo.outputs["Position"], sep_p.inputs[0])
    L.new(geo.outputs["Normal"], sep_n.inputs[0])

    def math_node(op, a=None, b=None, v0=None, v1=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        if a is not None:
            L.new(a, n.inputs[0])
        elif v0 is not None:
            n.inputs[0].default_value = v0
        if b is not None:
            L.new(b, n.inputs[1])
        elif v1 is not None:
            n.inputs[1].default_value = v1
        return n.outputs[0]

    # horizontal facade coordinate: y on x-facing walls, x on y-facing walls
    ax = math_node("ABSOLUTE", sep_n.outputs["X"])
    facing_x = math_node("GREATER_THAN", ax, v1=0.5)
    mixu = N.new("ShaderNodeMix")
    mixu.data_type = "FLOAT"
    L.new(facing_x, mixu.inputs["Factor"])
    L.new(sep_p.outputs["X"], mixu.inputs["A"])
    L.new(sep_p.outputs["Y"], mixu.inputs["B"])
    u = mixu.outputs["Result"]
    v = sep_p.outputs["Z"]

    attr = {}
    for nm in ("bid", "btype", "blit"):
        a = N.new("ShaderNodeAttribute")
        a.attribute_type = "GEOMETRY"
        a.attribute_name = nm
        attr[nm] = a.outputs["Fac"]

    cw = math_node("ADD", math_node("MULTIPLY", attr["btype"], v1=1.6), v1=2.4)   # window pitch
    ch = math_node("ADD", math_node("MULTIPLY", attr["bid"], v1=0.6), v1=3.2)     # floor height
    uu = math_node("DIVIDE", u, cw)
    vv = math_node("DIVIDE", math_node("SUBTRACT", v, v1=1.5), ch)
    fu, fv = math_node("FRACT", uu), math_node("FRACT", vv)
    iu, iv = math_node("FLOOR", uu), math_node("FLOOR", vv)

    def band(x, lo, hi, soft=0.04):
        a = N.new("ShaderNodeMapRange")
        a.interpolation_type = "SMOOTHSTEP"
        a.inputs["From Min"].default_value = lo - soft
        a.inputs["From Max"].default_value = lo + soft
        L.new(x, a.inputs["Value"])
        b = N.new("ShaderNodeMapRange")
        b.interpolation_type = "SMOOTHSTEP"
        b.inputs["From Min"].default_value = hi + soft
        b.inputs["From Max"].default_value = hi - soft
        L.new(x, b.inputs["Value"])
        return math_node("MULTIPLY", a.outputs["Result"], b.outputs["Result"])

    strip = math_node("GREATER_THAN", attr["btype"], v1=0.72)   # office strip glazing
    wx = band(fu, 0.16, 0.84)
    wx = math_node("MAXIMUM", wx, strip)
    wy = band(fv, 0.28, 0.82)
    win = math_node("MULTIPLY", wx, wy)
    # walls only, no roofs, nothing below the first floor
    wall = math_node("LESS_THAN", math_node("ABSOLUTE", sep_n.outputs["Z"]), v1=0.5)
    win = math_node("MULTIPLY", win, wall)
    win = math_node("MULTIPLY", win, math_node("GREATER_THAN", v, v1=4.0))

    # per-window random: lit or not, colour pick, brightness
    comb = N.new("ShaderNodeCombineXYZ")
    L.new(iu, comb.inputs["X"])
    L.new(iv, comb.inputs["Y"])
    L.new(attr["bid"], comb.inputs["Z"])
    wn = N.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "4D"
    L.new(comb.outputs[0], wn.inputs["Vector"])
    wn.inputs["W"].default_value = 3.1
    lights = N.new("ShaderNodeValue")
    lights.name = "city_lights"
    lights.label = "city_lights"
    lights.outputs[0].default_value = 1.0
    thresh = math_node("MULTIPLY", attr["blit"], lights.outputs[0])
    lit = math_node("LESS_THAN", wn.outputs["Value"], thresh)
    wn2 = N.new("ShaderNodeTexWhiteNoise")
    wn2.noise_dimensions = "4D"
    L.new(comb.outputs[0], wn2.inputs["Vector"])
    wn2.inputs["W"].default_value = 7.7
    ramp = N.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (1.0, 0.62, 0.32, 1)
    els[1].position, els[1].color = 0.55, (1.0, 0.82, 0.55, 1)
    e = els.new(0.78)
    e.color = (0.85, 0.92, 1.0, 1)
    e = els.new(0.95)
    e.color = (0.7, 1.0, 0.85, 1)
    ramp.color_ramp.interpolation = "CONSTANT"
    L.new(wn2.outputs["Value"], ramp.inputs["Fac"])
    bright = math_node("ADD", math_node("MULTIPLY", wn2.outputs["Value"], v1=0.9), v1=0.5)
    k = math_node("MULTIPLY", math_node("MULTIPLY", win, lit), bright)
    strength = N.new("ShaderNodeValue")
    strength.name = "window_strength"
    strength.outputs[0].default_value = window_strength
    k = math_node("MULTIPLY", k, strength.outputs[0])
    L.new(ramp.outputs["Color"], p.inputs["Emission Color"])
    L.new(k, p.inputs["Emission Strength"])
    # glass reads a bit glossier than the wall
    rough = N.new("ShaderNodeMix")
    rough.data_type = "FLOAT"
    L.new(win, rough.inputs["Factor"])
    rough.inputs["A"].default_value = 0.6
    rough.inputs["B"].default_value = 0.22
    L.new(rough.outputs["Result"], p.inputs["Roughness"])
    return mat


# ---------------------------------------------------------------- lights & traffic

def _point_cloud_cubes(name, pts, size, coll):
    verts, faces = [], []
    s = size / 2
    for (x, y, z) in pts:
        b = len(verts)
        verts += [(x - s, y - s, z - s), (x + s, y - s, z - s), (x + s, y + s, z - s), (x - s, y + s, z - s),
                  (x - s, y - s, z + s), (x + s, y - s, z + s), (x + s, y + s, z + s), (x - s, y + s, z + s)]
        faces += [(b, b + 1, b + 2, b + 3), (b + 4, b + 7, b + 6, b + 5), (b, b + 4, b + 5, b + 1),
                  (b + 1, b + 5, b + 6, b + 2), (b + 2, b + 6, b + 7, b + 3), (b + 3, b + 7, b + 4, b)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    return link(bpy.data.objects.new(name, me), coll)


def _strip_mesh(name, path_pts, width, z, coll, offset=0.0):
    """Thin quad strip following a polyline; UV.x = arc length (m)."""
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    pts = [Vector(p) for p in path_pts]
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + (b - a).length)
    left, right = [], []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        nrm = Vector((-t.y, t.x, 0))
        c = p + nrm * offset
        left.append(bm.verts.new((c.x + nrm.x * width / 2, c.y + nrm.y * width / 2, z)))
        right.append(bm.verts.new((c.x - nrm.x * width / 2, c.y - nrm.y * width / 2, z)))
    for i in range(len(pts) - 1):
        f = bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
        for loop, (uu, vv) in zip(f.loops, ((acc[i], 0), (acc[i], 1), (acc[i + 1], 1), (acc[i + 1], 0))):
            loop[uv].uv = (uu, vv)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me), coll)


def traffic_material(name, color, speed, period=9.0, duty=0.12, strength=14.0, seed=0.0):
    """Moving dashes along UV.x (car lights). speed in m/s; negative = reverse."""
    mat = bpy.data.materials.new(name)
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["UV"], sep.inputs[0])
    t = frame_value_node(nt, "time")
    mv = N.new("ShaderNodeMath")
    mv.operation = "MULTIPLY_ADD"
    mv.inputs[1].default_value = -speed
    L.new(t.outputs[0], mv.inputs[0])
    L.new(sep.outputs["X"], mv.inputs[2])
    # irregular spacing: two dash trains with different periods
    def train(p, d, ph):
        a = N.new("ShaderNodeMath")
        a.operation = "ADD"
        a.inputs[1].default_value = ph
        L.new(mv.outputs[0], a.inputs[0])
        b = N.new("ShaderNodeMath")
        b.operation = "DIVIDE"
        b.inputs[1].default_value = p
        L.new(a.outputs[0], b.inputs[0])
        c = N.new("ShaderNodeMath")
        c.operation = "FRACT"
        L.new(b.outputs[0], c.inputs[0])
        dd = N.new("ShaderNodeMath")
        dd.operation = "LESS_THAN"
        dd.inputs[1].default_value = d
        L.new(c.outputs[0], dd.inputs[0])
        return dd.outputs[0]
    m1 = train(period, duty, seed)
    m2 = train(period * 1.73, duty * 0.8, seed * 3.1 + 2.0)
    mx = N.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    L.new(m1, mx.inputs[0])
    L.new(m2, mx.inputs[1])
    st = N.new("ShaderNodeMath")
    st.operation = "MULTIPLY"
    st.inputs[1].default_value = strength
    L.new(mx.outputs[0], st.inputs[0])
    L.new(st.outputs[0], em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mix = N.new("ShaderNodeMixShader")
    L.new(mx.outputs[0], mix.inputs[0])
    L.new(tr.outputs[0], mix.inputs[1])
    L.new(em.outputs[0], mix.inputs[2])
    L.new(mix.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    return mat


def blink_material(name, color, period=1.6, strength=30.0):
    mat = bpy.data.materials.new(name)
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    t = frame_value_node(nt, "time")
    d = N.new("ShaderNodeMath")
    d.operation = "DIVIDE"
    d.inputs[1].default_value = period
    L.new(t.outputs[0], d.inputs[0])
    f = N.new("ShaderNodeMath")
    f.operation = "PINGPONG"
    f.inputs[1].default_value = 0.5
    L.new(d.outputs[0], f.inputs[0])
    s = N.new("ShaderNodeMath")
    s.operation = "MULTIPLY"
    s.inputs[1].default_value = strength * 2
    L.new(f.outputs[0], s.inputs[0])
    L.new(s.outputs[0], em.inputs["Strength"])
    L.new(em.outputs[0], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------- environment

def sky_world(sc, zenith=(0.0018, 0.0028, 0.008), horizon=(0.045, 0.028, 0.03), strength=1.0, stars=True):
    w = bpy.data.worlds.new("NightSky")
    sc.world = w
    nt = node_tree(w)
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputWorld")
    bg = N.new("ShaderNodeBackground")
    tc = N.new("ShaderNodeTexCoord")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = N.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.49, (*horizon, 1)
    els[1].position, els[1].color = 0.62, (*zenith, 1)
    L.new(sep.outputs["Z"], ramp.inputs["Fac"])
    col = ramp.outputs["Color"]
    if stars:
        vn = N.new("ShaderNodeTexVoronoi")
        vn.inputs["Scale"].default_value = 420.0
        mr = N.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.035
        mr.inputs["From Max"].default_value = 0.0
        mr.inputs["To Max"].default_value = 0.25
        L.new(tc.outputs["Generated"], vn.inputs["Vector"])
        L.new(vn.outputs["Distance"], mr.inputs["Value"])
        hz = N.new("ShaderNodeMapRange")
        hz.inputs["From Min"].default_value = 0.53
        hz.inputs["From Max"].default_value = 0.7
        L.new(sep.outputs["Z"], hz.inputs["Value"])
        mm = N.new("ShaderNodeMath")
        mm.operation = "MULTIPLY"
        L.new(mr.outputs["Result"], mm.inputs[0])
        L.new(hz.outputs["Result"], mm.inputs[1])
        add = N.new("ShaderNodeMix")
        add.data_type = "RGBA"
        add.blend_type = "ADD"
        add.inputs["Factor"].default_value = 1.0
        L.new(col, add.inputs["A"])
        cc = N.new("ShaderNodeCombineColor")
        L.new(mm.outputs[0], cc.inputs[0])
        L.new(mm.outputs[0], cc.inputs[1])
        L.new(mm.outputs[0], cc.inputs[2])
        L.new(cc.outputs[0], add.inputs["B"])
        col = add.outputs["Result"]
    L.new(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    L.new(bg.outputs[0], out.inputs["Surface"])
    return w


def water_material():
    mat = bpy.data.materials.new("Bay")
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    p = N.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (0.004, 0.006, 0.01, 1)
    p.inputs["Roughness"].default_value = 0.06
    p.inputs["Specular IOR Level"].default_value = 0.7
    tex = N.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 0.08
    tex.inputs["Detail"].default_value = 8.0
    t = frame_value_node(nt, "time", scale=0.04 / 24)
    tex.noise_dimensions = "4D"
    L.new(t.outputs[0], tex.inputs["W"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    L.new(tex.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], p.inputs["Normal"])
    return mat


def _annulus(name, R_in, R_out, h, seg, coll):
    """A vertical ring wall (drum) between radii R_in and R_out, height h."""
    bm = bmesh.new()
    rings = []
    for (r, z) in ((R_out, 0), (R_out, h), (R_in, h), (R_in, 0)):
        rings.append([bm.verts.new((r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg), z))
                      for i in range(seg)])
    for k in range(4):
        a, b = rings[k], rings[(k + 1) % 4]
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((a[i], a[j], b[j], b[i]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me), coll)


def reactor_facility(col, pos=REACTOR_POS, glow=(0.15, 0.6, 1.0), strength=10.0, seed=5):
    """A drum-shaped fusion hall on the far shore: ring wall, a thin band of blue
    light along its rim, blue light spilling up from inside, plant blocks and a stack."""
    rnd = random.Random(seed)
    wall_mat = mat_principled("FacilityWall", (0.06, 0.065, 0.07), rough=0.55, metal=0.3)
    drum = _annulus("FacilityDrum", REACTOR_R - 14.0, REACTOR_R, 46.0, 192, col)
    drum.location = pos
    assign(drum, wall_mat)
    band = add_prim("torus", "FacilityBand", col, R=REACTOR_R + 0.6, r=1.1, su=256, sv=8, smooth=True)
    band.location = pos + Vector((0, 0, 44.0))
    assign(band, mat_emission("FacilityGlow", glow, strength))
    band2 = add_prim("torus", "FacilityBandLow", col, R=REACTOR_R + 0.6, r=0.5, su=256, sv=8, smooth=True)
    band2.location = pos + Vector((0, 0, 18.0))
    assign(band2, mat_emission("FacilityGlowLow", glow, strength * 0.5))
    # light pouring up out of the open drum, caught by the haze
    floor = add_prim("cylinder", "FacilityCore", col, r=REACTOR_R - 14.0, depth=2.0, seg=96)
    floor.location = pos + Vector((0, 0, 30.0))
    assign(floor, mat_emission("FacilityCoreGlow", glow, strength * 0.8))
    up = bpy.data.lights.new("FacilityUp", "SPOT")
    up.color = glow
    up.energy = 4.0e7
    up.spot_size = math.radians(70)
    up.spot_blend = 1.0
    up.shadow_soft_size = 40
    uo = link(bpy.data.objects.new("FacilityUp", up), col)
    uo.location = pos + Vector((0, 0, 32.0))
    uo.rotation_euler = (0, 0, 0)  # spot points down -Z by default; flip it up
    uo.rotation_euler = (math.pi, 0, 0)
    # plant blocks with small white work lights
    blk = mat_principled("PlantBlock", (0.04, 0.042, 0.045), rough=0.6)
    work = mat_emission("WorkLight", (1.0, 0.92, 0.8), 18.0)
    for k in range(26):
        a = rnd.uniform(0, 2 * math.pi)
        rr = REACTOR_R + rnd.uniform(25, 140)
        b = add_prim("cube", f"Plant{k}", col)
        sx, sy, sz = rnd.uniform(20, 60), rnd.uniform(15, 40), rnd.uniform(8, 30)
        b.scale = (sx, sy, sz)
        b.location = pos + Vector((rr * math.cos(a), rr * math.sin(a), sz / 2))
        b.rotation_euler = (0, 0, a)
        assign(b, blk)
        for q in range(rnd.randint(1, 3)):
            l = add_prim("cube", f"Work{k}_{q}", col)
            l.scale = (1.2, 1.2, 1.2)
            l.location = b.location + Vector((rnd.uniform(-sx, sx) * 0.4, rnd.uniform(-sy, sy) * 0.4, sz / 2 + 1))
            assign(l, work)
    stack = add_prim("cylinder", "Stack", col, r=7.0, r2=5.0, depth=150.0, seg=24)
    stack.location = pos + Vector((REACTOR_R + 95.0, 60.0, 75.0))
    assign(stack, mat_principled("StackMat", (0.25, 0.25, 0.26), rough=0.6))
    red = blink_material("AviationRed", (1.0, 0.05, 0.02), period=1.6, strength=40.0)
    for z in (60.0, 110.0, 151.0):
        b = add_prim("sphere", f"StackLight{z}", col, r=1.6, seg=12, rings=6)
        b.location = pos + Vector((REACTOR_R + 95.0, 60.0 - 6.0, z))
        assign(b, red)
    return drum


def _east_district(seed, keep_out):
    """Low-rise blocks east of the city's last column (x 1504 to 2444), so the view toward her tower has a city
    behind it instead of an empty field. Same parcels and heights as citygen._buildings (they fall off with the
    distance from downtown: 12 to 40 m out here), its own seed so the rest of the city is untouched. Nothing here
    is in the view from her window (south-west): x >= 1504 lies east of that view's edge."""
    rnd = np.random.default_rng(seed)
    out = []
    pitch = BLOCK + STREET
    for bx in range(16, 27):
        for by in range(-3, 31):
            cx, cy = bx * pitch, by * pitch - 120.0
            if cy < -230:
                continue
            k = rnd.integers(1, 5)
            parcels = [(cx, cy, BLOCK, BLOCK)]
            for _ in range(k - 1):
                x, y, w, h = parcels.pop(rnd.integers(len(parcels)))
                if w > h:
                    sp = rnd.uniform(0.35, 0.65) * w
                    parcels += [(x - w / 2 + sp / 2, y, sp, h), (x + sp / 2, y, w - sp, h)]
                else:
                    sp = rnd.uniform(0.35, 0.65) * h
                    parcels += [(x, y - h / 2 + sp / 2, w, sp), (x, y + sp / 2, w, h - sp)]
            for (x, y, w, h) in parcels:
                inset = rnd.uniform(2.0, 6.0)
                w2, h2 = max(6.0, w - 2 * inset), max(6.0, h - 2 * inset)
                d = math.hypot(x + 60.0, y - 420.0)
                hgt = 12 + 190 * math.exp(-d / 520.0) * rnd.lognormal(0, 0.45) + rnd.uniform(0, 18)
                if any(math.hypot(x - qx, y - qy) < rq for qx, qy, rq in keep_out):
                    continue
                out.append((x, y, w2, h2, hgt))
    return out


def her_block(col, rng):
    """Her tower at the city's east edge, where the room's window plate was rendered from (flight.WIN_C), a few lower
    buildings behind it and a low-rise district round it (_east_district). The tower's south-west and south-east faces
    carry floor slabs and mullions with a grid of windows the size of hers (2.9 x 1.65 m, 3.6 m apart, 3.2 m floors),
    lit ones with a sash bar and some with curtains or blinds. Hers is left bare: the compositor shows her room through
    its outline (flight.WINDOW_CORNERS)."""
    import flight as F
    T, N, Z = F.T, F.N, Vector((0, 0, 1))
    c = F.WIN_C
    t0, t1, depth, top = -13.4, 19.6, 26.0, 186.0       # along the face (T), into the tower (-N), height
    floor0 = c.z - 1.375                                 # her room's floor
    # the faint cool glow of the city's sky on the walls and on the concrete edges of each floor: unlit, the last
    # seconds before her window rendered pure black round it, and the room floated in a void
    wall = mat_principled("TowerWall", (0.03, 0.032, 0.04), rough=0.6, spec=0.35, emission=(0.42, 0.46, 0.6),
                          emission_strength=0.012)
    concrete = mat_principled("TowerSlab", (0.11, 0.11, 0.12), rough=0.7, spec=0.3, emission=(0.55, 0.57, 0.65),
                              emission_strength=0.035)

    def box(name, center, ax_u, ax_v, su, sv, sz, mat, z0):
        """A box with its sides along ax_u (length su) and ax_v (sv), height sz, base at z0."""
        bm = bmesh.new()
        pts = []
        for zz in (z0, z0 + sz):
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                v = Vector((center.x, center.y, 0.0)) + ax_u * (du * su / 2) + ax_v * (dv * sv / 2)
                pts.append(bm.verts.new((v.x, v.y, zz)))
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            bm.faces.new([pts[i] for i in f])
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        ob = link(bpy.data.objects.new(name, me), col)
        assign(ob, mat)
        return ob

    box("HerTower", c + T * ((t0 + t1) / 2) - N * (depth / 2), T, N, t1 - t0, depth, top, wall, 0.0)
    # floor slabs: a concrete edge at every floor on the two faces seen from the bay
    for j in range(-46, 12):
        z = floor0 + 3.2 * j
        if not 3.0 < z < top - 3.0:
            continue
        box(f"SlabSW{j}", c + T * ((t0 + t1) / 2) + N * 0.18, T, N, t1 - t0 + 0.7, 0.36, 0.26, concrete, z - 0.26)
        box(f"SlabSE{j}", c + T * (t0 - 0.18) - N * (depth / 2), T, N, 0.36, depth + 0.7, 0.26, concrete, z - 0.26)
    # mullions between the windows (clear of hers, which spans -1.45 .. 1.45 along the face)
    for k in range(-4, 6):
        box(f"MullSW{k}", c + T * (3.6 * k + 1.8) + N * 0.06, T, N, 0.14, 0.12, top - 4.0, concrete, 2.0)
    for k in range(0, 8):
        box(f"MullSE{k}", c + T * (t0 - 0.06) - N * (3.6 * k + 1.8), T, N, 0.12, 0.14, top - 4.0, concrete, 2.0)
    # windows: quads 2 cm proud of the faces, lit or dark per window. None over hers: the room shows through the
    # outline of the opening on the face itself, and a quad in front of it (2 cm nearer the camera, so a little larger)
    # left its lit edge round the room as a white frame
    verts, faces, lit, hue = [], [], [], []
    rows = [c.z + 3.2 * j for j in range(-45, 12) if 6.0 < c.z + 3.2 * j < top - 4.0]

    def quad(center, along, w=2.9, h=1.65):
        b0 = len(verts)
        for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            v = center + along * (du * w / 2) + Z * (dv * h / 2)
            verts.append((v.x, v.y, v.z))
        faces.append((b0, b0 + 1, b0 + 2, b0 + 3))

    for z in rows:
        for k in range(-3, 6):
            if k == 0 and abs(z - c.z) < 0.1:
                continue
            quad(c + T * (3.6 * k) + N * 0.02 + Z * (z - c.z), T)
            # (from dim to bright: in the print every lit window had come out the same paper white)
            lit.append(float(rng.random() < 0.46) * rng.uniform(0.2, 1.0))
            hue.append(rng.random())
        for k in range(0, 7):                               # the south-east face (toward -T)
            quad(c + T * (t0 - 0.02) - N * (3.6 * k), -N)
            lit.append(float(rng.random() < 0.36) * rng.uniform(0.2, 1.0))
            hue.append(rng.random())
    me = bpy.data.meshes.new("HerTowerWindows")
    me.from_pydata(verts, [], faces)
    kind = np.random.default_rng(41).random(len(faces))    # what hangs in each window (its own generator: the rest
    for nm, arr in (("wlit", lit), ("whue", hue), ("wkind", kind)):     # of the city keeps its random sequence)
        at = me.attributes.new(nm, "FLOAT", "FACE")
        at.data.foreach_set("value", list(arr))
    uv = me.uv_layers.new(name="UVMap")                     # 0..1 across each window, for the sash and curtains
    uv.data.foreach_set("uv", [x for _ in faces for corner in ((0, 0), (1, 0), (1, 1), (0, 1)) for x in corner])
    me.update()
    win = link(bpy.data.objects.new("HerTowerWindows", me), col)
    m = bpy.data.materials.new("TowerWindows")
    nt = node_tree(m)
    Nn, L = nt.nodes, nt.links
    pr = Nn.get("Principled BSDF")
    pr.inputs["Base Color"].default_value = (0.012, 0.014, 0.02, 1)
    pr.inputs["Roughness"].default_value = 0.15
    al = Nn.new("ShaderNodeAttribute")
    al.attribute_type, al.attribute_name = "GEOMETRY", "wlit"
    ah = Nn.new("ShaderNodeAttribute")
    ah.attribute_type, ah.attribute_name = "GEOMETRY", "whue"
    ramp = Nn.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (1.0, 0.62, 0.32, 1)
    els[1].position, els[1].color = 0.55, (1.0, 0.82, 0.55, 1)
    e = els.new(0.8)
    e.color = (0.85, 0.92, 1.0, 1)
    ramp.color_ramp.interpolation = "CONSTANT"
    L.new(ah.outputs["Fac"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], pr.inputs["Emission Color"])
    mul = Nn.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    L.new(al.outputs["Fac"], mul.inputs[0])
    mul.inputs[1].default_value = 2.6                       # up close the city's 4.0 bloomed into glowing blocks

    def op(kind_, a, b=None, c3=None):
        n = Nn.new("ShaderNodeMath")
        n.operation = kind_
        for i, x in enumerate((a, b, c3)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            elif x is not None:
                L.new(x, n.inputs[i])
        return n.outputs[0]

    # up close the lit windows were blank glowing blocks: each gets a dark frame round it and the sash bar down its
    # middle, a ceiling light that falls off toward the sill, and by its wkind a curtain drawn part way across from one
    # side (35%) or blinds (17%)
    ak = Nn.new("ShaderNodeAttribute")
    ak.attribute_type, ak.attribute_name = "GEOMETRY", "wkind"
    sep = Nn.new("ShaderNodeSeparateXYZ")
    L.new(Nn.new("ShaderNodeTexCoord").outputs["UV"], sep.inputs[0])
    u, v, kd = sep.outputs[0], sep.outputs[1], ak.outputs["Fac"]
    f_bar = op("MULTIPLY_ADD", op("LESS_THAN", op("ABSOLUTE", op("SUBTRACT", u, 0.5)), 0.012), -0.85, 1.0)
    u_side = op("MULTIPLY_ADD", op("LESS_THAN", kd, 0.17), op("MULTIPLY_ADD", u, -2.0, 1.0), u)
    edge = op("MULTIPLY_ADD", op("FRACT", op("MULTIPLY", kd, 7.3)), 0.38, 0.58)
    f_cur = op("MULTIPLY_ADD", op("MULTIPLY", op("LESS_THAN", kd, 0.35), op("GREATER_THAN", u_side, edge)), -0.72, 1.0)
    blinds = op("MULTIPLY", op("GREATER_THAN", kd, 0.35), op("LESS_THAN", kd, 0.52))
    slats = op("GREATER_THAN", op("SINE", op("MULTIPLY", v, 56.5)), 0.25)
    f_bl = op("MULTIPLY_ADD", op("MULTIPLY", blinds, slats), -0.6, 1.0)
    frame = op("MAXIMUM", op("GREATER_THAN", op("ABSOLUTE", op("SUBTRACT", u, 0.5)), 0.465),
               op("GREATER_THAN", op("ABSOLUTE", op("SUBTRACT", v, 0.5)), 0.43))
    f_bar = op("MULTIPLY", f_bar, op("MULTIPLY_ADD", frame, -0.88, 1.0))
    pattern = op("MULTIPLY", op("MULTIPLY", f_bar, f_cur), op("MULTIPLY", f_bl, op("MULTIPLY_ADD", v, 0.35, 0.75)))
    L.new(op("MULTIPLY", mul.outputs[0], pattern), pr.inputs["Emission Strength"])
    assign(win, m)
    # red aviation lights on the roof corners, and a band of the reactor ring's cyan round the top floor: the flight
    # is aimed at this tower from two kilometres out, and dark among the city's lights it only became the destination
    # in the last seconds
    red = blink_material("TowerRed", (1.0, 0.04, 0.02), period=1.6, strength=45.0)
    corners = [c + T * a2 - N * b2 for a2, b2 in ((t0, 0.0), (t1, 0.0), (t1, depth), (t0, depth))]
    assign(_point_cloud_cubes("TowerRoofLights", [(v.x, v.y, top + 1.2) for v in corners], 2.2, col), red)
    crown = mat_principled("TowerCrown", (0.05, 0.06, 0.07), rough=0.5, emission=(0.45, 0.85, 1.0),
                           emission_strength=4.0)
    for nm, ctr, au, av, su, sv in (("CrownSW", c + T * ((t0 + t1) / 2) + N * 0.12, T, N, t1 - t0 + 0.24, 0.24),
                                    ("CrownSE", c + T * (t0 - 0.12) - N * (depth / 2), T, N, 0.24, depth + 0.24),
                                    ("CrownNE", c + T * (t1 + 0.12) - N * (depth / 2), T, N, 0.24, depth + 0.24),
                                    ("CrownNW", c + T * ((t0 + t1) / 2) - N * (depth + 0.12), T, N, t1 - t0 + 0.24, 0.24)):
        box(nm, ctr, au, av, su, sv, 2.4, crown, top - 4.4)
    # lower buildings behind it (north-east) and the low-rise district round it, in the city's own facade
    behind = []
    for a2, b2, w, d, h in ((-38.0, 34.0, 30.0, 40.0, 58.0), (34.0, 48.0, 40.0, 30.0, 40.0),
                            (-6.0, 74.0, 52.0, 38.0, 74.0), (62.0, 14.0, 30.0, 30.0, 27.0),
                            (-70.0, 80.0, 36.0, 44.0, 46.0), (24.0, 110.0, 44.0, 34.0, 33.0)):
        v = c + T * a2 - N * b2
        behind.append((v.x, v.y, w, d, h))
    tower_xy = c + T * ((t0 + t1) / 2) - N * (depth / 2)
    east = _east_district(29, [(tower_xy.x, tower_xy.y, 70.0)] + [(x, y, 34.0) for x, y, _, _, _ in behind])
    city = _box_mesh("HerBlock", behind + east, rng, col)
    assign(city, bpy.data.materials["Facade"])
    # street lamps through the new district
    pitch = BLOCK + STREET
    lamps = []
    for bx in range(17, 27):
        for by in range(-2, 31):
            x, y = bx * pitch - pitch / 2, by * pitch - 120.0
            if y < -230 or rng.random() > 0.85:
                continue
            lamps.append((x + pitch / 2 + rng.uniform(-4, 4), y + rng.uniform(-40, 40), 7.0))
            lamps.append((x + rng.uniform(-30, 30), y + pitch / 2, 7.0))
    assign(_point_cloud_cubes("EastLamps", lamps, 1.4, col), bpy.data.materials["Sodium"])
    return win


def build(sc, seed=11, lights=1.0, facility=True, window_strength=4.0, her_tower=False):
    col = collection("City")
    rng = np.random.default_rng(seed)
    boxes = _buildings(seed)
    city = _box_mesh("Buildings", boxes, rng, col)
    fm = facade_material(window_strength=window_strength)
    fm.node_tree.nodes["city_lights"].outputs[0].default_value = lights
    assign(city, fm)

    ground = add_prim("plane", "Ground", col)
    ground.scale = (3400, 2000, 1)
    ground.location = (0, 1000 - 240, 0)
    assign(ground, mat_principled("Asphalt", (0.012, 0.012, 0.014), rough=0.35, spec=0.5))
    sea = add_prim("plane", "Sea", col)
    sea.scale = (8000, 4000, 1)
    sea.location = (0, -240 - 2000, -1.0)
    assign(sea, water_material())

    # street lamps along the grid
    pitch = BLOCK + STREET
    lamps = []
    for bx in range(-16, 17):
        for by in range(-2, 33):
            if rng.random() < 0.85:
                x = bx * pitch + pitch / 2
                y = by * pitch - 120.0
                if y < -230:
                    continue
                lamps.append((x + rng.uniform(-4, 4), y + rng.uniform(-40, 40), 7.0))
                lamps.append((x - pitch / 2 + rng.uniform(-30, 30), y + pitch / 2, 7.0))
    lamp_ob = _point_cloud_cubes("StreetLamps", lamps, 1.4, col)
    assign(lamp_ob, mat_emission("Sodium", (1.0, 0.45, 0.12), 26.0))

    # elevated highway with traffic in both directions
    path = _highway_path(seed)
    deck = _strip_mesh("HighwayDeck", path, 22.0, 24.0, col)
    assign(deck, mat_principled("Deck", (0.03, 0.03, 0.033), rough=0.5))
    hw_lamps = [(p[0], p[1], 31.0) for i, p in enumerate(path) if i % 2 == 0]
    hl = _point_cloud_cubes("HighwayLamps", hw_lamps, 1.2, col)
    assign(hl, mat_emission("HighwaySodium", (1.0, 0.5, 0.16), 30.0))
    for lane, (color, speed, off) in enumerate((((1.0, 0.92, 0.8), 28.0, 3.0), ((1.0, 0.92, 0.8), 31.0, 7.0),
                                                ((1.0, 0.04, 0.02), -27.0, -3.0), ((1.0, 0.04, 0.02), -30.0, -7.0))):
        s = _strip_mesh(f"Traffic{lane}", path, 0.9, 24.6, col, offset=off)
        assign(s, traffic_material(f"TrafficMat{lane}", color, speed, seed=lane * 1.7,
                                   strength=22.0 if color[1] > 0.5 else 16.0))
    # avenues at street level
    for k, by in enumerate((4, 9, 15, 22)):
        y = by * pitch - 120.0 + pitch / 2
        pts = [(x, y, 0) for x in np.linspace(-1500, 1500, 60)]
        for lane, (color, speed, off) in enumerate((((1.0, 0.92, 0.8), 14.0, 2.5),
                                                    ((1.0, 0.04, 0.02), -13.0, -2.5))):
            s = _strip_mesh(f"Ave{k}_{lane}", pts, 0.8, 0.6, col, offset=off)
            assign(s, traffic_material(f"AveMat{k}_{lane}", color, speed, period=13.0, duty=0.08,
                                       seed=k + lane, strength=18.0))

    # aviation lights on the tallest towers
    red = blink_material("RoofRed", (1.0, 0.04, 0.02), period=1.6, strength=30.0)
    tops = [(x, y, h + 1.5) for (x, y, w, d, h) in boxes if h > 95]
    if tops:
        tl = _point_cloud_cubes("RoofLights", tops, 1.8, col)
        assign(tl, red)

    if facility:
        reactor_facility(col)
    if her_tower:
        her_block(col, rng)
    return col


def test_view(sc, opts):
    from common import look_rotation, make_camera, setup_compositor
    sky_world(sc)
    build(sc, lights=float(opts.get("lights", 1.0)))
    setup_compositor(sc, bloom=0.55, bloom_threshold=0.8, streaks=0.12, dispersion=0.006,
                     mist_color=(0.03, 0.026, 0.04), mist_amount=0.85)
    sc.view_layers[0].use_pass_mist = True
    w = sc.world
    w.mist_settings.start = 250
    w.mist_settings.depth = 3200
    w.mist_settings.falloff = "QUADRATIC"
    cam = make_camera(sc, lens=float(opts.get("lens", 35)), clip=(1.0, 12000.0))
    view = opts.get("view", "window")
    if view == "window":
        pos = Vector((1500.0, 900.0, 170.0))
        tgt = Vector((300.0, -900.0, 0.0))
    elif view == "top":
        pos = Vector((0.0, 500.0, 2400.0))
        tgt = Vector((0.0, 500.0, 0.0))
    else:
        pos = Vector((-700.0, 250.0, 120.0))
        tgt = Vector((300.0, 80.0, 20.0))
    cam.location = pos
    cam.rotation_euler = look_rotation(pos, tgt)
    return cam


def plate_view(sc, opts):
    """High-res still of the city from Rin's window, used as the room's backdrop."""
    from common import look_rotation, make_camera, setup_compositor
    sky_world(sc)
    build(sc, lights=float(opts.get("lights", 1.0)))
    setup_compositor(sc, bloom=0.5, bloom_threshold=0.8, streaks=0.0, dispersion=0.0,
                     mist_color=(0.03, 0.026, 0.04), mist_amount=0.85)
    sc.view_layers[0].use_pass_mist = True
    w = sc.world
    w.mist_settings.start = 250
    w.mist_settings.depth = 3200
    w.mist_settings.falloff = "QUADRATIC"
    cam = make_camera(sc, lens=26.0, clip=(1.0, 12000.0))
    pos = Vector((1500.0, 900.0, 150.0))
    tgt = Vector((250.0, -900.0, 60.0))
    cam.location = pos
    cam.rotation_euler = look_rotation(pos, tgt)
    sc.render.resolution_x, sc.render.resolution_y = 2880, 1620
    sc.render.resolution_percentage = 100
    sc.eevee.taa_render_samples = 32
    sc.render.use_motion_blur = False
    return cam


def build_shot(sc, shot):
    from common import setup_compositor
    st = shot.get("setup", {})
    if st.get("sky") == "dawn":
        import scene_dusk
        scene_dusk.dawn_sky(sc)
    else:
        sky_world(sc)
    build(sc, lights=st.get("lights", 1.0), window_strength=st.get("window_strength", 4.0),
          facility=st.get("facility", True), her_tower=st.get("her_tower", False))
    comp = dict(bloom=0.55, bloom_threshold=0.8, streaks=0.12, dispersion=0.006,
                mist_color=(0.03, 0.026, 0.04), mist_amount=0.85)
    comp.update(st.get("comp", {}))
    setup_compositor(sc, **comp)
    sc.view_layers[0].use_pass_mist = True
    w = sc.world
    w.mist_settings.start, w.mist_settings.depth = st.get("mist", (250, 3200))
    w.mist_settings.falloff = "QUADRATIC"
    return {"facade": bpy.data.materials["Facade"]}


def animate(sc, objs, shot, f0, f1, cards=None, cam=None):
    from common import key_socket, key_light
    an = shot.get("anim", {})
    dur = shot["t1"] - shot["t0"]
    nt = objs["facade"].node_tree
    if "city_lights" in an:
        key_socket(nt.nodes["city_lights"].outputs[0], an["city_lights"], f0, dur)
    if "window_strength" in an:
        key_socket(nt.nodes["window_strength"].outputs[0], an["window_strength"], f0, dur)
    if "facility_core" in an:
        # the light inside the drum alone: dim while the ring above it stands for the title ring
        m = bpy.data.materials.get("FacilityCoreGlow")
        if m:
            em = m.node_tree.nodes.get("Emission")
            base = em.inputs["Strength"].default_value
            key_socket(em.inputs["Strength"], [(u, base * v) for u, v in an["facility_core"]], f0, dur)
    if "facility" in an:
        for nm in ("FacilityGlow", "FacilityGlowLow", "FacilityCoreGlow"):
            m = bpy.data.materials.get(nm)
            if m:
                em = m.node_tree.nodes.get("Emission")
                base = em.inputs["Strength"].default_value
                key_socket(em.inputs["Strength"], [(u, base * v) for u, v in an["facility"]], f0, dur)
        up = bpy.data.objects.get("FacilityUp")
        if up:
            key_light(up.data, [(u, 4.0e7 * v) for u, v in an["facility"]], f0, dur)
