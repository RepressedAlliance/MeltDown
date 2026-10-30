"""The opening's one camera move, from the title into her room (S03 in the city, S09 in the room).

The title ring (2D, S00) cuts to the reactor's ring seen from straight above, the same size in the frame; the camera
sinks toward it while the piano fades, tilts up over the build so the whole night city across the bay is revealed on
the drums' entry, and from there pushes at one rate toward a single lit window high in her tower, through it, and
down over her lying awake in bed. One path, defined in the city's coordinates; the room shot renders the same path
mapped into the room through her window (room_to_city), and the compositor shows the room inside the window's outline
(the "portal", projected per frame by render_shot) while the camera is still outside.

Pure geometry on mathutils (Blender's Python): opening(t) gives (position, rotation, lens) at song time t.
"""
import math

from mathutils import Matrix, Quaternion, Vector

import timeline as TL

# ---------------------------------------------------------------- places
REACTOR = Vector((900.0, -1150.0, 0.0))     # scene_city.REACTOR_POS
BAND_Z, BAND_R = 44.0, 170.6                 # the glowing band along the drum's rim (scene_city.reactor_facility)
# her window: where the room's city plate was rendered from (scene_city.plate_view), facing the way it looks
WIN_C = Vector((1500.0, 900.0, 150.0))       # the window opening's centre on the tower's outer face
N = Vector((-1250.0, -1800.0, 0.0)).normalized()   # outward normal (south-west, over the bay to the reactor)
Z = Vector((0.0, 0.0, 1.0))
T = N.cross(Z)                               # along the facade: the room's +x
ROOM_C = Vector((1.8, 2.82, 1.375))          # the same point in the room (window opening centre, outer wall face)
R_ROOM = Matrix((T, N, Z)).transposed()       # columns: room x, y, z axes in the city


def room_to_city(p):
    return WIN_C + R_ROOM @ (Vector(p) - ROOM_C)


def city_to_room(p):
    return ROOM_C + R_ROOM.transposed() @ (Vector(p) - WIN_C)


def to_room(p, q):
    """A camera pose in the city as the room shot sees it."""
    return city_to_room(p), (R_ROOM.transposed().to_quaternion() @ q).normalized()


# the window opening's corners (outer face) in the city, for the portal mask: room x 0.35..3.25, z 0.55..2.2
WINDOW_CORNERS = [room_to_city((x, 2.82, z)) for x, z in ((0.35, 0.55), (3.25, 0.55), (3.25, 2.2), (0.35, 2.2))]
PANE = room_to_city((1.075, 2.82, 1.40))     # the left pane's middle: what the camera flies at (the middle bar is
                                             # in the window's centre)

# ---------------------------------------------------------------- timing (song seconds)
T_MATCH = TL.on_grid(TL.DOWNBEATS[3])       # the title ring becomes the reactor's (bar 3)
T_TILT0 = TL.DOWNBEATS[4]                   # the build: the camera starts to tilt up and move
T_TILT1 = TL.DOWNBEATS[5]                   # the drums: the city revealed, the push under way
T_ARC = TL.DOWNBEATS[13]                    # the swing round to face her window is complete on the crash
T_ENTER = TL.DOWNBEATS[16]                  # through the window
T_SETTLE = TL.DOWNBEATS[18]                 # above her face, as the band hits (her eyes open)
T_END = TL.DOWNBEATS[20] + 0.5              # past the cut to S10 (29.43)

LENS = 24.0
F_PX = LENS / 36.0 * 1920.0
TITLE_RATE = 0.22                           # S00's ring: r 150 px growing at this log rate
R_TITLE = 150.0 * math.exp(TITLE_RATE * T_MATCH)
D_MATCH = BAND_R * F_PX / R_TITLE           # height above the band that draws it at R_TITLE
D_SWITCH = 1.6                              # from here (outside the window) the move bends into the room
EL_END = math.radians(4.0)                  # the last of the approach comes in slightly from above


def _smoother(x):
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (6 * x - 15) + 10)


def _look(f, up=Z):
    """Rotation of a camera looking along f with up near `up` (Blender cameras look down their -Z)."""
    f = Vector(f).normalized()
    r = f.cross(up)
    if r.length < 1e-6:
        r = f.cross(Vector((0, 1, 0)))
    r.normalize()
    u = r.cross(f)
    return Matrix((r, u, -f)).transposed().to_quaternion()


