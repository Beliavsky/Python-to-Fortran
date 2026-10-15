"""Statement templates for coverage_probe.py genops: array methods,
operators and indexing (reads and writes). Each template is a list of
statements over the probe fixtures (x, xi, m, mr, b) that leaves its
result in r; y and z are scratch names. Templates numpy rejects for the
fixtures (or that warn) are dropped by genops."""

from __future__ import annotations

_VEC = ["x", "xi", "b"]
_MAT = ["m", "mr"]


def _methods() -> list[tuple[str, list[str]]]:
    out = []
    reduce = ["sum", "mean", "std", "var", "min", "max", "argmin", "argmax", "prod", "all", "any"]
    for a in _VEC + _MAT:
        for f in reduce + ["cumsum", "cumprod"]:
            out.append(("method-reduce", [f"r = {a}.{f}()"]))
        for f in reduce + ["cumsum", "cumprod"]:
            if a in _MAT:
                for kw in ("axis=0", "axis=1", "axis=-1"):
                    out.append(("method-axis", [f"r = {a}.{f}({kw})"]))
        if a in _MAT:
            for f in ("sum", "mean", "max", "min", "std", "any"):
                out.append(("method-keepdims", [f"r = {a}.{f}(axis=0, keepdims=True)"]))
                out.append(("method-keepdims", [f"r = {a}.{f}(axis=1, keepdims=True)"]))
            for f in ("std", "var"):
                out.append(("method-ddof", [f"r = {a}.{f}(ddof=1)"]))
                out.append(("method-ddof", [f"r = {a}.{f}(axis=0, ddof=1)"]))
        for e in ("round()", "round(1)", "clip(0, 2)", "clip(min=0)", "astype(int)", "astype(float)",
                  "astype(bool)", "ravel()", "flatten()", "copy()", "argsort()", "conj()", "real", "imag",
                  "T", "transpose()", "squeeze()", "repeat(2)", "take([0, 1])", "nonzero()[0]", "cumsum()[-1]",
                  "reshape(-1)", "size", "ndim", "shape[0]", "sum() / len(" + a + ")", "mean().round(3)",
                  "max() - " + a + ".min()", "dot(" + a + ")", "swapaxes(0, 1)", "diagonal()", "trace()",
                  "argmax(axis=0)"):
            out.append(("method-misc", [f"r = {a}.{e}"]))
        out.append(("method-sort", [f"y = {a}.copy()", "y.sort()", "r = y"]))
        if a in _MAT:
            out.append(("method-sort", [f"y = {a}.copy()", "y.sort(axis=0)", "r = y"]))
            out.append(("method-sort", [f"r = {a}.argsort(axis=1)"]))
            out.append(("method-misc", [f"r = {a}.reshape(1, -1)"]))
            out.append(("method-misc", [f"r = {a}.reshape(-1, 1)[0]"]))
            out.append(("method-misc", [f"r = {a}.T @ {a}"]))
            out.append(("method-misc", [f"r = {a}.shape[1]"]))
        else:
            out.append(("method-misc", [f"r = {a}.reshape(2, 2)"]))
            out.append(("method-misc", [f"r = {a}.reshape(-1, 1)"]))
            out.append(("method-misc", [f"r = {a} @ {a}"]))
    return out


def _operators() -> list[tuple[str, list[str]]]:
    out = []
    pairs = [("x", "x"), ("xi", "xi"), ("x", "xi"), ("xi", "x"), ("x", "2.5"), ("2.5", "x"), ("xi", "3"),
             ("3", "xi"), ("xi", "-3"), ("-7", "xi"), ("x", "-2"), ("m", "m"), ("m", "x[:2]"), ("x[:2]", "m"),
             ("mr", "x[:3]"), ("m", "x[:2].reshape(-1, 1)"), ("mr", "mr"), ("m", "1.5"), ("xi", "x[0]"),
             ("b", "x"), ("b", "xi"), ("b", "b"), ("x[:, None]", "x"), ("x", "x[:, None]")]
    ops = ["+", "-", "*", "/", "//", "%", "**", "<", "<=", "==", "!=", ">", ">="]
    for a, c in pairs:
        for op in ops:
            out.append((f"op-{'arith' if op in '+-*/' or op in ('//', '%', '**') else 'cmp'}", [f"r = {a} {op} {c}"]))
    for a, c in [("xi", "xi"), ("b", "b"), ("xi", "3"), ("b", "True"), ("xi > 1", "xi < 4"), ("x > 0", "b")]:
        for op in ("&", "|", "^"):
            out.append(("op-bit", [f"r = ({a}) {op} ({c})"]))
    for a in ["x", "xi", "m", "b", "xi > 2"]:
        out.append(("op-unary", [f"r = -({a})" if a != "b" else "r = ~b"]))
        out.append(("op-unary", [f"r = abs({a})"]))
        out.append(("op-unary", [f"r = +({a})"]))
    out += [("op-unary", ["r = ~xi"]), ("op-unary", ["r = ~(x > 0)"]), ("op-unary", ["r = xi << 2"]),
            ("op-unary", ["r = xi >> 1"])]
    for a in ["x", "xi", "m"]:
        for op in ("+=", "-=", "*=", "/=", "//=", "%=", "**="):
            for c in ("2", "1.5", a):
                out.append(("op-inplace", [f"y = {a}.copy()" if a != "xi" or op not in ("/=", "**=") or c != "1.5"
                                           else f"y = {a}.astype(float)", f"y {op} {c}", "r = y"]))
    out += [("op-chain", ["r = (x + 1) * (x - 1) / 2"]), ("op-chain", ["r = x ** 2 - 2 * x + 1"]),
            ("op-chain", ["r = (m @ m)[0] + x[:2]"]), ("op-chain", ["r = 1 / (1 + x ** 2)"]),
            ("op-chain", ["r = (xi * 2 + 1) // 3 % 4"]), ("op-chain", ["r = -xi ** 2"]),
            ("op-chain", ["r = (-xi) ** 2"]), ("op-chain", ["r = 2 ** xi"]), ("op-chain", ["r = 2.0 ** -xi"]),
            ("op-chain", ["r = x / 4"]), ("op-chain", ["r = (x > 0) * x"]),
            ("op-chain", ["r = (x > 0).sum()"]), ("op-chain", ["r = (m > 1).mean(axis=0)"]),
            ("op-chain", ["r = x - x.mean()"]), ("op-chain", ["r = (m - m.mean(axis=0)) / m.std(axis=0)"]),
            ("op-chain", ["r = m / m.sum(axis=1, keepdims=True)"]), ("op-chain", ["r = m - m.max(axis=1)[:, None]"])]
    return out


