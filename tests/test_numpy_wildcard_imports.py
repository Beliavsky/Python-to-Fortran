"""Scope resolution and end-to-end coverage for NumPy star imports."""

import ast
import contextlib
import io
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python_numpy_imports import normalize_numpy_wildcard_imports


@pytest.mark.parametrize("source", [
    "from numpy import *\nprint(zeros(2), pi, int64(3), linalg.det(eye(2)))",
    "from numpy import *\ndef f(sum):\n    return sum + 1\nprint(f(7), sum(arange(4)))",
    "from numpy import *\ndef f():\n    zeros = 9\n    return zeros\nprint(f(), zeros(2))",
    "from numpy import *\nprint(zeros(2))\nzeros = 3\nprint(zeros)",
    "def zeros(n):\n    return n + 1\nfrom numpy import *\nprint(zeros(2))",
    "from numpy import *\ndef zeros(n):\n    return n + 1\nprint(zeros(2))",
    "from numpy import *\nfrom math import sin\nprint(sin(0.5), cos(0.5))",
    "from numpy import *\nfrom numpy import sum as total\nprint(total(arange(4)))\ntotal = 8\nprint(total)",
    "from numpy import *\nprint([sum + 1 for sum in range(3)], sum(arange(3)))",
    "from numpy import *\nf = lambda sum: sum + 1\nprint(f(3), sum(arange(3)))",
    "from numpy import *\nnp = 7\nprint(np, zeros(2))",
    "from numpy import *\ndef f(np):\n    return np + sum(arange(3))\nprint(f(7))",
    "from numpy import *\nimport math as np\nprint(np.sin(0.5), zeros(2))",
    "from numpy import *\nxp2f_user_np = 8\nnp = 7\nprint(np, xp2f_user_np, zeros(2))",
    "from numpy import *\ndef f():\n    from math import sin\n    return sin(0.5)\nprint(f(), sin(0.5))",
    "from numpy import *\ndef f():\n    from numpy import sum as total\n    return total(arange(4))\nprint(f())",
    "from __future__ import annotations\nfrom numpy import *\nprint(zeros(2))",
    "from numpy import *\nzeros = 7\nfrom numpy import *\nprint(zeros(2))",
    "from numpy import *\ndef outer():\n    def inner():\n        return zeros\n    zeros = 7\n    return inner()\nprint(outer())",
])
def test_wildcard_normalization_preserves_python_bindings(source):
    tree = normalize_numpy_wildcard_imports(ast.parse(source))
    outputs = []
    for program in (source, compile(tree, "<normalized>", "exec")):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(program, {})
        outputs.append(output.getvalue())
    assert outputs[0] == outputs[1]
    assert not any(isinstance(n, ast.ImportFrom) and n.module == "numpy" for n in ast.walk(tree))
    assert ast.dump(normalize_numpy_wildcard_imports(tree)) == ast.dump(tree)


def test_unknown_names_are_not_assumed_numpy():
    tree = normalize_numpy_wildcard_imports(ast.parse("from numpy import *\nprint(not_a_numpy_function(2))"))
    assert "not_a_numpy_function(2)" in ast.unparse(tree)
    assert "np.not_a_numpy_function" not in ast.unparse(tree)


@pytest.mark.parametrize("source, message", [
    ("from numpy import *\nif True:\n    zeros = 7\nprint(zeros)", "rebinding"),
    ("from numpy import *\ndef f():\n    return zeros(2)\nf()\nzeros = 7", "ambiguous"),
    ("from numpy import *\nfrom foo import *", "another wildcard"),
    ("if True:\n    from numpy import *\nprint(zeros(2))", "unconditional"),
    ("from numpy import *\ndef f():\n    global zeros\n    zeros = 7", "global/nonlocal"),
    ("from numpy import *\nfrom numpy import sin as wave\ndef f():\n    global wave\n    wave = 7", "global/nonlocal"),
    ("from numpy import *\nif True:\n    from numpy import zeros as z\nprint(z(2))", "Conditional NumPy"),
    ("from numpy import *\ndef outer():\n    from numpy import sin\n    def inner():\n        return sin(1)\n    from math import sin\n    return inner()\nprint(outer())", "ambiguous"),
    ("from numpy import *\nf = lambda: zeros(2)\nzeros = lambda n: n\nprint(f())", "ambiguous"),
    ("def f():\n    return zeros(2)\nf()\nfrom numpy import *", "ambiguous"),
])
def test_ambiguous_wildcard_binding_is_rejected(source, message):
    with pytest.raises(NotImplementedError, match=message):
        normalize_numpy_wildcard_imports(ast.parse(source))


def test_wildcard_does_not_define_unbound_np():
    tree = normalize_numpy_wildcard_imports(ast.parse("from numpy import *\nprint(np.zeros(2))"))
    with pytest.raises(NameError):
        exec(compile(tree, "<normalized>", "exec"), {})


def test_relative_numpy_is_not_treated_as_numpy():
    tree = ast.parse("from .numpy import *\nprint(zeros(2))")
    before = ast.dump(tree)
    assert ast.dump(normalize_numpy_wildcard_imports(tree)) == before


@pytest.mark.parametrize("source", [
    """from numpy import *
from scipy import linalg
a = array([[4.0, 2.0], [2.0, 3.0]])
b = zeros((2, 2))
b[:] = a
c = concatenate((a, b), 1)
u = linalg.cholesky(a)
print(c.shape[0], c.shape[1])
for i in range(2):
    for j in range(2):
        print(u[i, j])
print(sum(arange(4)), pi)
v = array([1, 2, 3], dtype=int64)
print(v[2])
""",
    """from numpy import *
np = 7
def f(sum):
    return sum + 1
def g():
    zeros = 9
    return zeros
print(np, f(3), g())
a = zeros(2)
print(a[0], a[1])
""",
])
def test_wildcard_compile_and_run_diff(tmp_path, source):
    script = tmp_path / "xwildcard.py"
    script.write_text(source, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "xp2f.py"), str(script), "--compile", "--run-diff"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Run diff: MATCH" in result.stdout, result.stdout + result.stderr


def test_wildcard_module_compile(tmp_path):
    script = tmp_path / "xwildcard_module.py"
    script.write_text("from numpy import *\ndef total(n: int) -> float:\n    return sum(arange(n, dtype=float))\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "xp2f.py"), str(script), "--module", "--compile"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Build:" in result.stdout, result.stdout + result.stderr
