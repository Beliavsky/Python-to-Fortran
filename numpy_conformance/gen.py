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
    "r1": "np.array([-2.0, 0.5, 0.5, 3.0, 7.5])",
    "ri1": "np.array([1, 3, 3, 8])",
    "ix": "np.array([0, 2, 5])",
    "nb1": "np.array([0, 2, 1, 2, 5, 0])",
    "g3": "np.array([[2.0, -1.0, 0.5], [1.0, 3.0, 1.0], [0.0, 1.0, 1.5]])",
    "r3": "np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [1.0, 0.0, 1.0]])",
    "b32": "np.array([[1.0, 0.0], [2.0, 1.0], [-1.0, 3.0]])",
    "a42": "np.array([[1.0, 1.0], [1.0, 2.0], [1.0, 3.0], [1.0, 4.0]])",
    "y4": "np.array([1.1, 1.9, 3.2, 3.9])",
    "sa3": "np.array([[[4.0, 1.0], [1.0, 3.0]], [[2.0, 0.5], [0.5, 1.0]], [[5.0, 2.0], [2.0, 6.0]]])",
    "sk3": "np.array([[[2, 1], [1, 3]], [[4, 1], [2, 5]]])",
    "sm3": "np.array([[[1.0, 2.0, 0.5], [0.0, 1.0, 3.0]], [[2.0, -1.0, 1.0], [1.0, 1.0, 1.0]], [[0.5, 0.0, 2.0], [1.5, 2.0, -1.0]]])",
    "sr3": "np.array([[[1.0, 2.0], [2.0, 4.0]], [[1.0, 0.0], [0.0, 1.0]]])",
    "sm2": "np.array([[1.0, 2.0, 0.5], [0.0, 1.0, 3.0]])",
    "sb1": "np.array([1.0, 2.0])",
    "sb2": "np.array([[1.0, 0.0, 2.0], [3.0, 1.0, -1.0]])",
    "sb3": "np.array([[[1.0], [2.0]], [[0.5], [1.0]], [[2.0], [-1.0]]])",
    "sa4": "np.stack([sa3, sa3 * 2.0 - 1.0])",
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

# Phase 4: set/search functions and indexing.
SPECS.update({
    "setsearch": [
        "np.searchsorted(r1, {N1})", "np.searchsorted(r1, {S})", "np.searchsorted(r1, {N1}, side='right')",
        "np.searchsorted(ri1, {S}, side='right')", "np.searchsorted(ri1, i1)",
        "np.isin({A1}, ri1)", "np.isin({N2}, [1, 3, -0.5])", "np.isin({N1}, r1, invert=True)",
        "np.intersect1d({N1}, ri1)", "np.union1d({N1}, r1)", "np.setdiff1d({N1}, ri1)", "np.setxor1d(i1, ri1)",
        "np.bincount(nb1)", "np.bincount(nb1, minlength=8)", "np.bincount(nb1, weights=f1)",
        "np.digitize({N1}, r1)", "np.digitize({N1}, r1, right=True)",
        "np.unique({A1}, return_counts=True)[1]", "np.unique({A1}, return_index=True)[1]",
        "np.unique({A1}, return_inverse=True)[1]", "np.unique({A1}, return_counts=True)[0]",
        "np.count_nonzero({A2}, axis=0)", "np.count_nonzero({A2}, axis=1)",
    ],
    "indexing": [
        "{A1}[ix]", "{A2}[[1, 0]]", "{A2}[[1, 0], :]", "{A2}[:, [2, 0]]", "{A2}[[0, 1], [2, 0]]",
        "{N1}[{N1} > 0]", "{N2}[{N2} > 0]", "{A1}[b1]", "np.take({A1}, ix)", "np.take({A2}, [1, 0], axis=1)",
        "{A1}[-1]", "{A1}[::-2]", "{A2}[-1, ::-1]", "{N1}[np.argsort({N1})]", "{N1}[ix[::-1]]",
        "STMT w = {N1}.copy(); w[w > 0] = 0 => w", "STMT w = {N2}.copy(); w[w < 0] += 10 => w",
        "STMT w = {N1}.copy(); w[ix] = -7 => w", "STMT w = {N1}.copy(); w[[0, 1]] = w[[1, 0]] => w",
        "STMT w = {N2}.copy(); w[:, [0, 2]] = 0 => w", "STMT w = {N1}.copy(); np.put(w, ix, 9) => w",
        "STMT w = {N1}.copy(); w[ix] += 1 => w", "STMT w = {N2}.copy(); w[w > 1] = w[w > 1] * 2 => w",
        "STMT w = {N1}.copy(); w[np.argsort(w)[:2]] = 0 => w", "STMT w = {N1}.copy(); w[np.where(w < 0)] = 1 => w",
        "STMT w = {N2}.copy(); w[1] = w[0][::-1] => w", "STMT w = {N1}.copy(); w[b1] = {S} => w",
    ],
})

