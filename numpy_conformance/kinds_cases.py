"""Statement templates for coverage_probe.py genkinds: the kind (bool,
int, float, complex) of results, which a translation can get wrong while
the values look right -- dtype= in each spelling (including another
array's dtype), astype, the kinds numpy's functions and operators return
for integer and boolean input, assignments into arrays of another kind,
and user functions called with arguments of different kinds and ranks.
Each template leaves its result in r (y and z are scratch names; a
function case prints y too). Templates numpy rejects or warns on are
dropped by genkinds."""

from __future__ import annotations

# dtype spellings numpy accepts.
DTYPES = ["int", "float", "bool", "complex", "np.int32", "np.int64", "np.float64", "np.float32",
          "np.complex128", "np.bool_", "'int64'", "'float64'", "'f8'", "'i8'", "'bool'", "'complex128'",
          "np.dtype('int64')", "np.dtype(float)", "xi.dtype", "x.dtype", "b.dtype", "z.dtype"]
_Z = "z = np.array([1.0 + 2.0j, -0.5j, 3.0])"


def _dtype_cases() -> list[tuple[str, list[str]]]:
    out = []
    makers = ["np.zeros(3, dtype={d})", "np.ones((2, 2), dtype={d})", "np.full(3, 2, dtype={d})",
              "np.arange(4, dtype={d})", "np.array([1.7, -2.2, 0.0], dtype={d})", "np.asarray(xi, dtype={d})",
              "np.array(xi, dtype={d})", "np.zeros_like(x, dtype={d})", "np.ones_like(xi, dtype={d})",
              "np.full_like(x, 3, dtype={d})", "np.eye(2, dtype={d})", "np.identity(2, dtype={d})",
              "np.linspace(0, 4, 5, dtype={d})", "x.astype({d})", "xi.astype({d})", "b.astype({d})",
              "m.astype({d})", "np.sum(xi, dtype={d})", "xi.sum(dtype={d})", "np.prod(xi, dtype={d})",
              "np.cumsum(xi, dtype={d})", "np.mean(xi, dtype={d})", "x.mean(dtype={d})",
              "np.zeros(3, {d})", "np.ones(2, {d})", "np.array([1.5, 2.5], {d})"]
    for mk in makers:
        for d in DTYPES:
            stmts = ([_Z] if "z." in d else []) + [f"r = {mk.format(d=d)}"]
            out.append(("dtype", stmts))
    return out