def _sph(az, el):
    return Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))


# ---------------------------------------------------------------- the move
H0 = (PANE - REACTOR).to_2d().normalized().to_3d()          # heading from the reactor to her window
Q_DOWN = _look(Vector((0, 0, -1)), H0)                       # straight down, the frame's top toward her window


def _above(t):
    """Sinking toward the ring at the title's rate."""
    return REACTOR + Vector((0, 0, BAND_Z + D_MATCH * math.exp(-TITLE_RATE * (t - T_MATCH))))


V0 = _above(T_TILT0) - PANE                                  # where the approach starts, seen from her window
D0 = V0.length
AZ0, EL0 = math.atan2(V0.y, V0.x), math.asin(V0.z / D0)
AZ1 = math.atan2(N.y, N.x)
# The push, as a rate of growth of the picture (log per second): it starts as the camera tilts up, glides over the bay
# while the city is taken in (and the credits come up), then gathers pace toward her tower, fastest on the crash
# (T_ARC), and eases down to come in to land at her window. The peak is solved so the camera is D_SWITCH from the
# pane GLIDE seconds before it passes through the window at T_ENTER. (A single constant rate from 2 km away put the
# camera over the bay at 800 m/s: a smear, not a flight.)
T_GLIDE = TL.DOWNBEATS[7]                   # the glide over the bay ends; the push gathers pace
R_TILT, R_GLIDE, R_LAND = 0.12, 0.2, 0.5
GLIDE = 2.32
T_SWITCH = T_ENTER - GLIDE


def _rate(t, peak):
    if t <= T_TILT0:
        return 0.0
    if t <= T_TILT1:
        return R_TILT * _smoother((t - T_TILT0) / (T_TILT1 - T_TILT0))
    if t <= T_GLIDE:
        return R_TILT + (R_GLIDE - R_TILT) * _smoother((t - T_TILT1) / (T_GLIDE - T_TILT1))
    if t <= T_ARC:
        return R_GLIDE + (peak - R_GLIDE) * _smoother((t - T_GLIDE) / (T_ARC - T_GLIDE))
    return peak + (R_LAND - peak) * _smoother((t - T_ARC) / (T_SWITCH - T_ARC))


_STEP = 1.0 / 480


def _integral(peak, t1):
    n = max(1, int((t1 - T_TILT0) / _STEP))
    h = (t1 - T_TILT0) / n
    return sum(_rate(T_TILT0 + (k + 0.5) * h, peak) for k in range(n)) * h


_need = math.log(D0 / D_SWITCH)
_a = _integral(0.0, T_SWITCH)
PEAK = (_need - _a) / (_integral(1.0, T_SWITCH) - _a)       # the integral is linear in the peak
_TABLE = [0.0]
for _k in range(int((T_SWITCH + 1.0 - T_TILT0) / _STEP) + 2):
    _t = T_TILT0 + (_k + 0.5) * _STEP
    _TABLE.append(_TABLE[-1] + _rate(min(_t, T_SWITCH), PEAK) * _STEP)


def _dist(t):
    if t <= T_TILT0:
        return D0
    x = (t - T_TILT0) / _STEP
    k = min(int(x), len(_TABLE) - 2)
    integ = _TABLE[k] + (_TABLE[k + 1] - _TABLE[k]) * (x - k)
    return D0 * math.exp(-integ)


def _approach(t):
    w = _smoother((t - T_TILT1) / (T_ARC - T_TILT1))
    az = AZ0 + (AZ1 - AZ0) * w
    el = EL0 + (EL_END - EL0) * w
    return PANE + _dist(t) * _sph(az, el), az


def _approach_rot(t):
    p, az = _approach(t)
    q = _look(PANE - p)
    # bank a little into the swing round her tower
    h = 0.05
    daz = (_approach(t + h)[1] - _approach(t - h)[1]) / (2 * h)
    bank = max(-0.07, min(0.07, -1.6 * daz))
    return (Quaternion((PANE - p).normalized(), bank) @ q).normalized()


