"""Rin's room: a small Japanese apartment room on a high floor at night.

Layout (metres): x 0..3.6 (left->right), y 0..2.7 (door->window), z 0..2.4.
The window wall is y = 2.7 and looks out over the city plate. A ring
fluorescent lamp hangs from the ceiling centre: the first "ring" of the film.
`time_of_day`: "night" (city glow), "night_lamp" (ring lamp on), "dusk", "morning".
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector

from common import (ROOT, add_prim, assign, collection, frame_value_node, link, mat_emission,
                    mat_principled, node_tree)

W, D, H = 3.6, 2.7, 2.4
WIN_X0, WIN_X1, WIN_Z0, WIN_Z1 = 0.35, 3.25, 0.55, 2.2


def box(name, size, loc, mat, coll, bevel=0.0, seg=2):
    ob = add_prim("cube", name, coll)
    ob.scale = size
    ob.location = loc
    if bevel > 0:
        m = ob.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = seg
        m.limit_method = "ANGLE"
        ob.modifiers.new("WN", "WEIGHTED_NORMAL")
        ob.data.shade_smooth()
    assign(ob, mat)
    return ob


def wall_mat():
    m = mat_principled("Wallpaper", (0.78, 0.77, 0.74), rough=0.85)
    nt = node_tree(m)
    p = nt.nodes.get("Principled BSDF")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 180.0
    nz.inputs["Detail"].default_value = 3.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.06
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def floor_mat():
    m = bpy.data.materials.new("Flooring")
    nt = node_tree(m)
    N, L = nt.nodes, nt.links
    p = N.get("Principled BSDF")
    tc = N.new("ShaderNodeTexCoord")
    br = N.new("ShaderNodeTexBrick")
    br.offset = 0.37
    br.squash = 1.0
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 1.2
    br.inputs["Row Height"].default_value = 0.15
    br.inputs["Mortar Size"].default_value = 0.002
    br.inputs["Color1"].default_value = (0.32, 0.2, 0.12, 1)
    br.inputs["Color2"].default_value = (0.24, 0.15, 0.09, 1)
    br.inputs["Mortar"].default_value = (0.08, 0.05, 0.03, 1)
    L.new(tc.outputs["Object"], br.inputs["Vector"])
    wave = N.new("ShaderNodeTexWave")
    wave.inputs["Scale"].default_value = 6.0
    wave.inputs["Distortion"].default_value = 6.0
    L.new(tc.outputs["Object"], wave.inputs["Vector"])
    mix = N.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.25
    L.new(br.outputs["Color"], mix.inputs["A"])
    L.new(wave.outputs["Color"], mix.inputs["B"])
    L.new(mix.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.32
    return m


def cloth_mat(name, color, rough=0.9, sheen=0.4):
    m = mat_principled(name, color, rough=rough)
    p = node_tree(m).nodes.get("Principled BSDF")
    try:
        p.inputs["Sheen Weight"].default_value = sheen
    except KeyError:
        pass
    return m


def rumpled(name, size, loc, mat, coll, amp=0.02, seed=0, bev=0.04):
    """A soft box (duvet / mattress): bevelled, lightly subdivided, noise lumps."""
    ob = box(name, size, loc, mat, coll)
    b = ob.modifiers.new("Bevel", "BEVEL")
    b.width = bev
    b.segments = 4
    s = ob.modifiers.new("Sub", "SUBSURF")
    s.levels = s.render_levels = 2
    tex = bpy.data.textures.new(name + "_n", "CLOUDS")
    tex.noise_scale = 0.35
    d = ob.modifiers.new("Disp", "DISPLACE")
    d.texture = tex
    d.strength = amp
    d.texture_coords = "GLOBAL"
    ob.data.shade_smooth()
    return ob


# ---------------------------------------------------------------- the bed
# along the left wall, head at the window; the mattress top is where the cards sit
BED_X0, BED_X1, BED_Y0, BED_Y1 = 0.05, 1.05, 0.6, 2.6
MAT_X0, MAT_X1, MAT_Y0, MAT_Y1 = 0.07, 1.03, 0.62, 2.58
MAT_TOP = 0.38
PILLOW_C = (0.55, 2.33)


def _mesh_object(name, verts, faces, coll, mat, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = link(bpy.data.objects.new(name, me), coll)
    if smooth:
        me.shade_smooth()
    assign(ob, mat)
    return ob


def _drape(s, r=0.04):
    """Cloth carried over a rounded edge: (outward offset, drop) s metres past the edge."""
    q = math.pi * r / 2
    if s <= 0:
        return s, 0.0
    if s < q:
        a = s / r
        return r * math.sin(a), r * (1 - math.cos(a))
    return r, r + (s - q)


def _waves(seed, n=6, amp=0.007, lam=(0.25, 0.7)):
    rnd = random.Random(seed)
    ws = []
    for _ in range(n):
        th = rnd.uniform(0, math.pi)
        k = 2 * math.pi / rnd.uniform(*lam)
        ws.append((k * math.cos(th), k * math.sin(th), rnd.uniform(0, 6.28), amp * rnd.uniform(0.4, 1.0)))
    return lambda x, y: sum(a * math.sin(kx * x + ky * y + ph) for kx, ky, ph, a in ws) / math.sqrt(n / 2)


def duvet_layer(name, v0, v1, z0, coll, mat, seed=2, over=(0.04, 0.3, 0.26), nu=90, nv=80, thick=0.045, lip=0.0):
    """A quilt lying on the mattress between v0..v1 metres from the foot edge, its free edges
    carried over the mattress edge and hanging in soft folds (the wall side is tucked in).
    lip > 0: the edge at v0 lies on whatever is below (a folded-back top) and rises over `lip` metres."""
    ol, orr, of = over
    lump = _waves(seed)
    fold = _waves(seed + 11, n=4, amp=0.03, lam=(0.18, 0.4))
    u0, u1 = -ol, (MAT_X1 - MAT_X0) + orr
    va = v0 - (of if v0 <= 0 else 0.0)
    verts, faces = [], []
    for j in range(nv + 1):
        v = va + (v1 - va) * j / nv
        for i in range(nu + 1):
            u = u0 + (u1 - u0) * i / nu
            xf, yf = MAT_X0 + u, MAT_Y0 + v
            sx = max(xf - MAT_X1, MAT_X0 - xf, 0.0)
            sy = max(MAT_Y0 - yf, 0.0)
            dx, dzx = _drape(sx)
            dy, dzy = _drape(sy)
            x = MAT_X1 + dx if xf > MAT_X1 else (MAT_X0 - dx if xf < MAT_X0 else xf)
            y = MAT_Y0 - dy if yf < MAT_Y0 else yf
            drop = max(dzx, dzy)
            hang = min(1.0, max(0.0, (drop - 0.04) / 0.16))
            z = z0 + lump(xf, yf) * (1 - min(1.0, drop / 0.05)) - drop
            if lip > 0:
                e = min(1.0, max(0.0, (v - v0) / lip))
                z -= (thick + 0.006) * (1 - e * e * (3 - 2 * e))
            # hanging cloth falls in vertical folds
            if xf > MAT_X1:
                x += fold(0.0, yf) * hang
            if yf < MAT_Y0:
                y -= fold(xf, 0.0) * hang
            verts.append((x, y, z))
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            faces.append((a, a + 1, a + nu + 2, a + nu + 1))
    ob = _mesh_object(name, verts, faces, coll, mat)
    so = ob.modifiers.new("Thick", "SOLIDIFY")
    so.thickness = thick
    so.offset = 1.0
    so.use_even_offset = True
    sub = ob.modifiers.new("Sub", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    return ob


def pillow_mesh(name, center, a, b, c_top, c_bot, coll, mat, yaw=0.0, dent=None, n=56, m=36, p=3.0, q=0.55):
    """A plump pillow: top and bottom bulges meeting at a seam, thick in the middle and pinched at
    the corners. dent = (dx, dy, radius, depth) presses a hollow where a head lies."""
    def f(x, y):
        return max(0.0, 1 - abs(x / a) ** p) ** q * max(0.0, 1 - abs(y / b) ** p) ** q
    xs = [a * math.sin(math.pi * (i / n - 0.5)) for i in range(n + 1)]
    ys = [b * math.sin(math.pi * (j / m - 0.5)) for j in range(m + 1)]
    idx, verts = {}, []

    def key(side, i, j):
        return ("s", i, j) if i in (0, n) or j in (0, m) else (side, i, j)

    for side, cz in (("t", c_top), ("b", -c_bot)):
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                k = key(side, i, j)
                if k in idx:
                    continue
                z = cz * f(x, y)
                if side == "t" and dent and k[0] != "s":
                    ddx, ddy, dr, dd = dent
                    z -= dd * math.exp(-((x - ddx) ** 2 + (y - ddy) ** 2) / dr ** 2) * f(x, y) ** 0.3
                idx[k] = len(verts)
                verts.append((x, y, z))
    faces = []
    for side in ("t", "b"):
        for j in range(m):
            for i in range(n):
                quad = (idx[key(side, i, j)], idx[key(side, i + 1, j)], idx[key(side, i + 1, j + 1)],
                        idx[key(side, i, j + 1)])
                faces.append(quad if side == "t" else quad[::-1])
    ob = _mesh_object(name, verts, faces, coll, mat)
    ob.location = (center[0], center[1], MAT_TOP + c_bot * 0.6)
    ob.rotation_euler = (0, 0, math.radians(yaw))
    sub = ob.modifiers.new("Sub", "SUBSURF")
    sub.levels, sub.render_levels = 1, 1
    return ob


def wood_mat(name, axis, light=(0.42, 0.32, 0.24), dark=(0.3, 0.21, 0.14)):
    """Solid wood with its grain along `axis` ("X", "Y" or "Z"): noise stretched along the board into
    streaks of two tones of the same timber, with a faint matching relief."""
    m = mat_principled(name, light, rough=0.45)
    nt = node_tree(m)
    N, L = nt.nodes, nt.links
    p = N.get("Principled BSDF")
    geo = N.new("ShaderNodeNewGeometry")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = {"X": (1.2, 70, 70), "Y": (70, 1.2, 70), "Z": (70, 70, 1.2)}[axis]
    L.new(geo.outputs["Position"], mp.inputs["Vector"])
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 1.0
    nz.inputs["Detail"].default_value = 6.0
    nz.inputs["Distortion"].default_value = 1.2
    L.new(mp.outputs["Vector"], nz.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB")
    lo, hi = ramp.color_ramp.elements
    lo.position, hi.position = 0.38, 0.62
    lo.color, hi.color = (*dark, 1.0), (*light, 1.0)
    L.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], p.inputs["Base Color"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    L.new(nz.outputs["Fac"], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def bed_frame(coll):
    """A low bed in solid wood, built the way one is: four posts outside the mattress corners, rails
    between them that the mattress sits down into, and at the head two taller posts carrying a top rail
    over a row of slats (under the window sill). Returns the parts the bedding collides with."""
    wx, wy, wz = wood_mat("BedWoodX", "X"), wood_mat("BedWoodY", "Y"), wood_mat("BedWoodZ", "Z")
    t, p = 0.022, 0.045                      # rail thickness, post section
    rz0, rz1 = 0.1, 0.25                     # rails: bottom and top (the mattress sits 13 cm proud of them)
    top = 0.585                              # headboard top, just under the sill
    xl, xr = MAT_X0 - p / 2, MAT_X1 + p / 2  # post centres, outside the mattress
    yf, yh = MAT_Y0 - p / 2, MAT_Y1 + p / 2
    parts = []
    for k, (x, y, zt) in enumerate(((xl, yf, rz1 + 0.02), (xr, yf, rz1 + 0.02), (xl, yh, top), (xr, yh, top))):
        parts.append(box(f"BedPost{k}", (p, p, zt), (x, y, zt / 2), wz, coll, bevel=0.005, seg=2))
    rh, rc = rz1 - rz0, (rz0 + rz1) / 2
    for nm, size, loc, mat in (
            ("BedRailL", (t, MAT_Y1 - MAT_Y0, rh), (MAT_X0 - t / 2, (MAT_Y0 + MAT_Y1) / 2, rc), wy),
            ("BedRailR", (t, MAT_Y1 - MAT_Y0, rh), (MAT_X1 + t / 2, (MAT_Y0 + MAT_Y1) / 2, rc), wy),
            ("BedRailFoot", (MAT_X1 - MAT_X0, t, rh), ((MAT_X0 + MAT_X1) / 2, MAT_Y0 - t / 2, rc), wx),
            ("BedRailHead", (MAT_X1 - MAT_X0, t, rh), ((MAT_X0 + MAT_X1) / 2, MAT_Y1 + t / 2, rc), wx)):
        parts.append(box(nm, size, loc, mat, coll, bevel=0.003, seg=2))
    # the slats the mattress rests on (only seen from very low)
    parts.append(box("BedDeck", (MAT_X1 - MAT_X0, MAT_Y1 - MAT_Y0, 0.02),
                     ((MAT_X0 + MAT_X1) / 2, (MAT_Y0 + MAT_Y1) / 2, MAT_TOP - 0.19), wx, coll))
    # headboard: a top rail with a slight overhang over seven slats
    parts.append(box("HeadRail", (xr - xl + p + 0.02, p + 0.012, 0.04), ((xl + xr) / 2, yh, top - 0.02), wx, coll,
                     bevel=0.006, seg=2))
    n, sw = 7, 0.06
    gap = (MAT_X1 - MAT_X0 - n * sw) / (n + 1)
    for k in range(n):
        x = MAT_X0 + gap + sw / 2 + k * (sw + gap)
        parts.append(box(f"HeadSlat{k}", (sw, 0.016, top - 0.04 - rz1), (x, yh, (rz1 + top - 0.04) / 2), wz, coll,
                         bevel=0.003, seg=2))
    return parts


def mattress_dent(ob, sit, depth=0.025, along=0.32, across=0.2):
    """Where she sits the mattress gives: a shallow hollow under her seat and feet. sit = (x, y, ax, ay):
    the middle of it and the horizontal direction her drawing spans."""
    x0, y0, ax, ay = sit
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=30, use_grid_fill=True)
    (sx, sy, sz), (cx, cy, _cz) = ob.scale, ob.location
    for v in bm.verts:
        if v.co.z > 0.499:
            dx, dy = cx + v.co.x * sx - x0, cy + v.co.y * sy - y0
            a, c = dx * ax + dy * ay, -dx * ay + dy * ax
            v.co.z -= depth / sz * math.exp(-(a / along) ** 2 - (c / across) ** 2)
    bm.to_mesh(ob.data)
    bm.free()
    ob["dent"] = [round(float(v), 4) for v in (*sit, depth, along, across)]


def bed_set(coll, pillow_dent=None, quilt=None, sit=None):
    """Low wooden bed (bed_frame) with its head under the window sill, a thick mattress in a fitted
    sheet, a pillow at the head end and a cloth-simulated quilt (bedding.py): spread over the bed below
    the pillow (the default; she sits on it), or tucked over her as she lies. sit: where she sits on it
    (see mattress_dent); the quilt settles into the hollow."""
    import bedding
    frame = bed_frame(coll)
    sheet = bedding.add_wrinkles(cloth_mat("Sheet", (0.8, 0.83, 0.88)), scale=4.0, strength=0.1)
    mat_ob = box("Mattress", (MAT_X1 - MAT_X0, MAT_Y1 - MAT_Y0, 0.18), ((MAT_X0 + MAT_X1) / 2, (MAT_Y0 + MAT_Y1) / 2,
                                                                        MAT_TOP - 0.09), sheet, coll)
    if sit:
        mattress_dent(mat_ob, sit)
    b = mat_ob.modifiers.new("Bevel", "BEVEL")
    b.width, b.segments = 0.035, 4
    s = mat_ob.modifiers.new("Sub", "SUBSURF")
    s.levels = s.render_levels = 1
    mat_ob.data.shade_smooth()
    case = bedding.add_wrinkles(cloth_mat("Pillowcase", (0.93, 0.93, 0.9)), scale=9.0, strength=0.05)
    # an inflated, sewn pillowcase (bedding.simulate_pillow); a head pressed into it where she lies
    press = None
    if pillow_dent:
        press = (PILLOW_C[0] + pillow_dent[0], PILLOW_C[1] + pillow_dent[1])
    # nobody's head on it: plumped up (more air in it), so it reads as a soft pillow, not a slab
    pillow = bedding.simulate_pillow(coll, mat_ob, PILLOW_C, MAT_TOP, head=press, pressure=6.5 if press else 11.0)
    sp = pillow.modifiers.new("Sub", "SUBSURF")
    sp.levels = sp.render_levels = 2
    pillow.data.shade_smooth()
    assign(pillow, case)
    q = dict(mode="spread", edge=1.95)
    q.update(quilt or {})
    if q["mode"] == "none":
        return
    ob = bedding.simulate_quilt(coll, [mat_ob, pillow, *frame], (MAT_X0, MAT_X1, MAT_Y0, MAT_Y1, MAT_TOP),
                                q["edge"], field=q.get("field"))
    bedding.dress_quilt(ob, bedding.gingham_mat("QuiltCover"))


def _quilting(mat):
    """Stitched channels: a fine bump along the quilt's sewn lines."""
    nt = node_tree(mat)
    p = nt.nodes.get("Principled BSDF")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 2.2
    wave.inputs["Distortion"].default_value = 0.6
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeMath")
    ramp.operation = "POWER"
    ramp.inputs[1].default_value = 6.0
    nt.links.new(wave.outputs["Fac"], ramp.inputs[0])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.2
    bump.invert = True
    nt.links.new(ramp.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])


