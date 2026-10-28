"""Shared Blender helpers: render setup, compositor, materials, cameras.

Every scene is built procedurally from scratch inside a factory-empty file,
so a shot render is fully reproducible from code.
"""
import math
import random
from pathlib import Path

import bpy
import mathutils
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
FPS = 24


# ---------------------------------------------------------------- scene setup

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    return sc


def setup_render(sc, preview=False, samples=None, motion_blur=True, res=(1920, 1080), pct=None,
                 look="AgX - Medium High Contrast", exposure=0.0, gamma=1.0):
    # each shader-compile worker owns a GL context; the auto count (one per core) costs gigabytes of commit
    try:
        bpy.context.preferences.system.gpu_shader_workers = 1
    except Exception:
        pass
    r = sc.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x, r.resolution_y = res
    r.resolution_percentage = pct or (50 if preview else 100)
    r.fps = FPS
    r.film_transparent = False
    r.filter_size = 1.2
    r.use_motion_blur = motion_blur
    r.motion_blur_shutter = 0.5
    r.dither_intensity = 1.0
    ee = sc.eevee
    # the printed look in the comp hides fine render noise, so finals need fewer samples
    ee.taa_render_samples = samples or (12 if preview else 32)
    ee.use_raytracing = True
    ee.ray_tracing_method = "SCREEN"
    ee.use_shadows = True
    ee.shadow_ray_count = 2
    ee.shadow_step_count = 8
    ee.volumetric_tile_size = "8" if preview else "4"
    ee.volumetric_samples = 48 if preview else 96
    ee.use_volumetric_shadows = True
    ee.motion_blur_steps = 1
    ee.bokeh_max_size = 64
    ee.use_fast_gi = True
    # smaller GPU pools keep the driver's mirrored system-memory footprint down
    try:
        ee.shadow_pool_size = "256" if not preview else "128"
        if preview:
            ee.volumetric_tile_size = "16"
            ee.volumetric_samples = 32
        else:
            # finals are halftone-printed in the comp: coarser froxels and half-res traces are invisible there
            ee.volumetric_tile_size = "8"
            ee.volumetric_samples = 64
            ee.ray_tracing_options.resolution_scale = "2"
        import os
        if os.environ.get("MV_VOLTILE"):
            ee.volumetric_tile_size = os.environ["MV_VOLTILE"]
            ee.volumetric_samples = int(os.environ.get("MV_VOLSAMPLES", "32"))
        if os.environ.get("MV_LOWMEM") == "1":
            ee.use_raytracing = False
            ee.use_fast_gi = False
            ee.shadow_pool_size = "128"
        ee.gi_irradiance_pool_size = "16"
    except Exception:
        pass
    vs = sc.view_settings
    vs.view_transform = "AgX"
    try:
        vs.look = look
    except TypeError:
        vs.look = "None"
    vs.exposure = exposure
    vs.gamma = gamma
    im = r.image_settings
    if preview:
        im.file_format = "PNG"
        im.color_mode = "RGB"
        im.color_depth = "8"
        im.compression = 15
    else:
        # finals go through the halftone print pass, so high-quality JPEG is indistinguishable and ~5x smaller
        im.file_format = "JPEG"
        im.color_mode = "RGB"
        im.quality = 95
    return sc


def setup_compositor(sc, bloom=0.35, bloom_threshold=0.9, bloom_size=0.75, streaks=0.0,
                     streak_threshold=2.5, dispersion=0.006, distortion=0.0, mist_color=None,
                     mist_amount=0.0):
    """Render layer -> optional mist fog -> bloom -> anamorphic streaks -> lens."""
    tree = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    N, L = tree.nodes, tree.links
    rl = N.new("CompositorNodeRLayers")
    cur = rl.outputs["Image"]
    if mist_color is not None and mist_amount > 0:
        sc.view_layers[0].use_pass_mist = True
        mix = N.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MIX"
        mul = N.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = mist_amount
        L.new(rl.outputs["Mist"], mul.inputs[0])
        L.new(mul.outputs[0], mix.inputs["Factor"])
        L.new(cur, mix.inputs["A"])
        mix.inputs["B"].default_value = (*mist_color, 1.0)
        cur = mix.outputs["Result"]
    if bloom > 0:
        g = N.new("CompositorNodeGlare")
        g.inputs["Type"].default_value = "Bloom"
        g.inputs["Quality"].default_value = "High"
        g.inputs["Threshold"].default_value = bloom_threshold
        g.inputs["Strength"].default_value = bloom
        g.inputs["Size"].default_value = bloom_size
        L.new(cur, g.inputs["Image"])
        cur = g.outputs["Image"]
    if streaks > 0:
        g = N.new("CompositorNodeGlare")
        g.inputs["Type"].default_value = "Streaks"
        g.inputs["Quality"].default_value = "High"
        g.inputs["Threshold"].default_value = streak_threshold
        g.inputs["Strength"].default_value = streaks
        g.inputs["Streaks"].default_value = 2
        g.inputs["Streaks Angle"].default_value = 0.0
        g.inputs["Fade"].default_value = 0.93
        L.new(cur, g.inputs["Image"])
        cur = g.outputs["Image"]
    if dispersion > 0 or distortion != 0:
        ld = N.new("CompositorNodeLensdist")
        ld.inputs["Distortion"].default_value = distortion
        ld.inputs["Dispersion"].default_value = dispersion
        try:
            ld.inputs["Fit"].default_value = True
        except Exception:
            pass
        L.new(cur, ld.inputs["Image"])
        cur = ld.outputs["Image"]
    out = N.new("NodeGroupOutput")
    L.new(cur, out.inputs[0])
    sc.compositing_node_group = tree
    return tree


