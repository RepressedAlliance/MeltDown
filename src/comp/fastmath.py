"""Whole-frame float32 arithmetic in one multi-threaded pass (numexpr).

numexpr promotes float32 arrays to float64 when an expression contains a float literal, so
constants are passed in by name and converted to float32 here.
"""
import numexpr as ne
import numpy as np

ne.set_num_threads(8)


def ev(expr, out=None, **names):
    loc = {k: (np.float32(v) if isinstance(v, (float, int)) and not isinstance(v, bool) else v)
           for k, v in names.items()}
    return ne.evaluate(expr, local_dict=loc, out=out)


def clip01(a, out=None):
    return ne.evaluate("where(a < 0, 0, where(a > 1, 1, a))", local_dict={"a": a}, out=out)


# numpy reductions over a 3-wide last axis are ~50x slower than an elementwise pass
def max3(rgb):
    return ne.evaluate("where(r > g, where(r > b, r, b), where(g > b, g, b))",
                       local_dict={"r": rgb[..., 0], "g": rgb[..., 1], "b": rgb[..., 2]})


def min3(rgb):
    return ne.evaluate("where(r < g, where(r < b, r, b), where(g < b, g, b))",
                       local_dict={"r": rgb[..., 0], "g": rgb[..., 1], "b": rgb[..., 2]})