def curtain(name, x0, x1, z0, z1, y, mat, coll, folds=9, depth=0.05, wind=0.0, seed=0):
    """Pleated curtain; `wind` animates a travelling billow (spring breeze)."""
    nx, nz = 120, 60
    bm = bmesh.new()
    vs = []
    for j in range(nz + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / nz
            vs.append(bm.verts.new((x0 + (x1 - x0) * u, y, z0 + (z1 - z0) * v)))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            bm.faces.new((vs[a], vs[a + 1], vs[a + nx + 2], vs[a + nx + 1]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    ob = link(bpy.data.objects.new(name, me), coll)
    # pleats + optional billow via a geometry-nodes free displacement: use shape of sine in shader-free way
    gn = ob.modifiers.new("Pleats", "NODES")
    gn.node_group = _curtain_nodes(name, x0, x1, z0, z1, folds, depth, wind)
    assign(ob, mat)
    return ob


def _curtain_nodes(name, x0, x1, z0, z1, folds, depth, wind):
    ng = bpy.data.node_groups.new(name + "_GN", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    gi = N.new("NodeGroupInput")
    go = N.new("NodeGroupOutput")
    pos = N.new("GeometryNodeInputPosition")
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(pos.outputs[0], sep.inputs[0])
    t = N.new("GeometryNodeInputSceneTime")

    def m(op, a, b=None, bv=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        L.new(a, n.inputs[0])
        if b is not None:
            L.new(b, n.inputs[1])
        elif bv is not None:
            n.inputs[1].default_value = bv
        return n.outputs[0]

    k = 2 * math.pi * folds / (x1 - x0)
    pleat = m("MULTIPLY", m("SINE", m("MULTIPLY", sep.outputs["X"], bv=k)), bv=depth)
    # billow: wave travelling across, stronger at the bottom hem
    hem = m("SUBTRACT", m("MULTIPLY", sep.outputs["Z"], bv=-1.0 / (z1 - z0)), bv=-z1 / (z1 - z0))
    ph = m("ADD", m("MULTIPLY", sep.outputs["X"], bv=2.2), m("MULTIPLY", t.outputs["Seconds"], bv=1.7))
    bil = m("MULTIPLY", m("MULTIPLY", m("SINE", ph), hem), bv=-0.22 * wind)
    bil2 = m("MULTIPLY", m("MULTIPLY", m("SINE", m("ADD", m("MULTIPLY", sep.outputs["X"], bv=5.1),
                                                      m("MULTIPLY", t.outputs["Seconds"], bv=2.9))), hem),
             bv=-0.06 * wind)
    dy = m("ADD", m("ADD", pleat, bil), bil2)
    comb = N.new("ShaderNodeCombineXYZ")
    L.new(dy, comb.inputs["Y"])
    sp = N.new("GeometryNodeSetPosition")
    L.new(gi.outputs[0], sp.inputs["Geometry"])
    L.new(comb.outputs[0], sp.inputs["Offset"])
    L.new(sp.outputs[0], go.inputs[0])
    return ng


LAMP_X, LAMP_Y = 0.6, 1.55   # hung above the bed so the lying-down POV sees a perfect ring
LAMP_ENERGY = 70.0


def ring_lamp(coll, on=True, strength=18.0, flicker=0.0):
    z = H - 0.12
    base = add_prim("cylinder", "LampBase", coll, r=0.27, depth=0.05, seg=64)
    base.location = (LAMP_X, LAMP_Y, H - 0.03)
    assign(base, mat_principled("LampBaseMat", (0.85, 0.85, 0.84), rough=0.4))
    tube = add_prim("torus", "RingTube", coll, R=0.2, r=0.016, su=128, sv=12, smooth=True)
    tube.location = (LAMP_X, LAMP_Y, z)
    tm = mat_emission("RingTubeMat", (0.86, 0.93, 1.0), strength if on else 0.0)
    if flicker > 0:
        nt = node_tree(tm)
        em = nt.nodes.get("Emission")
        t = frame_value_node(nt, "time")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.noise_dimensions = "1D"
        nz.inputs["Scale"].default_value = 9.0
        nt.links.new(t.outputs[0], nz.inputs["W"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.35
        mr.inputs["From Max"].default_value = 0.42
        mr.inputs["To Min"].default_value = strength * (1 - flicker)
        mr.inputs["To Max"].default_value = strength
        nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], em.inputs["Strength"])
    assign(tube, tm)
    shade = add_prim("cylinder", "LampShade", coll, r=0.29, r2=0.27, depth=0.08, seg=64, caps=True)
    shade.location = (LAMP_X, LAMP_Y, z - 0.02)
    sm = mat_principled("LampShadeMat", (0.95, 0.95, 0.95), rough=0.6, alpha=0.25)
    assign(shade, sm)
    shade.hide_render = True  # the bare ring reads better on camera; keep the mesh for later shots
    # hung right over the bed, the fitting would print a soft grey ring on the quilt in every light
    for ob in (base, tube, shade):
        ob.visible_shadow = False
    light = bpy.data.lights.new("RingLight", "AREA")
    light.shape = "DISK"
    light.size = 0.5
    light.color = (0.86, 0.93, 1.0)
    light.energy = LAMP_ENERGY if on else 0.0
    lo = link(bpy.data.objects.new("RingLight", light), coll)
    lo.location = (LAMP_X, LAMP_Y, z - 0.05)
    return tube, lo


def wall_clock(coll, loc=(W - 0.02, 1.0, 1.85), r=0.16):
    face = add_prim("cylinder", "ClockFace", coll, r=r, depth=0.025, seg=64)
    face.rotation_euler = (0, math.radians(90), 0)
    face.location = loc
    assign(face, mat_principled("ClockFaceMat", (0.9, 0.9, 0.88), rough=0.5))
    rim = add_prim("torus", "ClockRim", coll, R=r, r=0.012, su=96, sv=10, smooth=True)
    rim.rotation_euler = (0, math.radians(90), 0)
    rim.location = (loc[0] - 0.012, loc[1], loc[2])
    assign(rim, mat_principled("ClockRimMat", (0.05, 0.05, 0.05), rough=0.3))
    tick_m = mat_principled("ClockTickMat", (0.05, 0.05, 0.05), rough=0.4)
    for k in range(12):
        a = 2 * math.pi * k / 12
        tk = add_prim("cube", f"ClockTick{k}", coll)
        tk.scale = (0.004, 0.006 if k % 3 else 0.012, 0.028)
        tk.location = (loc[0] - 0.014, loc[1] + math.sin(a) * r * 0.82, loc[2] + math.cos(a) * r * 0.82)
        tk.rotation_euler = (-a, 0, 0)
        assign(tk, tick_m)
    hands = {}
    for nm, ln, wd in (("Hour", 0.08, 0.008), ("Minute", 0.12, 0.006), ("Second", 0.13, 0.002)):
        piv = link(bpy.data.objects.new("Clock" + nm + "Pivot", None), coll)
        piv.location = (loc[0] - 0.02, loc[1], loc[2])
        h = add_prim("cube", "Clock" + nm, coll)
        h.scale = (0.003, wd, ln)
        h.location = (0, 0, ln / 2 - 0.015)
        h.parent = piv
        assign(h, mat_principled(nm + "Mat", (0.8, 0.1, 0.05) if nm == "Second" else (0.03, 0.03, 0.03),
                                 rough=0.4))
        hands[nm] = piv
    return hands


def desk_props(coll, x=2.9, y=2.2):
    top = box("DeskTop", (0.9, 0.5, 0.03), (x, y, 0.7), mat_principled("DeskMat", (0.55, 0.42, 0.3), rough=0.45),
              coll, bevel=0.004)
    for dx in (-0.42, 0.42):
        for dy in (-0.22, 0.22):
            box("DeskLeg", (0.03, 0.03, 0.69), (x + dx, y + dy, 0.345),
                mat_principled("DeskLegMat", (0.08, 0.08, 0.085), rough=0.4, metal=0.6), coll)
    # digital clock: the display texture is written by the comp step (02:00 etc.)
    clk = box("DeskClock", (0.14, 0.05, 0.07), (x - 0.25, y + 0.1, 0.75),
              mat_principled("DeskClockMat", (0.02, 0.02, 0.02), rough=0.3), coll, bevel=0.006)
    disp = add_prim("plane", "DeskClockDisplay", coll)
    disp.scale = (0.11, 0.05, 1)
    disp.rotation_euler = (math.radians(90), 0, 0)
    disp.location = (x - 0.25, y + 0.074, 0.75)
    dm = mat_emission("DeskClockDisplayMat", (1.0, 0.25, 0.08), 3.0)
    assign(disp, dm)
    lighter = box("Lighter", (0.024, 0.012, 0.075), (x + 0.05, y - 0.05, 0.755),
                  mat_principled("LighterMat", (1.0, 0.75, 0.05), rough=0.15, alpha=0.75), coll, bevel=0.003)
    glass = add_prim("cylinder", "Glass", coll, r=0.035, r2=0.03, depth=0.11, seg=48)
    glass.location = (x + 0.25, y - 0.1, 0.77)
    gm = mat_principled("GlassMat", (0.9, 0.95, 1.0), rough=0.02, alpha=0.18)
    assign(glass, gm)
    return {"clock_display": disp, "lighter": lighter}


def crt_material(static=1.0, host=0.0):
    """CRT picture: animated static, scanlines, a rolling bar, and the talk-show host on air: Rin
    (assets/tv/rin_on_air.png, made by src/tools/make_tv_picture.py) with a little snow over her."""
    m = bpy.data.materials.new("CRTScreenMat")
    nt = node_tree(m)
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    em = N.new("ShaderNodeEmission")
    tc = N.new("ShaderNodeTexCoord")
    t = frame_value_node(nt, "time")

    def mth(op, a=None, b=None, av=None, bv=None):
        n = N.new("ShaderNodeMath")
        n.operation = op
        if a is not None:
            L.new(a, n.inputs[0])
        elif av is not None:
            n.inputs[0].default_value = av
        if b is not None:
            L.new(b, n.inputs[1])
        elif bv is not None:
            n.inputs[1].default_value = bv
        return n.outputs[0]

    def vec(op, a, bv):
        n = N.new("ShaderNodeVectorMath")
        n.operation = op
        L.new(a, n.inputs[0])
        n.inputs[1].default_value = bv
        return n.outputs[0]

    # static: 4D white noise re-seeded every frame
    cell = N.new("ShaderNodeVectorMath")
    cell.operation = "FLOOR"
    L.new(vec("MULTIPLY", tc.outputs["UV"], (320.0, 240.0, 1.0)), cell.inputs[0])
    wn = N.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "4D"
    L.new(cell.outputs[0], wn.inputs["Vector"])
    L.new(mth("FLOOR", mth("MULTIPLY", t.outputs[0], bv=24.0)), wn.inputs["W"])
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["UV"], sep.inputs[0])
    # scanlines and a slow rolling bar
    scan = N.new("ShaderNodeMapRange")
    scan.inputs["From Min"].default_value = -1
    scan.inputs["To Min"].default_value = 0.65
    L.new(mth("SINE", mth("MULTIPLY", sep.outputs["Y"], bv=900.0)), scan.inputs["Value"])
    roll = mth("FRACT", mth("ADD", mth("MULTIPLY", t.outputs[0], bv=0.35), sep.outputs["Y"]))
    bar = N.new("ShaderNodeMapRange")
    bar.inputs["From Max"].default_value = 0.12
    bar.inputs["To Min"].default_value = 1.6
    bar.inputs["To Max"].default_value = 1.0
    L.new(roll, bar.inputs["Value"])
    # the host on air, revealed by the `host` value
    onair = N.new("ShaderNodeTexImage")
    onair.image = bpy.data.images.load(str(ROOT / "assets" / "tv" / "rin_on_air.png"), check_existing=True)
    L.new(tc.outputs["UV"], onair.inputs["Vector"])
    picture = onair.outputs["Color"]
    wave_png = ROOT / "assets" / "tv" / "rin_on_air_wave.png"
    if wave_png.exists():
        # her waving hand's other drawing, swapped in on the beat by the `wave` value (anim crt_wave)
        onair2 = N.new("ShaderNodeTexImage")
        onair2.image = bpy.data.images.load(str(wave_png), check_existing=True)
        L.new(tc.outputs["UV"], onair2.inputs["Vector"])
        wavev = N.new("ShaderNodeValue")
        wavev.name = "wave"
        wavev.outputs[0].default_value = 0.0
        swap = N.new("ShaderNodeMix")
        swap.data_type = "RGBA"
        L.new(wavev.outputs[0], swap.inputs["Factor"])
        L.new(onair.outputs["Color"], swap.inputs["A"])
        L.new(onair2.outputs["Color"], swap.inputs["B"])
        picture = swap.outputs["Result"]
    tint = N.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs["Factor"].default_value = 1.0
    L.new(picture, tint.inputs["A"])
    tint.inputs["B"].default_value = (0.82, 0.9, 1.0, 1)
    hostv = N.new("ShaderNodeValue")
    hostv.name = "host"
    hostv.outputs[0].default_value = host
    hostmask = mth("MULTIPLY", hostv.outputs[0], bv=0.88)
    statv = N.new("ShaderNodeValue")
    statv.name = "static"
    statv.outputs[0].default_value = static
    cc = N.new("ShaderNodeCombineColor")
    for k in range(3):
        L.new(wn.outputs["Value"], cc.inputs[k])
    pic = N.new("ShaderNodeMix")
    pic.data_type = "RGBA"
    L.new(statv.outputs[0], pic.inputs["Factor"])
    pic.inputs["A"].default_value = (0.55, 0.62, 0.8, 1)
    L.new(cc.outputs[0], pic.inputs["B"])
    show = N.new("ShaderNodeMix")
    show.data_type = "RGBA"
    L.new(hostmask, show.inputs["Factor"])
    L.new(pic.outputs["Result"], show.inputs["A"])
    L.new(tint.outputs["Result"], show.inputs["B"])
    L.new(show.outputs["Result"], em.inputs["Color"])
    L.new(mth("MULTIPLY", mth("MULTIPLY", scan.outputs["Result"], bar.outputs["Result"]), bv=1.0), em.inputs["Strength"])
    L.new(em.outputs[0], out.inputs["Surface"])
    return m


def crt_tv(coll, loc=(2.3, 0.3, 0.0)):
    body = box("CRT", (0.42, 0.4, 0.36), (loc[0], loc[1], loc[2] + 0.18 + 0.32),
               mat_principled("CRTMat", (0.035, 0.035, 0.04), rough=0.45), coll, bevel=0.02, seg=3)
    stand = box("TVStand", (0.6, 0.42, 0.32), (loc[0], loc[1], 0.16),
                mat_principled("StandMat", (0.15, 0.11, 0.08), rough=0.6), coll, bevel=0.005)
    scr = add_prim("plane", "CRTScreen", coll, xs=8, ys=8)
    scr.scale = (0.34, 0.27, 1)
    scr.rotation_euler = (math.radians(90), 0, math.radians(180))
    scr.location = (loc[0], loc[1] + 0.205, loc[2] + 0.5)
    assign(scr, crt_material())
    tl = bpy.data.lights.new("TVLight", "AREA")
    tl.size = 0.35
    tl.color = (0.75, 0.85, 1.0)
    tl.energy = 2.5
    to = link(bpy.data.objects.new("TVLight", tl), coll)
    to.location = (loc[0], loc[1] + 0.3, loc[2] + 0.5)
    to.rotation_euler = (math.radians(-90), 0, 0)
    return scr


def build(sc, time_of_day="night", lamp_on=None, city_plate=None, wind=0.0, seed=3, void=False, pillow_dent=None,
          quilt=None, sun=None, sit=None, rake=None, window_light=1.0):
    sun_opts = sun
    col = collection("Room")
    if void:
        return build_void(sc, col, city_plate, pillow_dent=pillow_dent, quilt=quilt, sit=sit)
    wm = wall_mat()
    # shell (floor, ceiling, walls; window wall has an opening)
    box("Floor", (W, D, 0.02), (W / 2, D / 2, -0.01), floor_mat(), col)
    box("Ceiling", (W, D, 0.02), (W / 2, D / 2, H + 0.01), mat_principled("CeilMat", (0.82, 0.82, 0.8), rough=0.9),
        col)
    box("WallL", (0.02, D, H), (-0.01, D / 2, H / 2), wm, col)
    box("WallR", (0.02, D, H), (W + 0.01, D / 2, H / 2), wm, col)
    box("WallB", (W, 0.02, H), (W / 2, -0.01, H / 2), wm, col)
    # window wall pieces around the opening
    box("WinWallBelow", (W, 0.12, WIN_Z0), (W / 2, D + 0.06, WIN_Z0 / 2), wm, col)
    box("WinWallAbove", (W, 0.12, H - WIN_Z1), (W / 2, D + 0.06, (H + WIN_Z1) / 2), wm, col)
    box("WinWallL", (WIN_X0, 0.12, WIN_Z1 - WIN_Z0), (WIN_X0 / 2, D + 0.06, (WIN_Z0 + WIN_Z1) / 2), wm, col)
    box("WinWallR", (W - WIN_X1, 0.12, WIN_Z1 - WIN_Z0), ((W + WIN_X1) / 2, D + 0.06, (WIN_Z0 + WIN_Z1) / 2),
        wm, col)
    skirting = mat_principled("Skirting", (0.25, 0.2, 0.16), rough=0.5)
    box("SkirtL", (0.012, D, 0.06), (0.006, D / 2, 0.03), skirting, col)
    box("SkirtR", (0.012, D, 0.06), (W - 0.006, D / 2, 0.03), skirting, col)
    # sliding window: aluminium frame and two glass panes
    alu = mat_principled("Alu", (0.55, 0.56, 0.58), rough=0.3, metal=0.9)
    fw = 0.035
    for nm, sz, lc in (("FrameTop", (WIN_X1 - WIN_X0, 0.07, fw), ((WIN_X0 + WIN_X1) / 2, D + 0.03, WIN_Z1 - fw / 2)),
                       ("FrameBot", (WIN_X1 - WIN_X0, 0.07, fw), ((WIN_X0 + WIN_X1) / 2, D + 0.03, WIN_Z0 + fw / 2)),
                       ("FrameL", (fw, 0.07, WIN_Z1 - WIN_Z0), (WIN_X0 + fw / 2, D + 0.03, (WIN_Z0 + WIN_Z1) / 2)),
                       ("FrameR", (fw, 0.07, WIN_Z1 - WIN_Z0), (WIN_X1 - fw / 2, D + 0.03, (WIN_Z0 + WIN_Z1) / 2)),
                       ("FrameMid", (fw, 0.07, WIN_Z1 - WIN_Z0), ((WIN_X0 + WIN_X1) / 2, D + 0.03,
                                                                  (WIN_Z0 + WIN_Z1) / 2))):
        box(nm, sz, lc, alu, col)
    glass = bpy.data.materials.new("WindowGlass")
    nt = node_tree(glass)
    nt.nodes.clear()
    go = nt.nodes.new("ShaderNodeOutputMaterial")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    gl = nt.nodes.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.03
    fr = nt.nodes.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.5
    fm = nt.nodes.new("ShaderNodeMath")
    fm.operation = "MULTIPLY_ADD"
    fm.inputs[1].default_value = 0.7
    fm.inputs[2].default_value = 0.05
    fm.name = "glass_reflect"
    nt.links.new(fr.outputs[0], fm.inputs[0])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fm.outputs[0], mx.inputs[0])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(gl.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], go.inputs["Surface"])
    glass.surface_render_method = "BLENDED"
    for k, x in enumerate((WIN_X0 + (WIN_X1 - WIN_X0) / 4, WIN_X0 + 3 * (WIN_X1 - WIN_X0) / 4)):
        pane = add_prim("plane", f"Pane{k}", col)
        pane.scale = ((WIN_X1 - WIN_X0) / 2 - fw, WIN_Z1 - WIN_Z0 - 2 * fw, 1)
        pane.rotation_euler = (math.radians(90), 0, 0)
        pane.location = (x, D + 0.02 + k * 0.025, (WIN_Z0 + WIN_Z1) / 2)
        pane.visible_shadow = False
        assign(pane, glass)
    # curtains: lace (sheer) + drape pushed to the sides
    lace = mat_principled("Lace", (0.92, 0.92, 0.9), rough=0.8, alpha=0.18)
    curtain("Lace", WIN_X0 + 1.6, WIN_X1 + 0.05, WIN_Z0 - 0.2, WIN_Z1 + 0.15, D - 0.06, lace, col, folds=14,
            depth=0.03, wind=wind)
    drape = cloth_mat("Drape", (0.22, 0.25, 0.32), rough=0.95)
    # the drape over the bed head stops just above the headboard instead of hanging into the pillow
    curtain("DrapeL", WIN_X0 - 0.15, WIN_X0 + 0.35, 0.62, WIN_Z1 + 0.15, D - 0.12, drape, col, folds=4, depth=0.05,
            wind=wind * 0.4)
    curtain("DrapeR", WIN_X1 - 0.3, WIN_X1 + 0.15, 0.3, WIN_Z1 + 0.15, D - 0.12, drape, col, folds=4, depth=0.05,
            wind=wind * 0.4)
    bed_set(col, pillow_dent=pillow_dent, quilt=quilt, sit=sit)
    props = desk_props(col)
    hands = wall_clock(col)
    tv = crt_tv(col)

    # lighting by time of day
    lamp = lamp_on if lamp_on is not None else (time_of_day == "night_lamp")
    ring, ring_light = ring_lamp(col, on=lamp, flicker=0.15 if lamp else 0.0)
    plate = None
    if city_plate:
        plate = add_prim("plane", "CityPlate", col)
        plate.scale = (90.0, 50.0, 1)
        plate.rotation_euler = (math.radians(90), 0, 0)
        plate.location = (W / 2, D + 45.0, 6.0)
        pm = bpy.data.materials.new("CityPlateMat")
        nt = node_tree(pm)
        nt.nodes.clear()
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(city_plate))
        tex.extension = "EXTEND"
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 1.0
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        assign(plate, pm)
    sky = {"night": ((0.3, 0.42, 0.7), 38.0, (1.0, 0.55, 0.25), 16.0),
           "night_lamp": ((0.3, 0.42, 0.7), 25.0, (1.0, 0.55, 0.25), 10.0),
           "dusk": ((1.0, 0.42, 0.25), 160.0, (0.9, 0.3, 0.45), 30.0),
           "morning": ((1.0, 0.88, 0.72), 220.0, (0.7, 0.8, 1.0), 40.0)}[time_of_day]
    # window light: a big soft area light just outside, plus a warm bounce from below (city)
    wl = bpy.data.lights.new("WindowLight", "AREA")
    wl.shape = "RECTANGLE"
    wl.size, wl.size_y = WIN_X1 - WIN_X0, WIN_Z1 - WIN_Z0
    # window_light < 1 darkens the room around her for a shot: her card is lit by its own props, so the
    # walls drop away and she stays the brightest thing in a grey print
    wl.color, wl.energy = sky[0], sky[1] * window_light
    wlo = link(bpy.data.objects.new("WindowLight", wl), col)
    wlo.location = ((WIN_X0 + WIN_X1) / 2, D - 0.1, (WIN_Z0 + WIN_Z1) / 2)
    wlo.rotation_euler = (math.radians(-90), 0, 0)  # area lights emit along local -Z: point into the room
    bl = bpy.data.lights.new("CityBounce", "AREA")
    bl.size = 2.5
    bl.color, bl.energy = sky[2], sky[3] * window_light
    blo = link(bpy.data.objects.new("CityBounce", bl), col)
    blo.location = (W / 2, D + 1.0, 0.0)
    blo.rotation_euler = (math.radians(-60), 0, 0)
    if rake:
        bed_rake(col, **(rake if isinstance(rake, dict) else {}))
    if time_of_day in ("dusk", "morning"):
        sun = bpy.data.lights.new("Sun", "SUN")
        sun.color = sky[0]
        sun.energy = 3.0 if time_of_day == "dusk" else 2.2
        sun.angle = math.radians(1.5)
        so = link(bpy.data.objects.new("Sun", sun), col)
        so.rotation_euler = (math.radians(80 if time_of_day == "dusk" else 65), 0, math.radians(165))
        if sun_opts:
            # over the bed a grazing sun drags long, dark shadows behind every fold of the quilt: the bed
            # shots raise it and soften it (elev: degrees above the horizon, angle: the sun disc)
            so.rotation_euler = (math.radians(90 - sun_opts.get("elev", 25)), 0,
                                 math.radians(sun_opts.get("azim", 165)))
            sun.angle = math.radians(sun_opts.get("angle", 1.5))
            sun.energy *= sun_opts.get("energy", 1.0)
    return {"col": col, "ring": ring, "ring_light": ring_light, "plate": plate, "clock": hands, "tv": tv,
            **props}


def test_view(sc, opts):
    from common import look_rotation, make_camera, setup_compositor, world_color
    tod = opts.get("tod", "night")
    world_color(sc, (0.01, 0.012, 0.02))
    plate = opts.get("plate")
    build(sc, time_of_day=tod, city_plate=plate, wind=float(opts.get("wind", 0)))
    setup_compositor(sc, bloom=0.4, bloom_threshold=1.0, dispersion=0.004)
    cam = make_camera(sc, lens=float(opts.get("lens", 24)))
    view = opts.get("view", "wide")
    if view == "wide":
        pos, tgt = Vector((2.9, 0.25, 1.45)), Vector((1.3, 2.7, 1.1))
    elif view == "top":
        pos, tgt = Vector((W / 2 + 0.01, D / 2, H - 0.18)), Vector((W / 2, D / 2 + 0.001, 0))
    else:
        pos, tgt = Vector((1.8, 1.0, 1.0)), Vector((0.55, 2.2, 0.6))
    cam.location = pos
    cam.rotation_euler = look_rotation(pos, tgt)
    return cam


def bed_rake(col, energy=8.0, color=(0.62, 0.72, 1.0), height=0.5, aim=1.0):
    """Moonlight through the bottom of the window, grazing along the bed from its head: the folds of the
    quilt and the pillow's swell get a lit side and a shaded side, which the print keeps (the big soft
    window light alone leaves the bedding one flat tone)."""
    from common import look_rotation
    lt = bpy.data.lights.new("BedRake", "AREA")
    lt.shape = "RECTANGLE"
    lt.size, lt.size_y = 0.8, 0.3
    lt.color, lt.energy = color, energy
    lt.use_shadow = False                    # shading only: no extra shadow maps for Eevee's pool
    ob = link(bpy.data.objects.new("BedRake", lt), col)
    ob.location = ((MAT_X0 + MAT_X1) / 2, D - 0.3, MAT_TOP + height)     # clear of the drape
    ob.rotation_euler = look_rotation(ob.location, Vector(((MAT_X0 + MAT_X1) / 2, aim, MAT_TOP)))
    return ob


def build_void(sc, col, city_plate=None, pillow_dent=None, quilt=None, sit=None):
    """The midnight room grown infinite: black mirror floor, no walls; the bed, the
    window frame and the ring lamp hang in nothing, the city far away."""
    floor = add_prim("plane", "VoidFloor", col)
    floor.scale = (400, 400, 1)
    floor.location = (W / 2, D / 2, 0)
    assign(floor, mat_principled("VoidFloorMat", (0.004, 0.004, 0.006), rough=0.08, spec=0.6))
    bed_set(col, pillow_dent=pillow_dent, quilt=quilt, sit=sit)
    alu = mat_principled("Alu", (0.55, 0.56, 0.58), rough=0.3, metal=0.9)
    fw = 0.035
    cx, cz = (WIN_X0 + WIN_X1) / 2, (WIN_Z0 + WIN_Z1) / 2
    for nm, sz, lc in (("FrameTop", (WIN_X1 - WIN_X0, 0.07, fw), (cx, D + 0.03, WIN_Z1)),
                       ("FrameBot", (WIN_X1 - WIN_X0, 0.07, fw), (cx, D + 0.03, WIN_Z0)),
                       ("FrameL", (fw, 0.07, WIN_Z1 - WIN_Z0), (WIN_X0, D + 0.03, cz)),
                       ("FrameR", (fw, 0.07, WIN_Z1 - WIN_Z0), (WIN_X1, D + 0.03, cz)),
                       ("FrameMid", (fw, 0.07, WIN_Z1 - WIN_Z0), (cx, D + 0.03, cz))):
        box(nm, sz, lc, alu, col)
    ring, ring_light = ring_lamp(col, on=False)
    plate = None
    if city_plate:
        plate = add_prim("plane", "CityPlate", col)
        plate.scale = (90.0, 50.0, 1)
        plate.rotation_euler = (math.radians(90), 0, 0)
        plate.location = (W / 2, D + 45.0, 6.0)
        pm = bpy.data.materials.new("CityPlateMat")
        nt = node_tree(pm)
        nt.nodes.clear()
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(city_plate))
        tex.extension = "EXTEND"
        em = nt.nodes.new("ShaderNodeEmission")
        em.name = "PlateEmission"
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        assign(plate, pm)
    key = bpy.data.lights.new("VoidKey", "SPOT")
    key.color = (0.55, 0.65, 1.0)
    key.energy = 120
    key.spot_size = math.radians(40)
    key.spot_blend = 0.6
    ko = link(bpy.data.objects.new("VoidKey", key), col)
    ko.location = (0.55, 1.6, 5.5)
    return {"col": col, "ring": ring, "ring_light": ring_light, "plate": plate, "key": ko}