# Phase 5: linear algebra (decompositions checked by sign/order-free
# quantities: sorted eigenvalues, |reconstruction - a|, |Q.T Q - I|).
SPECS.update({
    "linalg2": [
        'np.linalg.det(s2)',
        'np.linalg.det(g3)',
        'np.linalg.det(k2)',
        'np.linalg.inv(s2)',
        'np.linalg.inv(g3)',
        'np.linalg.solve(s2, v3)',
        'np.linalg.solve(g3, b32)',
        'np.linalg.solve(k2, v3)',
        'np.linalg.matrix_rank(s2)',
        'np.linalg.matrix_rank(r3)',
        'np.linalg.slogdet(g3)[0]',
        'np.linalg.slogdet(g3)[1]',
        'np.linalg.cond(s2)',
        'np.linalg.cond(g3, 1)',
        'np.linalg.matrix_power(g3, 3)',
        'np.linalg.matrix_power(s2, 0)',
        'np.linalg.multi_dot([g3, s2, g3])',
        'np.linalg.pinv(f2)',
        'np.linalg.lstsq(a42, y4, rcond=None)[0]',
        'np.linalg.lstsq(a42, y4, rcond=None)[1]',
        'np.linalg.cholesky(s2)',
        'np.sort(np.linalg.eigvalsh(s2))',
        'np.sort(np.linalg.eigvals(g3).real)',
        'np.linalg.eigh(s2)[0]',
        'np.linalg.norm(s2 @ np.linalg.eigh(s2)[1] - np.linalg.eigh(s2)[1] * np.linalg.eigh(s2)[0])',
        'np.linalg.svd(f2, compute_uv=False)',
        'np.linalg.svd(g3)[1]',
        'np.linalg.norm(np.linalg.svd(f2, full_matrices=False)[0] @ np.diag(np.linalg.svd(f2, full_matrices=False)[1]) @ np.linalg.svd(f2, full_matrices=False)[2] - f2)',
        'np.abs(np.linalg.qr(g3)[1])',
        'np.linalg.norm(np.linalg.qr(g3)[0] @ np.linalg.qr(g3)[1] - g3)',
        'np.linalg.norm(np.linalg.qr(g3)[0].T @ np.linalg.qr(g3)[0] - np.eye(3))',
        'np.linalg.norm(g3, 2)',
        'np.linalg.norm(g3, -2)',
        "np.linalg.norm(g3, 'nuc')",
        'np.linalg.norm(g3, np.inf)',
        'np.linalg.norm(g3, 1)',
        'np.trace(g3)',
        'np.cross(v3, q1)',
        'np.cross(f2[0], f2[1])',
        'np.kron(s2, np.eye(2))',
        'np.tensordot(g3, s2, axes=1)',
        'np.tensordot(g3, s2, axes=2)',
        'np.einsum("ij,jk->ik", g3, s2)',
        'np.einsum("ii", g3)',
        'np.einsum("ij->ji", f2)',
        'np.einsum("i,i", v3, q1)',
        'np.einsum("ij,j->i", g3, v3)',
        'np.outer(v3, q1)',
        'np.vdot(g3, s2)',
        'np.inner(g3, s2)',
        'np.matmul(g3, v3)',
        'v3 @ g3',
        'np.linalg.vector_norm(v3)',
        'np.linalg.matrix_norm(g3)',
        'np.linalg.vecdot(v3, q1)',
        'np.linalg.svdvals(g3)',
        'np.linalg.outer(v3, q1)',
        'np.linalg.cross(v3, q1)',
        'np.linalg.matrix_transpose(f2)',
        'np.linalg.diagonal(g3)',
        'np.linalg.trace(g3)',
        'np.einsum("ij,jk", g3, s2)',
        'np.einsum("ik,kj->ij", g3, s2)',
        'np.einsum("ji", f2)',
        'np.einsum("ij,ij", g3, s2)',
        'np.einsum("i,j", v3, q1)',
        'np.einsum("ij->", f2)',
        'np.einsum("ij->j", f2)',
        'np.einsum("ij,kj->ik", f2, f2)',
        'np.einsum("ji,jk->ik", f2, f2)',
        'np.einsum("ii->i", g3)',
        'np.einsum("i,ij->j", v3, g3)',
        'np.linalg.cond(g3, np.inf)',
        "np.linalg.cond(g3, 'fro')",
        'np.linalg.cond(g3, -2)',
        'np.linalg.cond(s2, -1)',
        'np.linalg.norm(g3, -1)',
        'np.inner(v3, g3)',
        'np.inner(g3, v3)',
        'np.kron(k2, s2[:2, :2])',
        'np.linalg.vector_norm(f2)',
        'np.linalg.vector_norm(f2, ord=1)',
        'np.linalg.vector_norm(f2, axis=0)',
        'np.linalg.matrix_norm(g3, ord=1)',
        'np.linalg.norm(f2, None, 0)',
        'np.linalg.norm(f2, axis=None)',
    ],
})