def world_color(sc, color, strength=1.0, horizon=None):
    w = bpy.data.worlds.new("World")
    sc.world = w
    nt = w.node_tree if w.node_tree else None
    if nt is None:
        w.use_nodes = True
        nt = w.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    if horizon is None:
        bg.inputs["Color"].default_value = (*color, 1)
    else:
        # vertical gradient: zenith colour -> horizon colour
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        nt.links.new(tc.outputs["Generated"], sep.inputs[0])
        nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        ramp.color_ramp.elements[0].position = 0.48
        ramp.color_ramp.elements[0].color = (*horizon, 1)
        ramp.color_ramp.elements[1].position = 0.75
        ramp.color_ramp.elements[1].color = (*color, 1)
        nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return w


# ---------------------------------------------------------------- objects

def link(obj, coll=None):
    (coll or bpy.context.scene.collection).objects.link(obj)
    return obj


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def mesh_object(name, verts, faces, coll=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    return link(ob, coll)


def add_prim(kind, name, coll=None, **kw):
    """Primitive via bmesh ops into a fresh mesh (no bpy.ops context needed)."""
    import bmesh
    bm = bmesh.new()
    bm.loops.layers.uv.new("UVMap")
    if kind == "cube":
        bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    elif kind == "plane":
        bmesh.ops.create_grid(bm, x_segments=kw.get("xs", 1), y_segments=kw.get("ys", 1), size=0.5,
                              calc_uvs=True)
    elif kind == "cylinder":
        bmesh.ops.create_cone(bm, cap_ends=kw.get("caps", True), segments=kw.get("seg", 32),
                              radius1=kw.get("r", 0.5), radius2=kw.get("r2", kw.get("r", 0.5)),
                              depth=kw.get("depth", 1.0), calc_uvs=True)
    elif kind == "sphere":
        bmesh.ops.create_uvsphere(bm, u_segments=kw.get("seg", 24), v_segments=kw.get("rings", 12),
                                  radius=kw.get("r", 0.5), calc_uvs=True)
    elif kind == "torus":
        R, r = kw.get("R", 1.0), kw.get("r", 0.25)
        su, sv = kw.get("su", 96), kw.get("sv", 24)
        verts = []
        for i in range(su):
            a = 2 * math.pi * i / su
            for j in range(sv):
                b = 2 * math.pi * j / sv
                rr = R + r * math.cos(b)
                verts.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), r * math.sin(b))))
        for i in range(su):
            for j in range(sv):
                a = verts[i * sv + j]
                b2 = verts[((i + 1) % su) * sv + j]
                c = verts[((i + 1) % su) * sv + (j + 1) % sv]
                d = verts[i * sv + (j + 1) % sv]
                bm.faces.new((a, b2, c, d))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if kw.get("smooth"):
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    return link(ob, coll)


# ---------------------------------------------------------------- materials

def mat_emission(name, color, strength=1.0):
    m = bpy.data.materials.new(name)
    nt = m.node_tree if m.node_tree else None
    if nt is None:
        m.use_nodes = True
        nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def mat_principled(name, color, rough=0.5, metal=0.0, emission=None, emission_strength=0.0,
                   alpha=1.0, spec=0.5):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Specular IOR Level"].default_value = spec
    if emission is not None:
        p.inputs["Emission Color"].default_value = (*emission, 1)
        p.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        p.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    return m


def node_tree(m):
    if m.node_tree is None:
        m.use_nodes = True
    return m.node_tree


def frame_value_node(nt, name="time", scale=1.0 / FPS, offset=0.0):
    """A Value node driven by the current frame (seconds by default)."""
    v = nt.nodes.new("ShaderNodeValue")
    v.name = name
    d = v.outputs[0].driver_add("default_value").driver
    d.type = "SCRIPTED"
    d.expression = f"frame*{scale}+{offset}"
    return v


def assign(ob, mat):
    if ob.data.materials:
        ob.data.materials[0] = mat
    else:
        ob.data.materials.append(mat)
    return ob


# ---------------------------------------------------------------- camera

