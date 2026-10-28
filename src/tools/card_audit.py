"""Is Rin whole on screen? Checks every character card of the given 3D shots at a few instants.

blender -b --factory-startup -P src/tools/card_audit.py -- S05[,S14,...] [out=work/qc/card_audit/<shot>.json]
(or run all card shots: python src/tools/card_audit.py --all, which starts one Blender per shot)

For each card the drawing's opaque pixels are sampled, placed on the card in the scene and
projected through the camera. Reported per instant:
  in_frame   share of her pixels inside the frame (a close-up crops on purpose, a wide shot should not)
  hidden     share hidden by scene geometry, and by what (a bed she sinks into, a table in front)
  cut_edge   pixels where the drawing runs into the border of its image (an arm or a sleeve that
             simply stops) that land inside the frame unhidden: the drawing's own edge is on screen
  gap        lowest visible part of her above the surface under it (sitting/lying cards float)
"""
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "blender"))
from drive_shots import BLENDER  # noqa: E402
U_SAMPLES = (0.03, 0.5, 0.97)


def _alpha_points(pose, step=6):
    """Opaque pixels of the drawing (every `step` px) as card UVs (s right, t up), and the opaque
    pixels that touch the image border, with the side they touch."""
    import bpy
    import numpy as np
    img = bpy.data.images.load(str(ROOT / "assets" / "char" / pose / "color.png"), check_existing=True)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    a = px.reshape(h, w, 4)[..., 3] > 0.5          # rows bottom-up, like UV t
    pts = [((x + 0.5) / w, (y + 0.5) / h) for y in range(0, h, step) for x in range(0, w, step) if a[y, x]]
    edge = []
    for side, rows, cols in (("bottom", (0, 1), None), ("top", (h - 2, h - 1), None),
                             ("left", None, (0, 1)), ("right", None, (w - 2, w - 1))):
        if rows:
            edge += [((x + 0.5) / w, (y + 0.5) / h, side) for y in rows for x in range(0, w, 2) if a[y, x]]
        else:
            edge += [((x + 0.5) / w, (y + 0.5) / h, side) for x in cols for y in range(0, h, 2) if a[y, x]]
    return pts, edge


def _see_through(ob):
    """Objects a ray should pass: glass, lace, shadow and light helpers, anything not rendered."""
    if ob.hide_render or not ob.visible_camera:
        return True
    for m in getattr(ob.data, "materials", []) or []:
        if m and getattr(m, "surface_render_method", "") == "BLENDED":
            return True
    return False


