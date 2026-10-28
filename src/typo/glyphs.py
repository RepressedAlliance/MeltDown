"""Glyph outlines and Japanese text layout straight from font files.

Text is turned into per-glyph skia paths so every character can be moved,
scaled, rotated or styled on its own. Vertical layout uses the font's own
'vert'/'vrt2' alternates and vmtx metrics; proportional spacing uses
'palt'/'vpal' when the font has them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import skia
from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
FONTS = ROOT / "assets" / "fonts"
CACHE = ROOT / "work" / "font_instances"

FACE_FILES = {
    "mincho": ("shipporiminchob1/ShipporiMinchoB1-Medium.ttf", None),
    "mincho_b": ("shipporiminchob1/ShipporiMinchoB1-ExtraBold.ttf", None),
    "mincho_r": ("shipporiminchob1/ShipporiMinchoB1-Regular.ttf", None),
    "oldmincho_k": ("zenoldmincho/ZenOldMincho-Black.ttf", None),
    "gothic_k": ("zenkakugothicnew/ZenKakuGothicNew-Black.ttf", None),
    "gothic_b": ("zenkakugothicnew/ZenKakuGothicNew-Bold.ttf", None),
    "gothic_m": ("zenkakugothicnew/ZenKakuGothicNew-Medium.ttf", None),
    "gothic_l": ("zenkakugothicnew/ZenKakuGothicNew-Light.ttf", None),
    "dela": ("delagothicone/DelaGothicOne-Regular.ttf", None),
    "code_jp": ("mplus1code/MPLUS1Code[wght].ttf", {"wght": 400}),
    "code_jp_l": ("mplus1code/MPLUS1Code[wght].ttf", {"wght": 200}),
    "mono": ("jetbrainsmono/JetBrainsMono[wght].ttf", {"wght": 400}),
    "mono_l": ("jetbrainsmono/JetBrainsMono[wght].ttf", {"wght": 200}),
    "mono_b": ("jetbrainsmono/JetBrainsMono[wght].ttf", {"wght": 700}),
    "shoulders": ("bigshoulders/BigShoulders[opsz,wght].ttf", {"wght": 800, "opsz": 72}),
    "shoulders_l": ("bigshoulders/BigShoulders[opsz,wght].ttf", {"wght": 300, "opsz": 72}),
    "serif_i": ("instrumentserif/InstrumentSerif-Italic.ttf", None),
    "serif": ("instrumentserif/InstrumentSerif-Regular.ttf", None),
}


class _SkPen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.path = skia.Path()

    def _moveTo(self, pt):
        self.path.moveTo(pt[0], -pt[1])

    def _lineTo(self, pt):
        self.path.lineTo(pt[0], -pt[1])

    def _curveToOne(self, p1, p2, p3):
        self.path.cubicTo(p1[0], -p1[1], p2[0], -p2[1], p3[0], -p3[1])

    def _qCurveToOne(self, p1, p2):
        self.path.quadTo(p1[0], -p1[1], p2[0], -p2[1])

    def _closePath(self):
        self.path.close()

    def _endPath(self):
        pass


def _lookups(table, feature_tags):
    tbl = table.table
    if not tbl.FeatureList:
        return []
    idx = []
    for fr in tbl.FeatureList.FeatureRecord:
        if fr.FeatureTag in feature_tags:
            idx.extend(fr.Feature.LookupListIndex)
    out = []
    for i in sorted(set(idx)):
        lk = tbl.LookupList.Lookup[i]
        for st in lk.SubTable:
            if lk.LookupType in (7, 9):  # extension
                out.append((st.ExtensionLookupType, st.ExtSubTable))
            else:
                out.append((lk.LookupType, st))
    return out


class Face:
    def __init__(self, key: str):
        rel, axes = FACE_FILES[key]
        path = FONTS / rel
        if axes:
            CACHE.mkdir(parents=True, exist_ok=True)
            tag = "_".join(f"{k}{v}" for k, v in sorted(axes.items()))
            inst = CACHE / f"{path.stem.split('[')[0]}_{tag}.ttf"
            if not inst.exists():
                from fontTools.varLib import instancer
                vf = TTFont(path)
                instancer.instantiateVariableFont(vf, axes, inplace=True)
                vf.save(inst)
            path = inst
        self.key = key
        self.tt = TTFont(path, lazy=True)
        self.upm = self.tt["head"].unitsPerEm
        self.cmap = self.tt.getBestCmap()
        self.gs = self.tt.getGlyphSet()
        self.hmtx = self.tt["hmtx"].metrics
        self.vmtx = self.tt["vmtx"].metrics if "vmtx" in self.tt else None
        os2 = self.tt["OS/2"]
        self.asc, self.desc = os2.sTypoAscender, os2.sTypoDescender
        self.vert = {}
        self.palt, self.vpal = {}, {}
        if "GSUB" in self.tt:
            for typ, st in _lookups(self.tt["GSUB"], ("vert", "vrt2")):
                if typ == 1:
                    self.vert.update(st.mapping)
        if "GPOS" in self.tt:
            for tags, dst in ((("palt",), self.palt), (("vpal",), self.vpal)):
                for typ, st in _lookups(self.tt["GPOS"], tags):
                    if typ != 1:
                        continue
                    glyphs = st.Coverage.glyphs
                    if st.Format == 1:
                        vals = [st.Value] * len(glyphs)
                    else:
                        vals = st.Value
                    for g, v in zip(glyphs, vals):
                        dst[g] = (getattr(v, "XPlacement", 0) or 0, getattr(v, "YPlacement", 0) or 0,
                                  getattr(v, "XAdvance", 0) or 0, getattr(v, "YAdvance", 0) or 0)
        self._paths = {}

    def gname(self, ch: str, vertical=False):
        g = self.cmap.get(ord(ch))
        if g is None:
            return None
        if vertical:
            g = self.vert.get(g, g)
        return g

    def path(self, g) -> skia.Path:
        p = self._paths.get(g)
        if p is None:
            pen = _SkPen(self.gs)
            self.gs[g].draw(pen)
            p = pen.path
            self._paths[g] = p
        return p

    def hadv(self, g):
        return self.hmtx[g][0]

    def vadv(self, g):
        return self.vmtx[g][0] if self.vmtx else self.upm

    def vorigin(self, g):
        """Vertical origin height (font units, y-up) for a glyph."""
        if self.vmtx and g in self.vmtx:
            tsb = self.vmtx[g][1]
            b = self.path(g).computeTightBounds()
            if b.height() > 0:
                return -b.top() + tsb
        return self.asc + (self.upm - (self.asc - self.desc)) / 2


@lru_cache(maxsize=None)
def face(key: str) -> Face:
    return Face(key)


@dataclass
class Glyph:
    ch: str
    index: int            # character index in the line
    path: skia.Path       # font units, y-down, origin at glyph origin
    x: float              # placement of glyph origin, px
    y: float
    scale: float          # px per font unit
    cx: float             # visual center, px (for pivots)
    cy: float
    adv: float            # advance in px along the writing direction
    rot: float = 0.0      # base rotation (deg), e.g. sideways latin in vertical text


@dataclass
class Block:
    glyphs: list[Glyph] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    vertical: bool = False


SKIP = set(" 　")


def layout(text: str, face_key: str, size: float, vertical=False, tracking=0.0,
           proportional=True) -> Block:
    """Lay out one line. Horizontal: origin at left of baseline-centred em box
    top. Vertical: origin at column centre top. Units: px."""
    f = face(face_key)
    s = size / f.upm
    blk = Block(vertical=vertical)
    pen = 0.0
    for i, ch in enumerate(text):
        g = f.gname(ch, vertical)
        if g is None:
            g = f.gname("　") or ".notdef"
        if not vertical:
            adv = f.hadv(g)
            dx = 0
            if proportional and g in f.palt:
                xp, _, xa, _ = f.palt[g]
                dx, adv = xp, adv + xa
            x = pen + dx * s
            y = f.asc * s  # baseline below the em-box top
            p = f.path(g)
            b = p.computeTightBounds()
            blk.glyphs.append(Glyph(ch, i, p, x, y, s, x + (b.centerX()) * s,
                                    y + b.centerY() * s, adv * s))
            pen += adv * s + tracking * size
        else:
            adv = f.vadv(g)
            dy = 0
            if proportional and g in f.vpal:
                _, yp, _, ya = f.vpal[g]
                dy, adv = -yp, adv + ya
            ha = f.hadv(g)
            x = -ha * s / 2
            y = pen + (f.vorigin(g) + dy) * s
            p = f.path(g)
            b = p.computeTightBounds()
            blk.glyphs.append(Glyph(ch, i, p, x, y, s, x + b.centerX() * s, y + b.centerY() * s, adv * s))
            pen += adv * s + tracking * size
    pen -= tracking * size if text else 0
    if vertical:
        blk.width, blk.height = size, pen
    else:
        blk.width, blk.height = pen, size
    blk.glyphs = [g for g in blk.glyphs if g.ch not in SKIP]
    return blk


def glyph_matrix(g: Glyph, dx=0.0, dy=0.0, scale=1.0, rot=0.0, sx=1.0, sy=1.0) -> skia.Matrix:
    """Matrix mapping glyph font units to px with an extra transform about the glyph centre."""
    m = skia.Matrix()
    m.setTranslate(g.cx + dx, g.cy + dy)
    m.preRotate(rot + g.rot)
    m.preScale(scale * sx, scale * sy)
    m.preTranslate(-g.cx, -g.cy)
    m.preTranslate(g.x, g.y)
    m.preScale(g.scale, g.scale)
    return m
