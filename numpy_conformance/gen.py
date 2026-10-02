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

Every case is evaluated with NumPy first; combinations NumPy rejects are
dropped. Each surviving case is emitted twice: assigned at the top level
(`r_c001m = <expr>`) and returned from a function whose arguments get
their types from the call (`f_c001(i1)`), the two inference paths of xp2f.
Each prints a `case <id>` label line followed by the value, so run.py can
compare the cases one by one.

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

_FIXTURE_RE = re.compile(r"\b(" + "|".join(FIXTURES) + r")\b")


def expand(template):
    keys = re.findall(r"\{(\w+)\}", template)
    keys = list(dict.fromkeys(keys))
    if not keys:
        return [template]
    out = []
    for combo in itertools.product(*(PLACEHOLDERS[k] for k in keys)):
        s = template
        for k, v in zip(keys, combo):
            s = s.replace("{" + k + "}", v)
        out.append(s)
    return list(dict.fromkeys(out))


def numpy_accepts(expr, env):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            v = eval(expr, env)
    except Exception:
        return False
    if isinstance(v, tuple):
        return False
    return True


def build(name):
    env = {"np": np}
    for k, v in FIXTURES.items():
        env[k] = eval(v, env)
    exprs = []
    for template in SPECS[name]:
        for e in expand(template):
            if e not in exprs and numpy_accepts(e, env):
                exprs.append(e)
    return exprs


def program(name, exprs, ids=None):
    ids = ids or [f"c{k + 1:03d}" for k in range(len(exprs))]
    used = sorted({m for e in exprs for m in _FIXTURE_RE.findall(e)}, key=list(FIXTURES).index)
    lines = [f'"""xp2f NumPy conformance cases: {name} (generated by gen.py)."""', "import numpy as np", ""]
    for cid, e in zip(ids, exprs):
        params = sorted(set(_FIXTURE_RE.findall(e)), key=list(FIXTURES).index)
        lines += ["", f"def f_{cid}({', '.join(params)}):", f"    return {e}", ""]
    lines += ["", "# fixtures"]
    lines += [f"{k} = {FIXTURES[k]}" for k in used]
    for cid, e in zip(ids, exprs):
        params = sorted(set(_FIXTURE_RE.findall(e)), key=list(FIXTURES).index)
        lines += [
            "",
            f"# {e}",
            f"r_{cid}m = {e}",
            f'print("case {cid}m")',
            f"print(r_{cid}m)",
            f"r_{cid}f = f_{cid}({', '.join(params)})",
            f'print("case {cid}f")',
            f"print(r_{cid}f)",
        ]
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
    names = sys.argv[1:] or list(SPECS)
    total = 0
    for nm in names:
        path, n = write(nm)
        total += n
        print(f"{path.name}: {n} cases")
    print(f"total: {total} cases in {len(names)} programs")
