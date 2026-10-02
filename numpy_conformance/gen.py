"""Generate NumPy conformance programs for xp2f.py.

Each function in SPECS gets one program, cases/xnp_<name>.py. A spec entry
is an expression template; placeholders expand over the fixture variables
below, so one template covers int, float and bool inputs of each rank:

    {A}   any array      i1 f1 b1 i2 f2 b2
    {A1}  1-D array      i1 f1 b1
    {A2}  2-D array      i2 f2 b2
    {N}   numeric array  i1 f1 i2 f2
    {N1}  numeric 1-D    i1 f1
    {N2}  numeric 2-D    i2 f2
    {S}   scalar         i0 f0
    {T}   second scalar  j0 g0
    {SQ}  square matrix  s2 (well-conditioned float) k2 (integer)

A case is an expression, or statements and an expression written
`STMT <stmt>; <stmt> => <expr>` (for in-place operations); names w, w1,
w2, ... in it are local to the case.

Every case is evaluated with NumPy first; combinations NumPy rejects are
dropped. Each surviving case is emitted in up to three contexts: assigned
at the top level (`r_c001m = <expr>`), returned from a function whose
arguments get their types from the call (`f_c001(i1)`), and, for a
numeric result, accumulated in a loop (`acc = 0; for ...: acc +=
np.sum(<expr>)`, `l_c001`), the pattern of the int-started float
accumulator bug. Each prints a `case <id><context>` label line followed by
the value, so run.py can compare the cases one by one.

    python numpy_conformance/gen.py [name ...]
"""

from __future__ import annotations

import itertools
import re
import sys
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"

FIXTURES = {
    "i0": "3",
    "j0": "-2",
    "f0": "2.5",
    "g0": "-0.75",
    "i1": "np.array([3, -1, 4, 1, -5, 9])",
    "f1": "np.array([0.5, -1.25, 2.0, 3.75, -0.5, 1.5])",
    "b1": "np.array([True, False, True, True, False, False])",
    "i2": "np.array([[3, -1, 4], [1, -5, 9]])",
    "f2": "np.array([[0.5, -1.25, 2.0], [3.75, -0.5, 1.5]])",
    "b2": "np.array([[True, False, True], [True, False, False]])",
    "s2": "np.array([[4.0, 1.0, 0.5], [1.0, 3.0, 0.25], [0.5, 0.25, 2.0]])",
    "k2": "np.array([[2, 1, 0], [1, 3, 1], [0, 1, 4]])",
    "v3": "np.array([1.0, -2.0, 0.5])",
    "c1": "np.array([1 + 2j, -0.5 + 0j, 3 - 1j])",
    "p1": "np.array([0.25, 0.5, -0.75])",
    "q1": "np.array([1.5, 2.0, 3.0])",
    "e1": "np.array([1.0, np.nan, np.inf, -np.inf, -0.0])",
}

PLACEHOLDERS = {
    "A": ["i1", "f1", "b1", "i2", "f2", "b2"],
    "A1": ["i1", "f1", "b1"],
    "A2": ["i2", "f2", "b2"],
    "N": ["i1", "f1", "i2", "f2"],
    "N1": ["i1", "f1"],
    "N2": ["i2", "f2"],
    "S": ["i0", "f0"],
    "T": ["j0", "g0"],
    "SQ": ["s2", "k2"],
}

_REDUCE = [
    "np.{f}({A})", "{A}.{f}()",
    "np.{f}({A2}, axis=0)", "np.{f}({A2}, axis=1)", "np.{f}({A2}, axis=-1)",
    "np.{f}({A2}, axis=0, keepdims=True)", "np.{f}({N2}, axis=-1, keepdims=True)", "{N2}.{f}(axis=-1)",
]

