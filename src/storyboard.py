"""The film, shot by shot.

Each shot starts at `t` (seconds, snapped to the nearest beat unless free=True, then every cut to
the frame nearest an eighth note of the song's 165 BPM grid)
and runs until the next shot. Blender shots name a scene module + setup + camera
keys (u = fraction of the shot); 2D shots name a generator in comp/scenes2d.py.
Times refer to lyric lines through L(i) so the cut follows the singing.
Lyric typography is assigned per line in LYRIC_STYLES (independent of cuts).
"""
import math

from timeline import BEATS, DURATION, L, LINES, Le, beat_near, greet, on_grid

# ---------------------------------------------------------------- shared looks

NIGHT = dict(grade=dict(lift=(0.0, 0.004, 0.012), gain=(0.96, 1.0, 1.06), sat=1.05, contrast=1.04))
COREB = dict(grade=dict(lift=(0.0, 0.006, 0.02), gain=(0.92, 1.0, 1.1), sat=1.1, contrast=1.08),
             halation=dict(strength=0.12, color=(0.4, 0.7, 1.0)))
DAYW = dict(grade=dict(lift=(0.03, 0.03, 0.035), gain=(1.0, 0.99, 0.96), sat=0.7, contrast=1.0),
            halation=dict(strength=0.35, threshold=0.6), vignette=0.15)
DUSK = dict(grade=dict(lift=(0.01, 0.0, 0.01), gain=(1.08, 0.95, 0.86), sat=1.12, contrast=1.06),
            halation=dict(strength=0.3, color=(1.0, 0.4, 0.2)))
WHITE = dict(grade=dict(lift=(0.05, 0.055, 0.06), gain=(1.1, 1.1, 1.12), sat=0.7, contrast=0.95),
             halation=dict(strength=0.3, threshold=0.65, color=(0.8, 0.9, 1.0)))
MONO = dict(grade=dict(sat=0.12, contrast=1.25, gain=(1.0, 1.0, 1.02)), chroma=2.5,
            grain=dict(amount=0.05))
VOID = dict(grade=dict(lift=(0.0, 0.0, 0.006), gain=(0.82, 0.88, 1.0), sat=0.75, contrast=1.1), vignette=0.5)
# Rin asleep on her side on her bed, seen from above (S32, S65, S65b): the side-lying drawing (head on the
# left) lies across the bed, its top toward the room, her face over the front half of the pillow. The card
# leans 4 degrees along the bed (head end above the pillow, the rest just above the mattress), the quilt
# (bedding.py) is tucked over her up to the chest, raised over the covered part of her drawing, and a
# soft copy of her silhouette under the card grounds her on the sheet.
SLEEP_ON_BED = dict(h=0.85, loc=(0.107, 1.911, 0.475), rot=(0, 0, -90), tilt=4.0, motion="breath",
                    contact=dict(kind="lie"))
SLEEP_DENT = (0.11, -0.04, 0.12, 0.035)      # where her head presses the pillow (offset from its centre, x, y)
SLEEP_QUILT = dict(mode="tucked", edge=2.01, body=dict(pose="rin_sleep", h=0.85, loc=(0.107, 1.911, 0.475),
                                                     rot=(0, 0, -90), tilt=4.0))
# a sun low over the bed drags long dark shadows behind every fold of the quilt: lift it and soften it,
# and fill the room the way white walls do in daylight (the backs of the folds go grey without it)
BED_SUN = dict(elev=40, angle=6.0, energy=0.45)
MORNING_FILL = (0.42, 0.36, 0.3)
# seen from straight above, the drape over the bed head is only a stack of grey blades at the frame edge
OVERHEAD_HIDE = ["DrapeL"]
# lying on her back (S09, S54): the quilt up to her hips, her hands on her stomach above it
LIE_UP = dict(h=1.45, loc=(0.55, 1.024, 0.42), rot=(0, 0, 0), tilt=4.0, contact=dict(kind="lie"))
LIE_QUILT = dict(mode="tucked", edge=1.83, body=dict(pose="rin_lie_up", h=1.45, loc=(0.55, 1.024, 0.42),
                                                   rot=(0, 0, 0), tilt=4.0))
SIT = dict(kind="sit")   # a sitting card rests its drawing's lowest line on the quilt, a pressed blot under it
DAWN = dict(grade=dict(lift=(0.01, 0.005, 0.0), gain=(1.08, 1.0, 0.9), sat=1.08, contrast=1.02),
            halation=dict(strength=0.3, color=(1.0, 0.6, 0.3)))

PLATE = "assets/plates/city_window_night.png"
R = 12.0  # core major radius


def ring_pos(a, r, z):
    return (r * math.cos(a), r * math.sin(a), z)


SHOTS = []


def S(id, t, **kw):
    SHOTS.append(dict(id=id, t=t, **kw))


# ================================================================ INTRO 0 -> first line
# The way in is one continuous movement: the title ring dissolves into the ring lamp above her bed,
# the lamp's ring opens into her iris, we fall through the city in her eye, dive between the towers,
# fly through a lit window into her room; from there soft dissolves (each outgoing 3D shot renders a
# `tail` past its cut so it keeps moving under the dissolve) carry her gaze to the reactor, the title,
# the reactor again, her lying awake, and her standing at the window when she starts to sing.
# Every camera here moves forward at a steady pace (linear, no easing, nothing pulls back), and every
# dissolve or dolly-through hands one forward movement to the next: one push from the title to the
# first line, never a stop.
def _push(z0, z1, n=6, accel=0.0):
    """Keys for a 2D zoom that grows at a steady rate (exponential), or speeds up smoothly (accel > 0)."""
    import math
    a = math.log(z1 / z0)
    return [(k / n, round(z0 * math.exp(a * ((1 - accel) * k / n + accel * (k / n) ** 2)), 4))
            for k in range(n + 1)]


S("S00", 0.0, free=True, bg="ring", bg_args=dict(radius=230), hud=dict(level=2, alpha=0.8), finish=NIGHT,
  fx=[{"type": "zoom", "z": _push(1.0, 1.5)}])
S("S01", 3.6, scene="room", setup=dict(tod="night_lamp"), finish=NIGHT, in_="dissolve", in_dur=0.7,
  hud=dict(level=1, alpha=0.6),
  render=dict(exposure=-1.6),
  # rising towards the ring lamp, turning slowly, until the ring fills the frame and opens into her eye
  cam=dict(keys=[(0, (0.61, 1.5, 0.55), (0.6, 1.551, 2.3), 30, 0), (1, (0.6, 1.53, 1.25), (0.6, 1.552, 2.3), 30, 35)],
           ease="linear"),
  anim=dict(lamp=[(0, 1.0), (0.97, 1.0), (1.0, 0.0)]))
S("S02", 7.41, bg="eye", bg_args=dict(city_plate=PLATE, zoom=(1.04, 1.22), light=0.42), in_="flash", finish=NIGHT,
  fx=[{"type": "zoom", "z": _push(1.0, 3.2, accel=0.48), "cy": 40}])
S("S03", 9.6, scene="city", finish=NIGHT, in_="zoom", in_dur=0.4, tail=0.4,
  cam=dict(keys=[(0, (-900, 1700, 300), (-300, 900, 120), 28), (1, (-250, 980, 210), (380, 120, 60), 32)],
           ease="linear", shake=(0.6, 0.15, 0.4)))
# down a street canyon (y = 115 runs between two rows of blocks, 10 m clear of every wall; the old line
# cut through the buildings), tilting up to the lit high floors as it nears her block
S("S04", 11.8, scene="city", finish=NIGHT, in_="zoom", in_dur=0.4, tail=0.5,
  cam=dict(keys=[(0, (-760, 115, 22), (-460, 115.5, 26), 22), (1, (-520, 115, 30), (-230, 117, 75), 22)],
           ease="linear", shake=(0.12, 0.25, 1.5)))
S("S05", 13.82, scene="room", setup=dict(tod="night", clock="0200", rake=True), finish=NIGHT, in_="zoom", in_dur=0.4,
  tail=0.65,
  cam=dict(keys=[(0, (3.25, 0.3, 1.27), (0.8, 2.3, 0.85), 24), (1, (2.75, 0.8, 1.12), (0.75, 2.25, 0.8), 27)],
           fstop=4.0, ease="linear"),
  # she sits in the middle of the bed facing the window, clear of the pillow; the card turns to the camera
  cards=[dict(pose="rin_sit_knees", h=1.05, loc=(0.6, 1.45, 0.38), rot=(90, 0, 90), face_cam=True,
              contact=SIT,
              props=dict(key_dir=(0.8, 0.25, 0.4), key_col=(0.42, 0.52, 0.8), amb_col=(0.08, 0.09, 0.15),
                         rim_dir=(0.9, 0.2, 0), rim_col=(0.7, 0.82, 1.2), exposure=1.0))])
# out of her window towards the reactor: it starts where her window showed it (upper right, the same
# size), so the room dissolves away around it, then the camera flies on and turns until it is ahead
S("S06", 16.0, scene="city", finish=NIGHT, in_="dissolve", in_dur=0.6, tail=0.5,
  cam=dict(keys=[(0, (-133.2, -190.6, 80), (332.6, -347.6, -11.4), 35), (1, (299.1, -592.0, 70), (673.0, -921.4, 28.2), 35)],
           ease="linear", shake=(0.15, 0.03, 0.5)), hud=dict(level=1, alpha=0.8))
S("S07", 18.3, scene="city", finish=NIGHT, setup=dict(comp=dict(streaks=0.0)), in_="dissolve", in_dur=0.5,
  in_bloom=0.35, tail=0.45,
  cam=dict(keys=[(0, (-60, 450, 1000), (-60, 450.5, 0), 24, 0), (1, (-60, 430, 700), (-60, 430.5, 0), 24, 18)],
           ease="linear"))
