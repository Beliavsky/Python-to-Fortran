"""Regression coverage for concatenate axes and NumPy/SciPy Cholesky orientation."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRANSPILER = ROOT / "xp2f.py"


def translate(tmp_path, source, compare=True):
    script = tmp_path / "xconcat_axis.py"
    script.write_text(source, encoding="utf-8")
    args = [sys.executable, str(TRANSPILER), str(script)]
    if compare:
        args += ["--compile", "--run-diff"]
    return subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.parametrize("dtype", ["int", "float", "complex", "bool"])
def test_axes_and_values(tmp_path, dtype):
    lines = ["import numpy as np",
             f"a = np.array([[1, 0, 3], [4, 5, 6]], dtype={dtype})",
             f"b = np.array([[7, 8, 9]], dtype={dtype})",
             f"c = np.array([[2], [3]], dtype={dtype})",
             f"v = np.array([1, 0, 3], dtype={dtype})",
             f"w = np.array([4, 5], dtype={dtype})"]
    if dtype == "complex":
        lines += ["a = a + 0.25j", "c = c - 0.5j"]
    for index, (other, axis) in enumerate([
        ("b", ""), ("b", ", 0"), ("b", ", axis=0"),
        ("b", ", -2"), ("b", ", axis=-2"),
        ("c", ", 1"), ("c", ", axis=1"),
        ("c", ", -1"), ("c", ", axis=-1"),
    ]):
        name = f"m{index}"
        lines += [f"{name} = np.concatenate((a, {other}){axis})",
                  f"print({name}.shape[0], {name}.shape[1])",
                  f"for i in range({name}.shape[0]):",
                  f"    for j in range({name}.shape[1]):",
                  f"        print({name}[i, j])"]
    for index, axis in enumerate(["", ", 0", ", -1", ", axis=-1"]):
        name = f"v{index}"
        lines += [f"{name} = np.concatenate((v, w){axis})",
                  f"for i in range({name}.size):", f"    print({name}[i])"]
    result = translate(tmp_path, "\n".join(lines))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Run diff: MATCH" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("axis, message", [
    (", 2", "out of bounds"), (", -3", "out of bounds"),
    (", axis=2", "out of bounds"), (", None", "literal integer"),
    (", axis=None", "literal integer"), (", axis=k", "literal integer"),
    (", 1, axis=0", "more than once"), (", 0, None", "out argument"),
])
def test_reject_unsupported_axes(tmp_path, axis, message):
    result = translate(tmp_path, "import numpy as np\nk = 1\na = np.zeros((2, 3))\n"
                       f"b = np.concatenate((a, a){axis})\nprint(b)\n", compare=False)
    assert result.returncode != 0
    assert message in result.stdout + result.stderr


def test_prometeo_riccati(tmp_path):
    # Prometeo Riccati example, with explicit NumPy qualification.
    # Embed the small fixture so the tests do not require untracked reports.
    source = r"""
import numpy as np
from scipy import linalg

nx = 2
nu = 2
nxu = 4
N = 5

A = np.array([[0.8, 0.1], [0.3, 0.8]])
B = np.array([[1.0, 0.0], [0.0, 1.0]])
Q = np.array([[1.0, 0.0], [0.0, 1.0]])
R = np.array([[1.0, 0.0], [0.0, 1.0]])
P = Q

BA = np.zeros((nx, nxu))
M = np.zeros((nxu, nxu))
Mxx = np.zeros((nx, nx))
for i in range(N):
    BA = np.concatenate((B,A),1)
    BAtP = np.dot(np.transpose(BA), P)
    M = np.zeros((nxu, nxu))
    M[0:nu, 0:nu] = R
    M[nu:nu+nx, nu:nu+nx] = Q
    M = M + np.dot(BAtP, BA)
    L = linalg.cholesky(M)
    print('L:\n', L)
    Mxx = L[nu:nu+nx, nu:nu+nx]
    P = np.dot(np.transpose(Mxx), Mxx)
    print('P:\n', P)

P = Q
for i in range(N):
    P = Q + np.dot(np.transpose(A),np.dot(P,A)) - np.dot(np.dot(np.transpose(A),np.dot(P,B)), \
        linalg.solve(R + np.dot(np.transpose(B), np.dot(P,B)), \
        np.dot(np.dot(np.transpose(B),P), A)))

    print('P:\n', P)
"""
    # Print full-precision scalars to avoid unrelated matrix layout and
    # NumPy display-precision differences in the run-diff comparator.
    for name in ("L", "P"):
        source = source.replace(f"    print('{name}:\\n', {name})",
                                f"    for row in range({name}.shape[0]):\n"
                                f"        for col in range({name}.shape[1]):\n"
                                f"            print({name}[row, col])")
    result = translate(tmp_path, source)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Run diff: MATCH" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("imports, calls", [
    ("from scipy import linalg", ["linalg.cholesky(a)", "linalg.cholesky(a, False)", "linalg.cholesky(a, lower=False)", "linalg.cholesky(a, True)"]),
    ("import scipy.linalg as la", ["la.cholesky(a)", "la.cholesky(a, lower=True)"]),
    ("from scipy.linalg import cholesky as chol", ["chol(a)", "chol(a, lower=True)"]),
    ("import scipy as sp", ["sp.linalg.cholesky(a)"]),
    ("from numpy.linalg import cholesky as chol", ["chol(a)", "chol(a, upper=True)"]),
    ("from numpy import linalg as la", ["la.cholesky(a)", "la.cholesky(a, upper=True)"]),
])
def test_cholesky_orientation(tmp_path, imports, calls):
    # Deliberately different triangles: transposing only the OUTPUT would
    # still use the wrong input triangle for upper-factor requests.
    lines = ["import numpy as np", imports, "a = np.array([[4.0, 2.0], [1.0, 3.0]])"]
    for i, call in enumerate(calls + ["np.linalg.cholesky(a)", "np.linalg.cholesky(a, upper=True)"]):
        lines += [f"c{i} = {call}", "for row in range(2):", "    for col in range(2):",
                  f"        print(c{i}[row, col])"]
    result = translate(tmp_path, "\n".join(lines))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Run diff: MATCH" in result.stdout, result.stdout + result.stderr


@pytest.mark.parametrize("call, message", [
    ("la.cholesky(a, False, lower=True)", "duplicate keyword"),
    ("la.cholesky(a, lower=flag)", "literal Boolean"),
    ("np.linalg.cholesky(a, True)", "too many positional"),
    ("la.cholesky(a.astype(complex))", "complex Cholesky"),
])
def test_cholesky_rejections(tmp_path, call, message):
    result = translate(tmp_path, "import numpy as np\nfrom scipy import linalg as la\n"
                       "a = np.eye(2)\nflag = True\n" + f"b = {call}\nprint(b)\n", compare=False)
    assert result.returncode != 0
    assert message in result.stdout + result.stderr