SPECS = {
    "arange": [
        "np.arange(5)", "np.arange(5.0)", "np.arange(0.5, 3)", "np.arange(2, 11, 3)",
        "np.arange(10, 0, -3)", "np.arange(1.0, 0.0, -0.25)", "np.arange(0)",
        "np.arange(5, dtype=float)", "np.arange(5, dtype=np.float64)", "np.arange(0.0, 1.0, 0.1)",
        "np.arange({S})", "np.arange({T}, {S})", "np.arange(-3, 3)", "np.arange(3, dtype=np.int64)",
        "np.arange(1, 2, 0.3)", "np.arange(6).reshape(2, 3)",
    ],
    "linspace": [
        "np.linspace(0, 1, 5)", "np.linspace(0.0, 1.0, 4, endpoint=False)", "np.linspace(2, -1, 7)",
        "np.linspace({T}, {S}, 3)", "np.linspace(0, 10, 1)", "np.linspace(0, 1, 0)",
        "np.linspace(1, 5, 5, dtype=int)",
    ],
    "zeros": ["np.zeros(3)", "np.zeros((2, 3))", "np.zeros(4, dtype=int)", "np.zeros((2, 2), dtype=bool)",
              "np.zeros(0)", "np.zeros_like({A})", "np.zeros({S})"],
    "ones": ["np.ones(3)", "np.ones((2, 3))", "np.ones(4, dtype=int)", "np.ones((3, 1), dtype=bool)",
             "np.ones_like({A})"],
    "full": ["np.full(3, 7)", "np.full(3, 2.5)", "np.full((2, 3), -1.5)", "np.full(4, True)",
             "np.full((2, 2), {S})", "np.full_like({A}, 2)", "np.full(3, 7, dtype=float)"],
    "eye": ["np.eye(3)", "np.eye(2, 3)", "np.eye(3, k=1)", "np.eye(3, dtype=int)", "np.identity(3)"],
    "sum": [t.format(f="sum", A="{A}", A2="{A2}", N2="{N2}") for t in _REDUCE] + ["np.sum({A}, dtype=float)"],
    "prod": [t.format(f="prod", A="{A}", A2="{A2}", N2="{N2}") for t in _REDUCE],
    "mean": [t.format(f="mean", A="{A}", A2="{A2}", N2="{N2}") for t in _REDUCE],
    "min": [t.format(f="min", A="{A}", A2="{A2}", N2="{N2}") for t in _REDUCE] + ["np.amin({A})"],
    "max": [t.format(f="max", A="{A}", A2="{A2}", N2="{N2}") for t in _REDUCE] + ["np.amax({A})"],
    "argmin": ["np.argmin({A})", "{A}.argmin()", "np.argmin({A2}, axis=0)", "np.argmin({A2}, axis=1)"],
    "argmax": ["np.argmax({A})", "{A}.argmax()", "np.argmax({A2}, axis=0)", "np.argmax({A2}, axis=1)",
               "np.argmax({N2}, axis=-1)", "{N2}.argmax(axis=-1)"],
    "cumsum": ["np.cumsum({A})", "{A}.cumsum()", "np.cumsum({A2}, axis=0)", "np.cumsum({A2}, axis=1)",
               "np.cumsum({N2}, axis=-1)", "{N2}.cumsum(axis=-2)"],
    "cumprod": ["np.cumprod({A})", "np.cumprod({A2}, axis=0)", "np.cumprod({A2}, axis=1)"],
    "std": ["np.std({A})", "np.std({A2}, axis=0)", "np.std({A2}, axis=1)", "np.std({A}, ddof=1)",
            "np.std({N2}, axis=-1)",
            "{A}.std()"],
    "var": ["np.var({A})", "np.var({A2}, axis=0)", "np.var({A2}, axis=1)", "np.var({A}, ddof=1)"],
    "any_all": ["np.any({A})", "np.all({A})", "np.any({A2}, axis=0)", "np.all({A2}, axis=1)", "np.any({A2}, axis=-1)",
                "{A}.any()", "{A}.all()", "np.any({N} > 2)", "np.all({N} > -10)"],
    "where": ["np.where({N} > 1, {N}, 0)", "np.where({N} > 1, {N}, -0.5)", "np.where({A1})[0]",
              "np.where({N1} < 0, 1, 2)", "np.where({N2} > 0)[0]", "np.where({N2} > 0)[1]",
              "np.where({A2}, {S}, {T})"],
    "nonzero": ["np.nonzero({A1})[0]", "np.nonzero({A2})[0]", "np.nonzero({A2})[1]", "np.flatnonzero({A})",
                "np.count_nonzero({A})", "np.argwhere({A1})"],
    "sort": ["np.sort({A1})", "np.sort({A2})", "np.sort({A2}, axis=0)", "np.sort({A2}, axis=None)",
             "np.sort({N2}, axis=-1)", "np.sort({N2}, axis=-2)",
             "np.sort({A1})[::-1]"],
    "argsort": ["np.argsort({A1})", "np.argsort({N1})[::-1]", "np.argsort({A2}, axis=1)", "np.argsort({N2}, axis=-1)",
                "np.argsort({A2}, axis=0)", "np.argsort({N1}, kind='stable')"],
    "concatenate": ["np.concatenate(({A1}, {A1}))", "np.concatenate(({N1}, i1))",
                    "np.concatenate(({N2}, {N2}), axis=-1)",
                    "np.concatenate(({A2}, {A2}))", "np.concatenate(({A2}, {A2}), axis=1)",
                    "np.concatenate([{N1}, f1, i1])", "np.hstack(({N1}, f1))", "np.vstack(({A2}, {A2}))"],
    "reshape": ["{A1}.reshape(2, 3)", "{A1}.reshape((3, 2))", "np.reshape({A1}, (2, 3))", "{A2}.reshape(-1)",
                "{A1}.reshape(3, -1)", "{A2}.ravel()", "{A2}.flatten()", "{A2}.T", "np.transpose({A2})",
                "{A2}.reshape(3, 2)", "np.arange(24.0).reshape(2, 3, 4).ravel()",
                "np.arange(24).reshape(2, 3, 4).flatten()", "np.ravel({A2})"],
    "clip": ["np.clip({N}, -1, 2)", "np.clip({N}, -0.5, 1.5)", "np.clip({N}, 0, None)",
             "{N}.clip(-1, 3)", "np.clip({S}, 0, 1)"],
    "abs": ["np.abs({N})", "np.abs({S})", "np.absolute({N})", "abs({N})", "np.abs({T})", "np.fabs({N})"],
    "round": ["np.round({N})", "np.round(f1, 1)", "np.round({N} / 3, 2)", "np.around(f2)",
              "np.round(np.array([0.5, 1.5, 2.5, -0.5]))", "np.round({S} / 4, 1)", "np.rint(f1)",
              "np.floor({N})", "np.ceil({N})", "np.trunc({N} / 2)"],
    "diff": ["np.diff({N1})", "np.diff({N1}, n=2)", "np.diff({N2})", "np.diff({N2}, axis=0)",
             "np.diff({N2}, axis=-1)", "np.diff({N2}, axis=-2)"],
    "maximum": ["np.maximum({N}, 1)", "np.maximum({N1}, f1)", "np.minimum({N}, 0.5)",
                "np.minimum({N2}, i2)", "np.maximum({S}, {T})", "np.fmax({N}, 0)"],
    "dot": ["np.dot({N1}, f1)", "np.dot({N1}, i1)", "{N2} @ np.ones(3)", "np.dot({N2}, {N2}.T)",
            "{N2}.T @ {N2}", "np.matmul({N2}, np.ones((3, 2)))", "np.inner({N1}, i1)",
            "np.outer({N1}, np.array([1, 2]))", "np.vdot({N1}, f1)", "np.matmul({N2}, f2.T)",
            "np.dot(i2, f2.T)"],
    "unique": ["np.unique({A1})", "np.unique({A2})", "np.unique(np.array([3, 1, 3, 2, 1]))",
               "np.unique(np.array([2.5, -1.0, 2.5]))"],
    "math": ["np.sqrt(np.abs({N}))", "np.exp({N} / 4)", "np.log(np.abs({N}) + 1)", "np.log10(np.abs({N}) + 1)",
             "np.sin({N})", "np.cos({S})", "np.tanh({N})", "np.arctan2({N}, 2)", "np.hypot({N}, 1)",
             "np.square({N})", "np.power({N}, 2)", "np.sign({N})", "np.exp2({N1})", "np.log2(np.abs({N}) + 1)",
             "np.mod({N}, 3)", "np.floor_divide({N}, 2)", "{N} // 2", "{N} % 3", "{N} ** 2", "-{N}"],
}