S("S08", 22.7, scene="core", setup=dict(mood="blue", exterior=True), finish=COREB, in_="dissolve", in_dur=0.45,
  tail=0.6,
  cam=dict(keys=[(0, (44, -30, 8), (0, 0, -1), 35), (1, (32, -22, 5.5), (0, 0, -1), 35)], ease="linear"),
  anim=dict(plasma=[(0, 0.35), (1, 0.6)]))
S("S09", 26.0, scene="room", setup=dict(tod="night_lamp", pillow_dent=(0.0, -0.03, 0.12, 0.035), quilt=LIE_QUILT,
                                         hide=OVERHEAD_HIDE),
  finish=NIGHT, render=dict(exposure=-1.8), in_="dissolve", in_dur=0.45, tail=0.6,
  cam=dict(keys=[(0, (0.55, 1.95, 2.06), (0.551, 1.95, 0.4), 32, 0), (1, (0.55, 1.95, 1.86), (0.551, 1.95, 0.4), 35, 14)],
           ease="linear"),
  cards=[dict(pose="rin_lie_up", **LIE_UP,
              props=dict(key_dir=(0.0, 0.3, 0.9), key_col=(0.5, 0.55, 0.62), amb_col=(0.25, 0.28, 0.36),
                         rim_col=(0.0, 0.0, 0.0), exposure=1.0))])
# the bar before the first line (about the city lights at night): Rin at the window, her hand on the
# glass, a silhouette against the city, its lights melting into bokeh behind her
S("S10", 29.08, scene="room", setup=dict(tod="night"), finish=NIGHT, hud=dict(level=1, alpha=0.7), in_="dissolve",
  in_dur=0.45, tail=0.4,
  cam=dict(keys=[(0, (2.12, 0.92, 1.33), (1.55, 2.7, 1.26), 38), (1, (1.94, 1.18, 1.34), (1.5, 2.7, 1.26), 41)],
           fstop=2.0, ease="linear"),
  cards=[dict(pose="rin_window_back", h=0.95, loc=(1.25, 2.45, 0.6), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(-0.3, 0.2, 0.6), key_col=(0.18, 0.2, 0.32), amb_col=(0.06, 0.07, 0.12),
                         rim_dir=(1, 0.3, 0), rim_col=(1.0, 0.7, 0.4), exposure=1.0))])

# ================================================================ A1
S("S11", lambda: L(0) - 0.25, scene="room", setup=dict(tod="night"), finish=NIGHT,
  cam=dict(keys=[(0, (1.75, 1.15, 1.03), (1.0, 2.15, 1.0), 48), (1, (1.68, 1.25, 1.02), (1.0, 2.15, 1.02), 50)],
           fstop=2.2),
  render=dict(samples=64),
  cards=[dict(pose="rin_face_close", h=0.62, loc=(1.0, 2.2, 0.62), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.7, 0.2, 0.5), key_col=(0.32, 0.38, 0.55), amb_col=(0.12, 0.13, 0.2),
                         rim_dir=(-0.9, 0.3, 0), rim_col=(1.0, 0.62, 0.35), exposure=1.0))])
S("S12", lambda: L(2) - 0.2, scene="room", setup=dict(tod="night", clock="0200"), finish=NIGHT,
  cam=dict(keys=[(0, (2.58, 1.98, 0.8), (2.65, 2.274, 0.75), 85), (1, (2.62, 2.06, 0.79), (2.65, 2.274, 0.75), 100)],
           fstop=1.8))
S("S13", lambda: L(3) - 0.2, scene="city", finish=NIGHT, fx=[{"type": "strobe", "amount": 0.25}],
  cam=dict(keys=[(0, (-1300, 300, 90), (-600, 300, 40), 18), (1, (300, 300, 70), (1000, 280, 30), 18)],
           ease="in", shake=(0.5, 0.4, 2.0)))

# ================================================================ A2
S("S14", lambda: L(4) - 0.2, scene="room", setup=dict(tod="night"), finish=NIGHT,
  cam=dict(keys=[(0, (2.3, 1.3, 1.02), (2.75, 1.85, 0.97), 55), (1, (2.36, 1.38, 1.02), (2.75, 1.85, 0.97), 60)],
           fstop=2.0),
  cards=[dict(pose="rin_lighter_hand", h=0.32, loc=(2.75, 1.86, 0.76), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.5, 0.5, 0.6), key_col=(0.35, 0.3, 0.3), amb_col=(0.1, 0.1, 0.14),
                         rim_dir=(0, 1, 0), rim_col=(1.0, 0.55, 0.25), exposure=1.0))],
  # spark origin tracked from the render: the opening of the lighter hood, above the flint wheel
  fx=[{"type": "sparks", "angles": (-2.0, -0.35),
       "x": [(0.0, 1300), (0.2, 1302), (0.3, 1308), (0.4, 1320), (0.5, 1340), (0.6, 1364), (0.7, 1378),
             (0.8, 1387), (0.9, 1390), (1.0, 1391)],
       "y": [(0.0, 316), (0.1, 312), (0.2, 308), (0.3, 303), (0.4, 296), (0.5, 284), (0.6, 272), (0.7, 266),
             (0.8, 265), (1.0, 265)]}])
S("S15", lambda: L(5) - 0.2, scene="room", setup=dict(tod="night"), finish=NIGHT,
  fx=[{"type": "heat", "amount": 3.0}],
  # wide enough for her bow and the hand on her stomach together; the camera creeps in while the lens
  # widens a touch, so the frame holds both and only the room behind her tightens
  cam=dict(keys=[(0, (1.62, 1.5, 0.88), (1.0, 2.2, 0.96), 30), (1, (1.56, 1.57, 0.88), (1.0, 2.2, 0.96), 29)],
           fstop=2.0),
  render=dict(samples=64),
  # the line about a burning stomach: she presses a hand to it, wincing. Drawn with both arms inside the canvas and
  # staged at its own resolution, sized so her eyes fall where rin_face_close's do (src/char/fit_card.py)
  cards=[dict(pose="rin_wince", h=0.6846, loc=(1.0066, 2.2058, 0.5833), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.8, -0.3, 0.5), key_col=(0.9, 0.45, 0.2), amb_col=(0.1, 0.08, 0.1),
                         rim_dir=(-0.9, 0.3, 0), rim_col=(0.4, 0.55, 1.0), exposure=1.05))])
S("S15b", lambda: L(5) + 1.25, bg="chest_core", bg_args=dict(pose="rin_float"), finish=NIGHT,
  fx=[{"type": "zoom", "z": [(0, 1.0), (1, 1.12)]}, {"type": "heat", "amount": 2.0}])
S("S16", lambda: L(6) - 0.2, scene="room", setup=dict(tod="night"), finish=NIGHT,
  cam=dict(keys=[(0, (2.75, 1.85, 1.25), (2.0, 2.75, 1.25), 40), (1, (2.65, 1.95, 1.25), (1.9, 2.75, 1.25), 42)],
           fstop=2.8, focus=1.3),
  fx=[{"type": "darken", "rect": (630, 600, 890, 1080), "feather": 25, "amount": 0.9},
      {"type": "darken", "rect": (900, 860, 1920, 1080), "feather": 90, "amount": 0.45},
      {"type": "ghost", "pose": "rin_face_close", "x": 1180, "y": 640, "scale": 1.05, "opacity": 0.75,
       "holdout": 0.8, "drift": -60},
      {"type": "zoom", "z": [(0, 1.0), (1, 1.07)], "cx": 220, "cy": 60}, {"type": "kick", "amount": 0.008}])

# ================================================================ B1 (white afternoon dream)
S("S17", lambda: L(8) - 0.2, scene="room", setup=dict(tod="morning", wind=0.8, plate=None, world=(2.2, 2.2, 2.3)), finish=DAYW, in_="white",
  fx=[{"type": "exposure", "ev": -0.2}],
  # the line about a violent dream: in the white afternoon she stares at her own open hands. Medium shot
  # wide enough to hold her bow and both hands the whole time (a tighter push left a sliver of the bow
  # on the top edge), creeping in only a little
  cam=dict(keys=[(0, (1.57, 1.55, 0.95), (1.0, 2.2, 0.985), 29), (1, (1.56, 1.56, 0.95), (1.0, 2.2, 0.985), 30.5)],
           fstop=2.8),
  render=dict(samples=64),
  cards=[dict(pose="rin_hands", h=0.755, loc=(1.0, 2.2, 0.507), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.6, 0.3, 0.5), key_col=(0.6, 0.58, 0.55), amb_col=(0.55, 0.55, 0.6),
                         rim_dir=(0.9, 0.2, 0), rim_col=(0.45, 0.45, 0.47), exposure=1.0))])
S("S18", lambda: L(9) - 0.2, bg="eye", bg_args=dict(city_plate=None, zoom=(1.1, 1.3), tear=0.7, light=1.0),
  finish=DAYW, fx=[{"type": "strobe", "amount": 0.35}])
S("S19", lambda: L(10) - 0.2, scene="room", setup=dict(tod="morning", wind=1.0, plate=None, world=(2.2, 2.2, 2.3)), finish=DAYW,
  fx=[{"type": "exposure", "ev": -0.3}],
  cam=dict(keys=[(0, (1.9, 1.3, 1.0), (1.0, 2.2, 0.96), 70), (1, (1.8, 1.4, 1.0), (1.0, 2.2, 0.96), 74)],
           fstop=2.0),
  render=dict(samples=64),
  cards=[dict(pose="rin_profile_close", h=0.55, loc=(1.0, 2.2, 0.72), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.5, 0.4, 0.7), key_col=(0.6, 0.6, 0.6), amb_col=(0.6, 0.6, 0.65),
                         rim_dir=(1, 0, 0), rim_col=(0.45, 0.45, 0.47), exposure=1.0))])