# Phase 5b: stacked (batched) linear algebra -- the last two axes are the
# matrices.
SPECS.update({
    "linalg_stack": [
        'np.linalg.inv(sa3)',
        'np.linalg.det(sa3)',
        'np.linalg.det(sk3)',
        'np.linalg.cholesky(sa3)',
        'np.linalg.pinv(sm3)',
        'np.linalg.matrix_power(sa3, 3)',
        'np.linalg.matrix_rank(sr3)',
        'np.linalg.cond(sa3)',
        'np.linalg.eigvalsh(sa3)',
        'np.sort(np.linalg.eigvals(sa3).real, axis=-1)',
        'np.linalg.solve(sa3, sb1)',
        'np.linalg.solve(sa3, sb2)',
        'np.linalg.solve(sa3, sb3)',
        'np.linalg.norm(sa3, axis=(1, 2))',
        'np.linalg.norm(sa3, axis=(-2, -1))',
        'np.linalg.norm(sa3, ord=2, axis=(1, 2))',
        'np.linalg.matrix_norm(sa3)',
        'np.linalg.trace(sa3)',
        'np.linalg.diagonal(sm3)',
        'sa3 @ sa3',
        'sa3 @ sm2',
        'sm2.T @ sa3',
        'sa3 @ sb1',
        'sb1 @ sa3',
        'np.matmul(sa3, sa3)',
        "np.einsum('bij,bjk->bik', sa3, sa3)",
        'np.linalg.det(sa4)',
        'np.linalg.inv(sa4)',
        'np.linalg.eigvalsh(sa4)',
        'np.linalg.svd(sm3, compute_uv=False)',
        'np.linalg.slogdet(sa3)[1]',
        'np.linalg.eigh(sa3)[0]',
        'np.abs(np.linalg.qr(sm3)[1])',
        'np.trace(sa3)',
        "np.einsum('bij,jk->bik', sa3, sm2)",
        "np.einsum('ij,bjk->bik', sm2.T, sa3)",
        "np.einsum('bij,j->bi', sa3, sb1)",
        "np.einsum('bii->b', sa3)",
        "np.einsum('bii->bi', sa3)",
        "np.einsum('bij->bji', sm3)",
        'np.linalg.norm(sa4, axis=(2, 3))',
        'np.linalg.matrix_rank(np.stack([sr3, sr3]))',
        'np.linalg.slogdet(sa3)[0]',
        'np.linalg.svd(sm3)[1]',
        'np.linalg.norm(np.linalg.qr(sm3)[0] @ np.linalg.qr(sm3)[1] - sm3)',
        'np.linalg.det(sa4)',
        'np.linalg.solve(sa3, sb1) @ sb1',
    ],
})