SPECS.update({
    "linalg_norm": [
        "np.linalg.norm({N1})", "np.linalg.norm({N2})", "np.linalg.norm({N1}, 1)", "np.linalg.norm({N1}, np.inf)",
        "np.linalg.norm({N1}, ord=2)", "np.linalg.norm({N1}, -np.inf)", "np.linalg.norm({N2}, axis=0)",
        "np.linalg.norm({N2}, axis=1)", "np.linalg.norm({N2}, axis=-1)", "np.linalg.norm({SQ}, 'fro')",
        "np.linalg.norm({SQ}, 1)", "np.linalg.norm({SQ}, np.inf)", "np.linalg.norm({SQ}, 2)",
        "np.linalg.norm({N1} - 1)", "np.linalg.norm(v3 - {SQ} @ v3)",
    ],
    "linalg": [
        "np.linalg.solve({SQ}, v3)", "np.linalg.solve(s2, {SQ})", "np.linalg.det({SQ})", "np.linalg.inv({SQ})",
        "np.linalg.cholesky(s2)", "np.linalg.lstsq(f2.T, v3, rcond=None)[0]", "np.linalg.cond({SQ})",
        "np.linalg.solve({SQ}, v3) @ v3", "np.linalg.inv({SQ}) @ {SQ}", "np.linalg.det({SQ} * 2)",
        "np.linalg.matrix_power({SQ}, 2)", "np.linalg.eigvalsh(s2)",
    ],
    "diag_trace": [
        "np.diag({N1})", "np.diag({SQ})", "np.diag({N2})", "np.diag({N1}, 1)", "np.diag({N1}, k=-1)",
        "np.diag({SQ}, 1)", "np.diag({SQ}, -1)", "np.trace({SQ})", "np.trace({N2})", "{SQ}.trace()",
        "np.diagonal({SQ})", "np.diag(np.diag({SQ}))", "np.triu({SQ})", "np.tril({SQ}, -1)",
    ],
    "construct2": [
        "np.empty(3).shape", "np.empty((2, 3)).shape", "np.empty_like({A}).shape", "np.asarray({N1}, dtype=float)",
        "np.asarray([1, 2, 3])", "np.asarray({A1}, dtype=int)", "np.append({N1}, 7)", "np.append({N1}, {N1})",
        "np.append({N2}, {N2}, axis=0)", "np.append({N2}, {N2}, axis=1)", "np.append({N2}, 1.5)",
        "np.column_stack(({N1}, f1))", "np.meshgrid(i1[:3], f1[:2])[0]", "np.meshgrid(i1[:3], f1[:2])[1]",
        "np.meshgrid(i1[:3], f1[:2], indexing='ij')[0]", "np.flip({A1})", "np.flip({A2})", "np.flip({A2}, axis=0)",
        "np.flip({A2}, axis=1)", "np.flipud({A2})", "np.fliplr({A2})", "np.roll({A1}, 2)", "np.roll({A1}, -1)",
        "np.roll({A2}, 1)", "np.roll({A2}, 1, axis=0)", "np.roll({A2}, -1, axis=1)", "np.tile({N1}, 2)",
        "np.repeat({N1}, 2)", "np.ones((2, 3)).shape",
    ],
    "tests2": [
        "np.isfinite({N})", "np.isnan({N})", "np.isinf({N})", "np.isfinite(e1)", "np.isnan(e1)", "np.isinf(e1)",
        "np.nan_to_num(e1)", "np.array_equal({A}, {A})", "np.array_equal(i1, f1)", "np.array_equal(i1, i1 + 0)",
        "np.array_equal(i2, i2.T)", "np.allclose({N1}, {N1} + 1e-12)", "np.allclose(f1, f1 + 0.1)",
        "np.isclose({N1}, 1)", "np.finfo(float).eps", "np.finfo(float).max", "np.finfo(float).tiny",
        "np.finfo(np.float64).eps", "np.iinfo(np.int32).max", "np.sum(np.isnan(e1))",
    ],
    "math2": [
        "np.arctan({N})", "np.arccos(p1)", "np.arcsin(p1)", "np.tan({N1} / 4)", "np.sinh({N})", "np.cosh({N})",
        "np.arccosh(q1)", "np.arcsinh({N})", "np.arctanh(p1)", "np.gcd(i1, 6)", "np.gcd(i1, i1 + 2)",
        "np.lcm(i1, 4)", "np.conjugate(c1)", "np.conj(c1)", "np.angle(c1)", "np.abs(c1)", "np.real(c1)",
        "np.imag(c1)", "c1.conjugate()", "np.angle(f1)", "np.deg2rad({N1})", "np.rad2deg(p1)", "np.cbrt({N1})",
        "np.expm1(p1)", "np.log1p(q1)",
    ],
    "stats2": [
        "np.corrcoef(f1, i1)", "np.corrcoef(f2)", "np.quantile({N1}, 0.5)", "np.quantile({N1}, 0.25)",
        "np.quantile({N2}, 0.5)", "np.quantile({N1}, [0.1, 0.9])", "np.median({N})", "np.median({N2}, axis=0)",
        "np.percentile({N1}, 75)", "np.ptp({N1})", "np.average({N1})", "np.average(f1, weights=q1[[0, 1, 2, 0, 1, 2]])",
        "np.cov(f1, i1)", "np.histogram(f1, bins=3)[0]",
    ],
    "inplace": [
        "STMT w = {SQ}.copy(); np.fill_diagonal(w, 0) => w", "STMT w = {SQ}.copy(); np.fill_diagonal(w, 9) => w",
        "STMT w = f2.copy(); np.fill_diagonal(w, -1.5) => w", "STMT w = {N1}.copy(); w[::2] = 0 => w",
        "STMT w = {N1}.copy(); w.sort() => w", "STMT w = {N2}.copy(); w[0, :] = w[1, :] => w",
        "STMT w = {N2}.copy(); w += 1 => w", "STMT w = {N1}.copy(); w *= 2 => w", "STMT w = {N1}.copy(); w /= 4 => w",
        "STMT w = f1.copy(); w[w < 0] = 0 => w", "STMT w = {N2}.copy(); w[:, 1] = -1 => w",
        "STMT w = np.zeros(3); w[1] = {S} => w", "STMT w = np.zeros((2, 2)); w[0] = v3[:2] => w",
    ],
})