S("S20", lambda: L(11) - 0.2, scene="room", setup=dict(tod="morning", plate=None, world=(2.2, 2.2, 2.3)), finish=DAYW,
  fx=[{"type": "exposure", "ev": [(0, -0.3), (0.7, 0.2), (1, 1.6)]}, {"type": "glitch", "on": [(0, 0), (0.6, 0), (0.62, 1), (1, 1)],
                                                         "amount": 1.0}],
  hud=dict(level=1, alarm=True),
  # from her whole head, bow included, a decisive push to her eyes
  cam=dict(keys=[(0, (1.62, 1.5, 0.98), (1.0, 2.2, 1.0), 37), (1, (1.42, 1.73, 0.95), (1.0, 2.2, 0.95), 78)],
           fstop=2.0),
  render=dict(samples=64),
  # the line about eyes close to tears: tears welling on the lower lids (aligned to rin_face_close)
  cards=[dict(pose="rin_teary", h=0.62, loc=(1.0, 2.2, 0.62), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.5, 0.4, 0.7), key_col=(0.6, 0.6, 0.6), amb_col=(0.6, 0.6, 0.65),
                         rim_dir=(-1, 0, 0), rim_col=(0.45, 0.45, 0.47), exposure=1.0))])
S("S21", 66.22, bg="white", bg_args=dict(level=1.0), finish=WHITE, hud=dict(level=2, alarm=True, col=(0.9, 0.1, 0.08)),
  out="black", out_dur=0.15)

# ================================================================ CHORUS 1 (blue core)
S("S22", 67.98, scene="city", finish=COREB, in_="flash",
  cam=dict(keys=[(0, (900, -1150, 1900), (900, -1149.5, 0), 22, 0), (1, (900, -1150, 70), (900, -1149.5, 0), 16, 60)],
           ease="in"),
  anim=dict(facility=[(0, 1.0), (1, 3.0)]))
S("S23", lambda: L(13) - 0.15, scene="core", setup=dict(mood="blue"), finish=COREB, in_="white", in_dur=0.2,
  cam=dict(keys=[(0, ring_pos(0.0, R + 1.6, 0.5), ring_pos(0.35, R, 0.0), 20, -5),
                 (1, ring_pos(0.55, R + 1.6, 0.4), ring_pos(0.9, R, 0.0), 20, 8)], ease="linear",
           shake=(0.03, 0.4, 1.2)))
# the floating shots (S24, S40, S59) open on her whole figure, bow to feet inside the frame, and push in
# to a cut at mid-thigh; the aim rises with the push so her bow keeps its margin under the top edge
S("S24", lambda: L(14) - 0.15, scene="core", setup=dict(mood="blue"), finish=COREB,
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.4, 0.5), ring_pos(0.16, R + 2.2, 0.03), 25.6, -6),
                 (1, ring_pos(0.03, R + 2.5, 0.3), ring_pos(0.16, R + 2.2, 0.34), 36, -2)], fstop=2.0),
  cards=[dict(pose="rin_float", h=1.7, loc=ring_pos(0.16, R + 2.2, -0.9), rot=(90, -10, 0), face_cam=True,
              props=dict(key_dir=(-0.7, 0.3, 0.6), key_col=(0.25, 0.5, 0.85), amb_col=(0.12, 0.18, 0.35),
                         rim_dir=(-0.9, 0.2, 0.0), rim_col=(0.55, 0.85, 1.0), exposure=1.0),
              keys={"rot_deg": [(0, (90, -10, 0)), (1, (90, 6, 0))]})])
S("S25", lambda: L(15) - 0.15, scene="core", setup=dict(mood="blue", exterior=True), finish=COREB,
  cam=dict(keys=[(0, (36, -24, 12), (0, 0, -1), 30), (0.5, (40, 6, 16), (0, 0, -1), 30),
                 (1, (30, 30, 10), (0, 0, -1), 30)], ease="inout"),
  anim=dict(plasma=[(0, 0.8), (1, 1.4)]))
S("S26", lambda: L(16) - 0.15, scene="core", setup=dict(mood="blue"), finish=COREB,
  # seen from below she fills the frame fast: the aim sits high and the camera creeps only half as far,
  # so her raised hand and bow stay under the top edge
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.0, -2.6), ring_pos(0.08, R + 1.6, 1.1), 24, 0),
                 (1, ring_pos(0.01, R + 2.0, -2.5), ring_pos(0.08, R + 1.4, 1.3), 23, 10)], fstop=2.8,
           focus="card", focus_at=0.78),
  cards=[dict(pose="rin_float_reach", h=1.7, loc=ring_pos(0.08, R + 1.8, -1.3), rot=(90, 0, 0), face_cam="full",
              props=dict(key_dir=(0.0, 0.8, 0.5), key_col=(0.3, 0.6, 1.0), amb_col=(0.1, 0.16, 0.3),
                         rim_dir=(0, 1, 0), rim_col=(0.7, 0.9, 1.0), exposure=1.0))])
S("S27", lambda: L(17) - 0.15, scene="core", setup=dict(mood="blue"), finish=COREB,
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.4, 0.3), ring_pos(0.05, R + 2.3, 0.15), 70),
                 (1, ring_pos(0.008, R + 2.38, 0.3), ring_pos(0.05, R + 2.3, 0.15), 80)], fstop=1.8,
           focus="card", focus_at=0.56),
  # the line about being forgiven: lids lowered, a faint smile (aligned to rin_face_close)
  cards=[dict(pose="rin_serene", h=0.62, loc=ring_pos(0.05, R + 2.3, -0.2), rot=(90, 0, 0), face_cam="screen",
              blink=True,
              props=dict(key_dir=(-0.8, 0.2, 0.5), key_col=(0.3, 0.55, 0.9), amb_col=(0.12, 0.17, 0.3),
                         rim_dir=(-1, 0.2, 0), rim_col=(0.6, 0.9, 1.0), exposure=1.0))])

# ================================================================ INTERLUDE
S("S28", 92.73, bg="hudmap", finish=NIGHT, hud=dict(level=2))
S("S29", 97.1, scene="dusk", setup=dict(place="balcony"), finish=DUSK, in_="glitch",
  fx=[{"type": "zoom", "z": [(0, 1.0), (1, 1.1)], "cy": -280}, {"type": "heat", "amount": 2.0}],
  cam=dict(keys=[(0, (1499.0, 901.5, 151.3), (900, -1150, 40), 135), (1, (1499.0, 901.5, 151.3), (900, -1150, 60), 120)],
           ease="inout", shake=(0.0, 0.05, 0.3)))

# ================================================================ A3 / A4 (dusk)
# from her whole figure with a strip of the balcony floor under her feet, a slow push and tilt up to a
# cut at mid-thigh (the old push ended on her boot tops, a crop at the knee)
S("S30", 102.55, scene="dusk", setup=dict(place="balcony"), finish=DUSK,
  cam=dict(keys=[(0, (1501.6, 902.3, 151.25), (1490, 886, 149.5), 32), (1, (1501.2, 901.7, 151.45), (1490, 886, 151.1), 36)],
           fstop=4.0),
  cards=[dict(pose="rin_back_stand", h=1.5, loc=(1499.6, 899.5, 150.0), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.0, 0.3, -0.6), key_col=(0.2, 0.1, 0.1), amb_col=(0.25, 0.14, 0.14),
                         rim_dir=(0.2, 0.9, 0), rim_col=(1.0, 0.45, 0.2), exposure=1.0))])
S("S31", lambda: L(19) - 0.2, scene="dusk", setup=dict(place="stairs"), finish=DUSK,
  cam=dict(keys=[(0, (0.15, -1.6, 0.55), (-0.1, 2.6, 2.2), 22), (1, (0.15, -1.2, 0.62), (-0.1, 2.6, 2.3), 22)]),
  anim=dict(step_beats=True))
# the dusk verse begins: she lies awake in the sunset and the light
# drains from her face over the line. Exactly the framing of the last morning (S65b), where she lies there
# asleep; she blinks with the sleeping drawing (color_blink = rin_sleep). Staged as SLEEP_ON_BED (below).
S("S32", lambda: L(20) - 0.2, scene="room", setup=dict(tod="dusk", pillow_dent=SLEEP_DENT, quilt=SLEEP_QUILT,
                                                       hide=OVERHEAD_HIDE,
                                                       sun=dict(elev=30, angle=6.0, energy=0.6),
                                                       world=(0.38, 0.24, 0.2)), finish=DUSK,
  cam=dict(keys=[(0, (0.62, 2.24, 1.6), (0.621, 2.24, 0.47), 30, 0), (1, (0.62, 2.25, 1.58), (0.621, 2.25, 0.47), 31, 3)],
           fstop=8.0),
  render=dict(samples=64),
  cards=[dict(pose="rin_sleep_awake", **SLEEP_ON_BED, blink=True,
              props=dict(key_dir=(0.3, 0.7, 0.6), key_col=(0.0, 0.0, 0.0), amb_col=(1.12, 0.68, 0.55),
                         rim_dir=(0, 1, 0), rim_col=(0.0, 0.0, 0.0), exposure=1.0),
              keys={"amb_col": [(0, (1.12, 0.68, 0.55)), (0.35, (1.05, 0.64, 0.52)), (1, (0.6, 0.37, 0.43))]})],
  anim=dict(window_light=[(0, 160.0), (0.35, 150.0), (1, 40.0)]))
S("S33", lambda: L(22) - 0.2, scene="dusk", setup=dict(place="balcony"), finish=DUSK,
  fx=[{"type": "heat", "amount": 4.0}],
  cam=dict(keys=[(0, (1499.0, 901.5, 151.3), (900, -1150, 120), 160),
                 (1, (1499.0, 901.5, 151.3), (900, -1150, 95), 200)]))
