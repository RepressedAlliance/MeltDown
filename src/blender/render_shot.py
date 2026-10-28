"""Render one storyboard shot with Blender.

blender -b --factory-startup -P render_shot.py -- <shot_id> [preview=1] [step=N] [frames=a-b] [still=u]

Frames are numbered on the song's global 24 fps timeline, so time-driven
shaders (traffic, plasma, static) stay continuous across cuts.
Output: work/render/<shot_id>/<frame>.png  (preview: work/preview/<shot_id>/...)
"""
import importlib
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import common  # noqa: E402
from character import add_card  # noqa: E402
from common import FPS, Shake, bake_camera, ease, sample_keys  # noqa: E402


def _keys_abs(keys, t0, dur):
    """Storyboard keys use u in [0,1] (fraction of shot) unless given as ('s', seconds)."""
    out = []
    for k in keys:
        u = k[0]
        t = u[1] if isinstance(u, (list, tuple)) else u * dur
        out.append((t,) + tuple(k[1:]))
    return out


def setup_camera(sc, shot, t0, dur, f0, f1):
    cam_spec = shot["cam"]
    cam = common.make_camera(sc, lens=cam_spec.get("lens", 35), clip=tuple(cam_spec.get("clip", (0.05, 12000))))
    keys = _keys_abs(cam_spec["keys"], t0, dur)
    kind = cam_spec.get("ease", "inout")
    pos_k = [(k[0], Vector(k[1]), kind) for k in keys]
    tgt_k = [(k[0], Vector(k[2]), kind) for k in keys]
    lens_k = [(k[0], k[3] if len(k) > 3 else cam_spec.get("lens", 35), kind) for k in keys]
    roll_k = [(k[0], k[4] if len(k) > 4 else cam_spec.get("roll", 0.0), kind) for k in keys]
    sh = cam_spec.get("shake")
    shake = Shake(seed=hash(shot["id"]) % 1000, amp=sh[0], rot_amp=sh[1], freq=sh[2]) if sh else None
    fstop = cam_spec.get("fstop")
    focus = cam_spec.get("focus", "target")

    def fn(t, f):
        p = sample_keys(pos_k, t)
        q = sample_keys(tgt_k, t)
        roll = sample_keys(roll_k, t)
        if t > dur:
            # a tail past the cut (the next shot dissolves in over it): keep the last velocity
            h = 1.0 / FPS
            p = p + (p - sample_keys(pos_k, dur - h)) * ((t - dur) / h)
            q = q + (q - sample_keys(tgt_k, dur - h)) * ((t - dur) / h)
        if shake:
            dp, dr = shake(t + t0)
            p = p + dp
            roll += dr
        s = {"pos": p, "target": q, "roll": roll, "lens": sample_keys(lens_k, t)}
        if fstop:
            s["fstop"] = fstop
            s["focus"] = (q - p).length if focus == "target" else float(focus)
        return s

    # bake one frame before/after for motion blur continuity
    bake_camera(sc, cam, f0 - 1, f1 + 1, lambda t, f: fn((f - f0) / FPS, f))
    return cam