# Edge-case inputs (phase 3): program "<spec>__<edge>" runs <spec>'s
# templates with the placeholders mapped to these fixtures instead; only
# cases that use one of them are kept.
EDGE_FIXTURES = {
    "z1": "np.array([], dtype=float)",
    "zi1": "np.array([], dtype=int)",
    "z2": "np.zeros((0, 3))",
    "o1": "np.array([2.5])",
    "oi1": "np.array([7])",
    "o2": "np.array([[1.5]])",
    "n1": "np.array([1.0, np.nan, -2.0, np.inf, -np.inf, 0.5])",
    "n2": "np.array([[1.0, np.nan, -2.0], [np.inf, 0.5, -np.inf]])",
    "i3": "np.arange(24).reshape(2, 3, 4) - 7",
    "f3": "(np.arange(24).reshape(2, 3, 4) - 7) * 0.5",
    "c2": "np.array([[1 + 2j, -0.5 + 0j, 3 - 1j], [2j, 1 - 1j, -2 + 0.5j]])",
}
FIXTURES.update(EDGE_FIXTURES)

EDGE_SETS = {
    "empty": {"A1": ["z1", "zi1"], "A2": ["z2"], "N1": ["z1", "zi1"], "N2": ["z2"]},
    "one": {"A1": ["o1", "oi1"], "A2": ["o2"], "N1": ["o1", "oi1"], "N2": ["o2"]},
    "nan": {"A1": ["n1"], "A2": ["n2"], "N1": ["n1"], "N2": ["n2"]},
    "3d": {"A1": [], "A2": ["i3", "f3"], "N1": [], "N2": ["i3", "f3"]},
    "complex": {"A1": ["c1"], "A2": ["c2"], "N1": ["c1"], "N2": ["c2"]},
}
for _es in EDGE_SETS.values():
    _es["A"] = _es["A1"] + _es["A2"]
    _es["N"] = _es["N1"] + _es["N2"]