# the line about the setting sun: her eye, swollen from crying, the setting sun and
# the city in its iris
S("S33b", lambda: L(23) - 0.2, bg="eye",
  bg_args=dict(pose="rin_eye_macro_teary", city_plate="assets/plates/city_window_dusk.png", zoom=(1.06, 1.24),
               reflect=1.1, light=1.0),
  finish=DUSK, fx=[{"type": "heat", "amount": 1.5}])
S("S34", lambda: L(24) - 0.2, scene="dusk", setup=dict(place="balcony", lights=0.15), finish=DUSK,
  fx=[{"type": "melt", "amount": [(0, 0.0), (1, 0.85)]}, {"type": "heat", "amount": 2.5}],
  cam=dict(keys=[(0, (1499.0, 901.5, 152.0), (300, -900, 80), 50), (1, (1499.0, 901.5, 152.0), (300, -900, 70), 55)]))

# ================================================================ B2 (blue hour, curtains, bubbles)
S("S35", lambda: L(26) - 0.2, scene="room", setup=dict(tod="night", wind=1.2, rake=True, hide=[
    "Lace", "DeskTop", "DeskLeg", "DeskLeg.001", "DeskLeg.002", "DeskLeg.003", "DeskClock", "DeskClockDisplay",
    "Lighter", "Glass"]), finish=NIGHT,
  # the camera sits far enough left that the reactor ring stays inside one pane of the window
  cam=dict(keys=[(0, (2.6, 0.5, 1.32), (1.0, 2.3, 1.0), 24), (1, (2.52, 0.6, 1.29), (0.97, 2.3, 0.98), 25)], fstop=3.2),
  cards=[dict(pose="rin_sit_knees", h=1.05, loc=(0.6, 1.45, 0.38), rot=(90, 0, 90), face_cam=True,
              contact=SIT,
              props=dict(key_dir=(0.8, 0.25, 0.4), key_col=(0.42, 0.52, 0.85), amb_col=(0.09, 0.1, 0.17),
                         rim_dir=(0.9, 0.2, 0), rim_col=(0.7, 0.82, 1.2), exposure=1.0))])
# the line about words spilling from her lips: a tighter profile, lips parted as she murmurs.
# The card is sized so her eye sits where the old profile's did (the drawing has less shoulder).
S("S36", lambda: L(28) - 0.25, scene="room", setup=dict(tod="night", wind=0.6), finish=NIGHT,
  cam=dict(keys=[(0, (1.95, 1.05, 1.06), (1.0, 2.2, 1.08), 62), (1, (1.88, 1.12, 1.06), (1.0, 2.2, 1.08), 64)],
           fstop=2.0),
  render=dict(samples=64),
  cards=[dict(pose="rin_profile_speak", h=0.485, loc=(0.944, 2.154, 0.787), rot=(90, 0, 0), face_cam=True,
              blink=True,
              props=dict(key_dir=(0.7, 0.2, 0.5), key_col=(0.3, 0.38, 0.6), amb_col=(0.12, 0.14, 0.22),
                         rim_dir=(1, 0.2, 0), rim_col=(0.6, 0.75, 1.0), exposure=1.0))])
# the break before the white chorus: in the dark the film's ring draws itself again, then flashes into the
# reactor's ring (S38)
S("S37", 139.08, free=True, bg="ring", bg_args=dict(radius=170, grow=True), finish=NIGHT, out="white",
  out_dur=0.35)

# ================================================================ CHORUS 2 (white)
S("S38", 139.98, scene="core", setup=dict(mood="white", exterior=True), finish=WHITE, in_="flash",
  cam=dict(keys=[(0, (0, -48, 30), (0, 0, -2), 28), (1, (20, -40, 24), (0, 0, -2), 28)]),
  anim=dict(plasma=[(0, 1.4), (1, 2.0)]))
S("S39", lambda: L(31) - 0.15, scene="core", setup=dict(mood="white"), finish=WHITE,
  fx=[{"type": "memories"}],
  cam=dict(keys=[(0, ring_pos(0.0, R + 1.6, 0.3), ring_pos(0.3, R, 0.0), 22),
                 (1, ring_pos(0.25, R + 1.6, 0.3), ring_pos(0.55, R, 0.0), 22)], ease="linear"))
# on the beat before the line opens (the first-pass timeline put the cut two frames after its first word)
S("S40", lambda: greet(32), free=True, scene="core", setup=dict(mood="white"), finish=WHITE,
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.4, 0.4), ring_pos(0.16, R + 2.2, 0.02), 25.2, 4),
                 (1, ring_pos(0.03, R + 2.5, 0.2), ring_pos(0.16, R + 2.2, 0.33), 36, -3)], fstop=2.0),
  # the line about memories melting into white: limp, head bowed, as if fainting into the light (the first
  # chorus had her open-armed, looking up)
  cards=[dict(pose="rin_float_limp", h=1.7, loc=ring_pos(0.16, R + 2.2, -0.9), rot=(90, 8, 0), face_cam=True,
              props=dict(key_dir=(-0.4, 0.6, 0.6), key_col=(0.55, 0.6, 0.65), amb_col=(0.45, 0.48, 0.55),
                         rim_dir=(-0.9, 0.2, 0.0), rim_col=(0.45, 0.45, 0.47), exposure=1.05))])
# cut one eighth before the hook lands (the first-pass timeline had it 0.3 s late)
S("S41", lambda: greet(33), free=True, scene="core", setup=dict(mood="white"), finish=WHITE,
  cam=dict(keys=[(0, ring_pos(0.0, R - 1.4, -0.6), ring_pos(0.4, R, 0.0), 18, 10),
                 (1, ring_pos(0.7, R - 1.4, -0.4), ring_pos(1.1, R, 0.0), 18, -10)], ease="linear"))
S("S42", lambda: L(34) - 0.15, scene="core", setup=dict(mood="white"), finish=WHITE,
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.6, 1.2), ring_pos(0.12, R + 2.3, -0.3), 30),
                 (1, ring_pos(0.04, R + 2.6, 0.9), ring_pos(0.12, R + 2.3, -0.3), 34)], fstop=2.2),
  cards=[dict(pose="rin_sleep", h=0.95, loc=ring_pos(0.12, R + 2.3, -0.9), rot=(70, 0, 0), face_cam="full",
              props=dict(key_dir=(0.0, 0.7, 0.6), key_col=(0.5, 0.55, 0.6), amb_col=(0.5, 0.52, 0.58),
                         rim_dir=(0, 1, 0), rim_col=(0.45, 0.45, 0.47), exposure=1.05))])

# ================================================================ BRIDGE: clocks, TV, echoes
S("S42b", 160.4, scene="core", setup=dict(mood="white", exterior=True), finish=WHITE,
  cam=dict(keys=[(0, (24, -30, 14), (0, 0, -1), 30), (1, (60, -80, 40), (0, 0, -1), 30)], ease="in"),
  anim=dict(plasma=[(0, 2.0), (1, 4.0)]), out="white", out_dur=1.2)
S("S43", 164.72, scene="gears", setup=dict(mood="steel"), finish=MONO, in_="black", in_dur=0.6,
  cam=dict(keys=[(0, (1.4, -3.6, 2.2), (0.2, 0.0, 0.0), 60), (1, (0.9, -3.2, 1.6), (0.3, 0.2, 0.0), 70)], fstop=2.8))
S("S43b", 172.91, scene="room", setup=dict(tod="night", lamp=False), finish=MONO,
  cam=dict(keys=[(0, (3.0, 1.05, 1.88), (3.6, 1.0, 1.85), 70), (1, (3.05, 1.02, 1.86), (3.6, 1.0, 1.85), 85)],
           fstop=2.2),
  anim=dict(clock_tick=True))
S("S43c", 179.46, scene="room", setup=dict(tod="night", lamp=False, rake=True), finish=MONO,
  cam=dict(keys=[(0, (3.2, 2.4, 1.5), (1.2, 0.8, 0.6), 24), (1, (3.1, 2.2, 1.45), (1.2, 0.8, 0.6), 26)], fstop=4.0),
  cards=[dict(pose="rin_sit_knees", h=1.05, loc=(0.6, 1.4, 0.38), rot=(90, 0, -90), face_cam=True,
              contact=SIT,
              props=dict(key_dir=(0.8, 0.1, 0.5), key_col=(0.35, 0.4, 0.5), amb_col=(0.03, 0.035, 0.05),
                         rim_dir=(-1, 0.2, 0), rim_col=(0.25, 0.3, 0.4), exposure=1.0))],
  anim=dict(crt_static=[(0, 1.0), (1, 1.0)]), fx=[{"type": "tvflicker"}])
# the line about the TV host: the set tunes in out of the snow while it is sung, and the host is Rin herself,
# smiling and waving on air. The render runs on to 196.72 so the inserts below can re-use it.
S("S44", 186.0, scene="room", setup=dict(tod="night", lamp=False), finish=MONO, render_to=196.72,
  cam=dict(keys=[(0, (2.3, 1.6, 0.6), (2.3, 0.4, 0.52), 45), (1, (2.3, 1.35, 0.55), (2.3, 0.4, 0.52), 52)],
           fstop=2.8),
  anim=dict(crt_host=[(0, 0.0), (0.04, 0.0), (0.3, 1.0), (1, 1.0)],
            crt_static=[(0, 1.0), (0.04, 1.0), (0.32, 0.2), (1, 0.2)]))