def render_shot_constant(action):
    curves = list(action.fcurves) if hasattr(action, "fcurves") else [
        fc for layer in action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        if "blink" in fc.data_path:
            for kp in fc.keyframe_points:
                kp.interpolation = "CONSTANT"


def setup_cards(sc, shot, cam, f0, dur):
    objs = []
    for spec in shot.get("cards", []):
        rot = tuple(math.radians(a) for a in spec.get("rot", (90, 0, 0)))
        ob = add_card(spec["pose"], height=spec.get("h", 1.5), location=spec.get("loc", (0, 0, 0)),
                      rotation=rot, **spec.get("props", {}))
        if spec.get("tilt"):
            # a card lying on the bed leans along it (degrees about world X, through its origin): head end
            # up on the pillow, feet down on the mattress
            from mathutils import Matrix
            ob.rotation_euler = (Matrix.Rotation(math.radians(spec["tilt"]), 3, "X") @
                                 ob.rotation_euler.to_matrix()).to_euler()
        if spec.get("face_cam") == "full":
            c = ob.constraints.new("DAMPED_TRACK")
            c.target = cam
            c.track_axis = "TRACK_NEGATIVE_Y"
        elif spec.get("face_cam"):
            c = ob.constraints.new("LOCKED_TRACK")
            c.target = cam
            c.track_axis = "TRACK_NEGATIVE_Y"
            c.lock_axis = "LOCK_Z"
        # life: breathing (scale from the card's bottom edge) or a weightless drift for floating poses
        motion = spec.get("motion", "drift" if "float" in spec["pose"] else "breath")
        if motion and not spec.get("keys", {}).get("loc") and not spec.get("shadow_only"):
            import math as _m
            base_loc = ob.location.copy()
            base_rot = ob.rotation_euler.copy()
            ph = (hash(spec["pose"]) % 100) / 100 * 6.28
            n = int(dur * FPS) + 2
            for k in range(0, n + 6, 6):
                tt = (f0 + k) / FPS
                if motion == "breath":
                    sz = 1 + 0.007 * _m.sin(tt * 2 * _m.pi / 3.8 + ph)
                    ob.scale = (1.0, 1.0, sz)
                    ob.keyframe_insert("scale", index=2, frame=f0 + k)
                else:
                    ob.location = base_loc + Vector((0, 0, 0.035 * _m.sin(tt * 2 * _m.pi / 5.0 + ph)))
                    ob.keyframe_insert("location", frame=f0 + k)
                    if "rot_deg" not in spec.get("keys", {}):
                        ob.rotation_euler = (base_rot.x, base_rot.y + 0.03 * _m.sin(tt * 2 * _m.pi / 7.0 + ph),
                                             base_rot.z)
                        ob.keyframe_insert("rotation_euler", frame=f0 + k)
        if spec.get("blink"):
            import random
            rnd = random.Random(hash(spec["pose"]) % 997 + f0)
            fr = f0 + rnd.randint(12, 40)
            while fr < f0 + dur * FPS:
                for ff, v in ((fr - 1, 0.0), (fr, 1.0), (fr + 2, 1.0), (fr + 3, 0.0)):
                    ob["blink"] = v
                    ob.keyframe_insert('["blink"]', frame=ff)
                fr += rnd.randint(60, 100)
            act = ob.animation_data.action if ob.animation_data else None
            if act:
                render_shot_constant(act)
        for prop, keys in spec.get("keys", {}).items():
            for k in keys:
                u, v = k[0], k[1]
                f = f0 + (u[1] if isinstance(u, (list, tuple)) else u * dur) * FPS
                if prop in ("loc", "rot_deg"):
                    if prop == "loc":
                        ob.location = v
                        ob.keyframe_insert("location", frame=f)
                    else:
                        ob.rotation_euler = (math.radians(v[0] - 90), math.radians(v[1]), math.radians(v[2]))
                        ob.keyframe_insert("rotation_euler", frame=f)
                else:
                    ob[prop] = list(v) if isinstance(v, (list, tuple)) else v
                    ob.keyframe_insert(f'["{prop}"]', frame=f)
        if "blink" in spec.get("keys", {}) and ob.animation_data:
            # scripted eye opening/blinks swap images, never cross-fade them
            render_shot_constant(ob.animation_data.action)
        objs.append(ob)
    return objs


def prepare(shot_id, preview=False, pct=None, samples=None):
    import storyboard
    shots = storyboard.resolved()
    shot = next(s for s in shots if s["id"] == shot_id)
    # render_to: keep rendering past the cut when later inserts re-use this shot's frames (frames_from)
    # tail: a few frames past the cut for the next shot to dissolve over (the camera keeps moving)
    t0, t1 = shot["t0"], max(shot["t1"], shot.get("render_to", 0.0))
    dur = t1 - t0
    f0, f1 = int(round(t0 * FPS)), int(round((t1 + shot.get("tail", 0.0)) * FPS)) - 1
    sc = common.reset()
    r = shot.get("render", {})
    common.setup_render(sc, preview=preview, samples=(None if preview else r.get("samples")),
                        motion_blur=r.get("motion_blur", True), pct=int(pct or (50 if preview else 100)),
                        look=r.get("look", "AgX - Medium High Contrast"), exposure=r.get("exposure", 0.0))
    if preview:
        sc.eevee.taa_render_samples = int(samples or 8)
    sc.frame_start, sc.frame_end = f0, f1
    mod = importlib.import_module(f"scene_{shot['scene']}")
    objs = mod.build_shot(sc, shot) if hasattr(mod, "build_shot") else mod.build(sc, **shot.get("setup", {}))
    cam = setup_camera(sc, shot, t0, dur, f0, f1)
    cards = setup_cards(sc, shot, cam, f0, dur)
    if hasattr(mod, "animate"):
        mod.animate(sc, objs, shot, f0, f1, cards=cards, cam=cam)
    if "comp_blender" in shot:
        common.setup_compositor(sc, **shot["comp_blender"])
    return sc, shot, f0, f1


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    shot_id = argv[0]
    opts = dict(a.split("=", 1) for a in argv[1:])
    preview = opts.get("preview", "0") == "1"
    sc, shot, f0, f1 = prepare(shot_id, preview, opts.get("pct"), opts.get("samples"))
    out_root = common.ROOT / "work" / ("preview" if preview else "render") / shot_id
    if "still" in opts:
        f = f0 + int(float(opts["still"]) * (f1 - f0))
        out_root.mkdir(parents=True, exist_ok=True)
        sc.frame_set(f)
        sc.render.filepath = str(out_root / f"still_{f:05d}.png")
        bpy.ops.render.render(write_still=True)
        print("STILL_OK", sc.render.filepath)
        return
    a, b = f0, f1
    if "frames" in opts:
        a, b = (int(x) for x in opts["frames"].split("-"))
    common.render_frames(sc, out_root, a, b, step=int(opts.get("step", 1)))
    print("SHOT_OK", shot_id, a, b)


if __name__ == "__main__":
    main()