def split_name(name):
    """(spec, edge set or None) of a program name such as "sum__nan"."""
    spec, _, edge = name.partition("__")
    return spec, (edge or None)


_FIXTURE_RE = re.compile(r"\b(" + "|".join(FIXTURES) + r")\b")


def expand(template, placeholders=None):
    placeholders = dict(PLACEHOLDERS, **(placeholders or {}))
    keys = re.findall(r"\{(\w+)\}", template)
    keys = list(dict.fromkeys(keys))
    if not keys:
        return [template]
    out = []
    for combo in itertools.product(*(placeholders[k] for k in keys)):
        s = template
        for k, v in zip(keys, combo):
            s = s.replace("{" + k + "}", v)
        out.append(s)
    return list(dict.fromkeys(out))


def parse_case(case):
    """(statements, expression) of a case: `STMT a; b => expr` or `expr`."""
    if case.startswith("STMT "):
        body, expr = case[len("STMT "):].rsplit("=>", 1)
        return [s.strip() for s in body.split(";") if s.strip()], expr.strip()
    return [], case


def _local_names(case, cid, ctx):
    """case with its local names (w, w1, ...) made unique to cid/ctx."""
    return re.sub(r"\bw(\d*)\b", lambda m: f"w{m.group(1)}_{cid}{ctx}", case)