# the singing speeds up through the bridge, so does the cutting: TV, Rin and the clock intercut on the
# bars, then on the beats, into the wall of TVs. Inserts re-frame frames already rendered for S43-S44.
# a decisive punch-in on the screen (a 1.3x step on the same axis read as a jump cut)
S("S44b", 190.36, frames_from=dict(id="S44", at=4.4), finish=MONO,
  fx=[{"type": "zoom", "z": [(0, 1.55), (1, 1.62)], "cy": -300}])
# reverse shot: the real Rin on the bed, chin on her knees, watching herself smile on the screen. Shot from
# beside the TV (behind the camera), so only the flicker of its light reaches her; the card stands where
# her head is in S43c, sized like the other close-ups (aligned to rin_face_close)
S("S44c", 192.55, scene="room", setup=dict(tod="night", lamp=False), finish=MONO, render_to=195.0,
  cam=dict(keys=[(0, (1.9, 0.75, 1.12), (0.6, 1.42, 1.15), 52), (1, (1.87, 0.78, 1.12), (0.6, 1.42, 1.15), 56)],
           fstop=2.0),
  render=dict(samples=64),
  cards=[dict(pose="rin_watch_tv", h=0.6479, loc=(0.5974, 1.415, 0.7518), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.8, 0.1, 0.5), key_col=(0.4, 0.45, 0.55), amb_col=(0.04, 0.045, 0.06),
                         rim_dir=(-1, 0.2, 0), rim_col=(0.25, 0.3, 0.4), exposure=1.0))],
  anim=dict(crt_host=[(0, 1.0), (1, 1.0)], crt_static=[(0, 0.2), (1, 0.2)]), fx=[{"type": "tvflicker"}])
S("S44d", 194.72, frames_from=dict(id="S12", at=0.0), finish=MONO,
  fx=[{"type": "zoom", "z": [(0, 1.0), (1, 1.08)]}])
# the next line: Rin on the screen, lost and found in the snow
S("S45", 196.72, bg="static", bg_args=dict(signal=0.5), finish=MONO, fx=[{"type": "strobe", "amount": 0.2}])
S("S45c", 201.07, frames_from=dict(id="S43", at=4.0), finish=MONO,
  fx=[{"type": "zoom", "z": [(0, 1.35), (1, 1.5)], "cx": -40, "cy": 60}])
S("S45d", 203.09, bg="static", bg_args=dict(signal=0.35, pose="rin_laugh"), finish=MONO,
  fx=[{"type": "strobe", "amount": 0.3}])
S("S45e", 204.18, frames_from=dict(id="S44", at=7.0), finish=MONO,
  # the push is centred near the top of her bow, so the bow stays in and the frame grows downward
  fx=[{"type": "zoom", "z": [(0, 1.22), (1, 1.28)], "cy": -380}])
S("S45f", 205.28, frames_from=dict(id="S44c", at=0.3), finish=MONO,
  fx=[{"type": "zoom", "z": [(0, 1.0), (1, 1.04)], "cy": -480}, {"type": "tvflicker"}])
S("S45g", 205.83, frames_from=dict(id="S12", at=1.2), finish=MONO,
  fx=[{"type": "zoom", "z": [(0, 1.15), (1, 1.2)]}])
S("S45b", 206.37, bg="tv_wall", finish=MONO,
  fx=[{"type": "strobe", "amount": 0.45},
      {"type": "glitch", "on": [(0, 0), (0.6, 0), (0.62, 1)], "amount": 0.7}])

# ================================================================ ALLEGRO AGITATO (score + tinnitus)
S("S46", lambda: L(40) - 0.3, bg="score", bg_args=dict(mode="calm"), finish=dict(chroma=1.5))
S("S47", lambda: L(41) - 0.2, bg="tinnitus", bg_args=dict(pose="rin_ears_covered"), finish=dict(chroma=3.0),
  fx=[{"type": "strobe", "amount": 0.4}])
S("S48", lambda: L(42) - 0.3, bg="score", bg_args=dict(mode="wild"), finish=dict(chroma=2.5),
  fx=[{"type": "glitch", "on": [(0, 0), (0.7, 0), (0.72, 1)], "amount": 0.8}])
S("S49", lambda: L(43) - 0.2, bg="tinnitus", bg_args=dict(pose="rin_ears_covered", close=True),
  finish=dict(chroma=1.5), fx=[{"type": "strobe", "amount": 0.6}], out="black", out_dur=0.08)

# ================================================================ INSTRUMENTAL: the room grows infinite
# the void opens on the downbeat after the line is sung out (the music changes at 230.9)
S("S50", 230.88, scene="room", setup=dict(void=True, hide=["LampBase", "RingTube", "LampShade"]), finish=VOID,
  in_="black", in_dur=1.5,
  cam=dict(keys=[(0, (2.2, 0.2, 1.36), (0.6, 2.0, 0.68), 30), (1, (6.0, -14.0, 5.0), (0.6, 2.0, 0.6), 35)],
           ease="inout"),
  cards=[dict(pose="rin_sit_knees", h=1.05, loc=(0.6, 1.45, 0.38), rot=(90, 0, 90), face_cam=True,
              contact=SIT,
              props=dict(key_dir=(0.2, 0.9, 0.4), key_col=(0.25, 0.3, 0.5), amb_col=(0.05, 0.06, 0.1),
                         rim_dir=(0.9, 0.2, 0), rim_col=(0.35, 0.45, 0.8), exposure=1.0))],
  anim=dict(plate=[(0, 1.0), (1, 0.45)]))
# S50's pull-back continues as one take: on its last frame the city and the reactor go out window by
# window while the camera creeps toward her, until she is the only thing left on the bed in the dark
S("S51", 240.2, frames_from=dict(id="S50", at=9.75, speed=0.0), finish=VOID,
  fx=[{"type": "lights_out", "progress": [(0, 0.0), (0.72, 1.0), (1, 1.0)], "keep": (940, 540, 115)},
      {"type": "zoom", "z": [(0, 1.0), (0.3, 1.06), (1, 1.5)], "cx": -20, "cy": -20}])
S("S52", 250.0, scene="room", setup=dict(void=True, hide=["LampBase", "RingTube", "LampShade"]), finish=VOID,
  hud=dict(level=1, alpha=0.6), render=dict(samples=64),
  fx=[{"type": "breath"}],
  cam=dict(keys=[(0, (1.6, 1.5, 0.95), (1.0, 2.2, 0.92), 65), (1, (1.5, 1.6, 0.94), (1.0, 2.2, 0.92), 80)],
           fstop=2.0),
  # alone in the infinite dark room, sleepless: eyes wide open on nothing, one tear (aligned to rin_face_close)
  cards=[dict(pose="rin_sleepless", h=0.62, loc=(1.0, 2.2, 0.62), rot=(90, 0, 0), face_cam=True,
              props=dict(key_dir=(0.6, 0.3, 0.5), key_col=(0.1, 0.13, 0.22), amb_col=(0.03, 0.035, 0.06),
                         rim_dir=(-1, 0.2, 0), rim_col=(0.3, 0.45, 0.9), exposure=1.0))],
  anim=dict(plate=[(0, 0.0), (1, 0.0)]))

# ================================================================ IGNITION (B3 over the band)
S("S53", 259.82, scene="city", finish=NIGHT, in_="flash", setup=dict(lights=0.0),
  cam=dict(keys=[(0, (1450, 1250, 260), (500, -400, 40), 26), (1, (1150, 900, 200), (600, -700, 40), 30)],
           shake=(0.8, 0.2, 0.8)),
  anim=dict(city_lights=[(0, 1.0), (0.15, 1.0), (1, 0.06)], window_strength=[(0, 9.0), (0.2, 5.0), (1, 4.0)],
            facility=[(0, 2.0), (1, 4.5)]))
# seen from straight above, the window frame hanging in the void is only a few unreadable bars: hidden
S("S54", lambda: L(45) - 0.2, scene="room", setup=dict(void=True, hide=["LampBase", "RingTube", "LampShade", "FrameTop",
                                                                         "FrameBot", "FrameL", "FrameR", "FrameMid"],
                                                       pillow_dent=(0.0, -0.03, 0.12, 0.035), quilt=LIE_QUILT),
  finish=VOID,
  cam=dict(keys=[(0, (0.56, 1.62, 3.2), (0.561, 1.62, 0.0), 30, 0), (1, (0.56, 1.62, 9.5), (0.561, 1.62, 0.0), 30, 28)],
           ease="out"),
  cards=[dict(pose="rin_lie_up", **{**LIE_UP, "motion": "breath"},
              props=dict(key_dir=(0.0, 0.3, 0.9), key_col=(0.22, 0.27, 0.42), amb_col=(0.05, 0.06, 0.1),
                         rim_col=(0.0, 0.0, 0.0), exposure=1.0))],
  anim=dict(plate=[(0, 0.0), (1, 0.0)]))
S("S55", lambda: L(46) - 0.2, bg="chest_core", bg_args=dict(pose="rin_float", mode="tight"), finish=NIGHT,
  fx=[{"type": "zoom", "z": [(0, 1.0), (1, 1.06)], "cy": 100}, {"type": "heat", "amount": 2.5}])
S("S56", lambda: L(47) - 0.2, scene="core", setup=dict(mood="blue"), finish=COREB,
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.0, -2.6), ring_pos(0.08, R + 1.6, 1.1), 24, 0),
                 (1, ring_pos(0.008, R + 2.0, -2.5), ring_pos(0.08, R + 1.4, 1.3), 23, -10)], fstop=2.8,
           focus="card", focus_at=0.8),
  # the line about not being able to breathe: a hand pressed to her chest, head thrown back, mouth open
  cards=[dict(pose="rin_chest_clutch", h=1.7, loc=ring_pos(0.08, R + 1.8, -1.3), rot=(90, 0, 0), face_cam="full",
              props=dict(key_dir=(0.0, 0.8, 0.5), key_col=(0.4, 0.7, 1.0), amb_col=(0.12, 0.18, 0.32),
                         rim_dir=(0, 1, 0), rim_col=(0.8, 0.95, 1.0), exposure=1.0))],
  anim=dict(plasma=[(0, 1.0), (1, 3.0)]), out="white", out_dur=0.4)