def _indexing() -> list[tuple[str, list[str]]]:
    out = []
    vec = ["[0]", "[-1]", "[1:3]", "[::-1]", "[::2]", "[-3:]", "[:-1]", "[1::2]", "[3:0:-1]", "[-2::-1]",
           "[[0, 2]]", "[[-1, 0, 0]]", "[x > 0]", "[b]", "[xi % 4]", "[np.array([3, 1])]", "[None, :]",
           "[:, None]", "[np.newaxis]", "[...]", "[1:1]", "[10:]", "[-10:2]", "[2:-2]", "[xi > 2]"]
    for a in _VEC:
        for s in vec:
            out.append(("index-vec", [f"r = {a}{s}"]))
    mat = ["[0]", "[-1]", "[:, 1]", "[1, :]", "[-1, -1]", "[::-1]", "[:, ::-1]", "[::-1, ::-1]", "[0, 1:]",
           "[:, :1]", "[m > 1]", "[[1, 0]]", "[:, [1, 0]]", "[[0, 1], [1, 0]]", "[1][0]", "[None]", "[:, None, 0]",
           "[..., 0]", "[0, ...]", "[[True, False]]", "[:, [True, False]]", "[np.array([1]), :]", "[-1:, :]",
           "[0:1, 0:1]", "[1, ::-1]"]
    for a in _MAT:
        for s in mat:
            if a == "mr" and s in ("[m > 1]",):
                s = "[mr > 1]"
            if a == "mr" and s in ("[[True, False]]",):
                s = "[[False, True]]"
            out.append(("index-mat", [f"r = {a}{s}"]))
    writes = ["y[1] = 9", "y[-1] = -1", "y[1:3] = 7", "y[::2] = 0", "y[::-1] = y", "y[y > 1] = 0",
              "y[[0, 2]] = 5", "y[[0, 2]] += 1", "y[b] = 3", "y[:] = 1", "y[1:3] = [4, 5]", "y[::-2] = -9",
              "y[xi % 4] = 2", "y[-2:] += y[:2]", "y[y < 0] *= -1", "y[0] += y[-1]"]
    for a in ("x", "xi"):
        for w in writes:
            out.append(("index-write", [f"y = {a}.copy()", w, "r = y"]))
    mwrites = ["y[0, 0] = 9", "y[:, 0] = 7", "y[1] = 5", "y[1, :] = x[:y.shape[1]]", "y[:, -1] += 1",
               "y[y > 1] = 0", "y[y > 1] *= 2", "y[::-1] = y", "y[[1, 0]] = y", "y[:, [1, 0]] = 3",
               "y[0] = y[1]", "y[:, 0] = y[:, -1]", "y.T[0] = 4", "y[0, ::-1] = y[0]", "y[...] = 2"]
    for a in _MAT:
        for w in mwrites:
            out.append(("index-write-mat", [f"y = {a}.copy()", w, "r = y"]))
    out += [("index-view", ["y = x.copy()", "z = y[1:3]", "z[0] = 99", "r = y"]),
            ("index-view", ["y = m.copy()", "z = y[0]", "z[1] = 42", "r = y"]),
            ("index-view", ["y = x.copy()", "z = y", "z[0] = -5", "r = y"]),
            ("index-view", ["y = x.copy()", "z = y.copy()", "z[0] = -5", "r = y"]),
            ("index-view", ["y = m.copy()", "z = y.T", "z[0, 1] = 8", "r = y"]),
            ("index-view", ["y = x.copy()", "z = y[::-1]", "z[0] = 7", "r = y"]),
            ("index-view", ["y = m.copy()", "z = y.reshape(-1)", "z[0] = 3", "r = y"])]
    return out