# Two halves, so each program builds in reasonable time.
_ls = SPECS.pop("linalg_stack")
SPECS["linalg_stack_a"] = _ls[:len(_ls) // 2]
SPECS["linalg_stack_b"] = _ls[len(_ls) // 2:]

# Phase 6: small integer dtypes (numpy wraps int8/int16/uint8/uint16
# arithmetic around; reductions such as sum widen to int64), iinfo, and
# conversions with astype / np.int8(...).
FIXTURES.update({
    "q8": "np.array([100, -120, 7, 127, -128, 0], dtype=np.int8)",
    "qu8": "np.array([200, 3, 255, 0, 128, 17], dtype=np.uint8)",
    "q16": "np.array([30000, -30000, 5, 32767, -1, 2], dtype=np.int16)",
    "qu16": "np.array([60000, 1, 65535, 0, 40000, 7], dtype=np.uint16)",
    "q82": "np.array([[100, -3, 50], [7, 127, -128]], dtype=np.int8)",
})
PLACEHOLDERS["Q"] = ["q8", "qu8", "q16", "qu16"]

# Phase 8: windows, FFT shifts, legacy polynomials, frexp/modf, NaN quantiles.
SPECS["numerics1"] = [
    "np.hanning(7)", "np.hamming(6)", "np.blackman(5)", "np.bartlett(6)", "np.kaiser(5, 2.5)", "np.hanning(1)",
    "np.hamming(3) * {N1}[:3]", "np.fft.fftshift({N1})", "np.fft.ifftshift({N1})", "np.fft.fftshift({N2})",
    "np.fft.fftshift({N2}, axes=1)", "np.fft.ifftshift({N2}, axes=(0,))", "np.fft.fftshift(np.fft.fftfreq(5))",
    "np.abs(np.fft.ifft({N1}))", "np.poly({N1}[:3])", "np.poly(q1)", "np.polyadd({N1}, q1)", "np.polysub(q1, {N1})",
    "np.polymul({N1}, q1)", "np.polymul({N1}, [2, -1])", "np.polydiv({N1}, q1)[0]", "np.polydiv({N1}, q1)[1]",
    "np.polydiv({N1}, np.array([1.0, -2.0]))[1]", "np.polyint({N1})", "np.polyint({N1}, 2)",
    "np.polyint({N1}, k=3.0)", "np.polyint(q1, m=2, k=[1.0, -1.0])", "np.frexp({N})[0]", "np.frexp({N})[1]",
    "np.modf({N} * 1.5)[0]", "np.modf({N} * 1.5)[1]", "STMT w1, w2 = np.polydiv({N1}, q1) => w1.sum() + w2.sum()",
    "STMT w1, w2 = np.frexp({N1} * 3.0) => w1 * w2", "STMT w1, w2 = np.modf({S} * 2.5) => w1 + w2",
    "np.nanmedian(nn1)", "np.nanpercentile(nn1, 30)", "np.nanquantile(nn1, 0.8)", "np.nanmedian({N1})",
    "np.nanmedian(nn2)", "np.nanmedian(nn2, axis=0)", "np.nanpercentile(nn2, 25, axis=1)",
    "np.nanquantile(nn2, 0.5, axis=-1)", "np.nanmedian(n1)",
    # np.emath of inputs with values outside the real domain (complex in
    # numpy too; the translation is always complex).
    "np.emath.sqrt({N1})", "np.emath.log({N1})", "np.emath.log2(f1)", "np.emath.log10({N1})",
    "np.emath.logn(3, f1)", "np.emath.power(f1, 0.5)", "np.emath.arcsin(f1)", "np.emath.arccos(f1)",
    "np.emath.arctanh(f1)", "np.emath.sqrt({N1}) * 2.0 + 1.0", "np.emath.sqrt(j0 * 1.0)",
]
FIXTURES["nn1"] = "np.array([1.0, np.nan, 3.0, 7.0, np.nan, 2.0])"
FIXTURES["nn2"] = "np.array([[1.0, np.nan, 3.0], [4.0, 5.0, np.nan]])"

# Phase 7: numerical calculus on samples (uneven coordinates xc).
FIXTURES["xc"] = "np.array([0.0, 0.5, 1.5, 3.0, 3.5, 5.0])"
SPECS["calculus"] = [
    "np.gradient({N1})", "np.gradient({N1}, 0.5)", "np.gradient({N1}, xc)", "np.gradient({N1}, xc, edge_order=2)",
    "np.gradient({N1}, edge_order=2)", "np.gradient({N1}, np.linspace(0.0, 2.5, 6))", "np.gradient({N1}[:2])",
    "np.gradient({N2}, axis=0)", "np.gradient({N2}, axis=1)", "np.gradient({N2}, 2.0, axis=-1, edge_order=2)",
    "np.gradient({N2}, xc[:3], axis=1)", "STMT w1, w2 = np.gradient({N2}) => w1 + 10 * w2",
    "STMT w1, w2 = np.gradient({N2}, 0.5, xc[:3]) => w1 - w2",
    "np.trapezoid({N1})", "np.trapezoid({N1}, xc)", "np.trapezoid({N1}, dx=0.5)",
    "np.interp(np.array([0.25, 2.0, 4.9]), xc, {N1})", "np.interp(np.array([-1.0, 6.0]), xc, {N1}, left=-5.0, right=5.0)",
    "np.interp({S}, xc, {N1})", "np.diff({N1}) / np.diff(xc)",
    "np.interp(np.array([-0.5, 2.0, 5.5, 7.0]), xc, {N1}, period=4.0)", "np.interp({S}, xc, {N1}, period=4.0)",
    "np.polynomial.legendre.leggauss(4)[0]", "np.polynomial.legendre.leggauss(5)[1]",
    "np.histogram2d(f1, xc, bins=3)[0]", "np.histogram2d(i1, f1, bins=[2, 3], density=True)[0]",
    "np.histogram2d(f1, xc, bins=2, range=[[-2.0, 4.0], [0.0, 5.0]])[1]", "np.histogram2d(f1, xc, bins=2, weights=xc)[0]",
    "np.histogram({N1}, bins=3)[1]", "np.histogram({N1}, bins=3, range=(-2, 10))[0]",
]

SPECS["dtypes"] = [
    "{Q} + {Q}", "{Q} * 3", "{Q} - 100", "-{Q}", "{Q} // 3", "{Q} % 7", "{Q} ** 2", "np.abs({Q})",
    "{Q} + i1", "{Q} * 1.5", "{Q} / 2", "q8 + q16", "q8 + qu8", "qu8 + q16", "qu8 + qu16", "q8 * qu8",
    "np.sum({Q})", "np.cumsum({Q})", "np.prod(q8[:3])", "np.mean({Q})", "np.max({Q}) + 100", "{Q}.min() - 100",
    "{Q}[1] * 2", "{Q}[::2] + 100", "np.diff({Q})", "np.where({Q} > 5, {Q}, 0) + 100", "np.minimum({Q}, 5) - 100",
    "np.sort({Q}) * 2", "np.flip({Q}) + {Q}", "np.concatenate([{Q}, {Q}]) * 3", "np.dot(q8, q8)",
    "q82 @ q82.T", "q82.T + q82.T", "q82 * 2", "np.sum(q82, axis=0)", "np.max(q82, axis=1) + 100",
    "{Q}.astype(int) * 1000", "{Q}.astype(np.float64) / 2", "(i1 * 50).astype(np.int8)",
    "(f1 * 100).astype(np.int8)", "(i1 * 100).astype(np.uint8)", "(i1 * 20000).astype(np.int16)",
    "(i1 * 30000).astype(np.uint16)", "i2.astype(np.int8) * 64", "np.int16(i0) * 20000",
    "STMT w = {Q}.copy(); w += 100 => w", "STMT w = {Q}.copy(); w *= 3 => w", "STMT w = {Q}.copy(); w[1:3] -= 50 => w",
    "STMT w = q8.copy(); w[0] = 3 => w * 50", "STMT w = np.zeros(3, dtype=np.int8); w[1] = 100 => w + w",
    "STMT w = np.full(4, 7, dtype=np.uint8) => w - 10", "STMT w = np.arange(5, dtype=np.int16) => w * 10000",
    "np.iinfo(np.int8).max", "np.iinfo(np.int8).min", "np.iinfo(np.int16).min", "np.iinfo(np.uint8).max",
    "np.iinfo(np.int32).min", "np.iinfo(np.int32).max", "np.iinfo(int).bits",
    "{Q}.dtype == np.int8", "i1.dtype == np.int64", "f1.dtype == np.float64", "f1.dtype != np.int64",
]

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