S("S57", 271.33, bg="white", finish=WHITE, hud=dict(level=2, alarm=True, col=(0.95, 0.15, 0.1)))

# ================================================================ FINAL CHORUS -> DAWN
S("S58", 273.07, scene="core", setup=dict(mood="blue", exterior=True), finish=COREB, in_="flash",
  cam=dict(keys=[(0, (26, -30, 4), (0, 0, 0), 24), (1, (36, -14, 18), (0, 0, -1), 28)], shake=(0.1, 0.2, 1.0)),
  anim=dict(plasma=[(0, 2.0), (1, 2.6)]))
S("S59", lambda: L(49) - 0.15, scene="core", setup=dict(mood="blue"), finish=COREB,
  cam=dict(keys=[(0, ring_pos(0.0, R + 2.4, 0.5), ring_pos(0.16, R + 2.2, 0.03), 25.6, -4),
                 (1, ring_pos(0.04, R + 2.5, 0.3), ring_pos(0.16, R + 2.2, 0.34), 33.5, 3)], fstop=2.0),
  cards=[dict(pose="rin_float", h=1.7, loc=ring_pos(0.16, R + 2.2, -0.9), rot=(90, -6, 0), face_cam=True,
              props=dict(key_dir=(-0.7, 0.3, 0.6), key_col=(0.3, 0.55, 0.9), amb_col=(0.12, 0.18, 0.35),
                         rim_dir=(-0.9, 0.2, 0.0), rim_col=(0.6, 0.9, 1.0), exposure=1.0,
                         dissolve_col=(0.8, 0.95, 1.0)),
              keys={"dissolve": [(0, 0.0), (0.25, 0.0), (1, 1.0)]})],
  fx=[{"type": "particles", "from": "rin"}])
S("S60", lambda: L(50) - 0.15, scene="core", setup=dict(mood="dawn"), finish=DAWN,
  cam=dict(keys=[(0, ring_pos(0.0, R + 1.6, 0.4), ring_pos(0.35, R, 0.0), 20, -6),
                 (1, ring_pos(0.45, R + 1.6, 0.3), ring_pos(0.8, R, 0.0), 20, 6)], ease="linear"))
S("S61", lambda: L(51) - 0.15, scene="dusk", setup=dict(place="balcony", sky="dawn", lights=0.2,
                                                        comp=dict(mist_color=(0.5, 0.32, 0.2))), finish=DAWN,
  cam=dict(keys=[(0, (1499.0, 901.5, 151.3), (300, -900, 60), 40), (1, (1499.0, 901.5, 151.6), (300, -900, 90), 36)]))
S("S62", lambda: L(52) - 0.15, scene="city", setup=dict(sky="dawn", lights=0.1, comp=dict(mist_color=(0.45, 0.32, 0.22))),
  finish=DAWN,
  cam=dict(keys=[(0, (-600, 1400, 320), (300, 0, 60), 30), (1, (-200, 1100, 260), (600, -300, 60), 32)]))
S("S63", lambda: L(53) - 0.15, scene="gears", setup=dict(mood="gold"), finish=DAWN,
  cam=dict(keys=[(0, (1.6, -3.4, 2.0), (0.3, 0.1, 0.0), 50), (1, (0.4, -3.6, 1.4), (0.3, 0.2, 0.0), 55)], fstop=3.5))
# the last line is sung a second earlier than the first-pass timeline had it: the shot opens with it
S("S64", lambda: greet(54), free=True, scene="dusk", setup=dict(place="balcony", sky="dawn", lights=0.05,
                                                        comp=dict(mist_color=(0.5, 0.35, 0.22))), finish=DAWN,
  cam=dict(keys=[(0, (1500.5, 902.5, 151.5), (300, -900, 70), 28), (1, (1503.0, 906.0, 153.0), (300, -900, 70), 24)]))

# ================================================================ OUTRO: morning, she sleeps
# Lying on her side, seen from above like the night-time S09: the drawing lies flat across the bed, its
# top (her back) toward the room and her face on the front half of the pillow, which takes a dent under
# her head. Only from above does a side-lying drawing sit on a bed: from the side her head would float
# well above the pillow. The camera's up is the room side, so her head is on the left of the frame, as
# in S09 and in the close-up S65c.
# Close-ups of her lying down are lit flat (key and rim off, the light's colour carried by amb_col): the
# drawing has its own cel shading, and the card's silhouette-normal key light laid a second, unrelated
# shadow across her face and hair at this size.
FLAT_MORNING = dict(key_dir=(0.3, 0.7, 0.6), key_col=(0.0, 0.0, 0.0), amb_col=(1.04, 0.98, 0.92),
                    rim_dir=(0, 1, 0), rim_col=(0.0, 0.0, 0.0), exposure=1.0)
# the whole bed from above, the morning sun across it; the camera sinks a little and turns level
S("S65", 301.45, scene="room", setup=dict(tod="morning", wind=0.35, pillow_dent=SLEEP_DENT, quilt=SLEEP_QUILT, sun=BED_SUN,
                                         world=MORNING_FILL, hide=OVERHEAD_HIDE), finish=DAWN,
  hud=dict(level=1, alpha=0.75), render=dict(exposure=-0.7),
  cam=dict(keys=[(0, (0.62, 1.7, 1.98), (0.621, 1.7, 0.45), 24, -10), (1, (0.62, 1.8, 1.82), (0.621, 1.8, 0.45), 26, 0)],
           ease="inout"),
  cards=[dict(pose="rin_sleep", **SLEEP_ON_BED, props=dict(FLAT_MORNING))])
# closer, her face on the pillow (the framing of the dusk S32)
S("S65b", 309.6, scene="room", setup=dict(tod="morning", wind=0.25, pillow_dent=SLEEP_DENT, quilt=SLEEP_QUILT, sun=BED_SUN,
                                          world=MORNING_FILL, hide=OVERHEAD_HIDE), finish=DAWN,
  hud=dict(level=1, alpha=0.85),
  cam=dict(keys=[(0, (0.62, 2.24, 1.6), (0.621, 2.24, 0.47), 30, 0), (1, (0.62, 2.25, 1.58), (0.621, 2.25, 0.47), 31, 3)],
           fstop=8.0),
  render=dict(exposure=-0.7, samples=64),
  cards=[dict(pose="rin_sleep", **SLEEP_ON_BED, props=dict(FLAT_MORNING))])
# the last image: the morning she thought she would not see. Seen from above on the pillow, she sleeps,
# opens her eyes on the downbeat of the last bar as the light swells, smiles; the title comes up over
# her as the song rings out, and the film goes to black with the silence. The card lies flat on the
# pillow, sized so her eyes are the same distance apart as in the other close-ups.
S("S65c", 316.73, scene="room", setup=dict(tod="morning", wind=0.25, pillow_dent=SLEEP_DENT, quilt=SLEEP_QUILT,
                                           sun=BED_SUN, world=MORNING_FILL, hide=OVERHEAD_HIDE),
  finish=DAWN,
  render=dict(exposure=-0.5, samples=64),
  cam=dict(keys=[(0, (0.575, 2.38, 1.11), (0.575, 2.40, 0.51), 55, -3),
                 (1, (0.575, 2.385, 1.09), (0.575, 2.40, 0.51), 60, 1)], fstop=2.8, ease="linear"),
  cards=[dict(pose="rin_wake", h=0.329, loc=(0.565, 2.269, 0.51), rot=(0, 0, 0), contact=dict(kind="lie", blur=0.006, strength=0.65, cast=0.025, cast_strength=0.35),
              props=dict(FLAT_MORNING, amb_col=(1.08, 1.02, 0.95)),
              keys={"blink": [(("s", 0.0), 1.0), (("s", 2.17), 1.0), (("s", 2.19), 0.0),
                              (("s", 5.85), 0.0), (("s", 5.87), 1.0), (("s", 5.96), 1.0), (("s", 5.98), 0.0)]})],
  fx=[{"type": "exposure", "ev": [(0, -0.2), (0.175, -0.2), (0.21, 0.18), (1, 0.08)]}],
  # the title small enough to end above her collar and clear of the credits panel
  title=dict(mode="poster", at=0.31, col=(0.33, 0.2, 0.12), panel="right", size=110),
  out="black", out_dur=2.6)


# ================================================================ lyrics typography

def _tate_cols(lines, x0, step, y=150, **kw):
    out = {}
    for k, i in enumerate(lines):
        out[i] = dict(style="tate", x=x0 - k * step, y=y, index=i + 1, **kw)
    return out


LYRIC_STYLES = {}
LYRIC_STYLES.update(_tate_cols([0, 1], 1720, 96, size=58, shadow=0.6))
LYRIC_STYLES.update(_tate_cols([2, 3], 1720, 96, size=58, shadow=0.6))
LYRIC_STYLES.update(_tate_cols([4, 5], 326, 96, size=58, shadow=0.6))  # columns read right to left
LYRIC_STYLES.update(_tate_cols([6, 7], 1720, 96, size=58, color=(0.82, 0.88, 1.0), shadow=0.6))
LYRIC_STYLES[7]["shots"] = ("S16",)  # the night line ends at the cut into the white dream
for i, (x, y) in zip(range(8, 12), ((960, 760), (960, 760), (960, 760), (960, 760))):
    LYRIC_STYLES[i] = dict(style="impact", x=x, y=y, size=74, face="mincho_b", color=(0.1, 0.1, 0.13),
                           overshoot=0.15, slam=0.35, marker=(1.0, 0.86, 0.12), shadow=0.0)