def _mutators() -> list[tuple[str, list[str]]]:
    """In-place mutating functions and flat (C-order) index helpers, where a
    column-major slip would be silent."""
    out = []
    for a in ("x", "xi", "m", "mr"):
        for s in ("np.put(y, [0, 2], [9, 8])", "np.put(y, [-1], 5)", "np.put(y, 1, 7)", "np.put(y, [1, 3], 6)",
                  "y.put([0, 1], [5, 6])", "y.put([2], 7)", "np.place(y, y > 1, [7, 8])", "np.place(y, y > 1, 0)",
                  "np.putmask(y, y > 1, [7, 8, 9])", "np.putmask(y, y > 1, 0)", "np.copyto(y, 2)",
                  "np.copyto(y, y[::-1])", "np.copyto(y, -y, where=y > 1)", "y.fill(4)", "y.flat[3] = 9",
                  "y.flat[[0, 2]] = -1", "y.ravel()[1] = 5", "np.fill_diagonal(y, 7)",
                  "np.fill_diagonal(y, [1, 2])"):
            out.append(("mutate", [f"y = {a}.copy()", s, "r = y"]))
    for a in ("m", "mr"):
        for s in ("np.copyto(y, x[:y.shape[1]])", "np.copyto(y, 0, where=y > 1)",
                  "np.put_along_axis(y, np.argmax(y, axis=1)[:, None], 0, axis=1)",
                  "np.put_along_axis(y, np.argmin(y, axis=0)[None, :], -1, axis=0)",
                  "np.fill_diagonal(y.T, 5)"):
            out.append(("mutate", [f"y = {a}.copy()", s, "r = y"]))
        out += [("flat-index", [f"r = {a}.flat[4]"]), ("flat-index", [f"r = {a}.ravel()[3]"]),
                ("flat-index", [f"r = {a}.flatten(order='F')"]), ("flat-index", [f"r = {a}.ravel(order='F')"]),
                ("flat-index", [f"r = np.unravel_index({a}.argmax(), {a}.shape)[0]"]),
                ("flat-index", [f"r = np.unravel_index({a}.argmax(), {a}.shape)[1]"]),
                ("flat-index", [f"y, z = np.unravel_index({a}.argmin(), {a}.shape)", "r = np.array([y, z])"]),
                ("flat-index", [f"r = np.unravel_index(np.argsort({a}, axis=None), {a}.shape)[1]"]),
                ("flat-index", [f"r = {a}.reshape(-1, order='F')"]),
                ("flat-index", [f"r = {a}.reshape({a}.shape[1], -1)"]),
                ("flat-index", [f"r = np.take({a}, [0, 3])"]),
                ("flat-index", [f"r = np.argwhere({a} > 1)"])]
    out += [("flat-index", ["r = np.unravel_index(5, (2, 3))[0]"]),
            ("flat-index", ["r = np.unravel_index(5, (2, 3))[1]"]),
            ("flat-index", ["r = np.unravel_index([1, 4], (2, 3))[1]"]),
            ("flat-index", ["r = np.unravel_index([1, 4], (2, 3), order='F')[0]"]),
            ("flat-index", ["r = np.ravel_multi_index(([0, 1], [2, 0]), (2, 3))"]),
            ("flat-index", ["r = np.ravel_multi_index((1, 2), (2, 3))"]),
            ("flat-index", ["r = np.ravel_multi_index(([0, 1], [2, 0]), (2, 3), order='F')"]),
            ("flat-index", ["r = np.ravel_multi_index(np.nonzero(mr > 0.5), mr.shape)"])]
    for a in ("x", "xi"):
        out += [("callable", [f"r = np.piecewise({a}, [{a} < 0, {a} >= 0], [lambda t: -t, lambda t: t ** 2])"]),
                ("callable", [f"r = np.piecewise({a}, [{a} < 1], [0, 1])"]),
                ("callable", [f"r = np.piecewise({a}, [{a} < 0, {a} > 2], [-1, 1, 0])"])]
    for a in ("m", "mr"):
        for ax in (0, 1):
            out += [("callable", [f"r = np.apply_along_axis(np.sum, {ax}, {a})"]),
                    ("callable", [f"r = np.apply_along_axis(lambda v: v.max() - v.min(), {ax}, {a})"]),
                    ("callable", [f"r = np.apply_along_axis(np.sort, {ax}, {a})"])]
    return out


def templates() -> list[tuple[str, list[str]]]:
    seen, out = set(), []
    for g, stmts in _methods() + _operators() + _indexing() + _mutators():
        key = tuple(stmts)
        if key not in seen:
            seen.add(key)
            out.append((g, stmts))
    return out