def make_camera(sc, name="Cam", lens=35.0, sensor=36.0, clip=(0.05, 6000.0)):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = sensor
    cd.clip_start, cd.clip_end = clip
    cam = link(bpy.data.objects.new(name, cd))
    sc.camera = cam
    return cam


def look_rotation(pos, target, roll_deg=0.0):
    d = (Vector(target) - Vector(pos)).normalized()
    q = d.to_track_quat("-Z", "Y")
    if roll_deg:
        q = q @ mathutils.Quaternion((0, 0, 1), math.radians(roll_deg))
    return q.to_euler()


def ease(t, kind="inout"):
    t = min(1.0, max(0.0, t))
    if kind == "linear":
        return t
    if kind == "in":
        return t * t * t
    if kind == "out":
        return 1 - (1 - t) ** 3
    if kind == "expo_out":
        return 1 - 2 ** (-10 * t) if t < 1 else 1.0
    if kind == "expo_in":
        return 2 ** (10 * (t - 1)) if t > 0 else 0.0
    return t * t * (3 - 2 * t) if kind == "smooth" else (4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2)


def lerp(a, b, t):
    if isinstance(a, (tuple, list, Vector)):
        return Vector(a).lerp(Vector(b), t)
    return a + (b - a) * t


def sample_keys(keys, t):
    """keys: list of (time, value, ease_kind_to_next). Returns value at t."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0, k), (t1, v1, _) in zip(keys, keys[1:]):
        if t <= t1:
            u = (t - t0) / max(1e-6, t1 - t0)
            return lerp(v0, v1, ease(u, k))
    return keys[-1][1]


class Shake:
    """Smooth handheld noise from summed sines (deterministic per seed)."""

    def __init__(self, seed=1, amp=0.02, rot_amp=0.3, freq=0.6):
        rnd = random.Random(seed)
        self.ph = [rnd.uniform(0, 100) for _ in range(12)]
        self.amp, self.rot_amp, self.freq = amp, rot_amp, freq

    def __call__(self, t):
        f, p = self.freq, self.ph
        def n(i):
            return (math.sin(t * f * 2.1 + p[i]) * 0.6 + math.sin(t * f * 3.7 + p[i + 1]) * 0.3
                    + math.sin(t * f * 7.3 + p[i + 2]) * 0.1)
        return Vector((n(0), n(3), n(6))) * self.amp, n(9) * self.rot_amp


def bake_camera(sc, cam, frame_start, frame_end, fn):
    """fn(t_seconds_in_shot, frame) -> dict(pos, target, roll, lens, focus, fstop)."""
    cd = cam.data
    for f in range(frame_start, frame_end + 1):
        t = (f - frame_start) / FPS
        s = fn(t, f)
        cam.location = s["pos"]
        cam.rotation_euler = look_rotation(s["pos"], s["target"], s.get("roll", 0.0))
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        if "lens" in s:
            cd.lens = s["lens"]
            cd.keyframe_insert("lens", frame=f)
        if "focus" in s:
            cd.dof.use_dof = True
            cd.dof.focus_distance = s["focus"]
            cd.dof.aperture_fstop = s.get("fstop", 2.8)
            cd.dof.keyframe_insert("focus_distance", frame=f)
            cd.dof.keyframe_insert("aperture_fstop", frame=f)
    act = cam.animation_data.action if cam.animation_data else None
    _linearize(act)
    if cd.animation_data and cd.animation_data.action:
        _linearize(cd.animation_data.action)


def _linearize(action):
    if action is None:
        return
    curves = []
    if hasattr(action, "fcurves"):
        curves = list(action.fcurves)
    else:  # layered actions (Blender 5.x)
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


def render_frames(sc, out_dir, frame_start, frame_end, step=1, skip_existing=True):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = ".jpg" if sc.render.image_settings.file_format == "JPEG" else ".png"
    # frames rendered with other settings (resolution, samples) are never reused
    r = sc.render
    sig = f"{r.resolution_x}x{r.resolution_y}@{r.resolution_percentage} s{sc.eevee.taa_render_samples}"
    sig_file = out_dir / ".settings"
    if not sig_file.exists() or sig_file.read_text().strip() != sig:
        skip_existing = False
        sig_file.write_text(sig)
    for f in range(frame_start, frame_end + 1, step):
        path = out_dir / f"{f:05d}{ext}"
        if skip_existing and path.exists() and path.stat().st_size > 0:
            continue
        sc.frame_set(f)
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)


def key_socket(sock, keys, f0, dur, fps=24):
    """Keyframe a node socket default_value from [(u, value), ...] (u = shot fraction)."""
    for u, v in keys:
        sock.default_value = v
        sock.keyframe_insert("default_value", frame=f0 + u * dur * fps)


def key_light(light_data, keys, f0, dur, fps=24):
    for u, v in keys:
        light_data.energy = v
        light_data.keyframe_insert("energy", frame=f0 + u * dur * fps)
