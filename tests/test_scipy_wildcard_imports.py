"""SciPy wildcard resolution, diagnostics, and real numerical regressions."""

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
    "from scipy.linalg import *\nprint(det([[4., 2.], [2., 3.]]))",
    "from numpy import *\nfrom scipy.linalg import *\nprint(cholesky(array([[4., 2.], [2., 3.]])))",
    "from scipy.linalg import *\nfrom numpy import *\nprint(cholesky(array([[4., 2.], [2., 3.]])))",
    "from scipy.linalg import *\nfrom numpy.linalg import cholesky\nprint(cholesky([[4., 2.], [2., 3.]]))",
    "from numpy.linalg import cholesky\nfrom scipy.linalg import *\nprint(cholesky([[4., 2.], [2., 3.]]))",
    "from scipy.linalg import *\ndef f(solve):\n    return solve + 1\nprint(f(7), det([[2.]]))",
    "from scipy.linalg import *\ndef f():\n    det = 7\n    return det\nprint(f(), det([[2.]]))",
    "from scipy.linalg import *\ndef solve(x):\n    return x + 1\nprint(solve(2))",
    "from scipy.linalg import *\nprint(det([[2.]]))\ndet = 7\nprint(det)",
    "from scipy.linalg import *\nxp2f_scipy_linalg = 7\nprint(xp2f_scipy_linalg, det([[2.]]))",
    "from scipy.linalg import *\nnp = 7\nprint(np, det([[2.]]))",
    "from scipy.linalg import *\nprint(7)",  # Unused unsupported exports are harmless.
])
def test_scipy_wildcard_binding_semantics(source):
    tree = normalize_numpy_wildcard_imports(ast.parse(source))
    outputs = []
    for program in (source, compile(tree, "<normalized>", "exec")):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(program, {})
        outputs.append(output.getvalue())
    assert outputs[0] == outputs[1]
    assert ast.dump(normalize_numpy_wildcard_imports(tree)) == ast.dump(tree)


@pytest.mark.parametrize("source, message", [
    ("from scipy.linalg import *\nprint(schur([[1.]]))", "Unsupported SciPy operation: scipy.linalg.schur"),
    ("from scipy.linalg import *\nprint(solve([[1.]], [2.], lower=True))", "Unsupported SciPy call options: scipy.linalg.solve"),
    ("from scipy.special import *\nprint(gamma(3))", "Unsupported SciPy wildcard import: scipy.special"),
    ("from scipy import *", "Unsupported SciPy wildcard import: scipy"),
    ("from scipy.linalg import *\nfrom foo import *", "another wildcard"),
    ("from scipy.linalg import *\nif True:\n    solve = 7", "rebinding"),
    ("from scipy.linalg import *\ndef f():\n    return cholesky([[1.]])\nfrom numpy.linalg import cholesky\nprint(f())", "ambiguous"),
])
def test_scipy_wildcard_diagnostics(source, message):
    with pytest.raises(NotImplementedError, match=message):
        normalize_numpy_wildcard_imports(ast.parse(source))


@pytest.mark.parametrize("imports, factor", [
    ("from numpy import *\nfrom scipy.linalg import *", "cholesky(a)"),
    ("from scipy.linalg import *\nfrom numpy import *", "cholesky(a, lower=True)"),
    ("from numpy import *\nfrom scipy.linalg import *\nfrom numpy.linalg import cholesky", "cholesky(a)"),
])
def test_scipy_wildcard_compile_diff(tmp_path, imports, factor):
    source = imports + f"""
a = array([[4.0, 2.0], [1.0, 3.0]])
b = array([1.0, 2.0])
x = solve(a, b)
c = {factor}
d = inv(a)
print(det(a))
print(norm(b))
for i in range(2):
    print(x[i])
    for j in range(2):
        print(c[i, j], d[i, j])
"""
    script = tmp_path / "xscipy_star.py"
    script.write_text(source, encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "xp2f.py"), str(script), "--compile", "--run-diff"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Run diff: MATCH" in result.stdout, result.stdout + result.stderr


def test_scipy_wildcard_unsupported_cli(tmp_path):
    script = tmp_path / "xscipy_unsupported.py"
    script.write_text("from scipy.linalg import *\nprint(schur([[1.]]))\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "xp2f.py"), str(script)], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "Unsupported SciPy operation: scipy.linalg.schur" in result.stdout + result.stderr
    assert not (tmp_path / "xscipy_unsupported_p.f90").exists()