# S17 frames her open hands in the lower middle: the first line goes to the empty lower right
LYRIC_STYLES[8].update(x=1560, y=930, size=62)
for i, note in zip((12, 15, 30, 33, 48),
                   ("FUSION REACTOR  /  炉心温度 15,000,000 ℃", "FUSION REACTOR  /  磁場閉じ込め 定常",
                    "FUSION REACTOR  /  炉心温度 100,000,000 ℃", "FUSION REACTOR  /  記憶領域 白色化",
                    "FUSION REACTOR  /  炉心温度 ∞")):
    LYRIC_STYLES[i] = dict(style="impact", x=960, y=380, size=210, face="gothic_k", annot=note, heat=True)
for i in (13, 16, 31, 34, 49):
    LYRIC_STYLES[i] = dict(style="impact", x=960, y=640, size=118, face="gothic_k")
LYRIC_STYLES[34]["y"] = 900  # under Rin, who floats across the middle of S42
LYRIC_STYLES[14] = dict(style="tate", x=1660, y=120, size=84, face="mincho_b", attack=0.3, color=(0.85, 0.95, 1.0))
LYRIC_STYLES[17] = dict(style="impact", x=960, y=905, size=64, face="mincho_b", overshoot=0.1, slam=0.5)
LYRIC_STYLES[16]["at_shot"] = {"S27": dict(y=965, size=96)}   # carried into the close-up: below her chin
# long lines start higher so they keep most of their size inside the frame (14 / 16 characters)
LYRIC_STYLES[32] = dict(style="tate", x=1660, y=70, size=84, face="mincho_b", attack=0.3, color=(1, 1, 1))
# light type (it flips to the key ink where the core whites out): the grey frame swallowed dark ink
# under the reactor on the open page, not inside its glowing lower half
LYRIC_STYLES[35] = dict(style="impact", x=960, y=1000, size=64, face="mincho_b", overshoot=0.1, slam=0.5,
                        color=(0.97, 0.98, 1.0))
LYRIC_STYLES.update(_tate_cols([18, 19], 1720, 96, size=58, color=(1.0, 0.86, 0.78)))
LYRIC_STYLES.update(_tate_cols([20, 21], 326, 96, size=58, color=(1.0, 0.86, 0.78)))
LYRIC_STYLES.update(_tate_cols([22, 23], 1720, 96, size=58, color=(1.0, 0.8, 0.7)))
for i, x in ((24, 1720), (25, 1624)):
    LYRIC_STYLES[i] = dict(style="tate", x=x, y=150, size=58, color=(1.0, 0.8, 0.7), index=i + 1, melt=1.0)
LYRIC_STYLES.update(_tate_cols([26, 27], 1720, 96, size=58, color=(0.82, 0.88, 1.0)))
# the words wait just in front of her parted lips (S36 frame, measured from the render) and float off
# spaced so neighbouring bubbles do not cross, starting clear of her face and reading left to right
LYRIC_STYLES[28] = dict(style="bubbles", x=1500, y=720, size=46, tracking=0.55, bubble=0.8, spread=40.0,
                        rise=320.0, shots=("S36",))
LYRIC_STYLES[29] = dict(style="bubbles", x=1500, y=720, size=46, tracking=0.55, bubble=0.8, spread=40.0,
                        rise=320.0, seed=5, shots=("S36",))
for i, (x, y) in zip(range(36, 40), ((140, 120), (1000, 120), (140, 120), (1000, 120))):
    LYRIC_STYLES[i] = dict(style="echo", x=x, y=y, size=54, copies=10, dx=6.0, tail=6.0,
                           shots=("S43", "S43b", "S43c", "S44", "S44b", "S44c", "S44d", "S45", "S45c", "S45d",
                                  "S45e", "S45f", "S45g", "S45b"))
for i in range(40, 44):
    LYRIC_STYLES[i] = dict(style="score_line", tail=0.6, italic="Allegro agitato" if i in (40, 42) else None)
for i, x in zip(range(44, 48), (1720, 1624, 1720, 1624)):
    LYRIC_STYLES[i] = dict(style="tate", x=x, y=150, size=58, index=i + 1)
LYRIC_STYLES[50] = dict(style="tate", x=1660, y=70, size=72, face="mincho_b", attack=0.32, color=(0.9, 0.97, 1.0))
LYRIC_STYLES[51] = dict(style="tate", x=1700, y=150, size=60, face="mincho_b", attack=0.36, color=(1.0, 0.96, 0.88),
                        index=52)
LYRIC_STYLES[52] = dict(style="tate", x=1604, y=150, size=60, face="mincho_b", attack=0.36, color=(1.0, 0.96, 0.88),
                        index=53)
LYRIC_STYLES[53] = dict(style="impact", x=960, y=470, size=96, face="mincho_b", overshoot=0.08, slam=0.6,
                        color=(1.0, 0.92, 0.75))
# the last line of the song stays a while over the sleeping Rin and fades slowly
# the last line runs from the dawn city (S64) into her sleeping (S65): set right of centre in both, over
# the city and then over the open quilt, so it neither jumps at the cut nor covers her shoulders
LYRIC_STYLES[54] = dict(style="impact", x=1290, y=560, size=96, face="mincho_b", overshoot=0.08, slam=0.6,
                        color=(1.0, 0.92, 0.75), tail=6.0, hold=1.6, fade_out=0.9)


# ================================================================ design layer (titles, print marks, ring cuts)
DESIGN = {
    "S00": dict(title=dict(mode="ring"), marks=True, in_="black", in_dur=0.8),
    "S02": dict(in_="iris", in_dur=0.5),
    "S07": dict(title=dict(mode="poster"), marks=True),
    "S21": dict(marks=True, glow=0.0, stamps=[dict(text="臨界", x=1400, y=560, size=300, at=0.12)]),
    "S23": dict(in_="iris", in_dur=0.35),
    # small mincho over a mid-tone face: keep the type light on a soft dark-ink plate
    # her face fills the frame: a soft shade along the bottom lets the light line read over her chin
    "S27": dict(type_mode="plate", fx=[{"type": "darken", "rect": (240, 850, 1680, 1080), "feather": 140,
                                         "amount": 0.4}]),
    "S28": dict(marks=True),
    "S38": dict(in_="iris", in_dur=0.4),
    "S50": dict(marks=True),
    "S57": dict(marks=True, glow=0.0, stamps=[dict(text="暴走", x=620, y=500, size=280, angle=6, at=0.05),
                                    dict(text="溢出", x=1320, y=620, size=280, angle=-10, at=0.45)]),
}
for _s in SHOTS:
    for _k, _v in DESIGN.get(_s["id"], {}).items():
        _s[_k] = _v
# How each shot comes in where a plain cut jumped (a big change of light or place, a cut in the middle of
# a quiet sung line, a section change): dissolves where the picture changes place, a dolly-through where
# it moves into something (her chest, her eye, the sun in her eye), a flash or a fade through white where
# the light itself changes. Beat cuts stay in the choruses and the bridge montage. The shot before a
# dissolve or a dolly-through renders a `tail` past the cut, so it keeps moving underneath (TAILS).
FLOW = {
    "S11": dict(in_="dissolve", in_dur=0.35),                     # the window -> her face, first line
    "S15b": dict(in_="zoom", in_dur=0.3),                         # into her chest: the reactor diagram
    "S16": dict(in_="dissolve", in_dur=0.3, out="white", out_dur=0.35),   # and up into the white room
    "S18": dict(in_="zoom", in_dur=0.3),                          # into her eye
    "S24": dict(in_="flash"),                                     # out of the burnt-white page
    "S28": dict(in_="dissolve", in_dur=0.5),                      # chorus -> the map interlude
    "S30": dict(in_="dissolve", in_dur=0.4),
    "S31": dict(in_="dissolve", in_dur=0.4),
    "S32": dict(in_="dissolve", in_dur=0.5),                      # the dark stairs -> her lit room
    "S34": dict(in_="zoom", in_dur=0.4),                          # through the sun in her eye
    "S35": dict(in_="dissolve", in_dur=0.6, in_bloom=0.3),       # dusk -> blue hour
    "S36": dict(out="black", out_dur=0.35),                       # the room goes dark as the band stops
    "S43": dict(in_="white", in_dur=1.0),                         # the white chorus settles into the gears
    "S43b": dict(in_="dissolve", in_dur=0.6),
    "S43c": dict(in_="dissolve", in_dur=0.6),
    "S44": dict(in_="dissolve", in_dur=0.5),
    "S46": dict(in_="glitch"),
    "S52": dict(in_="dissolve", in_dur=1.0),                      # the empty dark -> her sleepless face
    "S54": dict(in_="dissolve", in_dur=0.6),
    "S55": dict(in_="dissolve", in_dur=0.4),
    "S56": dict(in_="zoom", in_dur=0.3),
    "S60": dict(in_="dissolve", in_dur=0.5, in_bloom=0.4),       # she dissolves into the light
    "S61": dict(in_="dissolve", in_dur=0.5),
    "S64": dict(in_="dissolve", in_dur=0.5),
    "S65": dict(in_="dissolve", in_dur=0.8),                      # the dawn city -> her morning room
    "S65b": dict(in_="dissolve", in_dur=0.6),
    "S65c": dict(in_="dissolve", in_dur=0.6),
}
TAILS = {"S15": 0.35, "S17": 0.35, "S27": 0.55, "S29": 0.45, "S30": 0.45, "S31": 0.55, "S34": 0.65, "S43": 0.65,
         "S43b": 0.65, "S43c": 0.55, "S53": 0.65, "S54": 0.45, "S59": 0.55, "S60": 0.55, "S63": 0.55, "S64": 0.85,
         "S65": 0.65, "S65b": 0.65}