def evaluate(case, env):
    stmts, expr = parse_case(case)
    local = dict(env)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for s in stmts:
            exec(s, local)
        return eval(expr, local)


def numpy_accepts(case, env):
    try:
        v = evaluate(case, env)
    except Exception:
        return False
    if isinstance(v, tuple) and not all(isinstance(x, (int, np.integer)) for x in v):
        return False
    return True


def _fixture_env():
    env = {"np": np}
    for k, v in FIXTURES.items():
        env[k] = eval(v, env)
    return env


def contexts(case):
    """The contexts a case is emitted in: "mf", plus "l" (accumulated in a
    loop) for a numeric array or scalar result."""
    try:
        v = np.asarray(evaluate(case, _fixture_env()))
    except Exception:
        return "mf"
    if v.dtype.kind not in "biufc":
        return "mf"
    with np.errstate(all="ignore"):
        big = v.size and np.nanmax(np.abs(np.where(np.isfinite(v), v, 0))) > 1e300
    # Summing values near the float maximum overflows, which the debug
    # build traps (numpy gives inf).
    return "mf" if big else "mfl"


def build(name):
    env = _fixture_env()
    spec, edge = split_name(name)
    edge_names = set()
    if edge is not None:
        edge_names = {f for group in EDGE_SETS[edge].values() for f in group}
    exprs = []
    for template in SPECS[spec]:
        for e in expand(template, EDGE_SETS[edge] if edge else None):
            if edge is not None and not (set(_FIXTURE_RE.findall(e)) & edge_names):
                continue
            if e not in exprs and numpy_accepts(e, env):
                exprs.append(e)
    return exprs


def program_names(edges=True):
    """All program names: one per spec, then one per spec and edge set."""
    names = list(SPECS)
    if edges:
        names += [f"{s}__{e}" for e in EDGE_SETS for s in SPECS]
    return names


def program(name, exprs, ids=None):
    ids = ids or [f"c{k + 1:03d}" for k in range(len(exprs))]
    used = sorted({m for e in exprs for m in _FIXTURE_RE.findall(e)}, key=list(FIXTURES).index)
    lines = [f'"""xp2f NumPy conformance cases: {name} (generated by gen.py)."""', "import numpy as np", ""]
    for cid, e in zip(ids, exprs):
        params = ", ".join(sorted(set(_FIXTURE_RE.findall(e)), key=list(FIXTURES).index))
        stmts, expr = parse_case(_local_names(e, cid, "f"))
        lines += ["", f"def f_{cid}({params}):"] + [f"    {s}" for s in stmts] + [f"    return {expr}", ""]
        if "l" in contexts(e):
            stmts, expr = parse_case(_local_names(e, cid, "l"))
            lines += ["", f"def l_{cid}({params}):", "    acc = 0", "    for k_loop in range(2):"]
            lines += [f"        {s}" for s in stmts] + [f"        acc += np.sum({expr})", "    return acc", ""]
    lines += ["", "# fixtures"]
    lines += [f"{k} = {FIXTURES[k]}" for k in used]
    for cid, e in zip(ids, exprs):
        params = ", ".join(sorted(set(_FIXTURE_RE.findall(e)), key=list(FIXTURES).index))
        stmts, expr = parse_case(_local_names(e, cid, "m"))
        lines += ["", f"# {e}"] + stmts + [
            f"r_{cid}m = {expr}",
            f'print("case {cid}m")',
            f"print(r_{cid}m)",
            f"r_{cid}f = f_{cid}({params})",
            f'print("case {cid}f")',
            f"print(r_{cid}f)",
        ]
        if "l" in contexts(e):
            lines += [f"r_{cid}l = l_{cid}({params})", f'print("case {cid}l")', f"print(r_{cid}l)"]
    return "\n".join(lines) + "\n"


def write(name):
    exprs = build(name)
    CASES.mkdir(exist_ok=True)
    path = CASES / f"xnp_{name}.py"
    path.write_text(program(name, exprs), encoding="utf-8")
    (CASES / f"xnp_{name}.cases").write_text(
        "".join(f"c{k + 1:03d}\t{e}\n" for k, e in enumerate(exprs)), encoding="utf-8"
    )
    return path, len(exprs)


if __name__ == "__main__":
    names = sys.argv[1:] or program_names()
    total = 0
    for nm in names:
        if not build(nm):
            continue
        path, n = write(nm)
        total += n
        print(f"{path.name}: {n} cases")
    print(f"total: {total} cases in {len(names)} programs")
