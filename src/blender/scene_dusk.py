"""Dusk: the city under a swollen red sun, a balcony, and an outdoor stairwell.

`place`: "balcony" (city behind a railing) or "stairs" (exterior apartment
stairs raked by the low sun; Rin climbs them a step to the beat, her shadow beside her on the wall).
"""
import math

import bpy
from mathutils import Vector

import scene_city
from common import (add_prim, assign, collection, link, mat_emission, mat_principled, node_tree,
                    setup_compositor)

SUN_DIR = Vector((-0.28, -0.96, 0.012)).normalized()   # sets right behind the fusion hall   # from the viewer toward the sun (south-west, low)
BALCONY = Vector((1500.0, 900.0, 150.0))
STEPS, RISE, RUN = 14, 0.18, 0.27   # the stairwell: step k's tread is centred at y = k * RUN, its top at RISE * (k + 1)


def dusk_sky(sc, strength=1.0):
    w = bpy.data.worlds.new("DuskSky")
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
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.47, (0.35, 0.06, 0.04, 1)
    e[1].position, e[1].color = 0.8, (0.03, 0.025, 0.08, 1)
    m1 = e.new(0.51)
    m1.color = (1.0, 0.28, 0.08, 1)
    m2 = e.new(0.57)
    m2.color = (0.55, 0.12, 0.22, 1)
    m3 = e.new(0.66)
    m3.color = (0.12, 0.05, 0.16, 1)
    L.new(sep.outputs["Z"], ramp.inputs["Fac"])
    # glow around the sun direction
    # view direction = -Incoming (world shader)
    geo = N.new("ShaderNodeNewGeometry")
    neg = N.new("ShaderNodeVectorMath")
    neg.operation = "SCALE"
    neg.inputs["Scale"].default_value = -1.0
    L.new(geo.outputs["Incoming"], neg.inputs[0])
    dot = N.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = SUN_DIR
    L.new(neg.outputs[0], dot.inputs[0])
    halo = N.new("ShaderNodeMapRange")
    halo.inputs["From Min"].default_value = 0.92
    halo.inputs["From Max"].default_value = 1.0
    halo.interpolation_type = "SMOOTHERSTEP"
    L.new(dot.outputs["Value"], halo.inputs["Value"])
    add = N.new("ShaderNodeMix")
    add.data_type = "RGBA"
    add.blend_type = "ADD"
    L.new(halo.outputs["Result"], add.inputs["Factor"])
    L.new(ramp.outputs["Color"], add.inputs["A"])
    add.inputs["B"].default_value = (1.0, 0.38, 0.12, 1)
    L.new(add.outputs["Result"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    L.new(bg.outputs[0], out.inputs["Surface"])
    return w


def sun_disk(col, origin, dist=6000.0, radius=330.0, strength=22.0):
    d = add_prim("sphere", "SunDisk", col, r=radius, seg=48, rings=24)
    d.location = Vector(origin) + SUN_DIR * dist
    assign(d, mat_emission("SunDiskMat", (1.0, 0.16, 0.04), strength))
    sun = bpy.data.lights.new("DuskSun", "SUN")
    sun.color = (1.0, 0.42, 0.2)
    sun.energy = 4.5
    sun.angle = math.radians(2.0)
    so = link(bpy.data.objects.new("DuskSun", sun), col)
    so.rotation_euler = (-SUN_DIR).to_track_quat("-Z", "Y").to_euler()
    return d, so


def balcony(col, base=BALCONY):
    slab = add_prim("cube", "BalconySlab", col)
    slab.scale = (4.0, 1.6, 0.18)
    slab.location = base + Vector((0, 0, -0.09))
    conc = mat_principled("Concrete", (0.32, 0.31, 0.3), rough=0.85)
    assign(slab, conc)
    rail_m = mat_principled("Rail", (0.08, 0.08, 0.085), rough=0.4, metal=0.8)
    # railing along the far edge (toward the city): posts + three bars
    fwd = Vector((-0.55, -0.83, 0)).normalized()
    side = Vector((-fwd.y, fwd.x, 0))
    slab.rotation_euler = (0, 0, math.atan2(fwd.y, fwd.x) + math.pi / 2)
    edge = base + fwd * 0.75
    for k in range(-5, 6):
        p = add_prim("cube", f"Post{k}", col)
        p.scale = (0.035, 0.035, 1.1)
        p.location = edge + side * (k * 0.38) + Vector((0, 0, 0.55))
        assign(p, rail_m)
    for z in (0.35, 0.72, 1.08):
        b = add_prim("cylinder", f"Bar{z}", col, r=0.02, depth=4.0, seg=12)
        b.location = edge + Vector((0, 0, z))
        b.rotation_euler = (math.radians(90), 0, math.atan2(side.y, side.x) + math.pi / 2)
        assign(b, rail_m)
    return edge, fwd, side


def stairs(col, origin=Vector((0, 0, 0)), steps=STEPS, rise=RISE, run=RUN, width=1.1):
    conc = mat_principled("StairConcrete", (0.36, 0.35, 0.33), rough=0.9)
    nt = node_tree(conc)
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6.0
    nz.inputs["Detail"].default_value = 8.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color = (0.22, 0.21, 0.2, 1)
    cr.color_ramp.elements[1].color = (0.42, 0.41, 0.39, 1)
    nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    for k in range(steps):
        s = add_prim("cube", f"Step{k}", col)
        s.scale = (width, run, rise * (k + 1))
        s.location = origin + Vector((0, k * run, rise * (k + 1) / 2))
        assign(s, conc)
    land = add_prim("cube", "Landing", col)
    land.scale = (width, 1.4, rise * steps)
    land.location = origin + Vector((0, steps * run + 0.7, rise * steps / 2))
    assign(land, conc)
    wall = add_prim("cube", "StairWall", col)
    wall.scale = (0.2, steps * run + 4.0, 6.0)
    wall.location = origin + Vector((-width / 2 - 0.1, steps * run / 2 + 0.5, 3.0))
    assign(wall, mat_principled("StairWallMat", (0.3, 0.27, 0.25), rough=0.9))
    rail_m = mat_principled("StairRail", (0.1, 0.1, 0.1), rough=0.4, metal=0.8)
    for k in range(0, steps, 2):
        p = add_prim("cube", f"Baluster{k}", col)
        p.scale = (0.03, 0.03, 0.95)
        p.location = origin + Vector((width / 2 - 0.05, k * run + run / 2, rise * (k + 1) + 0.47))
        assign(p, rail_m)
    for k in range(steps):
        e = add_prim("cube", f"StepEdge{k}", col)
        e.scale = (width * 0.96, 0.012, 0.008)
        e.location = origin + Vector((0, k * run - run / 2 + 0.006, rise * (k + 1) + 0.004))
        m = mat_emission(f"StepEdgeMat{k}", (1.0, 0.42, 0.18), 0.0)
        assign(e, m)
    hand = add_prim("cylinder", "Handrail", col, r=0.025, depth=steps * run * 1.15, seg=12)
    ang = math.atan2(rise, run)
    hand.rotation_euler = (math.radians(90) - ang, 0, 0)
    hand.location = origin + Vector((width / 2 - 0.05, steps * run / 2, rise * steps / 2 + 0.95))
    assign(hand, rail_m)
    return wall


def build(sc, place="balcony", city_lights=0.25, sky="dusk"):
    col = collection("Dusk")
    if sky == "night":
        scene_city.sky_world(sc)
    else:
        dusk_sky(sc)
    if place == "balcony":
        scene_city.build(sc, lights=city_lights, window_strength=2.5 if sky != "night" else 4.0)
        if sky != "night":
            sun_disk(col, BALCONY)
        edge, fwd, side = balcony(col)
        return {"col": col, "edge": edge, "fwd": fwd, "side": side}
    wall = stairs(col)
    ground = add_prim("plane", "StairGround", col)
    ground.scale = (60, 60, 1)
    ground.location = (0, 0, -0.01)
    assign(ground, mat_principled("StairGroundMat", (0.2, 0.19, 0.18), rough=0.9))
    sun = bpy.data.lights.new("StairSun", "SUN")
    sun.color = (1.0, 0.36, 0.14)
    sun.energy = 2.2
    sun.angle = math.radians(0.8)
    so = link(bpy.data.objects.new("StairSun", sun), col)
    so.rotation_euler = Vector((-1.0, 0.35, -0.22)).normalized().to_track_quat("-Z", "Y").to_euler()
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.04
    # dusty air so the sun cuts beams through the balusters
    vol = add_prim("cube", "StairAir", col)
    vol.scale = (14, 14, 9)
    vol.location = (0, 2, 4.4)
    vm = bpy.data.materials.new("StairAirMat")
    nt = node_tree(vm)
    nt.nodes.clear()
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = 0.006
    v.inputs["Color"].default_value = (1.0, 0.75, 0.6, 1)
    v.inputs["Anisotropy"].default_value = 0.55
    nt.links.new(v.outputs[0], o.inputs["Volume"])
    assign(vol, vm)
    return {"col": col, "wall": wall, "sun": so}


def test_view(sc, opts):
    from common import look_rotation, make_camera
    place = opts.get("place", "balcony")
    info = build(sc, place=place)
    setup_compositor(sc, bloom=0.6, bloom_threshold=0.9, streaks=0.1, dispersion=0.006,
                     mist_color=(0.42, 0.11, 0.07), mist_amount=0.42 if place == "balcony" else 0.0)
    sc.view_layers[0].use_pass_mist = True
    sc.world.mist_settings.start = 80
    sc.world.mist_settings.depth = 2600
    cam = make_camera(sc, lens=float(opts.get("lens", 30)), clip=(0.05, 12000))
    if place == "balcony":
        edge, fwd = info["edge"], info["fwd"]
        pos = BALCONY - fwd * 1.0 + Vector((0, 0, 1.35))
        tgt = edge + fwd * 50 + Vector((0, 0, -4))
    else:
        pos = Vector((0.2, -2.8, 1.2))
        tgt = Vector((-0.2, 2.0, 1.6))
    cam.location = pos
    cam.rotation_euler = look_rotation(pos, tgt)
    return cam


def dawn_sky(sc):
    """Morning: pale gold horizon under a clean blue zenith."""
    w = dusk_sky(sc)
    ramp = next(n for n in w.node_tree.nodes if n.bl_idname == "ShaderNodeValToRGB")
    cols = {0.47: (0.55, 0.42, 0.32, 1), 0.51: (1.0, 0.72, 0.42, 1), 0.57: (0.75, 0.62, 0.62, 1),
            0.66: (0.35, 0.45, 0.65, 1), 0.8: (0.12, 0.22, 0.45, 1)}
    for e in ramp.color_ramp.elements:
        best = min(cols, key=lambda p: abs(p - e.position))
        e.color = cols[best]
    mix = next(n for n in w.node_tree.nodes if n.bl_idname == "ShaderNodeMix")
    mix.inputs["B"].default_value = (1.0, 0.8, 0.5, 1)
    return w


def build_shot(sc, shot):
    st = shot.get("setup", {})
    place = st.get("place", "balcony")
    info = build(sc, place=place, city_lights=st.get("lights", 0.25), sky=st.get("sky", "dusk"))
    if st.get("sky") == "dawn":
        dawn_sky(sc)
        disk = bpy.data.objects.get("SunDisk")
        if disk:
            disk.data.materials[0].node_tree.nodes["Emission"].inputs["Color"].default_value = (1.0, 0.75, 0.4, 1)
    comp = dict(bloom=0.6, bloom_threshold=0.9, streaks=0.1, dispersion=0.006,
                mist_color=(0.42, 0.11, 0.07), mist_amount=0.42 if place == "balcony" else 0.0)
    comp.update(st.get("comp", {}))
    setup_compositor(sc, **comp)
    sc.view_layers[0].use_pass_mist = True
    sc.world.mist_settings.start, sc.world.mist_settings.depth = 80, 2600
    return info


def animate(sc, objs, shot, f0, f1, cards=None, cam=None):
    an = shot.get("anim", {})
    if an.get("step_beats"):
        import timeline as TL
        beats = [b for b in TL.BEATS if shot["t0"] <= b < shot["t1"]]
        # each beat lights the step she stands on: she starts on `climb_from` and goes up one a beat
        first = an.get("climb_from", 0)
        climbers = [(c, spec) for c, spec in zip(cards or [], shot.get("cards", [])) if spec.get("climb")]
        if climbers:
            climb(climbers, beats, first)
        for k, b in enumerate(beats):
            m = bpy.data.materials.get(f"StepEdgeMat{(first + k) % STEPS}")
            if m is None:
                continue
            em = m.node_tree.nodes["Emission"].inputs["Strength"]
            for f, v in ((b * 24 - 1, 0.0), (b * 24, 60.0), (b * 24 + 10, 6.0), (b * 24 + 60, 0.0)):
                em.default_value = v
                em.keyframe_insert("default_value", frame=f)
    for c, spec in zip(cards or [], shot.get("cards", [])):
        if spec.get("shadow_only"):
            c.visible_camera = False
            c.visible_shadow = True
            for m in c.data.materials:
                if hasattr(m, "use_transparent_shadow"):
                    m.use_transparent_shadow = True


def plate_view(sc, opts):
    """City from Rin's window at dusk or dawn (backdrop for the room)."""
    from common import look_rotation, make_camera
    sky = opts.get("sky", "dusk")
    build(sc, place="balcony", city_lights=float(opts.get("lights", 0.3)), sky="dusk")
    if sky == "dawn":
        dawn_sky(sc)
        disk = bpy.data.objects.get("SunDisk")
        disk.data.materials[0].node_tree.nodes["Emission"].inputs["Color"].default_value = (1.0, 0.75, 0.4, 1)
    for nm in [o.name for o in bpy.data.objects if o.name.startswith(("Post", "Bar", "BalconySlab"))]:
        bpy.data.objects[nm].hide_render = True
    setup_compositor(sc, bloom=0.5, bloom_threshold=0.9, dispersion=0.0,
                     mist_color=(0.42, 0.11, 0.07) if sky == "dusk" else (0.5, 0.36, 0.25), mist_amount=0.42)
    sc.view_layers[0].use_pass_mist = True
    sc.world.mist_settings.start, sc.world.mist_settings.depth = 80, 2600
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


def climb(cards, beats, first, ahead=0.09):
    """Rin up the stairs, a step to the beat, as stop-motion: two drawings of the climb (`climb` "a": left foot
    up on the next step, "b": right foot up) take turns. On each beat after the first the drawing changes and
    she stands one step higher: the foot that was up is now the one she stands on, so it stays planted while
    the other comes through. Both the change and the move fall between two frames, so no frame smears them,
    and she settles a little into the new step. Shadow cards with the same `climb` follow the same keys.
    Her card stands `ahead` in front of the middle of the tread: from below, the nosing of the step she is on
    would otherwise hide her heels."""
    import bedding
    sw = [math.ceil(b * 24 - 1e-6) - 0.5 for b in beats[1:]]    # frame times of the changes
    for c, spec in cards:
        h = spec.get("h", 1.5)
        x = spec.get("loc", (0.0, 0.0, 0.0))[0]
        sink = bedding.drawing_floor(spec["pose"]) * h      # the drawing's margin under her lower sole
        parity = 0 if spec["climb"] == "a" else 1

        def at(k):
            return Vector((x, (first + k) * RUN - ahead, RISE * (first + k + 1) - sink))

        c.location = at(0)
        c.keyframe_insert("location", frame=sw[0] - 1 if sw else 1)
        c.hide_render = parity != 0
        c.keyframe_insert("hide_render", frame=sw[0] - 1 if sw else 1)
        for k, f in enumerate(sw, 1):
            c.location = at(k)
            c.keyframe_insert("location", frame=f)
            c.hide_render = k % 2 != parity
            c.keyframe_insert("hide_render", frame=f)
            for df, sx, sz in ((-0.01, 1.0, 1.0), (0.0, 1.015, 0.975), (2.5, 1.0, 1.0)):   # settling onto the step
                c.scale = (sx, 1.0, sz)
                c.keyframe_insert("scale", frame=f + df)
        act = c.animation_data.action
        curves = list(act.fcurves) if hasattr(act, "fcurves") else [
            fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
        for fc in curves:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT" if fc.data_path in ("location", "hide_render") else "LINEAR"
