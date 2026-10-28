"""Clockwork: a train of meshing gears and an escapement that ticks on the beat.

`mood`: "steel" (cold, C section: the second hand that won't stop) or "gold"
(final chorus: every gear finally meshing in morning light).
All gears lie on one plane; speeds follow tooth ratios and each gear starts with its teeth set
into the gaps of the gear it drives, so the train meshes without passing through itself.
"""
import math
import random

try:  # the layout maths also runs outside Blender (src/tools/check_gears.py)
    import bmesh
    import bpy
    from mathutils import Vector

    from common import add_prim, assign, collection, link, mat_emission, mat_principled, node_tree
except ImportError:
    pass

MODULE = 0.06  # tooth size (m per tooth of pitch diameter)


def gear_mesh(name, teeth, thick=0.05, hole=0.2, coll=None, spokes=5):
    r_p = MODULE * teeth / 2
    r_o, r_r = r_p + MODULE, r_p - 1.25 * MODULE
    bm = bmesh.new()
    pts = []
    n = teeth * 4
    for k in range(n):
        a = 2 * math.pi * k / n
        phase = k % 4
        r = r_r if phase in (0, 3) else r_o
        # slight taper on the tooth flank
        da = (math.pi / n) * (0.25 if phase in (1, 2) else 0)
        aa = a + (da if phase == 1 else -da if phase == 2 else 0)
        pts.append((r * math.cos(aa), r * math.sin(aa)))
    hole_r = max(MODULE, r_r * hole)
    outer = [bm.verts.new((x, y, 0)) for x, y in pts]
    inner = [bm.verts.new((hole_r * math.cos(2 * math.pi * k / n), hole_r * math.sin(2 * math.pi * k / n), 0))
             for k in range(n)]
    for k in range(n):
        j = (k + 1) % n
        bm.faces.new((inner[k], inner[j], outer[j], outer[k]))
    geom = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    for v in [e for e in geom["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.z += thick
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = link(bpy.data.objects.new(name, me), coll)
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = 0.004
    bev.segments = 2
    bev.limit_method = "ANGLE"
    ob.modifiers.new("WN", "WEIGHTED_NORMAL")
    me.shade_smooth()
    return ob, r_p


def mesh_phase(phi, r_a, rot_a, r_b):
    """Rotation of gear B so that, on the line of centres (direction phi from A to B), a tooth of A
    sits in a gap of B. Teeth centres lie at fraction 0.375 of each pitch and gaps at 0.875 (see
    gear_mesh); arc positions along the common tangent must agree modulo the circular pitch."""
    p = math.pi * MODULE
    return phi + math.pi - (0.25 * p - r_a * (phi - rot_a)) / r_b


def layout(seed=4, base_speed=0.35, n=9):
    """[(x, y, rotation at frame 1, teeth, thickness, speed)] for the gear train. Every gear meshes
    with the previous one and keeps clear of all the others."""
    rnd = random.Random(seed)
    out = []
    ang = 0.0
    for k in range(n):
        teeth = rnd.choice([12, 16, 20, 24, 30, 36, 48])
        thick = rnd.choice([0.04, 0.06, 0.08])
        r = MODULE * teeth / 2
        if not out:
            out.append((0.0, 0.0, 0.0, teeth, thick, base_speed))
            continue
        px, py, prot, pteeth, _, pspeed = out[-1]
        pr = MODULE * pteeth / 2
        ang += rnd.uniform(-0.9, 0.9)
        rnd.choice([0.0, 0.0, 0.09, -0.09])  # (was a height step; drawn so the layout keeps its shape)
        d = pr + r
        for off in [0.0] + [s * 0.3 * i for i in range(1, 12) for s in (1, -1)]:
            a = ang + off
            x, y = px + d * math.cos(a), py + d * math.sin(a)
            if all(math.hypot(x - qx, y - qy) > MODULE * (qt / 2 + teeth / 2 + 2) + 0.03
                   for qx, qy, _, qt, _, _ in out[:-1]):
                ang = a
                break
        rot = mesh_phase(ang, pr, prot, r)
        out.append((x, y, rot, teeth, thick, -pspeed * pteeth / teeth))
    return out


def escapement_spot(train, x0, y0, r_out):
    """A place near the first gear whose footprint touches none of the train."""
    for k in range(48):
        a = 2.9 + 0.13 * k * (1 if k % 2 else -1)
        for dist in (1.7, 2.0, 2.4, 2.9):
            x, y = x0 + dist * math.cos(a), y0 + dist * math.sin(a)
            if all(math.hypot(x - gx, y - gy) > r_out + MODULE * (t / 2 + 1) + 0.05 for gx, gy, _, t, _, _ in train):
                return x, y
    return x0 - 3.5, y0 + 0.4


def build(sc, mood="steel", seed=4):
    col = collection("Gears")
    if mood == "gold":
        metal = mat_principled("Brass", (0.95, 0.68, 0.32), rough=0.22, metal=1.0)
        metal2 = mat_principled("Brass2", (0.85, 0.55, 0.25), rough=0.3, metal=1.0)
        key, fill = (1.0, 0.78, 0.5), (0.5, 0.65, 1.0)
    else:
        metal = mat_principled("Steel", (0.62, 0.64, 0.68), rough=0.25, metal=1.0)
        metal2 = mat_principled("Steel2", (0.42, 0.44, 0.48), rough=0.35, metal=1.0)
        key, fill = (0.75, 0.85, 1.0), (1.0, 0.3, 0.2)
    # a chain of meshing gears laid out along a zig-zag, all on one plane; each rotates by tooth ratio
    gears = []
    for k, (x, y, rot, teeth, thick, speed) in enumerate(layout(seed, base_speed=0.35)):
        g, r = gear_mesh(f"Gear{k}", teeth, thick=thick, coll=col)
        g.location = (x, y, 0.0)
        g.rotation_euler.z = rot
        assign(g, metal if k % 2 else metal2)
        _spin(g, speed)
        gears.append(g)
    # escapement wheel: steps once per beat (tick); set beside the train, clear of every gear
    esc, r = gear_mesh("Escape", 30, thick=0.03, coll=col)
    ex, ey = escapement_spot(layout(seed), gears[0].location.x, gears[0].location.y, r + MODULE)
    esc.location = (ex, ey, 0.12)
    assign(esc, metal)
    step = 2 * math.pi / 30
    import timeline as TL
    for b, tb in enumerate(TL.BEATS):     # on the song's beats, like the clock ticks in the mix
        f = tb * 24
        esc.rotation_euler.z = -b * step
        esc.keyframe_insert("rotation_euler", index=2, frame=f)
        esc.rotation_euler.z = -(b + 1) * step
        esc.keyframe_insert("rotation_euler", index=2, frame=f + 2)
    # lights
    for nm, colr, e, loc in (("Key", key, 900, (2.5, -2.5, 3.0)), ("Fill", fill, 300, (-3.0, 2.0, 1.5)),
                             ("Rim", key, 600, (0.0, 4.0, -1.0))):
        ld = bpy.data.lights.new(nm, "AREA")
        ld.color = colr
        ld.energy = e
        ld.size = 1.5
        lo = link(bpy.data.objects.new(nm, ld), col)
        lo.location = loc
        lo.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    graze = bpy.data.lights.new("Graze", "SPOT")
    graze.color = key
    graze.energy = 2500
    graze.spot_size = math.radians(55)
    graze.spot_blend = 0.4
    go = link(bpy.data.objects.new("Graze", graze), col)
    c0 = gears[len(gears) // 2].location
    go.location = c0 + Vector((-4.0, -2.0, 0.6))
    go.rotation_euler = (c0 - go.location).to_track_quat("-Z", "Y").to_euler()
    back = add_prim("plane", "Backplate", col)
    back.scale = (30, 30, 1)
    back.location = (0, 0, -0.6)
    assign(back, mat_principled("BackMat", (0.01, 0.01, 0.012), rough=0.6))
    return {"col": col, "gears": gears, "escape": esc}


def _spin(ob, speed):
    ob.keyframe_insert("rotation_euler", index=2, frame=1)
    ob.rotation_euler.z += speed * 330
    ob.keyframe_insert("rotation_euler", index=2, frame=1 + 330 * 24)
    act = ob.animation_data.action
    curves = list(act.fcurves) if hasattr(act, "fcurves") else [
        fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def test_view(sc, opts):
    from common import look_rotation, make_camera, setup_compositor, world_color
    world_color(sc, (0.003, 0.003, 0.004))
    info = build(sc, mood=opts.get("mood", "steel"))
    setup_compositor(sc, bloom=0.3, bloom_threshold=1.2, streaks=0.0, dispersion=0.006)
    gs = info["gears"]
    c = sum((g.location for g in gs), Vector()) / len(gs)
    ext = max((g.location - c).length for g in gs)
    cam = make_camera(sc, lens=float(opts.get("lens", 50)))
    pos = c + Vector((0.6, -1.4, 1.6)) * (ext * 1.1 + 1.5)
    cam.location = pos
    cam.rotation_euler = look_rotation(pos, c)
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = (c - pos).length
    cam.data.dof.aperture_fstop = 2.8
    return cam


def build_shot(sc, shot):
    from common import setup_compositor, world_color
    st = shot.get("setup", {})
    world_color(sc, (0.003, 0.003, 0.004))
    info = build(sc, mood=st.get("mood", "steel"))
    comp = dict(bloom=0.3, bloom_threshold=1.2, streaks=0.0, dispersion=0.006)
    comp.update(st.get("comp", {}))
    setup_compositor(sc, **comp)
    return info