# inside the room (room coordinates): over her face, then a slow push down to it
FACE_ABOVE = Vector((0.55, 2.17, 1.50))
FACE_END = Vector((0.55, 2.15, 1.24))
Q_FACE = _look(Vector((0, 0, -1)), Vector((1, 0, 0)))       # straight down, her head to the left of the frame
FACE_CITY = room_to_city(Vector((0.55, 2.22, 0.50)))       # her face on the pillow
T_LOOK0 = T_SWITCH - 1.6                                    # the look starts to find her through the window
T_TURN0 = T_ENTER - 0.5                                     # and turns over her as the camera passes through


def _inside(t):
    """Hermite from where the approach hands over (its position and velocity) to above her face, then the push."""
    p0 = city_to_room(_approach(T_SWITCH)[0])
    h = 1.0 / 48
    v0 = R_ROOM.transposed() @ ((_approach(T_SWITCH + h)[0] - _approach(T_SWITCH - h)[0]) / (2 * h))
    v_push = (FACE_END - FACE_ABOVE) / (T_END - T_SETTLE)
    if t <= T_SETTLE:
        dt = T_SETTLE - T_SWITCH
        w = (t - T_SWITCH) / dt
        h00, h10 = 2 * w ** 3 - 3 * w ** 2 + 1, w ** 3 - 2 * w ** 2 + w
        h01, h11 = -2 * w ** 3 + 3 * w ** 2, w ** 3 - w ** 2
        return p0 * h00 + v0 * dt * h10 + FACE_ABOVE * h01 + v_push * dt * h11
    return FACE_ABOVE + v_push * (t - T_SETTLE)


def opening(t):
    """(position, rotation, lens) of the opening's camera at song time t, in the city."""
    if t <= T_TILT0:
        return _above(t), Q_DOWN, LENS
    if t <= T_TILT1:
        w = _smoother((t - T_TILT0) / (T_TILT1 - T_TILT0))
        p = _above(t).lerp(_approach(t)[0], w)
        return p, Q_DOWN.slerp(_look(PANE - p), w), LENS
    p = _approach(t)[0] if t <= T_SWITCH else room_to_city(_inside(t))
    if t <= T_LOOK0:
        return p, _approach_rot(t), LENS
    # the last of the approach: the look leaves the pane for her, lying under the window, so she is in the frame
    # as the camera passes through it (aimed at the pane all the way, the turn inside swept over the floor first);
    # then the frame turns over her, rolling so her head comes to the left, and settles straight above her face
    w2 = _smoother((t - T_TURN0) / (T_SETTLE - T_TURN0))
    q_room = Q_FACE @ Quaternion((0, 0, 1), math.radians(9.0) * max(0.0, (t - T_SETTLE) / (T_END - T_SETTLE)))
    q_end = (R_ROOM.to_quaternion() @ q_room).normalized()
    w = _smoother((t - T_SWITCH) / (T_SETTLE - T_SWITCH))
    lens = LENS + (30.0 - LENS) * w + 3.0 * max(0.0, (t - T_SETTLE) / (T_END - T_SETTLE))
    if w2 <= 0.0:
        return p, _look(_look_dir(t, p)), lens
    if w2 >= 1.0:
        return p, q_end, lens
    # the turn over her: the view swings from her face to straight down while the picture rolls evenly from its up
    # as the turn begins to the final frame's (her head to the left: T). Slerping the look-at rotation into the final
    # one spun the picture 23 degrees in one frame where the camera passed over her face, since looking straight down
    # "up = sky" has no direction (flip_scan); blending the up hint from the sky to T instead crowded the whole
    # quarter turn into one second
    fwd = _look_dir(t, p).slerp(Vector((0.0, 0.0, -1.0)), w2)
    return p, _look(fwd, UP_TURN.slerp(T, w2)), lens


def _look_dir(t, p):
    """Where the camera looks on the last of the approach: from the pane to her face as it comes through."""
    w1 = _smoother((t - T_LOOK0) / (T_ENTER - T_LOOK0))
    return (PANE.lerp(FACE_CITY, w1) - p).normalized()


_p_turn = room_to_city(_inside(T_TURN0))
UP_TURN = _look(_look_dir(T_TURN0, _p_turn)) @ Vector((0.0, 1.0, 0.0))   # the picture's up as the turn begins


PATHS = {"opening": opening}
