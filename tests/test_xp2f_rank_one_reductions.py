"""Rank-aware helper arguments and canonical mean naming."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def compile_diff(tmp_path, lines):
    if shutil.which("gfortran") is None:
        pytest.skip("gfortran required")
    pytest.importorskip("numpy")
    source = tmp_path / "xreductions.py"
    source.write_text("\n".join(lines) + "\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(ROOT / "xp2f.py"), str(source),
                           "--compile", "--run-diff"], cwd=tmp_path,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr
    return source.with_name("xreductions_p.f90").read_text(encoding="utf-8")


@pytest.mark.parametrize("matrix", [False, True])
def test_rank_aware_reduction_helpers(tmp_path, matrix):
    literal = "[[1.0, 2.0], [3.0, 5.0]]" if matrix else "[1.0, 2.0, 3.0, 5.0]"
    lines = ["import numpy as np", f"a = np.array({literal})"]
    for name in ("mean", "std", "var", "nanmean", "nanstd", "nanvar", "nanmin", "nanmax"):
        lines.append(f"print(np.{name}(a))")
    lines += ["print(np.std(a, ddof=1), np.var(a, ddof=1))",
              "print(np.nanstd(a, ddof=1), np.nanvar(a, ddof=1))",
              "print(np.quantile(a, 0.25), np.median(a))",
              "q1, q2 = np.quantile(a, [0.25, 0.75])", "print(q1, q2)",
              "print(np.allclose(a, a + 0.0))"]
    if not matrix:
        lines += ["print(np.std(a[::2]))", "print(np.ravel(a))", "print(np.squeeze(a))"]
    generated = compile_diff(tmp_path, lines)
    assert "mean_1d(" not in generated
    if matrix:
        assert "std(reshape(" in generated
        assert "quantile_linear(reshape(a, [size(a)])" in generated
    else:
        assert "mean(a)" in generated and "std(a)" in generated
        assert "reshape(a, [size(a)])" not in generated
        for helper in ("var_1d", "nanmean", "nanstd", "nanvar", "nanmin", "nanmax", "quantile_linear"):
            assert f"{helper}(a" in generated


def test_vector_flatten_copy_and_self_assignment(tmp_path):
    generated = compile_diff(tmp_path, [
        "import numpy as np",
        "def change(x):",
        "    x[0] = 99.0",
        "a = np.array([1.0, 2.0, 3.0])",
        "b = a.flatten()",
        "b[0] = 7.0",
        "print(a)", "print(b)",
        "change(a.flatten())", "print(a)",
        "a = a.ravel()", "print(a)",
        "a = a.flatten()", "print(a)",
    ])
    assert "reshape(a, [size(a)])" in generated


def test_legacy_mean_wrapper(tmp_path):
    if shutil.which("gfortran") is None:
        pytest.skip("gfortran required")
    source = tmp_path / "legacy.f90"
    source.write_text("""program legacy
use python_mod, only: mean, mean_1d
use, intrinsic :: iso_fortran_env, only: real64
implicit none
real(real64) :: x(3) = [1.0_real64, 2.0_real64, 6.0_real64], empty(0)
if (mean_1d(x) /= mean(x)) stop 1
if (mean_1d(empty) /= 0.0_real64) stop 2
end program legacy
""", encoding="utf-8")
    executable = tmp_path / "legacy.exe"
    build = subprocess.run(["gfortran", str(ROOT / "python.f90"), str(ROOT / "lapack_d.f90"),
                            str(source), "-o", str(executable)],
                           cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(executable)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr


def test_integer_vector_and_user_mean_name(tmp_path):
    generated = compile_diff(tmp_path, [
        "import numpy as np", "def mean(x):", "    return x + 10",
        "a = np.array([1, 2, 3, 5], dtype=int)",
        "print(mean(2))", "print(np.mean(a), np.std(a), np.var(a))",
    ])
    assert "std(real(a, kind=dp))" in generated