PLATE = ROOT / "assets" / "plates" / "city_window_night.png"
PLATE_DUSK = ROOT / "assets" / "plates" / "city_window_dusk.png"
PLATE_DAWN = ROOT / "assets" / "plates" / "city_window_dawn.png"


def _quilt(q):
    """A tucked quilt is raised over the covered part of her body (q["body"]: that card's spec)."""
    if not q or q.get("mode") != "tucked":
        return q
    import bedding
    q = dict(q)
    q["field"] = bedding.body_field(q.pop("body"), q["edge"], MAT_TOP)
    return q


def _sit(shot):
    """The hollow under a card sitting on the bed: its spot and the direction its drawing spans (across
    the line of sight from the middle of the camera move, since the card turns to face the camera)."""
    for c in shot.get("cards", []):
        if (c.get("contact") or {}).get("kind") != "sit":
            continue
        keys = shot["cam"]["keys"]
        cx = (keys[0][1][0] + keys[-1][1][0]) / 2 - c["loc"][0]
        cy = (keys[0][1][1] + keys[-1][1][1]) / 2 - c["loc"][1]
        n = math.hypot(cx, cy) or 1.0
        # her seat ends up behind her feet as seen from the camera (bedding.seat_card): centre the
        # hollow between them
        return (c["loc"][0] - 0.1 * cx / n, c["loc"][1] - 0.1 * cy / n, -cy / n, cx / n)
    return None