def _result_kind_cases() -> list[tuple[str, list[str]]]:
    exprs = [
        "xi / 2", "xi // 2", "xi ** 2", "xi % 3", "x // 1", "xi * True", "xi + 0.0", "xi * 1j", "b + 1",
        "b * 2.5", "b & (xi > 1)", "~b", "-xi", "+b", "np.floor(xi)", "np.ceil(xi)", "np.trunc(xi)",
        "np.rint(xi)", "np.round(xi)", "np.around(x)", "np.abs(xi)", "np.sign(xi)", "np.sign(b)", "np.sqrt(xi)",
        "np.exp(xi)", "np.log1p(xi)", "np.square(xi)", "np.square(b)", "np.reciprocal(x)", "np.power(xi, 2)",
        "np.true_divide(xi, xi)", "np.floor_divide(xi, 2)", "np.floor_divide(x, 2)", "np.mod(x, 2)",
        "np.remainder(xi, 2)", "np.fmod(xi, 3)", "np.gcd(xi, 2)", "np.lcm(xi, 4)", "np.maximum(xi, 2)",
        "np.maximum(xi, 2.0)", "np.minimum(b, xi)", "np.fmax(xi, x)", "np.where(b, xi, 0)",
        "np.where(b, xi, 0.5)", "np.where(b, 1, 0)", "np.where(b, True, False)", "np.where(xi > 1)[0]",
        "np.clip(xi, 0, 2)", "np.clip(xi, 0.5, 2)", "np.clip(x, 0, 2)", "np.mean(xi)", "np.median(xi)",
        "np.average(xi)", "np.var(xi)", "np.std(b)", "np.sum(b)", "np.sum(xi)", "np.prod(b)", "np.cumsum(b)",
        "np.cumprod(xi)", "np.diff(xi)", "np.diff(b)", "np.ptp(xi)", "np.max(b)", "np.min(xi)",
        "np.argmax(x)", "np.count_nonzero(xi)", "np.sort(xi)", "np.sort(b)", "np.unique(xi)", "np.unique(b)",
        "np.concatenate((xi, x))", "np.concatenate((xi, b))", "np.concatenate((b, b))", "np.stack((xi, xi))",
        "np.hstack((b, xi))", "np.vstack((xi, x))", "np.append(xi, 2.5)", "np.append(xi, 2)",
        "np.insert(xi, 1, 9)", "np.dot(xi, xi)", "xi @ xi", "np.outer(xi, xi)", "np.outer(b, xi)",
        "np.kron(xi, b)", "np.interp(xi, xi[:2], xi[:2])", "np.histogram(x)[0]", "np.bincount(xi)",
        "np.searchsorted(np.sort(x), 0.0)", "np.percentile(xi, 50)", "np.quantile(xi, 0.5)", "np.nan_to_num(xi)",
        "np.logical_not(xi)", "np.logical_and(xi, b)", "np.isclose(xi, 1)", "np.isnan(xi)", "np.nonzero(b)[0]",
        "np.argsort(xi)", "np.cumsum(xi) / 2", "np.flip(b)", "np.roll(b, 1)", "np.tile(b, 2)", "np.repeat(xi, 2)",
        "np.trace(m)", "np.diag(xi)", "np.triu(xi.reshape(2, 2))", "np.linalg.norm(xi)", "np.linalg.det(m)",
        "np.real(xi)", "np.imag(xi)", "np.conj(xi)", "np.angle(xi)", "np.polyval(xi, 2)", "np.polyval(xi, 0.5)",
        "np.convolve(xi, xi)", "np.convolve(xi, x)", "np.cross(xi[:3], xi[1:])", "np.ediff1d(xi)",
        "np.heaviside(xi, 0.5)", "np.copysign(xi, -1)", "np.fabs(xi)", "np.hypot(xi, xi)", "np.arctan2(xi, xi)",
        "np.signbit(xi)", "np.full(2, True)", "np.full(2, 3)", "np.full(2, 2.5)", "np.zeros(2) + xi[:2]",
        "np.ones(2, dtype=int) * b[:2]", "np.array([True, 2])", "np.array([1, 2.5])", "np.array([b[0], xi[0]])",
        "xi[0] / xi[1]", "xi[0] // 2", "x[0] // 1", "int(x[2])", "float(xi[0])", "bool(xi[1])", "complex(x[0])",
        "np.int64(x[1])", "np.float64(xi[0])", "np.bool_(xi[0])", "7 // 2", "7 / 2", "2 ** 3", "2 ** -1",
        "True + True", "divmod(7, 2)[0]", "abs(-3)", "round(2.5)", "round(2.567, 2)", "max(xi[0], 2)",
        "max(xi[0], 2.5)", "sum([1, 2])", "len(xi) / 2", "xi.size // 3", "x.shape[0] * 1.5",
    ]
    return [("result-kind", [f"r = {e}"]) for e in exprs]


