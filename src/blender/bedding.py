"""Bedding for Rin's room: a cloth-simulated quilt, her body under it, and her contact shadows.

The quilt starts in its resting shape (just above the mattress, its sides over the edges)
and Blender's cloth solver lets it settle: the corners fall into cone folds, the cloth gathers over
her legs and hips. The settled mesh is cached (work/cache/bedding), so shots that share a bed share
exactly the same quilt.

quilt modes (setup quilt=dict(...)):
  spread  the made bed she sits on: covers the mattress up to `edge` (m, world y)
  tucked  she lies under it: covers her up to `edge`; a soft mound is raised where the covered part of
          her drawing lies (`card`: index of her card in the shot), so the cloth falls over a body
"""
import hashlib
import json
from contextlib import contextmanager
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

from common import ROOT, assign, link, node_tree

CACHE = ROOT / "work" / "cache" / "bedding"
CHAR = ROOT / "assets" / "char"
VERSION = 20          # bump when the simulation or the shapes change, so stale caches are not reused


# ---------------------------------------------------------------- her drawing, placed as a card

def card_frame(spec):
    """World matrix, width and height of a card exactly as character.add_card places it."""
    meta = json.loads((CHAR / spec["pose"] / "meta.json").read_text(encoding="utf-8"))
    w_px, h_px = meta["size"]
    h = spec.get("h", 1.5)
    w = h * w_px / h_px
    r = [math.radians(a) for a in spec.get("rot", (90, 0, 0))]
    rot = Euler((r[0] - math.radians(90), r[1], r[2])).to_matrix()
    if spec.get("tilt"):
        rot = Matrix.Rotation(math.radians(spec["tilt"]), 3, "X") @ rot
    m = Matrix.Translation(Vector(spec.get("loc", (0, 0, 0)))) @ rot.to_4x4()
    return m, w, h