def build_shot(sc, shot):
    from common import setup_compositor, world_color
    st = shot.get("setup", {})
    world_color(sc, st.get("world", (0.01, 0.012, 0.02)))
    tod = st.get("tod", "night")
    default_plate = {"dusk": PLATE_DUSK, "morning": PLATE_DAWN}.get(tod, PLATE)
    objs = build(sc, time_of_day=tod, lamp_on=st.get("lamp"),
                 city_plate=st.get("plate", default_plate), wind=st.get("wind", 0.0), void=st.get("void", False),
                 pillow_dent=st.get("pillow_dent"), quilt=_quilt(st.get("quilt")), sun=st.get("sun"),
                 sit=_sit(shot), rake=st.get("rake"), window_light=st.get("window_light", 1.0))
    for nm in st.get("hide", []):
        ob = bpy.data.objects.get(nm)
        if ob:
            ob.hide_render = True
    clock = st.get("clock")
    if clock and "clock_display" in objs:
        m = objs["clock_display"].data.materials[0]
        nt = node_tree(m)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(ROOT / "assets" / "plates" / f"clock_{clock}.png"))
        nt.links.new(tex.outputs["Color"], nt.nodes["Emission"].inputs["Color"])
    setup_compositor(sc, **st.get("comp", dict(bloom=0.4, bloom_threshold=1.0, dispersion=0.004)))
    return objs


