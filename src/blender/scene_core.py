"""The fusion core: a tokamak vacuum vessel seen from inside and outside.

Geometry is all procedural: tiled torus wall, helical plasma filaments, a
glowing volumetric plasma ring, toroidal field coils and a dark reactor hall.
`mood` picks the light: "blue" (chorus 1), "white" (chorus 2), "dawn" (final).
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from common import (add_prim, assign, collection, frame_value_node, link, mat_emission,
                    mat_principled, node_tree)

R_MAJOR = 12.0      # torus major radius (m)
R_VESSEL = 3.4      # vessel minor radius
R_PLASMA = 1.7      # plasma minor radius

MOODS = {
    "blue": dict(core=(0.55, 0.85, 1.0), glow=(0.03, 0.4, 1.0), edge=(0.3, 0.15, 1.0),
                 lamp=(0.15, 0.5, 1.0), wall=(0.012, 0.014, 0.018), fog=(0.01, 0.05, 0.12)),
    "white": dict(core=(1.0, 1.0, 1.0), glow=(0.55, 0.8, 1.0), edge=(0.75, 0.85, 1.0),
                  lamp=(0.8, 0.9, 1.0), wall=(0.05, 0.05, 0.055), fog=(0.1, 0.12, 0.15)),
    "dawn": dict(core=(1.0, 0.95, 0.85), glow=(1.0, 0.62, 0.3), edge=(0.95, 0.4, 0.55),
                 lamp=(1.0, 0.7, 0.45), wall=(0.05, 0.045, 0.04), fog=(0.14, 0.08, 0.05)),
}


def torus_mesh(name, R, r, su, sv, inward=False, coll=None, uv_scale=(1.0, 1.0)):
    bm = bmesh.new()
    uv = bm.loops.layers.uv.new("UVMap")
    verts = []
    for i in range(su + 1):
        a = 2 * math.pi * i / su
        for j in range(sv + 1):
            b = 2 * math.pi * j / sv
            rr = R + r * math.cos(b)
            verts.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), r * math.sin(b))))
    W = sv + 1
    for i in range(su):
        for j in range(sv):
            q = (verts[i * W + j], verts[(i + 1) * W + j], verts[(i + 1) * W + j + 1], verts[i * W + j + 1])
            if inward:
                q = q[::-1]
            f = bm.faces.new(q)
            uvs = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
            if inward:
                uvs = uvs[::-1]
            for loop, (ui, vj) in zip(f.loops, uvs):
                loop[uv].uv = (ui / su * uv_scale[0], vj / sv * uv_scale[1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    return link(bpy.data.objects.new(name, me), coll)


def wall_material(m):
    mat = bpy.data.materials.new("VesselWall")
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    p = N.get("Principled BSDF")
    tc = N.new("ShaderNodeTexCoord")
    brick = N.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.035
    brick.inputs["Mortar Smooth"].default_value = 0.2
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 1.0
    w = m["wall"]
    brick.inputs["Color1"].default_value = (w[0] * 1.3, w[1] * 1.3, w[2] * 1.3, 1)
    brick.inputs["Color2"].default_value = (w[0] * 0.7, w[1] * 0.7, w[2] * 0.7, 1)
    brick.inputs["Mortar"].default_value = (0.005, 0.005, 0.006, 1)
    mapping = N.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (190.0, 54.0, 1.0)  # tiles: toroidal x poloidal
    L.new(tc.outputs["UV"], mapping.inputs["Vector"])
    L.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    L.new(brick.outputs["Color"], p.inputs["Base Color"])
    bump = N.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    inv = N.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    L.new(brick.outputs["Fac"], inv.inputs[1])
    L.new(inv.outputs[0], bump.inputs["Height"])
    L.new(bump.outputs["Normal"], p.inputs["Normal"])
    # roughness varies per tile so the plasma reflections break up nicely
    noise = N.new("ShaderNodeTexWhiteNoise")
    noise.noise_dimensions = "3D"
    flo = N.new("ShaderNodeVectorMath")
    flo.operation = "FLOOR"
    L.new(mapping.outputs["Vector"], flo.inputs[0])
    L.new(flo.outputs["Vector"], noise.inputs["Vector"])
    rmap = N.new("ShaderNodeMapRange")
    rmap.inputs["To Min"].default_value = 0.08
    rmap.inputs["To Max"].default_value = 0.4
    L.new(noise.outputs["Value"], rmap.inputs["Value"])
    L.new(rmap.outputs["Result"], p.inputs["Roughness"])
    p.inputs["Metallic"].default_value = 0.85
    return mat


def plasma_volume_material(m, strength=2.2):
    mat = bpy.data.materials.new("PlasmaVolume")
    nt = node_tree(mat)
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    vol = N.new("ShaderNodeVolumePrincipled")
    vol.inputs["Density"].default_value = 0.0
    vol.inputs["Emission Color"].default_value = (*m["glow"], 1)
    t = frame_value_node(nt, "time")
    tc = N.new("ShaderNodeTexCoord")
    # swirl coordinates so noise streams around the ring
    rot = N.new("ShaderNodeVectorRotate")
    rot.rotation_type = "Z_AXIS"
    sp = N.new("ShaderNodeMath")
    sp.operation = "MULTIPLY"
    sp.inputs[1].default_value = 0.35
    L.new(t.outputs[0], sp.inputs[0])
    L.new(sp.outputs[0], rot.inputs["Angle"])
    L.new(tc.outputs["Object"], rot.inputs["Vector"])
    noise = N.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "4D"
    noise.inputs["Scale"].default_value = 0.55
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.62
    L.new(rot.outputs["Vector"], noise.inputs["Vector"])
    L.new(t.outputs[0], noise.inputs["W"])
    ramp = N.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    L.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    # radial falloff from the plasma axis: distance to the circle of radius R
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(tc.outputs["Object"], sep.inputs[0])
    lenxy = N.new("ShaderNodeVectorMath")
    lenxy.operation = "LENGTH"
    comb = N.new("ShaderNodeCombineXYZ")
    L.new(sep.outputs["X"], comb.inputs["X"])
    L.new(sep.outputs["Y"], comb.inputs["Y"])
    L.new(comb.outputs[0], lenxy.inputs[0])
    dr = N.new("ShaderNodeMath")
    dr.operation = "SUBTRACT"
    dr.inputs[1].default_value = R_MAJOR
    L.new(lenxy.outputs["Value"], dr.inputs[0])
    comb2 = N.new("ShaderNodeCombineXYZ")
    L.new(dr.outputs[0], comb2.inputs["X"])
    L.new(sep.outputs["Z"], comb2.inputs["Y"])
    dist = N.new("ShaderNodeVectorMath")
    dist.operation = "LENGTH"
    L.new(comb2.outputs[0], dist.inputs[0])
    fall = N.new("ShaderNodeMapRange")
    fall.inputs["From Min"].default_value = 0.0
    fall.inputs["From Max"].default_value = R_PLASMA
    fall.inputs["To Min"].default_value = 1.0
    fall.inputs["To Max"].default_value = 0.0
    fall.interpolation_type = "SMOOTHERSTEP"
    L.new(dist.outputs["Value"], fall.inputs["Value"])
    mul = N.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    L.new(ramp.outputs["Color"], mul.inputs[0])
    L.new(fall.outputs["Result"], mul.inputs[1])
    base = N.new("ShaderNodeMath")
    base.operation = "MULTIPLY_ADD"
    base.inputs[1].default_value = 0.35
    L.new(fall.outputs["Result"], base.inputs[0])
    L.new(mul.outputs[0], base.inputs[2])
    st = N.new("ShaderNodeMath")
    st.operation = "MULTIPLY"
    st.inputs[1].default_value = strength
    st.name = "plasma_strength"
    L.new(base.outputs[0], st.inputs[0])
    L.new(st.outputs[0], vol.inputs["Emission Strength"])
    L.new(vol.outputs[0], out.inputs["Volume"])
    return mat


def helix_curve(name, R, r, turns, phase, pts=900, coll=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(pts - 1)
    for k in range(pts):
        a = 2 * math.pi * k / (pts - 1)
        b = turns * a + phase
        rr = R + r * math.cos(b)
        sp.points[k].co = (rr * math.cos(a), rr * math.sin(a), r * math.sin(b), 1)
    sp.use_cyclic_u = True
    cu.bevel_depth = 0.012
    cu.bevel_resolution = 2
    return link(bpy.data.objects.new(name, cu), coll)


def d_coil(name, coll=None, height=10.5, width=6.2, thick=0.55, depth=0.9):
    """A D-shaped toroidal field coil in the XZ plane (straight leg at x=0)."""
    pts = []
    n = 64
    for k in range(n):
        a = math.pi * (k / (n - 1)) - math.pi / 2
        pts.append((width * math.cos(a), 0, height / 2 * math.sin(a)))
    pts = [(0, 0, -height / 2)] + pts + [(0, 0, height / 2)]
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for k, p in enumerate(pts):
        sp.points[k].co = (*p, 1)
    sp.use_cyclic_u = True
    prof = bpy.data.curves.new(name + "_prof", "CURVE")
    prof.dimensions = "2D"
    ps = prof.splines.new("POLY")
    ps.points.add(3)
    for k, (x, y) in enumerate(((-thick / 2, -depth / 2), (thick / 2, -depth / 2), (thick / 2, depth / 2),
                                (-thick / 2, depth / 2))):
        ps.points[k].co = (x, y, 0, 1)
    ps.use_cyclic_u = True
    po = link(bpy.data.objects.new(name + "_prof", prof), coll)
    po.hide_render = True
    po.hide_viewport = True
    cu.bevel_mode = "OBJECT"
    cu.bevel_object = po
    return link(bpy.data.objects.new(name, cu), coll)


def build(sc, mood="blue", exterior=True, seed=7):
    m = MOODS[mood]
    rnd = random.Random(seed)
    col = collection("Core")

    # vessel interior wall (normals inward) and outer shell
    wall = torus_mesh("VesselIn", R_MAJOR, R_VESSEL, 288, 64, inward=True, coll=col)
    assign(wall, wall_material(m))
    if exterior:
        shell = torus_mesh("VesselOut", R_MAJOR, R_VESSEL + 0.25, 192, 48, coll=col)
        assign(shell, mat_principled("Shell", (0.06, 0.065, 0.07), rough=0.32, metal=0.9))
        # ports: glowing windows on the outer equator leaking plasma light
        port_mat = mat_emission("Port", m["glow"], 9.0)
        for k in range(16):
            a = 2 * math.pi * (k + 0.5) / 16
            p = add_prim("cube", f"Port{k}", col)
            p.scale = (0.25, 1.3, 0.9)
            rr = R_MAJOR + R_VESSEL + 0.2
            p.location = (rr * math.cos(a), rr * math.sin(a), 0)
            p.rotation_euler = (0, 0, a)
            assign(p, port_mat)

    # plasma: volume ring + bright filaments + core ribbon
    pv = torus_mesh("PlasmaVol", R_MAJOR, R_PLASMA * 1.05, 128, 24, coll=col)
    assign(pv, plasma_volume_material(m))
    core = add_prim("torus", "PlasmaCore", col, R=R_MAJOR, r=0.07, su=256, sv=12, smooth=True)
    assign(core, mat_emission("PlasmaCoreMat", m["core"], 8.0))
    fil_mat = mat_emission("Filament", m["glow"], 6.0)
    fil_mat2 = mat_emission("FilamentEdge", m["edge"], 5.0)
    for k in range(28):
        r = rnd.uniform(0.25, R_PLASMA * 0.9)
        h = helix_curve(f"Fil{k}", R_MAJOR, r, turns=rnd.choice([2, 3, 4, 5]) * (1 if k % 2 else -1),
                        phase=rnd.uniform(0, 6.28), coll=col)
        h.data.bevel_depth = rnd.uniform(0.003, 0.01)
        assign(h, fil_mat if k % 3 else fil_mat2)
        # slow drift around the ring
        h.rotation_euler = (0, 0, 0)
        h.keyframe_insert("rotation_euler", index=2, frame=1)
        h.rotation_euler = (0, 0, rnd.uniform(0.6, 1.2) * (1 if k % 2 else -1))
        h.keyframe_insert("rotation_euler", index=2, frame=1 + 24 * 60)
        _linear_anim(h)

    # light from the plasma onto the wall
    for k in range(24):
        a = 2 * math.pi * k / 24
        ld = bpy.data.lights.new(f"PlasmaLamp{k}", "POINT")
        ld.color = m["lamp"]
        ld.energy = 140
        ld.shadow_soft_size = 1.2
        ld.use_shadow = False
        lo = link(bpy.data.objects.new(f"PlasmaLamp{k}", ld), col)
        lo.location = (R_MAJOR * math.cos(a), R_MAJOR * math.sin(a), 0)

    # faint fog inside the vessel so the light has body
    fog = torus_mesh("VesselFog", R_MAJOR, R_VESSEL * 0.98, 96, 16, coll=col)
    fm = bpy.data.materials.new("VesselFogMat")
    nt = node_tree(fm)
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = 0.004
    v.inputs["Color"].default_value = (*m["fog"], 1)
    v.inputs["Anisotropy"].default_value = 0.4
    nt.links.new(v.outputs[0], o.inputs["Volume"])
    assign(fog, fm)

    if exterior:
        coil_mat = mat_principled("Coil", (0.42, 0.44, 0.48), rough=0.28, metal=1.0)
        for k in range(18):
            a = 2 * math.pi * k / 18
            c = d_coil(f"TF{k}", col)
            c.location = (R_MAJOR - 4.4) * math.cos(a), (R_MAJOR - 4.4) * math.sin(a), 0
            c.rotation_euler = (0, 0, a)
            assign(c, coil_mat)
        cs = add_prim("cylinder", "Solenoid", col, r=3.6, depth=14, seg=64)
        assign(cs, mat_principled("SolenoidMat", (0.1, 0.11, 0.12), rough=0.4, metal=0.9))
        for z in (-6.2, 6.2):
            pf = add_prim("torus", f"PF{z}", col, R=R_MAJOR + 1.0, r=0.45, su=128, sv=16, smooth=True)
            pf.location.z = z
            assign(pf, coil_mat)
        # hall rim lights so the coils read against the dark
        for k, (pos, e) in enumerate((((0, 0, 28), 60000), ((40, 30, 8), 45000), ((-40, -30, 6), 30000))):
            ld = bpy.data.lights.new(f"HallLight{k}", "AREA")
            ld.size = 12
            ld.color = m["lamp"]
            ld.energy = e
            lo = link(bpy.data.objects.new(f"HallLight{k}", ld), col)
            lo.location = pos
            lo.rotation_euler = (Vector((0, 0, 0)) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
    return col


def test_view(sc, opts):
    from common import make_camera, look_rotation, setup_compositor, world_color
    mood = opts.get("mood", "blue")
    world_color(sc, (0.0, 0.0, 0.0))
    build(sc, mood=mood, exterior=opts.get("ext", "0") == "1")
    setup_compositor(sc, bloom=0.5, bloom_threshold=1.0, streaks=0.15, dispersion=0.008)
    cam = make_camera(sc, lens=float(opts.get("lens", 22)))
    view = opts.get("view", "inside")
    if view == "inside":
        a0 = 0.0
        pos = Vector(((R_MAJOR + 2.0) * math.cos(a0), (R_MAJOR + 2.0) * math.sin(a0), 0.6))
        a1 = 0.45
        tgt = Vector((R_MAJOR * math.cos(a1), R_MAJOR * math.sin(a1), 0.0))
    else:
        pos = Vector((34.0, -30.0, 16.0))
        tgt = Vector((0, 0, -1.0))
    cam.location = pos
    cam.rotation_euler = look_rotation(pos, tgt, float(opts.get("roll", 0)))
    return cam


def _linear_anim(ob):
    ad = ob.animation_data
    if not ad or not ad.action:
        return
    act = ad.action
    curves = list(act.fcurves) if hasattr(act, "fcurves") else [
        fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.extrapolation = "LINEAR"


def build_shot(sc, shot):
    from common import setup_compositor, world_color
    st = shot.get("setup", {})
    world_color(sc, (0.0, 0.0, 0.0))
    build(sc, mood=st.get("mood", "blue"), exterior=st.get("exterior", False))
    comp = dict(bloom=0.5, bloom_threshold=1.0, streaks=0.15, dispersion=0.008)
    comp.update(st.get("comp", {}))
    setup_compositor(sc, **comp)
    return {}


def animate(sc, objs, shot, f0, f1, cards=None, cam=None):
    from common import key_socket
    an = shot.get("anim", {})
    dur = shot["t1"] - shot["t0"]
    if "plasma" in an:
        m = bpy.data.materials.get("PlasmaVolume")
        n = m.node_tree.nodes.get("plasma_strength")
        base = n.inputs[1].default_value
        key_socket(n.inputs[1], [(u, base * v) for u, v in an["plasma"]], f0, dur)
        for nm in ("PlasmaCoreMat", "Filament", "FilamentEdge"):
            mm = bpy.data.materials.get(nm)
            em = mm.node_tree.nodes.get("Emission")
            b0 = em.inputs["Strength"].default_value
            key_socket(em.inputs["Strength"], [(u, b0 * v) for u, v in an["plasma"]], f0, dur)