def alpha_grid(pose, k=4):
    """The drawing's alpha, k-times smaller, rows bottom-up (like UV t)."""
    img = bpy.data.images.load(str(CHAR / pose / "color.png"), check_existing=True)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    a = px.reshape(h, w, 4)[: h // k * k, : w // k * k, 3]
    return a.reshape(h // k, k, w // k, k).mean(axis=(1, 3))


def drawing_floor(pose):
    """Height of the drawing's lowest opaque row, as a fraction of the card height (its bottom margin)."""
    a = alpha_grid(pose)
    rows = np.nonzero((a > 0.5).any(axis=1))[0]
    return float(rows[0]) / a.shape[0] if len(rows) else 0.0


def _blur(a, sigma):
    if sigma < 0.5:
        return a
    r = int(3 * sigma) + 1
    g = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    g /= g.sum()
    a = np.pad(a, r)
    a = np.apply_along_axis(np.convolve, 0, a, g, "valid")
    return np.apply_along_axis(np.convolve, 1, a, g, "valid")


def _dilate(a, n):
    out = a.copy()
    for dy in range(-n, n + 1):
        for dx in range(-n, n + 1):
            if dx * dx + dy * dy <= n * n:
                out = np.maximum(out, np.roll(np.roll(a, dy, 0), dx, 1))
    return out


def body_field(spec, edge, top, res=0.02, clear=0.03, dilate=0.04, close=0.12, blur=0.08):
    """Heightfield (x0, y0, res, height above top-0.03) of her body under the quilt: wherever the covered
    part of her drawing lies (world y < edge, plus a little), the body reaches `clear` above the card, so
    the cloth passes just over her. The silhouette is closed (a quilt bridges the gaps between knees,
    elbows and hands: one broad shape, not a lump per limb), dilated (every covered pixel stays under the
    cloth) and blurred (it reads as a body, not a slab)."""
    a = alpha_grid(spec["pose"])
    m, w, h = card_frame(spec)
    mi = m.inverted()
    n = (m.to_3x3() @ Vector((0, -1, 0))).normalized()          # the card's face normal
    o = m.translation
    cs = [m @ Vector(((s - 0.5) * w, 0, t * h)) for s in (0, 1) for t in (0, 1)]
    x0, x1 = min(c.x for c in cs) - 0.2, max(c.x for c in cs) + 0.2
    y0, y1 = min(c.y for c in cs) - 0.2, max(c.y for c in cs) + 0.2
    nx, ny = int((x1 - x0) / res) + 1, int((y1 - y0) / res) + 1
    mask = np.zeros((ny, nx), np.float32)
    zc = np.zeros((ny, nx), np.float32)
    for j in range(ny):
        y = y0 + j * res
        for i in range(nx):
            x = x0 + i * res
            # the card plane's height above (x, y)
            zc[j, i] = o.z - (n.x * (x - o.x) + n.y * (y - o.y)) / n.z if abs(n.z) > 1e-3 else o.z
            if y > edge + 0.1:
                continue
            p = mi @ Vector((x, y, zc[j, i]))
            s, t = p.x / w + 0.5, p.z / h
            if 0 <= s < 1 and 0 <= t < 1:
                mask[j, i] = a[int(t * a.shape[0]), int(s * a.shape[1])]
    mask = (mask > 0.3).astype(np.float32)
    k = max(1, int(round(close / res)))
    mask = 1.0 - _dilate(1.0 - _dilate(mask, k), k)          # closing: dilate, then erode
    f = _blur(_dilate(mask, max(1, int(round(dilate / res)))), blur / res)
    f = np.clip(f * 1.5, 0, 1) ** 0.6
    # full height right up to the quilt's edge (so its rim, not a slope, is where she comes out), gone
    # a few centimetres past it
    ys = (y0 + np.arange(ny) * res)[:, None]
    f *= np.clip((edge + 0.08 - ys) / 0.06, 0, 1)
    hz = np.clip(zc + clear - (top - 0.03), 0, None)
    return x0, y0, res, f * hz


# ---------------------------------------------------------------- the quilt

def _waves(seed, n=6, amp=0.01, lam=(0.2, 0.6)):
    rnd = random.Random(seed)
    ws = []
    for _ in range(n):
        th = rnd.uniform(0, math.pi)
        k = 2 * math.pi / rnd.uniform(*lam)
        ws.append((k * math.cos(th), k * math.sin(th), rnd.uniform(0, 6.28), amp * rnd.uniform(0.4, 1.0)))
    return lambda x, y: sum(a * math.sin(kx * x + ky * y + ph) for kx, ky, ph, a in ws) / math.sqrt(n / 2)


def _drape(s, r=0.07, flare=0.15):
    """Cloth carried over a rounded edge: (outward offset, drop) s metres past the edge. Below the bend
    the cloth leans out a little (flare): at a corner, where it hangs over two edges at once, a plumb
    drop would put many points on one line and the cloth solver would refuse the mesh."""
    q = math.pi * r / 2
    if s <= 0:
        return s, 0.0
    if s < q:
        a = s / r
        return r * math.sin(a), r * (1 - math.cos(a))
    return r + flare * (s - q), r + (s - q)


def quilt_rest(bed, edge, field=None, res=0.025, over=(0.03, 0.3, 0.26), lift=0.045, seed=4):
    """Vertices, faces and UVs of the quilt in its starting shape: a few centimetres above the mattress
    (and her body), its free sides carried over the mattress edge and hanging down, its top edge
    wandering a little around `edge`. bed: mattress (x0, x1, y0, y1, top)."""
    mx0, mx1, my0, my1, top = bed
    ol, orr, of = over
    wander = _waves(seed, n=3, amp=0.025, lam=(0.35, 0.8))
    lump = _waves(seed + 5, n=6, amp=0.008, lam=(0.15, 0.45))
    # the hanging sides start in loose vertical waves, so they settle into folds instead of a flat wall
    fold = _waves(seed + 11, n=4, amp=0.028, lam=(0.16, 0.36))
    u0, u1 = -ol, (mx1 - mx0) + orr
    va, vb = -of, (edge - my0)
    nu, nv = int((u1 - u0) / res), int((vb - va) / res)

    def ground(x, y):
        z = top
        if field is not None:
            fx0, fy0, fr, fz = field
            i, j = (x - fx0) / fr, (y - fy0) / fr
            if 0 <= i < fz.shape[1] - 1 and 0 <= j < fz.shape[0] - 1:
                i0, j0 = int(i), int(j)
                di, dj = i - i0, j - j0
                hz = (fz[j0, i0] * (1 - di) * (1 - dj) + fz[j0, i0 + 1] * di * (1 - dj) +
                      fz[j0 + 1, i0] * (1 - di) * dj + fz[j0 + 1, i0 + 1] * di * dj)
                z = max(z, top - 0.03 + hz)
        return z

    verts, uvs = [], []
    for j in range(nv + 1):
        for i in range(nu + 1):
            u = u0 + (u1 - u0) * i / nu
            v = va + (vb + wander(u, 0.0) - va) * j / nv
            xf, yf = mx0 + u, my0 + v
            sx = max(xf - mx1, mx0 - xf, 0.0)
            sy = max(my0 - yf, 0.0)
            dx, dzx = _drape(sx)
            dy, dzy = _drape(sy)
            x = mx1 + dx if xf > mx1 else (mx0 - dx if xf < mx0 else xf)
            y = my0 - dy if yf < my0 else yf
            drop = max(dzx, dzy)
            hang = min(1.0, max(0.0, (drop - 0.02) / 0.12))
            if xf > mx1:
                x += fold(0.0, yf) * hang
            elif xf < mx0:
                x -= fold(0.0, yf) * hang
            if yf < my0:
                y -= fold(xf, 0.0) * hang
            z = ground(min(max(xf, mx0), mx1), max(yf, my0)) + lift + lump(xf, yf) * (1 - min(1, drop / 0.05)) - drop
            verts.append((x, y, z))
            uvs.append((u / 0.04, v / 0.04))
    faces = [(j * (nu + 1) + i, j * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i)
             for j in range(nv) for i in range(nu)]
    return verts, faces, uvs


def _cache_key(**kw):
    s = json.dumps({**kw, "v": VERSION}, sort_keys=True, default=lambda o: np.asarray(o).round(4).tolist())
    return hashlib.md5(s.encode()).hexdigest()[:16]


def _shape_key(ob):
    co = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return (ob.name, co.min(axis=0).round(3).tolist(), co.max(axis=0).round(3).tolist(), co.mean(axis=0).round(4).tolist(),
            [round(v, 4) for v in (*ob.location, *ob.rotation_euler, *ob.scale)], list(ob.get("dent", ())))


def simulate_quilt(coll, colliders, bed, edge, field=None, frames=45, seed=4, name="Quilt"):
    """Build the quilt, let it settle under gravity (or load the settled shape), return the object."""
    verts, faces, uvs = quilt_rest(bed, edge, field, seed=seed)
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    # what it falls onto is part of the key, read from the mesh data and the object's own transform (its
    # evaluated bounds may still be stale here): a changed bed frame re-runs the simulation
    shapes = sorted(_shape_key(c) for c in colliders if c is not None)
    key = _cache_key(bed=bed, edge=edge, frames=frames, seed=seed, n=len(verts), colliders=shapes,
                     field=None if field is None else [field[0], field[1], field[2], float(field[3].sum())])
    path = CACHE / f"quilt_{key}.npy"
    if path.exists():
        co = np.load(path)
        me.vertices.foreach_set("co", co.ravel())
        me.update()
        return ob
    sc = bpy.context.scene
    rest = np.array(verts, np.float32)
    added, temp = [], []
    if field is not None:
        # her body under the quilt, as a collider for the simulation only
        fx0, fy0, fr, fz = field
        ny, nx = fz.shape
        bv = [(fx0 + i * fr, fy0 + j * fr, bed[4] - 0.03 + float(fz[j, i])) for j in range(ny) for i in range(nx)]
        # only the raised cells: a flat sheet left inside the mattress would stick out of its sides and
        # catch the hanging cloth
        bf = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i)
              for j in range(ny - 1) for i in range(nx - 1)
              if max(fz[j, i], fz[j, i + 1], fz[j + 1, i], fz[j + 1, i + 1]) > 0.035]
        # keep only the vertices those faces use (loose vertices stop the cloth solver silently)
        used = sorted({k for f in bf for k in f})
        remap = {k: n for n, k in enumerate(used)}
        bv = [bv[k] for k in used]
        bf = [tuple(remap[k] for k in f) for f in bf]
        bme = bpy.data.meshes.new("BodyUnderQuilt")
        bme.from_pydata(bv, [], bf)
        bme.update()
        body = bpy.data.objects.new("BodyUnderQuilt", bme)
        link(body, coll)
        colliders = list(colliders) + [body]
        temp.append(body)
    for c in colliders:
        if c and not any(m.type == "COLLISION" for m in c.modifiers):
            c.modifiers.new("Collision", "COLLISION")
            added.append(c)
        if c:
            c.collision.thickness_outer = 0.003
            c.collision.cloth_friction = 10.0
    # the wall side is tucked between mattress and wall: pin it
    pin = ob.vertex_groups.new(name="Pin")
    pin.add([k for k, v in enumerate(verts) if v[0] < bed[0] + 0.05], 1.0, "REPLACE")
    cl = ob.modifiers.new("Cloth", "CLOTH")
    s = cl.settings
    s.quality = 10
    s.mass = 0.6
    s.air_damping = 3.0
    s.tension_stiffness = s.compression_stiffness = 20.0
    s.shear_stiffness = 8.0
    s.bending_stiffness = 18.0
    s.vertex_group_mass = "Pin"
    cs = cl.collision_settings
    cs.collision_quality = 3
    cs.distance_min = 0.015
    cs.use_self_collision = False
    cl.point_cache.frame_start, cl.point_cache.frame_end = 1, frames
    keep = sc.frame_current
    fs, fe = sc.frame_start, sc.frame_end
    sc.frame_start, sc.frame_end = 1, frames
    sc.use_gravity = True
    for f in range(1, frames + 1):
        sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    settled = ob.evaluated_get(dg).data
    co = np.empty(len(settled.vertices) * 3, np.float32)
    settled.vertices.foreach_get("co", co)
    ob.modifiers.remove(cl)
    for c in added:
        for md in [md for md in c.modifiers if md.type == "COLLISION"]:
            c.modifiers.remove(md)
    for t in temp:
        bpy.data.objects.remove(t, do_unlink=True)
    sc.frame_start, sc.frame_end = fs, fe
    sc.frame_set(keep)
    c3 = co.reshape(-1, 3)
    moved = np.abs(c3 - rest).max()
    if not np.isfinite(c3).all() or moved > 0.6 or c3[:, 2].max() > bed[4] + 0.5:
        # the solver blew up: keep the resting shape and do not cache it
        print("QUILT_SIM_DIVERGED", round(float(moved), 2))
        me.vertices.foreach_set("co", rest.ravel())
        me.update()
        return ob
    me.vertices.foreach_set("co", co)
    me.update()
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(path, c3)
    print("QUILT_SIM_OK", round(float(moved), 3))
    return ob