def audit_shot(shot_id):
    sys.path.insert(0, str(ROOT / "src" / "blender"))
    sys.path.insert(0, str(ROOT / "src"))
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    import render_shot

    sc, shot, f0, f1 = render_shot.prepare(shot_id, preview=True, pct=25)
    f_end = int(round(shot["t1"] * 24)) - 1          # judge the cut itself, not the tail rendered past it
    cam = sc.camera
    report = {"shot": shot_id, "t0": shot["t0"], "t1": shot["t1"], "cards": []}
    used = set()
    for spec in shot.get("cards", []):
        name = f"Rin_{spec['pose']}"
        ob = next((o for o in sc.objects if o.type == "MESH" and o.name not in used and
                   (o.name == name or o.name.startswith(name + "."))), None)
        if ob is None or spec.get("shadow_only"):
            continue
        used.add(ob.name)
        pts, edge = _alpha_points(spec["pose"])
        me = ob.data
        xs = [v.co.x for v in me.vertices]
        zs = [v.co.z for v in me.vertices]
        x0, x1, z0, z1 = min(xs), max(xs), min(zs), max(zs)
        rows = []
        for u in U_SAMPLES:
            f = int(round(f0 + u * (f_end - f0)))
            sc.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            mw = ob.evaluated_get(dg).matrix_world.copy()
            cpos = cam.evaluated_get(dg).matrix_world.translation.copy()

            def place(s, t):
                return mw @ Vector((x0 + (x1 - x0) * s, 0.0, z0 + (z1 - z0) * t))

            def blocker(p):
                d = p - cpos
                dist = d.length
                d.normalize()
                o, left = cpos.copy(), dist - 0.004
                for _ in range(8):
                    hit, loc, _n, _i, hob, _m = sc.ray_cast(dg, o, d, distance=left)
                    if not hit:
                        return None
                    hob = hob.original if hasattr(hob, "original") else hob
                    if hob.name == ob.name or not _see_through(hob):
                        return None if hob.name == ob.name else hob.name
                    step = (loc - o).length + 0.002
                    o, left = loc + d * 0.002, left - step
                    if left <= 0:
                        return None
                return None

            n_in, hidden, lowest = 0, {}, None
            for s, t in pts:
                p = place(s, t)
                v = world_to_camera_view(sc, cam, p)
                if v.z <= 0 or not (0 <= v.x <= 1 and 0 <= v.y <= 1):
                    continue
                n_in += 1
                b = blocker(p)
                if b:
                    hidden[b] = hidden.get(b, 0) + 1
                elif lowest is None or p.z < lowest.z:
                    lowest = p
            cut = {}
            for s, t, side in edge:
                p = place(s, t)
                v = world_to_camera_view(sc, cam, p)
                if v.z <= 0 or not (0.002 <= v.x <= 0.998 and 0.002 <= v.y <= 0.998):
                    continue
                if blocker(p):
                    continue
                c = cut.setdefault(side, {"n": 0, "frame_xy": []})
                c["n"] += 1
                if len(c["frame_xy"]) < 4:
                    c["frame_xy"].append([round(v.x, 3), round(1 - v.y, 3)])
            gap = None
            if lowest is not None:
                hit, loc, *_ = sc.ray_cast(dg, lowest + Vector((0, 0, -0.003)), Vector((0, 0, -1)), distance=3.0)
                gap = round(lowest.z - loc.z, 3) if hit else None
            n = max(1, len(pts))
            rows.append({"u": u, "frame": f, "in_frame": round(n_in / n, 3),
                         "hidden": {k: round(v / max(1, n_in), 3) for k, v in sorted(hidden.items(), key=lambda kv: -kv[1])},
                         "cut_edge": cut, "gap": gap})
        report["cards"].append({"pose": spec["pose"], "samples": rows})
    return report


def main_blender():
    argv = sys.argv[sys.argv.index("--") + 1:]
    shots = argv[0].split(",")
    opts = dict(a.split("=", 1) for a in argv[1:])
    out_dir = Path(opts.get("out", ROOT / "work" / "qc" / "card_audit"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for sid in shots:
        rep = audit_shot(sid)
        (out_dir / f"{sid}.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print("AUDIT_OK", sid)


def main_all():
    sys.path.insert(0, str(ROOT / "src"))
    import storyboard
    out_dir = ROOT / "work" / "qc" / "card_audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = [s["id"] for s in storyboard.resolved()
           if s.get("cards") and s.get("bg", "blender") == "blender" and not s.get("frames_from")]
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    for sid in (only[0].split(",") if only else ids):
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", __file__, "--", sid],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        ok = (out_dir / f"{sid}.json").exists() and "AUDIT_OK" in r.stdout
        print(sid, "ok" if ok else "FAILED\n" + r.stdout[-1500:] + r.stderr[-800:], flush=True)
    summarize(out_dir)


def summarize(out_dir):
    lines = []
    for p in sorted(out_dir.glob("S*.json")):
        rep = json.loads(p.read_text(encoding="utf-8"))
        for c in rep["cards"]:
            for r in c["samples"]:
                flags = []
                hid = sum(r["hidden"].values())
                if hid > 0.03:
                    flags.append("hidden %.0f%% by %s" % (100 * hid, ",".join(list(r["hidden"])[:3])))
                for side, info in r["cut_edge"].items():
                    flags.append(f"cut edge {side} x{info['n']} at {info['frame_xy'][:2]}")
                if r["gap"] is not None and r["gap"] > 0.03:
                    flags.append(f"floats {r['gap']:.2f} m")
                lines.append(f"{rep['shot']:6s} {c['pose']:20s} u={r['u']:.2f} in={r['in_frame']:.2f}  " +
                             ("; ".join(flags) if flags else "ok"))
    txt = "\n".join(lines)
    (out_dir / "summary.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    if "--" in sys.argv:
        main_blender()
    else:
        main_all()
