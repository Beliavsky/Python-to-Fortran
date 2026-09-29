"""Scalar Boolean results and shape-safe array equality."""
import subprocess
import sys

import pytest

from test_xp2f_cli import XP2F_PATH, EXAMPLES_DIR, _run_xp2f_compile_diff


@pytest.mark.parametrize("example", ["xfilter_bounds.py", "xpartition_bounds.py"])
def test_bounds_examples(tmp_path, example):
    _run_xp2f_compile_diff(
        tmp_path, example, (EXAMPLES_DIR / example).read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.parametrize("dtype, values", [("int", "1, 2"), ("float", "1.5, 2.5"), ("bool", "True, False")])
def test_array_equal_conditions_and_shapes(tmp_path, dtype, values):
    _run_xp2f_compile_diff(tmp_path, "xequality.py", [
        "import numpy as np",
        f"a = np.array([{values}], dtype={dtype})",
        "b = a.copy()",
        "assert np.array_equal(a, b)",
        "assert not np.array_equal(a, a[:1])",
        "assert not np.array_equal(a[:1], a)",
        "assert not np.array_equal(a, a[:0])",
        "assert np.array_equal(a[:0], b[:0])",
        "assert not np.array_equal(a, a[::-1])",
        "m = a.reshape((1, 2))",
        "n = a.reshape((2, 1))",
        "assert np.array_equal(m, m)",
        "assert not np.array_equal(m, n)",
        "assert not np.array_equal(m, n[:0, :])",
        "assert not np.array_equal(m, a)",
        "assert np.array_equal(a[0], b[0])",
        "if np.array_equal(a, b):",
        "    print('equal')",
        "if not np.array_equal(a, a[:1]):",
        "    print('different shapes')",
        "print(np.array_equal(a, b))",
    ])


def test_array_equal_false_assertion_fails_at_runtime(tmp_path):
    source = tmp_path / "xbad_equal.py"
    source.write_text("import numpy as np\na = np.array([1, 2])\nb = np.array([1])\n"
                      "assert np.array_equal(a, b), 'different shapes'\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(XP2F_PATH), str(source), "--compile"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([str(tmp_path / "xbad_equal_p.exe")], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "AssertionError" in result.stdout + result.stderr