def simulate_pillow(coll, mattress, center, top, half=(0.31, 0.21), head=None, pressure=6.5, frames=60,
                    name="Pillow"):
    """A pillow the way one is made: two layers of a case sewn at the edges and inflated by the cloth
    solver's pressure, so it puffs up, pinches at the seam and creases. head = (x, y): a head comes down
    on it there and leaves its hollow and the creases around it. Cached like the quilt."""
    a, b = half
    nx, ny = 31, 21
    cx, cy = center
    z0 = top + 0.03
    verts, faces = [], []
    for dz in (0.012, -0.012):
        for j in range(ny + 1):
            for i in range(nx + 1):
                verts.append((cx - a + 2 * a * i / nx, cy - b + 2 * b * j / ny, z0 + dz))
    row, n1 = nx + 1, (nx + 1) * (ny + 1)
    for j in range(ny):
        for i in range(nx):
            q = (j * row + i, j * row + i + 1, (j + 1) * row + i + 1, (j + 1) * row + i)
            faces.append(q)
            faces.append(tuple(v + n1 for v in q[::-1]))
    border = ([(0, i) for i in range(nx)] + [(j, nx) for j in range(ny)] +
              [(ny, i) for i in range(nx, 0, -1)] + [(j, 0) for j in range(ny, 0, -1)])
    for k in range(len(border)):
        (j0, i0), (j1, i1) = border[k], border[(k + 1) % len(border)]
        a0, a1 = j0 * row + i0, j1 * row + i1
        faces.append((a0, a1, a1 + n1, a0 + n1))          # the seam
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    key = _cache_key(kind="pillow", center=center, top=top, half=half, head=head, pressure=pressure, frames=frames)
    path = CACHE / f"pillow_{key}.npy"
    if path.exists():
        me.vertices.foreach_set("co", np.load(path).ravel())
        me.update()
        return ob
    sc = bpy.context.scene
    temp, added = [], []
    if not any(m.type == "COLLISION" for m in mattress.modifiers):
        mattress.modifiers.new("Collision", "COLLISION")
        added.append(mattress)
    mattress.collision.thickness_outer = 0.004
    if head is not None:
        from common import add_prim
        hd = add_prim("sphere", "PillowHead", coll, seg=32, rings=16, r=0.11)
        hd.scale = (1.0, 0.85, 0.75)
        hd.location = (head[0], head[1], z0 + 0.35)
        hd.keyframe_insert("location", frame=1)
        hd.keyframe_insert("location", frame=28)
        hd.location = (head[0], head[1], z0 + 0.07)
        hd.keyframe_insert("location", frame=46)
        hd.modifiers.new("Collision", "COLLISION")
        hd.collision.thickness_outer = 0.004
        temp.append(hd)
    cl = ob.modifiers.new("Cloth", "CLOTH")
    st = cl.settings
    st.quality = 10
    st.mass = 0.15
    st.air_damping = 2.0
    st.tension_stiffness = st.compression_stiffness = 25.0
    st.shear_stiffness = 10.0
    st.bending_stiffness = 0.6
    st.use_pressure = True
    st.uniform_pressure_force = pressure
    cs = cl.collision_settings
    cs.distance_min = 0.004
    cs.use_self_collision = True
    cs.self_distance_min = 0.004
    cl.point_cache.frame_start, cl.point_cache.frame_end = 1, frames
    keep, fs, fe = sc.frame_current, sc.frame_start, sc.frame_end
    sc.frame_start, sc.frame_end = 1, frames
    for f in range(1, frames + 1):
        sc.frame_set(f)
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    co = np.empty(len(ev.vertices) * 3, np.float32)
    ev.vertices.foreach_get("co", co)
    ob.modifiers.remove(cl)
    for t in temp:
        bpy.data.objects.remove(t, do_unlink=True)
    for c in added:
        for md in [md for md in c.modifiers if md.type == "COLLISION"]:
            c.modifiers.remove(md)
    sc.frame_start, sc.frame_end = fs, fe
    sc.frame_set(keep)
    c3 = co.reshape(-1, 3)
    if not np.isfinite(c3).all() or c3[:, 2].max() > top + 0.3 or c3[:, 2].min() < top - 0.05:
        print("PILLOW_SIM_DIVERGED")
        return ob
    me.vertices.foreach_set("co", co)
    me.update()
    CACHE.mkdir(parents=True, exist_ok=True)
    np.save(path, c3)
    print("PILLOW_SIM_OK")
    return ob


