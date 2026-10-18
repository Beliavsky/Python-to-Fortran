"""Edge-value cases for coverage_probe.py (genedges): the inputs where
Python and Fortran disagree unless the translation takes care --
negative operands of floor division and modulo (Python floors, Fortran
truncates), rounding ties (half to even), NaN, inf and -0.0, empty and
one-element arrays, and integer edges (negative powers, shifts and
bitwise operations on negative numbers).

templates() returns (group, statements) pairs; the statements end by
assigning the result to r. Names a case assigns are renamed per case in a
grouped program, so each case may use any names.
"""

from __future__ import annotations

INT_PAIRS = [(7, 2), (-7, 2), (7, -2), (-7, -2), (0, -3), (-6, 3), (5, 7), (-5, 7)]
FLOAT_PAIRS = [(7.5, 2.0), (-7.5, 2.0), (7.5, -2.0), (-7.5, -2.0), (-0.5, 1.0), (6.0, -3.0)]
TIES = [0.5, 1.5, 2.5, -0.5, -1.5, -2.5, 0.49999999999999994, 3.5, -3.5]
XA = "np.array([7, -7, 5, -5, 0, -1])"
YA = "np.array([2, -2, 3, -3, 4, 5])"
FX = "np.array([7.5, -7.5, 5.25, -5.25, 0.0, -1.0])"
FY = "np.array([2.0, -2.0, 3.0, -3.0, 4.0, 5.0])"
XN = "np.array([1.0, np.nan, -2.0, 3.0])"
XF = "np.array([1.0, np.inf, -np.inf, 0.0])"
Z0 = "np.array([0.0, -0.0, 1.0])"
TIEA = "np.array([0.5, 1.5, 2.5, -0.5, -1.5, -2.5, 3.5])"