def ground_cards(cards, specs, cam=None, frame=None):
    """Sitting cards rest their drawing's lowest line on the quilt with a pressed blot under them; cards
    lying on the bed get a soft silhouette shadow."""
    import bedding
    for card, spec in zip(cards or [], specs):
        c = spec.get("contact")
        if not c:
            continue
        if c.get("kind") == "floor":
            # a card standing on the floor (S16): its lowest line on the floor, a soft blot under the part of the
            # drawing that touches it (the feet, the knees and hand, the whole curled side)
            import numpy as np
            h = spec.get("h", 1.5)
            card.location.z = -bedding.drawing_floor(spec["pose"]) * h
            a = bedding.alpha_grid(spec["pose"]) > 0.5          # rows bottom-up
            rows = np.nonzero(a.any(axis=1))[0]
            band = max(2, int(0.08 * (rows[-1] - rows[0])))
            cols = np.nonzero(a[rows[0]:rows[0] + band].any(axis=0))[0]
            nw = a.shape[1]
            width = h * nw / a.shape[0]
            x0, x1 = cols[0] / nw, (cols[-1] + 1) / nw
            span = (x1 - x0) * width
            bedding.sitting_blot(card, 0.0, size=(0.62 * span + 0.06, max(0.12, 0.18 * span)),
                                 strength=c.get("strength", 0.6), shift=(((x0 + x1) / 2 - 0.5) * width, 0.0))
            continue
        if c.get("kind") == "sit":
            with bedding.without_cards():
                z = bedding.surface_below(card.location.x, card.location.y, z_from=card.location.z + 0.6)
            if z is None:
                continue
            card.location.z = z - c.get("sink", 0.008) - bedding.drawing_floor(spec["pose"]) * spec.get("h", 1.5)
            shift = (0.0, -0.05)
            if cam is not None:
                sc = bpy.context.scene
                keep = sc.frame_current
                if frame is not None:
                    sc.frame_set(frame)
                push = bedding.seat_card(card, spec["pose"], spec.get("h", 1.5), cam)
                sc.frame_set(keep)
                if push is not None:
                    shift = (0.5 * push.x, 0.5 * push.y)
            bedding.sitting_blot(card, z, size=c.get("size", (0.78, 0.52)), strength=c.get("strength", 0.72),
                                 shift=shift, conform=True)
        else:
            bedding.lying_shadow(card, spec["pose"], blur=c.get("blur", 0.01), strength=c.get("strength", 0.55),
                                 cast=c.get("cast", 0.04), cast_strength=c.get("cast_strength", 0.3),
                                 shift=c.get("shift", (0.012, -0.012)))