def dress_quilt(ob, mat, thick=0.04):
    so = ob.modifiers.new("Thick", "SOLIDIFY")
    so.thickness, so.offset = thick, 0.0
    so.use_even_offset = True
    sub = ob.modifiers.new("Sub", "SUBSURF")
    sub.levels, sub.render_levels = 1, 2
    ob.data.shade_smooth()
    assign(ob, mat)
    return ob


# ---------------------------------------------------------------- materials

def gingham_mat(name, base=(0.93, 0.9, 0.82), ink=(0.74, 0.47, 0.08), cell=2.0, rough=0.85, sheen=0.5):
    """Quilt cover in a gingham of her yellow, in UV cells: the check follows every fold. The print
    (src/comp/printlook.py) has to carry it: 4 cm checks in a deep ochre against cream read as darker
    dots even where the blue night light washes their colour out; finer or paler checks fell between
    the halftone dots and below the yellow ink's threshold, and the quilt printed as a flat grey slab."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs["Roughness"].default_value = rough
    try:
        p.inputs["Sheen Weight"].default_value = sheen
    except KeyError:
        pass
    uv = nt.nodes.new("ShaderNodeUVMap")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])

    def stripes(sock):
        fr = nt.nodes.new("ShaderNodeMath")
        fr.operation = "PINGPONG"
        fr.inputs[1].default_value = 0.5 * cell
        nt.links.new(sock, fr.inputs[0])
        st = nt.nodes.new("ShaderNodeMath")
        st.operation = "GREATER_THAN"
        st.inputs[1].default_value = 0.25 * cell
        nt.links.new(fr.outputs[0], st.inputs[0])
        return st.outputs[0]

    sx, sy = stripes(sep.outputs["X"]), stripes(sep.outputs["Y"])
    both = nt.nodes.new("ShaderNodeMath")
    both.operation = "ADD"
    nt.links.new(sx, both.inputs[0])
    nt.links.new(sy, both.inputs[1])
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = 0.5           # 0 white, 0.5 single stripe, 1 crossing
    nt.links.new(both.outputs[0], k.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*base, 1)
    mix.inputs["B"].default_value = (*ink, 1)
    nt.links.new(k.outputs[0], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], p.inputs["Base Color"])
    return m


def add_wrinkles(mat, scale=5.0, strength=0.12, detail=3.0):
    """Fine creases in a fabric: a noise bump in world space (scaled boxes keep it isotropic)."""
    nt = node_tree(mat)
    p = nt.nodes.get("Principled BSDF")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail
    nz.inputs["Distortion"].default_value = 1.2
    nt.links.new(geo.outputs["Position"], nz.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return mat


# ---------------------------------------------------------------- her contact with the bed

def _shadow_material(name, image=None, strength=0.45, falloff=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    k = nt.nodes.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = strength
    if image is not None:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Cubic"
        tex.extension = "CLIP"
        nt.links.new(tex.outputs["Color"], k.inputs[0])
    else:
        # a soft round blot: 1 in the middle of the plane, 0 at its rim
        tc = nt.nodes.new("ShaderNodeTexCoord")
        ln = nt.nodes.new("ShaderNodeVectorMath")
        ln.operation = "LENGTH"
        nt.links.new(tc.outputs["Object"], ln.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.interpolation_type = "SMOOTHSTEP"
        mr.inputs["From Min"].default_value = falloff[0]
        mr.inputs["From Max"].default_value = falloff[1]
        mr.inputs["To Min"].default_value = 1.0
        mr.inputs["To Max"].default_value = 0.0
        nt.links.new(ln.outputs["Value"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], k.inputs[0])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    dark = nt.nodes.new("ShaderNodeEmission")
    dark.inputs["Color"].default_value = (0, 0, 0, 1)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(k.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(dark.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    m.surface_render_method = "BLENDED"
    return m


def lying_shadow(card, pose, blur=0.01, strength=0.55, cast=0.04, cast_strength=0.3, depth=0.008,
                 shift=(0.012, -0.012)):
    """Under a card that lies on the bed: a tight dark contact line hugging her outline (where hair,
    elbow and hip press on the sheet) plus a wider, fainter cast shadow, as one texture on a copy of the
    card just beneath it, parented to the card so it breathes with it."""
    a0 = alpha_grid(pose)
    hh, ww = a0.shape
    rows_per_m = hh / card.dimensions.z if card.dimensions.z > 0 else 1000.0
    a = (strength * _blur(a0, max(1.0, blur * rows_per_m)) +
         cast_strength * _blur(a0, max(1.0, cast * rows_per_m)))
    a = np.clip(a, 0, 1)
    img = bpy.data.images.new(f"{pose}_contact", ww, hh, alpha=True)
    img.colorspace_settings.name = "Non-Color"
    rgba = np.ones((hh, ww, 4), np.float32)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = a
    img.pixels.foreach_set(rgba.ravel())
    me = card.data.copy()
    me.materials.clear()
    me.materials.append(_shadow_material(f"Contact_{pose}", image=img, strength=1.0))
    sh = bpy.data.objects.new(card.name + "_contact", me)
    for c in card.users_collection:
        c.objects.link(sh)
    sh.parent = card
    rot = card.rotation_euler.to_matrix()
    sh.location = rot.inverted() @ Vector((shift[0], shift[1], -depth))
    sh.visible_shadow = False
    return sh


def sitting_blot(card, surface_z, size=(0.62, 0.5), strength=0.5, shift=(0.0, -0.05), falloff=(0.05, 0.45),
                 conform=False):
    """Where she sits the cloth is pressed and shaded: a soft blot on the surface under her. conform:
    the blot is laid onto the cloth (each point dropped onto the surface below it), so it follows the
    hollow and the folds instead of floating flat over them."""
    from common import add_prim
    coll = card.users_collection[0]
    pl = add_prim("plane", card.name + "_blot", coll)
    pl.scale = (size[0], size[1], 1)
    pl.location = (card.location.x + shift[0], card.location.y + shift[1], surface_z + 0.004)
    if conform:
        bm = bmesh.new()
        bm.from_mesh(pl.data)
        # dense enough (about 2 cm) that the cloth between samples cannot rise through it at a fold
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=64, use_grid_fill=True)
        bm.to_mesh(pl.data)
        bm.free()
        with without_cards():                   # her card and this blot itself
            for v in pl.data.vertices:
                wx, wy = pl.location.x + v.co.x * pl.scale.x, pl.location.y + v.co.y * pl.scale.y
                z = surface_below(wx, wy, z_from=surface_z + 0.3)
                if z is not None:
                    v.co.z = (z + 0.006 - pl.location.z) / pl.scale.z
        pl.data.update()
    assign(pl, _shadow_material(card.name + "_blotmat", strength=strength, falloff=falloff))
    pl.visible_shadow = False
    return pl


def _bottom_edge(low, nu):
    """The drawing's bottom edge (rows from the bottom of the image) at nu + 1 columns, each column taking
    the lowest point across its own width."""
    ww = len(low)
    half = max(1, ww // (2 * nu))
    cols = np.clip(np.round(np.linspace(0, 1, nu + 1) * (ww - 1)).astype(int), 0, ww - 1)
    return np.array([low[max(0, c - half):c + half + 1].min() for c in cols])


def _seat_push(edge, floor, hh, h, w, mw, cpos, sink, reach):
    """How far back along its camera ray each column of the bottom edge must go to rest on the surface;
    columns that bear no weight (higher than `reach` above the lowest point) are interpolated."""
    us = np.linspace(0, 1, len(edge))
    rise = (edge - floor) / hh * h
    push = np.full(len(edge), np.nan)
    for i, u in enumerate(us):
        if edge[i] >= hh or rise[i] > reach:
            continue
        p = mw @ Vector(((u - 0.5) * w, 0.0, edge[i] / hh * h))
        r = (p - cpos).normalized()
        tt = 0.0
        while tt < 0.6:
            qq = p + r * tt
            s = surface_below(qq.x, qq.y, z_from=qq.z + 0.5)
            if s is not None and qq.z <= s - sink:
                push[i] = tt
                break
            tt += 0.005
    ok = ~np.isnan(push)
    if not ok.any():
        return None
    return np.interp(us, us[ok], push[ok])


def seat_card(card, pose, h, cam, sink=0.004, reach=0.1, band=0.15):
    """A sitting drawing is drawn from above, so only its lowest point (her toes) touches the bed when the
    card stands upright: her seat, drawn higher, floats over the quilt. Slide the bottom of the card back
    along the camera's rays until each part of that edge that bears weight (within `reach` of the lowest
    point) rests on the surface behind it, easing back to the flat card over `band` metres above the
    edge. From the camera the drawing is unchanged; in the scene her seat now sits on the quilt behind
    her feet. Call with the scene at a representative frame (the card's tracking evaluated). Returns the
    mean horizontal push of the weight-bearing edge (world x, y), or None."""
    a = alpha_grid(pose)
    hh, ww = a.shape
    w = h * ww / hh
    low = np.array([np.nonzero(a[:, c] > 0.5)[0][0] if (a[:, c] > 0.5).any() else hh for c in range(ww)], float)
    if not (low < hh).any():
        return None
    floor = low.min()
    # the mesh: columns across the drawing, rows dense near the bottom where it bends
    nu = 64
    vs = np.unique(np.concatenate([np.linspace(0, 0.32, 33), np.linspace(0.32, 1.0, 18)]))
    me = card.data
    mats = list(me.materials)
    me.clear_geometry()
    verts = [((u - 0.5) * w, 0.0, v * h) for v in vs for u in np.linspace(0, 1, nu + 1)]
    faces = [(j * (nu + 1) + i, j * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i + 1, (j + 1) * (nu + 1) + i)
             for j in range(len(vs) - 1) for i in range(nu)]
    me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vx, _vy, vz = verts[me.loops[li].vertex_index]
            uvl.data[li].uv = (vx / w + 0.5, vz / h)
    me.uv_layers.active = uvl
    uvl.active_render = True
    for m in mats:
        if m.name not in [x.name for x in me.materials]:
            me.materials.append(m)
    me.update()
    bpy.context.view_layer.update()
    mw, cpos = card.matrix_world.copy(), cam.matrix_world.translation.copy()
    inv = mw.inverted()
    edge = _bottom_edge(low, nu)
    with without_cards():
        push = _seat_push(edge, floor, hh, h, w, mw, cpos, sink, reach)
    if push is None:
        return None
    base = np.where(edge < hh, edge / hh * h, floor / hh * h)
    moved = []
    for k, v in enumerate(me.vertices):
        i = k % (nu + 1)
        x, z = v.co.x, v.co.z
        above = z - base[i]
        f = 1.0 if above <= 0 else max(0.0, 1.0 - above / band)
        f = f * f * (3 - 2 * f)
        if f <= 0 or push[i] <= 0:
            continue
        p = mw @ Vector((x, 0.0, z))
        p2 = p + (p - cpos).normalized() * push[i] * f
        v.co = inv @ p2
        if above <= 0:
            moved.append((p2 - p).xy)
    me.update()
    if not moved:
        return Vector((0.0, 0.0))
    return sum(moved, Vector((0.0, 0.0))) / len(moved)


@contextmanager
def without_cards(prefix="Rin_"):
    """Take her cards (and their blots) out of the scene while rays are cast onto the bed. Skipping a hit
    is not enough: a card dips a little into the quilt, so a ray that goes on from where it met the card
    can be under the quilt's top already and find its underside."""
    obs = [o for o in bpy.context.scene.objects if o.name.startswith(prefix) and not o.hide_viewport]
    for o in obs:
        o.hide_viewport = True
    try:
        yield
    finally:
        for o in obs:
            o.hide_viewport = False


def surface_below(x, y, z_from=1.0, skip=("Rin_",)):
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    o, d = Vector((x, y, z_from)), Vector((0, 0, -1))
    for _ in range(6):
        hit, loc, _n, _i, ob, _m = sc.ray_cast(dg, o, d)
        if not hit:
            return None
        if not ob.name.startswith(skip) and not ob.hide_render:
            return loc.z
        o = loc + d * 0.002
    return None