def _assign_cases() -> list[tuple[str, list[str]]]:
    blocks = [
        ["y = xi.copy()", "y += 1", "r = y"],
        ["y = xi.copy()", "y = y * 2.5", "r = y"],
        ["y = xi.copy()", "y[0] = 2.7", "r = y"],
        ["y = xi.copy()", "y[1:3] = x[:2]", "r = y"],
        ["y = x.copy()", "y[0] = True", "r = y"],
        ["y = b.copy()", "y[0] = 0", "r = y"],
        ["y = b.copy()", "y[1] = 5", "r = y"],
        ["y = np.zeros(3, dtype=int)", "y[:] = x[:3]", "r = y"],
        ["y = np.zeros(3)", "y += xi[:3]", "r = y"],
        ["y = xi.copy()", "y //= 2", "r = y"],
        ["y = xi.copy()", "y *= 2", "r = y"],
        ["y = xi.copy()", "y[b] = 0", "r = y"],
        ["y = xi.copy()", "y[xi > 2] = x[0]", "r = y"],
        ["y = np.empty(3, dtype=int)", "y[0] = 1.9", "y[1] = -1.9", "y[2] = 0", "r = y"],
        ["y = np.zeros(2, dtype=bool)", "y[0] = 2.5", "r = y"],
        ["y = np.zeros((2, 2), dtype=int)", "y[0, :] = x[:2]", "r = y"],
        ["y = xi.astype(float)", "y /= 2", "r = y"],
        ["y = 3", "y = y / 2", "r = y"],
        ["y = 3", "y //= 2", "r = y"],
        ["y = 2", "y = y * 1.5", "r = y"],
        ["y = 0", "y += True", "r = y"],
        ["y = 1", "for k in range(3):", "    y = y * 2", "r = y"],
        ["y = 1.0", "for k in range(3):", "    y += k", "r = y"],
        ["y = xi[0]", "y = y + 0.5", "r = y"],
        ["y = np.sum(xi)", "y = y / 2", "r = y"],
        ["y = [1, 2, 3]", "r = np.array(y) / 2"],
        ["y = [1.5, 2]", "r = np.array(y)"],
        ["y = [True, False]", "r = np.array(y) + 1"],
        [_Z, "y = z.copy()", "y[0] = 2", "r = y"],
        [_Z, "r = z.real"],
        [_Z, "r = np.abs(z)"],
        [_Z, "r = z * 2"],
    ]
    return [("assign", blk) for blk in blocks]


def _function_cases() -> list[tuple[str, list[str]]]:
    """fn{k}(a) called with two arguments of different kinds or ranks: y
    and r are the two results (both printed)."""
    bodies = ["a * 2", "a + 1", "a / 2", "a // 2", "a.sum()", "a.mean()", "a.max()", "np.sum(a)", "a[0]",
              "a[::-1]", "np.zeros_like(a)", "np.zeros(len(a), dtype=a.dtype)", "a.astype(float)", "a > 1",
              "abs(a)", "np.cumsum(a)", "a * a", "np.sort(a)", "a.copy()", "np.where(a > 1, a, 0)"]
    args = ["xi", "x", "b", "3", "2.5", "m"]
    out, k = [], 0
    for body in bodies:
        for p1 in args:
            for p2 in args:
                if p1 == p2:
                    continue
                out.append(("function", [f"def fn{k}(a):\n    return {body}", f"y = fn{k}({p2})",
                                              "print(y)", f"r = fn{k}({p1})"]))
                k += 1
    two = ["a + c", "a * c", "a / c", "np.maximum(a, c)", "np.where(a > 1, a, c)", "a ** c"]
    pairs = [("xi, xi", "x, x"), ("b, b", "xi, xi"), ("xi, x", "x, xi"), ("xi, 2.5", "x, 3"),
             ("b, xi", "xi, b"), ("m, x[:2]", "xi, xi"), ("3, 4", "2.5, 1.5"), ("xi, 2", "b, True")]
    for body in two:
        for p1, p2 in pairs:
            out.append(("function", [f"def fn{k}(a, c):\n    return {body}", f"y = fn{k}({p2})",
                                          "print(y)", f"r = fn{k}({p1})"]))
            k += 1
    nested = ["def in{k}(a):\n    return a * 2\ndef fn{k}(a):\n    return in{k}(a) + 1",
              "def fn{k}(a, scale=2):\n    return a * scale",
              "def fn{k}(a):\n    t = a.copy()\n    t[0] = 1\n    return t",
              "def fn{k}(a):\n    s = 0\n    for v in a:\n        s = s + v\n    return s",
              "def fn{k}(a):\n    return np.array([a[0], a[-1]])"]
    for src in nested:
        for p1, p2 in (("xi", "x"), ("x", "xi"), ("b", "xi"), ("xi", "b")):
            out.append(("function", [src.format(k=k), f"y = fn{k}({p2})", "print(y)", f"r = fn{k}({p1})"]))
            k += 1
    return out


def templates() -> list[tuple[str, list[str]]]:
    seen, out = set(), []
    for g, stmts in _dtype_cases() + _result_kind_cases() + _assign_cases() + _function_cases():
        key = tuple(stmts)
        if key not in seen:
            seen.add(key)
            out.append((g, stmts))
    return out