def animate(sc, objs, shot, f0, f1, cards=None, cam=None):
    from common import key_light, key_socket
    ground_cards(cards, shot.get("cards", []), cam=cam, frame=(f0 + f1) // 2)
    an = shot.get("anim", {})
    dur = (f1 + 1 - f0) / 24  # the rendered range (may run past the cut, see render_to)
    if "exposure" in an:
        # the camera's exposure in stops at song times (s, stops): S09 sees her room from outside exposed like the
        # lit windows round hers, and settles to the room's night as the window fills the frame
        for ts, ev in an["exposure"]:
            sc.view_settings.exposure = ev
            sc.view_settings.keyframe_insert("exposure", frame=ts * 24)
    if "lamp" in an:
        key_light(objs["ring_light"].data, [(u, v * LAMP_ENERGY) for u, v in an["lamp"]], f0, dur)
        tube = objs["ring"].data.materials[0]
        em = node_tree(tube).nodes.get("Emission")
        if em and not em.inputs["Strength"].links:
            key_socket(em.inputs["Strength"], [(u, v * 18.0) for u, v in an["lamp"]], f0, dur)
    if "plate" in an and objs.get("plate"):
        em = objs["plate"].data.materials[0].node_tree.nodes.get("Emission") or \
            objs["plate"].data.materials[0].node_tree.nodes.get("PlateEmission")
        key_socket(em.inputs["Strength"], an["plate"], f0, dur)
    if "crt_host" in an and objs.get("tv"):
        nt = objs["tv"].data.materials[0].node_tree
        key_socket(nt.nodes["host"].outputs[0], an["crt_host"], f0, dur)
    if "crt_static" in an and objs.get("tv"):
        nt = objs["tv"].data.materials[0].node_tree
        key_socket(nt.nodes["static"].outputs[0], an["crt_static"], f0, dur)
    if "glow" in an:
        # a warm light where her stomach burns (S16): it moves with her drawings (song-time positions) and
        # flares on the band's hits (timeline.accents), lighting the floor around her
        import timeline as TL
        g = an["glow"]
        ld = bpy.data.lights.new("BellyGlow", "POINT")
        ld.color = g.get("color", (1.0, 0.45, 0.15))
        ld.shadow_soft_size = g.get("size", 0.1)
        lo = bpy.data.objects.new("BellyGlow", ld)
        sc.collection.objects.link(lo)
        for t, pos in g["at"]:
            lo.location = pos
            lo.keyframe_insert("location", frame=(math.ceil(t * 24 - 1e-6) - 0.5) if t > 0 else f0 - 2)
        base, peak = g.get("base", 3.0), g.get("peak", 12.0)
        beats = TL.accents(shot["t0"] - 0.8, shot["t1"] + 0.8)
        ld.energy = base
        ld.keyframe_insert("energy", frame=f0 - 2)
        for b, nxt in zip(beats, beats[1:] + [beats[-1] + 0.8]):
            for t, e in ((b - 1.0 / 24, base), (b, peak), (b + 0.3, base), (nxt - 1.5 / 24, base)):
                ld.energy = e
                ld.keyframe_insert("energy", frame=t * 24)
        for owner in (lo, ld):
            act = owner.animation_data.action
            curves = list(act.fcurves) if hasattr(act, "fcurves") else [
                fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
            for fc in curves:
                if fc.data_path == "location":
                    for kp in fc.keyframe_points:
                        kp.interpolation = "CONSTANT"
    if "crt_wave" in an and objs.get("tv") and "wave" in objs["tv"].data.materials[0].node_tree.nodes:
        # the host waves on the beat: her two drawings swap at song times (seconds, value 0 or 1)
        nt = objs["tv"].data.materials[0].node_tree
        sock = nt.nodes["wave"].outputs[0]
        for t, v in an["crt_wave"]:
            sock.default_value = float(v)
            sock.keyframe_insert("default_value", frame=math.ceil(t * 24 - 1e-6) - 0.5)
        act = nt.animation_data.action
        curves = list(act.fcurves) if hasattr(act, "fcurves") else [
            fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
        for fc in curves:
            if '"wave"' in fc.data_path:
                for kp in fc.keyframe_points:
                    kp.interpolation = "CONSTANT"
    if an.get("clock_tick") and objs.get("clock"):
        import timeline as TL
        sec = objs["clock"]["Second"]
        t0s, t1s = shot["t0"], shot["t1"]
        ticks = [b for b in TL.BEATS if t0s - 1 <= b <= t1s + 1]
        # the second hand steps BACKWARDS, on purpose: in the bridge time runs back (she longs to sleep "as before").
        # The eleventh cut turned it clockwise as a fix and the director asked for it back: keep it so
        for k, b in enumerate(ticks):
            fb = b * 24
            sec.rotation_euler = (math.radians(-6 * k), 0, 0)
            sec.keyframe_insert("rotation_euler", index=0, frame=fb)
            sec.rotation_euler = (math.radians(-6 * (k + 1)), 0, 0)
            sec.keyframe_insert("rotation_euler", index=0, frame=fb + 1.5)
    if "window_light" in an:
        wl = bpy.data.objects.get("WindowLight")
        if wl:
            key_light(wl.data, an["window_light"], f0, dur)