def templates():
    out = []

    def add(group, *stmts):
        out.append((group, list(stmts)))

    # Floor division and modulo of scalars (variables, not constants).
    for a, b in INT_PAIRS:
        if b:
            add("intdiv", f"a = {a}", f"b = {b}", "r = a // b")
            add("intdiv", f"a = {a}", f"b = {b}", "r = a % b")
            add("intdiv", f"a = {a}", f"b = {b}", "r = np.array(divmod(a, b))")
            add("intdiv", f"a = {a}", f"b = {b}", "r = int(a / b)")
            add("intdiv", f"a = {a}", f"b = {b}", "r = math.fmod(a, b)")
    for a, b in FLOAT_PAIRS:
        add("floatdiv", f"a = {a}", f"b = {b}", "r = a // b")
        add("floatdiv", f"a = {a}", f"b = {b}", "r = a % b")
        add("floatdiv", f"a = {a}", f"b = {b}", "r = math.fmod(a, b)")
        add("floatdiv", f"a = {a}", f"b = {b}", "r = math.remainder(a, b)")
        add("floatdiv", f"a = {a}", f"b = {b}", "r = np.array(divmod(a, b))")
    # Arrays: operators and numpy functions.
    for x, y in ((XA, YA), (FX, FY), (XA, FY)):
        for op in ("x // y", "x % y", "np.floor_divide(x, y)", "np.mod(x, y)", "np.remainder(x, y)",
                   "np.fmod(x, y)", "x // -3", "x % -3", "-7 // y", "-7 % y", "np.divmod(x, y)[0]",
                   "np.divmod(x, y)[1]"):
            add("arraydiv", f"x = {x}", f"y = {y}", f"r = {op}")
    # Rounding ties, truncation toward zero.
    for v in TIES:
        add("round", f"a = {v!r}", "r = round(a)")
        add("round", f"a = {v!r}", "r = np.round(a)")
        add("round", f"a = {v!r}", "r = int(a)")
        add("round", f"a = {v!r}", "r = math.floor(a)")
        add("round", f"a = {v!r}", "r = math.ceil(a)")
        add("round", f"a = {v!r}", "r = math.trunc(a)")
    for v, nd in ((2.675, 2), (0.125, 2), (-0.125, 2), (0.375, 2), (1.25, 1), (-1.25, 1), (12345.0, -2),
                  (-150.0, -2), (250.0, -2)):
        add("round", f"a = {v!r}", f"r = round(a, {nd})")
        add("round", f"a = {v!r}", f"r = np.round(a, {nd})")
    add("round", "a = -2.7", "r = int(a)")
    add("round", "a = 7", "r = round(a, -1)")
    add("round", "a = 25", "r = round(a, -1)")
    add("round", "a = -35", "r = round(a, -1)")
    for f in ("np.round(x)", "np.round(x, 1)", "np.around(x)", "np.rint(x)", "np.fix(x)", "np.trunc(x)",
              "np.floor(x)", "np.ceil(x)", "x.astype(int)", "np.round(x * 10, -1)", "x.round()"):
        add("roundarr", f"x = {TIEA}", f"r = {f}")
    add("roundarr", "x = np.array([-2.7, -0.2, 0.2, 2.7])", "r = x.astype(int)")
    add("roundarr", "x = np.array([-2.7, -0.2, 0.2, 2.7])", "r = np.round(x).astype(int)")
    # NaN.
    for f in ("np.max(x)", "np.min(x)", "np.nanmax(x)", "np.nanmin(x)", "np.minimum(x, 0.0)",
              "np.maximum(x, 0.0)", "np.fmin(x, 0.0)", "np.fmax(x, 0.0)", "np.sort(x)", "np.argsort(x)",
              "np.argmax(x)", "np.argmin(x)", "np.nanargmax(x)", "np.nanargmin(x)", "np.unique(x)",
              "np.sign(x)", "np.clip(x, -1.0, 1.0)", "x > 0", "x == x", "x != x", "np.isnan(x)",
              "np.cumsum(x)", "np.sum(x)", "np.mean(x)", "np.nansum(x)", "np.nanmean(x)", "np.median(x)",
              "np.nanmedian(x)", "np.abs(x)", "x.max()", "np.amax(x)", "np.ptp(x)", "np.std(x)",
              "np.nanstd(x)", "np.cumprod(x)", "np.nancumsum(x)", "np.where(x > 0, x, -x)",
              "np.sort(x)[::-1]", "np.maximum.accumulate(x)", "x[x > 0]", "np.count_nonzero(x > 0)",
              "np.any(x > 2)", "np.all(x > -5)", "np.round(x)", "np.floor(x)", "np.fix(x)",
              "np.searchsorted(np.sort(x), 0.5)", "np.max(np.array([[1.0, np.nan], [2.0, 3.0]]), axis=0)",
              "np.argmax(np.array([[1.0, np.nan], [2.0, 3.0]]), axis=1)"):
        add("nan", f"x = {XN}", f"r = {f}")
    add("nan", "a = float('nan')", "b = 1.0", "r = max(a, b)")
    add("nan", "a = float('nan')", "b = 1.0", "r = max(b, a)")
    add("nan", "a = float('nan')", "b = 1.0", "r = min(b, a)")
    add("nan", "a = float('nan')", "r = a == a")
    add("nan", "a = float('nan')", "r = math.isnan(a)")
    add("nan", "a = float('nan')", "r = np.sign(a)")
    add("nan", f"x = {XN}", "r = sorted(x.tolist())")
    add("nan", f"x = {XN}", "r = max(x.tolist())")
    # inf.
    for f in ("np.max(x)", "np.min(x)", "np.argmax(x)", "np.argmin(x)", "np.sort(x)", "np.argsort(x)",
              "np.sign(x)", "np.clip(x, -5.0, 5.0)", "np.isfinite(x)", "np.isinf(x)", "np.isposinf(x)",
              "np.isneginf(x)", "np.exp(-x)", "np.arctan(x)", "np.tanh(x)", "np.minimum(x, 2.0)",
              "np.abs(x)", "np.unique(x)", "x > 1e308", "np.nan_to_num(x)", "np.round(x)",
              "np.floor(x)", "1.0 / (1.0 + np.exp(-x))", "np.sqrt(np.abs(x))", "np.cumsum(np.abs(x[:2]))"):
        add("inf", f"x = {XF}", f"r = {f}")
    add("inf", "a = float('inf')", "r = -a")
    add("inf", "a = float('inf')", "r = math.isinf(a)")
    add("inf", "a = float('inf')", "r = min(a, 3.0)")
    add("inf", "a = float('inf')", "r = math.atan(a)")
    add("inf", "a = 1e308", "r = a * 10")
    # Signed zero.
    for f in ("np.sign(x)", "np.copysign(1.0, x)", "np.signbit(x)", "np.arctan2(x, -1.0)",
              "np.copysign(2.0, -x)", "np.sqrt(x)", "np.abs(x)", "x == 0.0", "np.minimum(x, 0.0)",
              "np.sort(x)", "np.round(np.array([-0.4, -0.5, -0.6]))", "np.ceil(np.array([-0.5, -0.1]))",
              "np.copysign(1.0, np.ceil(np.array([-0.5, -0.1])))", "np.copysign(1.0, np.round(np.array([-0.4])))",
              "np.copysign(1.0, np.trunc(np.array([-0.5])))", "np.copysign(1.0, -1.0 * np.zeros(2))"):
        add("zero", f"x = {Z0}", f"r = {f}")
    add("zero", "a = -0.0", "r = math.copysign(1.0, a)")
    add("zero", "a = -0.0", "r = math.atan2(a, -1.0)")
    add("zero", "a = -0.4", "r = math.copysign(1.0, round(a))")
    # Empty and one-element arrays.
    for f in ("np.sum(e)", "np.prod(e)", "np.cumsum(e)", "np.cumprod(e)", "np.sort(e)", "len(e)",
              "np.any(e)", "np.all(e)", "np.dot(e, e)", "np.concatenate((e, np.array([1.0])))",
              "np.linalg.norm(e)", "np.count_nonzero(e)", "e * 2.0", "np.unique(e)", "np.diff(e)",
              "np.argsort(e)", "e[e > 0]", "np.sum(e > 0)", "np.nansum(e)", "e.size", "np.where(e > 0)[0]",
              "np.flatnonzero(e)", "np.append(e, 3.0)", "np.convolve(np.array([1.0, 2.0]), np.array([3.0]))",
              "np.sum(np.zeros((0, 3)), axis=0)", "np.sum(np.zeros((3, 0)), axis=1)",
              "np.prod(np.zeros((0, 2)), axis=0)", "np.max(np.zeros((2, 3)), axis=1)",
              "np.hstack((e, e))", "np.outer(e, np.array([1.0, 2.0])).shape[0]"):
        add("empty", "e = np.array([], dtype=float)", f"r = {f}")
    for f in ("np.std(o)", "np.var(o)", "np.diff(o)", "np.convolve(o, o)", "np.median(o)", "np.cumprod(o)",
              "np.argmax(o)", "np.unique(o)", "np.mean(o)", "np.percentile(o, 30)", "np.sort(o)",
              "np.correlate(o, o)", "np.polyval(o, 3.0)", "np.gradient(np.array([1.0, 4.0]))",
              "np.cov(np.array([1.0, 3.0]))", "np.interp(2.0, o, o)", "np.trapezoid(o)",
              "np.linalg.norm(o)", "np.roll(o, 1)", "np.flip(o)", "np.tile(o, 3)", "o[-1]", "o[::-1]",
              "np.ediff1d(o)", "np.histogram(o, bins=2)[0]", "np.cumsum(o)"):
        add("one", "o = np.array([2.5])", f"r = {f}")
    add("one", "xi = np.array([4])", "r = np.mean(xi)")
    add("one", "xi = np.array([4])", "r = np.diff(xi)")
    # Integer edges.
    for stmt in ("r = a ** b", "r = a ** 2", "r = (-a) ** 3", "r = a ** 0", "r = 0 ** b"):
        for a, b in ((2, 3), (2, -1), (-2, -2), (0, 0), (-3, 3), (10, -2)):
            add("intpow", f"a = {a}", f"b = {b}", stmt)
    for stmt in ("r = a >> 1", "r = a << 2", "r = ~a", "r = a & 3", "r = a | 2", "r = a ^ 3", "r = a >> 3",
                 "r = abs(a)", "r = -a", "r = a % 3", "r = pow(a, 2, 5)", "r = math.gcd(a, 18)",
                 "r = a // 4", "r = int(a / 4)", "r = divmod(a, 4)[0]", "r = divmod(a, -4)[1]"):
        for a in (-8, -5, 7, 0):
            add("bits", f"a = {a}", stmt)
    for f in ("np.right_shift(x, 1)", "np.left_shift(x, 2)", "np.invert(x)", "np.bitwise_and(x, 3)",
              "np.bitwise_or(x, 2)", "np.bitwise_xor(x, 3)", "x >> 1", "x & 3", "~x", "np.abs(x)",
              "np.gcd(x, 18)", "np.lcm(x, 4)", "x ** 2", "np.power(x, 3)", "np.sign(x)", "x // 4",
              "np.negative(x)", "np.abs(x) % 3", "np.floor_divide(x, -4)", "np.square(x)"):
        add("bitsarr", "x = np.array([-8, -5, 7, 0, 12])", f"r = {f}")
    return out