for _s in SHOTS:
    for _k, _v in FLOW.get(_s["id"], {}).items():
        _s[_k] = _v
    if _s["id"] in TAILS:
        _s["tail"] = TAILS[_s["id"]]
for _sid in ("S45e", "S45f", "S45g", "S45b"):
    next(_s for _s in SHOTS if _s["id"] == _sid)["plate"] = 1.4
# and a steady, feathered shade where those lines sit: the echo block top left in the bridge inserts, the
# vertical column on the right over the window and the clock
READING_SHADE = {"S45e": (0, 0, 1000, 400), "S45f": (0, 0, 1000, 400), "S45g": (0, 0, 1000, 400),
                 "S45b": (0, 0, 1000, 400), "S11": (1440, 40, 1920, 780), "S12": (1440, 40, 1920, 780),
                 "S13": (1440, 40, 1920, 780), "S16": (1440, 40, 1920, 780), "S53": (1440, 40, 1920, 780),
                 "S62": (1440, 40, 1920, 780)}
for _sid, _rect in READING_SHADE.items():
    _s = next(_s for _s in SHOTS if _s["id"] == _sid)
    _s["fx"] = list(_s.get("fx", [])) + [{"type": "darken", "rect": _rect, "feather": 90, "amount": 0.5}]
# light type over lit windows, the reactor's rings and the gears' highlights: a wider, firmer backing
for _sid in ("S11", "S12", "S13", "S22", "S25", "S53", "S58", "S62", "S63"):
    next(_s for _s in SHOTS if _s["id"] == _sid)["plate"] = 1.25
# the TV caption sits low on the left, where a broadcast puts it: clear of her hands (S44c), the host's
# face and waving hand (S45) and most of the clock (S44d)
LYRIC_STYLES[37] = dict(style="telop", x=110, y=952, w=760, size=44, tail=1.5)

# a little life in the cut-outs: blinks on close-ups, hair moving where there is wind or weightlessness
# (amplitudes in UV units of the drawing; the sway is a slow smooth warp, see character.py)
# Sized from the camera so a hair tip moves about 7-13 px on screen (wind in the room, weightlessness
# in the reactor): enough to read through the print's 5.5 px dots, slow enough to stay a breeze. The
# "two layers" the director saw were the print inking the shaded strands grey (fixed in printlook.py).
# SWAY_RATE slows the motion: a breeze (0.85: one sway in 3.5 s), floating (0.7: in 4.3 s).
SWAY = {"S17": 0.0109, "S19": 0.0043, "S20": 0.0043, "S24": 0.0168, "S26": 0.015, "S27": 0.004, "S30": 0.0165,
        "S35": 0.012, "S36": 0.0054, "S40": 0.0165, "S42": 0.0108, "S54": 0.004, "S56": 0.0151, "S59": 0.017}
FLOATING = ("S24", "S26", "S27", "S40", "S42", "S56", "S59")
for _s in SHOTS:
    for _c in _s.get("cards", []):
        if _c["pose"] in ("rin_face_close", "rin_profile_close"):
            _c["blink"] = True
        if _s["id"] in SWAY:
            _c.setdefault("props", {})["sway"] = SWAY[_s["id"]]
            _c["props"]["sway_rate"] = 0.7 if _s["id"] in FLOATING else 0.85
# in the blue reactor her black boots print as the same ink as the dark behind them: a thin cool line all
# round her keeps the silhouette whole (character.py, outline_col); at dusk a warm one parts her legs from
# the dark city below the balcony
OUTLINE = {"S24": (0.3, 0.5, 0.8), "S26": (0.3, 0.5, 0.8), "S56": (0.3, 0.5, 0.8), "S59": (0.3, 0.5, 0.8),
           "S30": (0.5, 0.3, 0.2)}
for _s in SHOTS:
    for _c in _s.get("cards", []):
        if _s["id"] in OUTLINE:
            _c.setdefault("props", {})["outline_col"] = OUTLINE[_s["id"]]


# ================================================================ thermal stress before each meltdown: red slips first, then the type
THERMAL = {
    "S20": dict(fx=[{"type": "rgbsplit", "px": [(0, 0.0), (0.6, 2.0), (1, 16.0)]}],
                lyric_glitch=[(0, 0.0), (0.7, 0.0), (1, 1.0)]),
    "S49": dict(lyric_glitch=[(0, 0.2), (1, 0.6)]),
    "S56": dict(fx=[{"type": "rgbsplit", "px": [(0, 0.0), (0.7, 2.0), (1, 8.0)]}],
                lyric_glitch=[(0, 0.0), (0.75, 0.0), (1, 0.8)]),
    "S57": dict(lyric_glitch=[(0, 0.15), (1, 0.4)]),
}
for _s in SHOTS:
    for _k, _v in THERMAL.get(_s["id"], {}).items():
        if _k == "fx":
            _s["fx"] = list(_s.get("fx", [])) + _v
        else:
            _s[_k] = _v


# ================================================================ chorus energy: kick pushes and ink misregistration on snares
CHORUS_SHOTS = ["S22", "S23", "S24", "S25", "S26", "S27", "S38", "S39", "S40", "S41", "S42", "S42b",
                "S53", "S56", "S58", "S59", "S60", "S61", "S62", "S63", "S64"]
for _s in SHOTS:
    if _s["id"] in CHORUS_SHOTS:
        _s.setdefault("fx", [])
        _s["fx"] = list(_s["fx"]) + [{"type": "kick", "amount": 0.012}]
        _s["mis_hits"] = 5.0
# the bridge keeps a half-time pulse: a lighter push on its kicks
BRIDGE_SHOTS = ["S43", "S43b", "S43c", "S44", "S44b", "S44c", "S44d", "S45", "S45c", "S45d", "S45e", "S45f",
                "S45g", "S45b"]
for _s in SHOTS:
    if _s["id"] in BRIDGE_SHOTS:
        _s["fx"] = list(_s.get("fx", [])) + [{"type": "kick", "amount": 0.007}]


# ================================================================ print look per shot

INK_BY_FINISH = {id(NIGHT): "night", id(COREB): "core", id(DAYW): "dream", id(DUSK): "dusk", id(WHITE): "white",
                 id(MONO): "mono", id(VOID): "void", id(DAWN): "dawn"}
INK_OVERRIDE = {"S46": "score", "S48": "score", "S47": "agitato", "S49": "agitato", "S45": "mono", "S45b": "mono",
                "S21": "none", "S57": "none", "S37": "none", "S00": "graphic", "S28": "graphic", "S65c": "morning", "S33b": "dusk_eye"}
# the light burns through on the snare hits; between hits only the hottest core shows through
CHORUS = dict(base=0.1, energy=0.08, hits=0.3)
BURN = {
    "S01": 0.12, "S06": 0.15, "S12": 0.1, "S08": 0.12, "S25": CHORUS,
    "S22": dict(keys=[(0, 0.08), (0.75, 0.35), (1, 1.0)]),
    "S23": CHORUS, "S24": 0.0, "S26": 0.0,
    # S40 and S42 hold her in the white light: no burn, or her white clothes and face (brighter than any
    # threshold once bloomed) burn away to a blank silhouette
    "S38": CHORUS, "S39": CHORUS, "S40": 0.0, "S41": CHORUS, "S42": 0.0,
    "S42b": dict(keys=[(0, 0.3), (1, 1.0)]),
    "S53": dict(keys=[(0, 0.55), (0.15, 0.12), (1, 0.3)]), "S56": 0.0,
    "S58": CHORUS, "S59": dict(keys=[(0, 0.2), (1, 0.9)]), "S60": dict(base=0.3, energy=0.4, hits=0.3),
}
# plasma interiors render near white: print them a little darker so the filaments keep ink and shape
# (and the washed-out dream room, so Rin keeps her line and her yellow); the big dusk suns print as a
# clean paper disc on a fully inked red sky instead of a blown glare
PRINT_EV = {sid: -0.6 for sid in ("S23", "S24", "S26", "S39", "S40", "S41", "S59", "S60", "S17")}
PRINT_EV.update({"S29": -0.5, "S33": -0.5, "S34": -0.5})
# aerial city: merge the pinpoint windows into tone before the screen, or they print as dot noise
PRE_BLUR = {"S03": 1.2, "S07": 2.5}
for _s in SHOTS:
    if _s["id"] in PRINT_EV:
        _s["print_ev"] = PRINT_EV[_s["id"]]
    if _s["id"] in PRE_BLUR:
        _s["pre_blur"] = PRE_BLUR[_s["id"]]


# ================================================================ resolution

def resolved():
    out = []
    for s in SHOTS:
        t = s["t"]() if callable(s["t"]) else s["t"]
        if not s.get("free"):
            t = beat_near(t) if abs(beat_near(t) - t) < 0.18 else t
        if t > 0:
            t = on_grid(t)     # every cut on the song's eighth-note grid, to the frame
        d = {k: v for k, v in s.items() if k not in ("t", "in_")}
        if "in_" in s:
            d["in"] = s["in_"]
        d["t0"] = round(t, 4)
        d.setdefault("ink", INK_OVERRIDE.get(s["id"], INK_BY_FINISH.get(id(s.get("finish")), "night")))
        if s["id"] in BURN:
            d.setdefault("burn", BURN[s["id"]])
        out.append(d)
    out.sort(key=lambda d: d["t0"])
    for a, b in zip(out, out[1:]):
        a["t1"] = b["t0"]
    out[-1]["t1"] = DURATION
    return out


if __name__ == "__main__":
    for s in resolved():
        print(f'{s["id"]}  {s["t0"]:7.2f} -> {s["t1"]:7.2f}  ({s["t1"] - s["t0"]:5.2f}s)  '
              f'{s.get("scene", s.get("bg"))}')
