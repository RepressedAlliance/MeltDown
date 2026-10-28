"""City layout shared by the 3D city (Blender) and the 2D map (compositor). No bpy here."""
import math
import random

import numpy as np


BLOCK = 78.0
STREET = 16.0
REACTOR_POS = (900.0, -1150.0, 0.0)
REACTOR_R = 170.0


def _buildings(seed, extent=1500.0, downtown=(-60.0, 420.0)):
    rnd = np.random.default_rng(seed)
    out = []
    pitch = BLOCK + STREET
    n = int(extent // pitch)
    for bx in range(-n, n + 1):
        for by in range(-3, int(2 * n)):
            cx, cy = bx * pitch, by * pitch - 120.0
            if cy < -230:  # waterfront
                continue
            d = math.hypot(cx - downtown[0], cy - downtown[1])
            # lots: split the block into 1..4 parcels
            k = rnd.integers(1, 5)
            parcels = [(cx, cy, BLOCK, BLOCK)]
            for _ in range(k - 1):
                x, y, w, h = parcels.pop(rnd.integers(len(parcels)))
                if w > h:
                    s = rnd.uniform(0.35, 0.65) * w
                    parcels += [(x - w / 2 + s / 2, y, s, h), (x + s / 2, y, w - s, h)]
                else:
                    s = rnd.uniform(0.35, 0.65) * h
                    parcels += [(x, y - h / 2 + s / 2, w, s), (x, y + s / 2, w, h - s)]
            for (x, y, w, h) in parcels:
                inset = rnd.uniform(2.0, 6.0)
                w2, h2 = max(6.0, w - 2 * inset), max(6.0, h - 2 * inset)
                core = math.exp(-d / 520.0)
                hgt = 12 + 190 * core * rnd.lognormal(0, 0.45) + rnd.uniform(0, 18)
                if rnd.random() < 0.06 * core:
                    hgt *= 1.6
                out.append((x, y, w2, h2, hgt))
                # a slimmer tower on top of some podiums
                if hgt > 70 and rnd.random() < 0.35:
                    out.append((x + rnd.uniform(-w2, w2) * 0.15, y + rnd.uniform(-h2, h2) * 0.15,
                                w2 * 0.55, h2 * 0.55, hgt * rnd.uniform(1.15, 1.45)))
    return out


def _highway_path(seed):
    rnd = random.Random(seed)
    pts = []
    for i in range(240):
        t = i / 239
        x = -1500 + 3000 * t
        y = 120 + 260 * math.sin(t * 3.1 + 0.4) + 90 * math.sin(t * 7.3 + 1.1)
        pts.append((x, y, 0))
    return pts


