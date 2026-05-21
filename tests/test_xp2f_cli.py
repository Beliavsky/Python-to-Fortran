from __future__ import annotations

import csv
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import fortran_output as fout

XP2F_PATH = REPO_ROOT / "xp2f.py"
PYTHON_HELPER_PATH = REPO_ROOT / "python.f90"

SUPPORTED_PY_COMPILE_CASES = [
    "xoptions_pde.py",
    "xbs_monte_carlo.py",
]


def _run_xp2f_compile(tmp_path: Path, example_name: str) -> subprocess.CompletedProcess[str]:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    local_input = tmp_path / example_name
    shutil.copy2(REPO_ROOT / example_name, local_input)
    return subprocess.run(
        [sys.executable, str(XP2F_PATH), str(local_input), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("example_name", SUPPORTED_PY_COMPILE_CASES)
def test_xp2f_compiles_supported_local_python_examples(tmp_path: Path, example_name: str) -> None:
    proc = _run_xp2f_compile(tmp_path, example_name)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Auto helper files: python.f90" in proc.stdout
    assert "Build: PASS" in proc.stdout
    assert (tmp_path / f"{Path(example_name).stem}_p.f90").exists()


def test_xp2f_compiles_function_result_subscript_with_local_proc_module(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfunc_subscript_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def stats(x):",
                "    return [np.mean(x), np.std(x)]",
                "",
                "x = np.random.uniform(size=8)",
                "print(stats(x)[0])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xfunc_subscript_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "use xfunc_subscript_small_proc_mod, only: dp, stats" in out_text
    assert "print *, index1(stats(x)," in out_text


def test_xp2f_compiles_print_of_np_random_uniform_expr(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xprint_uniform_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "print(np.random.uniform(0.0, 1.0, size=3))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xprint_uniform_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "runif(int(3))" in out_text


def test_xp2f_multiarg_print_inserts_default_space_separator(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xprint_sep_small.py"
    src.write_text(
        "\n".join(
            [
                'c = "bob"',
                'print("name:", c)',
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    assert "name: bob" in proc.stdout
    out_text = (tmp_path / "xprint_sep_small_p.f90").read_text(encoding="utf-8")
    assert 'print *, "name:", " ", c' in out_text


def test_xp2f_multiarg_print_supports_literal_sep(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xprint_sep_literal_small.py"
    src.write_text(
        "\n".join(
            [
                "pi = 3.14",
                'print("x", "y", pi, sep=";;")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    assert "x;;y;;" in proc.stdout
    out_text = (tmp_path / "xprint_sep_literal_small_p.f90").read_text(encoding="utf-8")
    assert '"x"' in out_text
    assert '"y"' in out_text
    assert '";;"' in out_text
    assert "py_str(pi)" in out_text


def test_fortran_output_pretty_rounds_near_decimal_noise() -> None:
    got = fout.pretty_output_line(
        "0.99999999999999989 0.20000000000000001 0.69999999999999996 3.1400000000000001"
    )
    assert got == "1.0 0.2 0.7 3.14"


def test_xp2f_savetxt_default_delimiter_preserves_space(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xsavetxt_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                'x = np.array([[1.25, 2.5], [3.75, 4.0]])',
                'np.savetxt("out.txt", x, fmt="%.2f")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    out_txt = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert out_txt.splitlines()[0] == "1.25 2.50"
    assert out_txt.splitlines()[1] == "3.75 4.00"


def test_xp2f_cov_ndim_scalar_guard_keeps_matrix_target(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xcov_ndim_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x):",
                "    global_cov = np.cov(x, rowvar=False)",
                "    if np.ndim(global_cov) == 0:",
                "        global_cov = np.array([[float(global_cov)]])",
                "    return global_cov",
                "",
                "x = np.array([[1.0, 2.0], [3.0, 4.0], [2.0, 5.0]])",
                "print(f(x))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xcov_ndim_small_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), allocatable :: global_cov(:,:)" in out_text
    assert "real(kind=dp) :: global_cov" not in out_text


def test_xp2f_compiles_file_readlines_loop(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xreadlines_small.py"
    src.write_text(
        "\n".join(
            [
                'infile = "lines.txt"',
                'fp = open(infile, "r")',
                "lines = fp.readlines()",
                "for line in lines:",
                "    print(line.strip())",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "lines.txt").write_text(" a  \n\nb\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xreadlines_small_p.f90").read_text(encoding="utf-8")
    assert "allocate(lines_readlines(0))" in out_text
    assert "character(len=:), allocatable :: lines(:)" in out_text


def test_xp2f_keeps_nested_char_subscript_as_char(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xchar_subscript_small.py"
    src.write_text(
        "\n".join(
            [
                'lines = ["abcdef"]',
                "print(lines[0][1:4])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xchar_subscript_small_p.f90").read_text(encoding="utf-8")
    assert "py_str(lines(1)" not in out_text
    assert "print *, lines(1)(" in out_text


def test_xp2f_compiles_xcmath_module_calls(tmp_path: Path) -> None:
    proc = _run_xp2f_compile(tmp_path, "xcmath.py")

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xcmath_p.f90").read_text(encoding="utf-8")
    assert 'print *, "cmath.pi =", acos(-1.0_dp)' in out_text
    assert "complex_isfinite(" in out_text


def test_xp2f_marks_self_calling_subroutine_recursive(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrecursive_small.py"
    src.write_text(
        "\n".join(
            [
                "def collatz_path(n):",
                "    print(n)",
                "    if n > 1:",
                "        if n % 2 == 0:",
                "            collatz_path(int(n / 2))",
                "        else:",
                "            collatz_path(3 * n + 1)",
                "",
                "collatz_path(7)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xrecursive_small_p.f90").read_text(encoding="utf-8")
    assert "recursive subroutine collatz_path(" in out_text


def test_xp2f_runs_mixed_tuple_outputs_with_array_and_scalar(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xmixed_tuple_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def stats():",
                "    s = np.zeros(2)",
                "    total = 0",
                "    for i in range(4):",
                "        s[i % 2] = s[i % 2] + 1",
                "        total = total + i",
                "    total = total / float(4)",
                "    return s, total",
                "",
                "def run_stats():",
                "    s, turn_average = stats()",
                "    print(s)",
                "    print(turn_average)",
                "",
                "run_stats()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    assert "1.5" in proc.stdout or "1.5000000000000000" in proc.stdout


def test_xp2f_compiles_mixed_tuple_outputs_with_matrix_and_vector(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xmatrix_tuple_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def simulate(n, d):",
                "    x = np.empty((n, d), dtype=float)",
                "    z = np.empty(n, dtype=int)",
                "    for i in range(n):",
                "        z[i] = i % 2",
                "        for j in range(d):",
                "            x[i, j] = float(i + j)",
                "    return x, z",
                "",
                "def main():",
                "    x, z = simulate(4, 2)",
                "    print(x)",
                "    print(z)",
                "",
                "main()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xmatrix_tuple_small_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), allocatable :: x(:,:)" in out_text
    assert "call simulate(4, 2, x, z)" in out_text
    assert "real(kind=dp), allocatable :: x(:)" not in out_text


def test_xp2f_axis_reduction_temporaries_promote_to_vectors(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xaxis_reduce_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x):",
                "    log_prob = np.empty((x.shape[0], 3), dtype=float)",
                "    log_prob[:, 0] = x[:, 0]",
                "    log_prob[:, 1] = x[:, 1]",
                "    log_prob[:, 2] = x[:, 0] + x[:, 1]",
                "    amax = np.max(log_prob, axis=1)",
                "    s = np.sum(np.exp(log_prob - amax[:, None]), axis=1)",
                "    log_norm = amax + np.log(s)",
                "    resp = np.exp(log_prob - log_norm[:, None])",
                "    nk = np.sum(resp, axis=0) + 1e-15",
                "    return nk",
                "",
                "x = np.array([[1.0, 2.0], [3.0, 4.0]])",
                "print(f(x))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xaxis_reduce_small_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), allocatable :: amax(:)" in out_text
    assert "real(kind=dp), allocatable :: s(:)" in out_text
    assert "real(kind=dp), allocatable :: log_norm(:)" in out_text
    assert "real(kind=dp), allocatable :: nk(:)" in out_text
    assert "real(kind=dp) :: amax" not in out_text
    assert "real(kind=dp) :: nk" not in out_text


def test_xp2f_compiles_reserved_name_slogdet_tuple_unpack(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xslogdet_sign_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "a = np.array([[2.0, 0.0], [0.0, 3.0]])",
                "sign, logdet = np.linalg.slogdet(a)",
                "print(sign)",
                "print(logdet)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xslogdet_sign_small_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp) :: logdet, xsign" in out_text or "real(kind=dp) :: xsign, logdet" in out_text
    assert "xsign = merge(" in out_text


def test_xp2f_tuple_output_rank_preserved_by_top_level_usage(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xtuple_rank_use_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x):",
                "    w = np.array([0.25, 0.75])",
                "    mu = np.array([[1.0, 2.0], [3.0, 4.0]])",
                "    return w, mu",
                "",
                "w, mu = f(np.array([[0.0, 0.0]]))",
                "order = np.argsort(mu[:, 0])",
                "print(w[order])",
                "print(mu[order])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xtuple_rank_use_small_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), allocatable :: mu(:,:)" in out_text
    assert "allocate(order(size(mu(:, 1))))" in out_text or "allocate(order(size(mu(:, (1)))))" in out_text


def test_xp2f_compiles_function_result_slice_with_local_proc_module(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfunc_subscript_slice_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def stats(x):",
                "    return np.array([np.mean(x), np.std(x)])",
                "",
                "x = np.random.uniform(size=8)",
                "print(stats(x)[0:])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xfunc_subscript_slice_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "use xfunc_subscript_slice_small_proc_mod, only: dp, stats" in out_text
    assert "print *, slice1(stats(x)," in out_text


def test_xp2f_compiles_local_corrcoef_assignment_as_matrix(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xcorrcoef_local_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def avg_offdiag_corr(asset_rets):",
                "    corr = np.corrcoef(asset_rets.T)",
                "    n = corr.shape[0]",
                "    return (corr.sum() - np.trace(corr)) / (n * (n - 1))",
                "",
                "asset_rets = np.random.uniform(size=(8, 3))",
                "print(avg_offdiag_corr(asset_rets))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xcorrcoef_local_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "real(kind=dp), allocatable :: corr(:,:)" in out_text


def test_xp2f_propagates_matrix_arg_ranks_across_local_calls(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmatrix_arg_chain_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def moving_average(prices, window):",
                "    out = np.empty(prices.shape, dtype=float)",
                "    out[:] = prices",
                "    return out",
                "",
                "def strategy_weights(prices, k):",
                "    ma = moving_average(prices, k)",
                "    n_periods = prices.shape[0] - 1",
                "    n_stocks = prices.shape[1]",
                "    weights = np.zeros((n_periods, n_stocks), dtype=float)",
                "    weights[:] = ma[1:]",
                "    return weights",
                "",
                "def strategy_returns(prices, k):",
                "    weights = strategy_weights(prices, k)",
                "    return weights.shape[0]",
                "",
                "prices = np.random.uniform(size=(8, 3))",
                "print(strategy_returns(prices, 2))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xmatrix_arg_chain_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert out_text.count("real(kind=dp), intent(in) :: prices(:,:)") >= 2


def test_xp2f_keeps_scalar_broadcast_args_scalar(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xscalar_broadcast_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def scale_and_shift(x, scale, shift):",
                "    y = scale * x + shift",
                "    return y",
                "",
                "print(scale_and_shift(np.array([1.0, 2.0]), 0.5, 1.0))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xscalar_broadcast_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "real(kind=dp), intent(in) :: scale" in out_text
    assert "real(kind=dp), intent(in) :: shift" in out_text


def test_xp2f_lowers_logical_method_sum_to_count(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlogical_sum_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x):",
                "    mask = x > 0.0",
                "    return int(mask.sum())",
                "",
                "print(f(np.array([1.0, -1.0, 2.0])))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xlogical_sum_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "count(mask)" in out_text


def test_xp2f_compiles_count_mapped_integer_outputs_as_allocatable(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xprime_factor_small.py"
    src.write_text(
        "\n".join(
            [
                "from math import isqrt",
                "",
                "n = 360",
                "factors = []",
                "powers = []",
                "m = n",
                "if m != 0:",
                "    e = 0",
                "    while m % 2 == 0:",
                "        m //= 2",
                "        e += 1",
                "    if e > 0:",
                "        factors.append(2)",
                "        powers.append(e)",
                "    d = 3",
                "    while d <= isqrt(m):",
                "        e = 0",
                "        while m % d == 0:",
                "            m //= d",
                "            e += 1",
                "        if e > 0:",
                "            factors.append(d)",
                "            powers.append(e)",
                "        d += 2",
                "    if m > 1:",
                "        factors.append(m)",
                "        powers.append(1)",
                "print(factors)",
                "print(powers)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xprime_factor_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "integer, allocatable, intent(out) :: factors(:)" in out_text
    assert "integer, allocatable, intent(out) :: powers(:)" in out_text


def test_xp2f_compiles_fstring_listcomp_over_range(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfstring_listcomp_small.py"
    src.write_text(
        "\n".join(
            [
                "ncol = 3",
                'columns = [f"col{i}" for i in range(1, ncol + 1)]',
                "print(columns)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xfstring_listcomp_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "str_concat(" in out_text
    assert "arange_int(" in out_text
    assert "arange_int(int(1)" not in out_text
    assert "int(ncol + 1)" not in out_text


def test_xp2f_compiles_zip_loop_over_rank1_iterables(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xzip_loop_small.py"
    src.write_text(
        "\n".join(
            [
                'labels = [f"col{i}" for i in range(1, 4)]',
                "vals = [1.0, 2.0, 3.0]",
                "for label, value in zip(labels, vals):",
                '    print(f"{label}: {value}")',
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xzip_loop_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "do i_zip = 1, n_zip" in out_text
    assert "zip_labels" not in out_text
    assert "zip_vals" not in out_text
    assert 'write(*,"(a,a,g0)") labels(i_zip), ": ", vals(i_zip)' in out_text


def test_xp2f_aliases_fortran_keyword_data_name(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xdata_keyword_small.py"
    src.write_text(
        "\n".join(
            [
                "data = [1.0, 2.0, 3.0]",
                "print(data)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xdata_keyword_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "xdata" in out_text
    assert " :: data" not in out_text
    assert "\ndata =" not in out_text


def test_xp2f_compiles_bare_sqrt_and_sum_calls(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xbare_math_small.py"
    src.write_text(
        "\n".join(
            [
                "from math import sqrt",
                "import numpy as np",
                "x = np.array([1.0, 2.0, 3.0])",
                "print(sqrt(57.0))",
                "print(sum(x))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xbare_math_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "sqrt(" in out_text
    assert "sum(x)" in out_text


def test_xp2f_compiles_ord_and_chr_builtin_calls(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xord_chr_small.py"
    src.write_text(
        "\n".join(
            [
                "text = 'az'",
                "ival = ord(text[0])",
                "print(ival)",
                "print(chr(ord('z') - 1))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xord_chr_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "iachar(" in out_text
    assert "achar(int(" in out_text
    assert "iachar(text(" in out_text


def test_xp2f_compiles_multiple_name_assignment_once(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmultiple_assign_small.py"
    src.write_text(
        "\n".join(
            [
                "a = b = 4.5",
                "print(a, b)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xmultiple_assign_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "xp2f_assign_tmp_" not in out_text
    assert "b = 4.5_dp" in out_text
    assert "a = b" in out_text


def test_xp2f_old_style_percent_d_casts_real_args_for_write(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpercent_d_float.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "vals = np.zeros(2)",
                "vals[0] = 2",
                "vals[1] = 1",
                "print('  %2d  %2d  %10.4f  %14.6g ' % (vals[0], vals[1], 0.0, 1.0))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xpercent_d_float_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert 'write(*,"(\'  \',i2,\'  \',i2,\'  \',f10.4,\'  \',g14.6,\' \')")' in out_text
    assert "int(vals(1))" in out_text
    assert "int(vals(2))" in out_text


def test_xp2f_python_true_division_coerces_integer_operands(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xtrue_division_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "vals = np.array([2, 3])",
                "x = vals[0] / vals[1]",
                "print(x)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xtrue_division_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "real(vals(1), kind=dp) / real(vals(2), kind=dp)" in out_text


def test_xp2f_supports_imported_sys_exit_statement(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xexit_small.py"
    src.write_text(
        "\n".join(
            [
                "from sys import exit",
                "print('hi')",
                "exit('here')",
                "print('bye')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xexit_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert 'error stop "here"' in out_text


def test_xp2f_tuple_return_assignment_allows_subscript_targets(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xtuple_subscript_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f():",
                "    return 10.0, 20.0, 30.0, 40.0",
                "",
                "x = np.zeros(2)",
                "z, x[0], x[1], y = f()",
                "print(x)",
                "print(y)",
                "print(z)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    out_f90 = tmp_path / "xtuple_subscript_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "call f(z, x(1), x(2), y)" in out_text


def test_xp2f_compiles_np_hypot_call(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xhypot_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "a = 3.0",
                "b = 4.0",
                "print(np.hypot(a, b))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xhypot_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "sqrt((" in out_text


def test_xp2f_compiles_numpy_rounding_family_calls(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xnp_rounding_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "print(np.fix([2.1, 2.9, -2.1, -2.9]))",
                "print(np.rint([2.1, 2.9, -2.1, -2.9]))",
                "print(np.floor([2.1, 2.9, -2.1, -2.9]))",
                "print(np.ceil([2.1, 2.9, -2.1, -2.9]))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xnp_rounding_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "aint(" in out_text
    assert "anint(" in out_text
    assert "real(floor(" in out_text
    assert "real(ceiling(" in out_text


def test_xp2f_compiles_numpy_inverse_trig_aliases(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xnp_math_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "x = np.array([-0.99, 0.99])",
                "print(np.sin(x), np.cos(x), np.tan(x), np.arcsin(x), np.asin(x), np.atan(x))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xnp_math_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "asin(x)" in out_text
    assert "atan(x)" in out_text


def test_xp2f_compiles_numpy_angle_and_unary_math_aliases(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xnp_more_math_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "rad = np.array([0.0, np.pi / 6])",
                "lhs = np.array([2.0, -3.0])",
                "rhs = np.array([4.0, -6.0])",
                "print(np.degrees(rad))",
                "print(np.radians([0.0, 30.0]))",
                "print(np.deg2rad([0.0, 45.0]))",
                "print(np.rad2deg(rad))",
                "print(np.exp2([0.0, 1.0]))",
                "print(np.cbrt([-8.0, 27.0]))",
                "print(np.square(lhs))",
                "print(np.reciprocal(np.array([1.0, 2.0])))",
                "print(np.positive(lhs))",
                "print(np.negative(lhs))",
                "print(np.copysign(lhs, rhs))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xnp_more_math_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "180.0_dp / acos(-1.0_dp)" in out_text
    assert "acos(-1.0_dp) / 180.0_dp" in out_text
    assert "2.0_dp **" in out_text
    assert "sign(abs(" in out_text


def test_xp2f_compiles_numpy_unwrap_and_numpy_hasattr_probe(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xnp_unwrap_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "phase = np.array([0.0, 1.0, 2.0, -2.8])",
                "print(np.unwrap(phase))",
                "if hasattr(np, 'cumulative_sum'):",
                "    print(np.cumulative_sum(phase))",
                "if hasattr(np, 'bitwise_count'):",
                "    print(np.bitwise_count(np.array([0, 1], dtype=np.uint8)))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xnp_unwrap_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "unwrap_1d(" in out_text
    assert ".false." in out_text or ".true." in out_text


def test_xp2f_compiles_xnp_math_funcs_smoke(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    local_input = tmp_path / "xnp_math_funcs.py"
    shutil.copy2(REPO_ROOT / "xnp_math_funcs.py", local_input)

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(local_input), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_xp2f_compiles_local_callback_argument_call(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpass_func_small.py"
    src.write_text(
        "\n".join(
            [
                "def twice(x):",
                "    return 2*x",
                "",
                "def pass_func(f, x):",
                "    return f(x)",
                "",
                "print(pass_func(twice, 3.2))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xpass_func_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "procedure(" in out_text
    assert "return f(x)" not in out_text


def test_xp2f_runs_local_callback_argument_call(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xpass_func_small.py"
    src.write_text(
        "\n".join(
            [
                "def twice(x):",
                "    return 2*x",
                "",
                "def pass_func(f, x):",
                "    return f(x)",
                "",
                "print(pass_func(twice, 3.2))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "6.4" in proc.stdout
    assert "Run: PASS" in proc.stdout
    assert "6.4000000000000004" in proc.stdout or "\n6.4\n" in proc.stdout


def test_xp2f_postprocess_removes_unused_print_matrix_import(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmultiple_assign_small.py"
    src.write_text(
        "\n".join(
            [
                "a = b = 4.5",
                "print(a, b)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--postprocess"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xmultiple_assign_small_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "use python_mod, only: print_matrix" not in out_text


def test_xp2f_keeps_string_arg_scalar_when_indexed_for_ord(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xord_arg_small.py"
    src.write_text(
        "\n".join(
            [
                "def head_code(text):",
                "    return ord(text[0])",
                "print(head_code('az'))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xord_arg_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "character(len=*), intent(in) :: text" in out_text
    assert "character(len=*), intent(in) :: text(:)" not in out_text


def test_xp2f_compiles_tuple_wrapped_print_and_attr_expr(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xexpr_tuple_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "A = np.array([[1.0, 2.0]])",
                "A.shape",
                'print(\"x\"),',
                "print(A[0, 0])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xexpr_tuple_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert '"x"' in out_text
    assert "A.shape" not in out_text


def test_xp2f_compiles_empty_list_reset_for_known_array(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xempty_list_reset_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "def f(d, n):",
                "    theta = np.zeros((d - 1, n))",
                "    if d == 1:",
                "        theta = []",
                "        return theta",
                "    return theta",
                "print(f(2, 3))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xempty_list_reset_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "allocate(theta(0, 0))" in out_text or "allocate(theta(0,0))" in out_text


def test_xp2f_marks_rebound_array_dummy_allocatable(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrebound_dummy_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "def f(k, a):",
                "    if k == 0:",
                "        a = []",
                "    return a",
                "arr = np.array([1, 2])",
                "print(f(0, arr))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xrebound_dummy_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "allocatable, intent(inout) :: a(:)" in out_text


def test_xp2f_compiles_transpose_of_list_of_vectors(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xtranspose_list_vectors.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "x = np.array([1.0, 2.0])",
                "y = np.array([3.0, 4.0])",
                "z = np.array([5.0, 6.0])",
                "xyz = np.transpose([x, y, z])",
                "print(xyz)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xtranspose_list_vectors_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "transpose(reshape([x, y, z], [size(x), 3]))" in out_text


def test_xp2f_proc_module_wrapper_calls_local_main(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xproc_main_small.py"
    src.write_text(
        "\n".join(
            [
                "msg = 'hello'",
                "",
                "def main():",
                "    print(msg)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    exe_path = tmp_path / "xproc_main_small_p.exe"
    assert exe_path.exists()
    run_proc = subprocess.run(
        [str(exe_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_proc.returncode == 0, run_proc.stdout + run_proc.stderr
    assert "hello" in run_proc.stdout


def test_xp2f_uses_first_axis_extent_for_2d_slices(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xslice_2d_first_axis_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(prices):",
                "    return prices[1:] / prices[:-1]",
                "",
                "print(f(np.ones((4, 2))))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xslice_2d_first_axis_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "prices(2:size(prices,1), :)" in out_text
    assert "prices(1:(size(prices,1) - 1), :)" in out_text


def test_xp2f_preserves_fstring_widths_and_int_list_display(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfstring_formats_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "ks = np.array([50, 100, 150], dtype=int)",
                "k = 50",
                "mean_before = 1.234567",
                "mean_after = 0.5",
                "print(f\"strategy_k_list: {ks.tolist()}\")",
                "print(f\"{k:<6d}{mean_before:18.6f}{mean_after:18.6f}\")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xfstring_formats_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert 'write(*,"(a,a)") "strategy_k_list: ", str_int_list(ks, size(ks))' in out_text
    assert 'write(*,"(a,f18.6,f18.6)") str_ljust(py_str(k), 6), mean_before, mean_after' in out_text


def test_xp2f_lowers_bitwise_invert_on_logical_arrays(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xinvert_isnan_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "x = np.array([1.0, np.nan, 2.0])",
                "mask = ~np.isnan(x)",
                "print(mask)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xinvert_isnan_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "mask = .not. ieee_is_nan(x)" in out_text


def test_xp2f_lowers_masked_augassign_with_where(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmasked_augassign_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "x = np.array([1.0, np.nan, 2.0])",
                "y = np.zeros(3, dtype=int)",
                "y[~np.isnan(x)] += 1",
                "print(y)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xmasked_augassign_small_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "where (((.not. ieee_is_nan(x))))" in out_text
    assert "y = y + 1" in out_text


def test_xp2f_rng_replay_matches_python_for_normal_simulation(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrng_replay_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "n = 16",
                "niter = 4",
                "xsd = np.zeros(niter)",
                "",
                "for i in range(niter):",
                "    x = np.random.normal(size=n)",
                "    xsd[i] = np.std(x)",
                "",
                "print(np.mean(xsd), np.std(xsd), np.min(xsd), np.max(xsd))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff", "--rng-replay"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout


def test_xp2f_can_print_rng_replay_wrapper_source(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrng_replay_wrapper_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "x = np.random.normal(size=8)",
                "print(np.mean(x))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff", "--rng-replay", "--tee-rng-replay"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RNG replay wrapper (" in proc.stdout
    assert "def rec_normal(*args, **kwargs):" in proc.stdout
    assert "np.random.normal = rec_normal" in proc.stdout


def test_xp2f_can_save_rng_replay_wrapper_source(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrng_replay_save_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "x = np.random.normal(size=8)",
                "print(np.mean(x))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    wrapper_out = tmp_path / "saved_rng_replay_wrapper.py"

    proc = subprocess.run(
        [
            sys.executable,
            str(XP2F_PATH),
            str(src),
            "--run-diff",
            "--rng-replay",
            "--out-rng-replay-python",
            str(wrapper_out),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert wrapper_out.exists()
    wrapper_text = wrapper_out.read_text(encoding="utf-8")
    assert "def rec_normal(*args, **kwargs):" in wrapper_text
    assert "np.random.normal = rec_normal" in wrapper_text
    assert f"RNG replay wrapper saved: {wrapper_out}" in proc.stdout


def test_xp2f_rng_replay_supports_default_rng_standard_normal(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrng_replay_default_rng.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def main():",
                "    rng = np.random.default_rng(1234)",
                "    x = rng.standard_normal(12)",
                "    print(np.mean(x), np.std(x), np.min(x), np.max(x))",
                "",
                "main()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both", "--rng-replay"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout
    assert "STOP rng replay" not in proc.stdout


def test_xp2f_preserves_real_compare_and_same_mask_vector_assignment(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmask_copy_real_arg.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def persistent_like(prices):",
                "    ma = np.array([1.5, 2.5, 3.5], dtype=float)",
                "    raw = np.zeros(3, dtype=int)",
                "    raw[prices > ma] = 1",
                "    raw[prices < ma] = -1",
                "    out = np.zeros(3, dtype=int)",
                "    keep = raw != 0",
                "    out[keep] = raw[keep]",
                "    return out",
                "",
                "print(persistent_like(np.array([1.6, 2.4, 3.6])))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout


def test_xp2f_run_diff_ignores_elapsed_time_seconds_line(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xelapsed_time_diff.py"
    src.write_text(
        "\n".join(
            [
                "import time",
                "",
                "t0 = time.perf_counter()",
                "x = 0",
                "for i in range(1000):",
                "    x += i",
                "print(x)",
                "print(f\"elapsed_time_seconds: {time.perf_counter() - t0:.6f}\")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout


def test_xp2f_numeric_diff_ignores_version_lines(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xnumeric_diff_version.py"
    src.write_text(
        "\n".join(
            [
                "import platform",
                "import math",
                "",
                "print('python version:', platform.python_version())",
                "print(math.sqrt(2.0))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff", "--numeric-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: DIFF" in proc.stdout
    assert "Run numeric diff: MATCH" in proc.stdout


def test_xp2f_numeric_diff_tol_implies_run_both(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xnumeric_diff_tol_only.py"
    src.write_text(
        "\n".join(
            [
                "print(1.0)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--numeric-diff-tol", "1e-9"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run (python):" in proc.stdout
    assert "Run numeric diff: MATCH" in proc.stdout


def test_xp2f_numeric_diff_matches_complex_output_forms(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xcomplex_numeric_diff.py"
    src.write_text(
        "\n".join(
            [
                "z1 = 3 + 4j",
                "z2 = 1j",
                "print(z1)",
                "print(z2)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--numeric-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    assert "Run numeric diff: MATCH" in proc.stdout


def test_xp2f_numeric_diff_keeps_plain_python_tuples_split(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xtuple_numeric_diff.py"
    src.write_text(
        "\n".join(
            [
                "import cmath",
                "z = 3 + 4j",
                "print(cmath.polar(z))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--numeric-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    assert "Run numeric diff: MATCH" in proc.stdout


def test_xp2f_supports_imported_time_function(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xxtime.py"
    src.write_text(
        "\n".join(
            [
                "from time import time",
                "t0 = time()",
                "print(time() - t0)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xxtime_p.f90").read_text(encoding="utf-8")
    assert "py_time()" in out_text


def test_xp2f_compiles_numpy_array_transform_frontier(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xnp_array_frontier.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "a = np.arange(6).reshape(2, 3)",
                "s2 = np.arange(12).reshape(3, 4)",
                "parts = np.split(s2, 2, axis=1)",
                "for i, part in enumerate(parts):",
                "    print(i)",
                "    print(part)",
                "print(np.shape(a))",
                "",
                "dst = np.zeros((2, 3))",
                "src_arr = np.ones((2, 3))",
                "np.copyto(dst, src_arr)",
                "print(np.ravel(a))",
                "print(list(a.flat))",
                "",
                "x3 = np.arange(24).reshape(2, 3, 4)",
                "print(np.rollaxis(x3, 2, 0))",
                'permute_dims = getattr(np, "permute_dims", np.transpose)',
                "print(permute_dims(x3, (2, 0, 1)))",
                'matrix_transpose = getattr(np, "matrix_transpose", None)',
                'if matrix_transpose is None and hasattr(np, "linalg") and hasattr(np.linalg, "matrix_transpose"):',
                "    matrix_transpose = np.linalg.matrix_transpose",
                "if matrix_transpose is not None:",
                "    print(matrix_transpose(x3))",
                "",
                "v = np.array([1, 2, 3])",
                "print(np.atleast_3d(v))",
                "",
                "u = np.array([1, 2, 3])",
                "w = np.array([[10], [20]])",
                "bobj = np.broadcast(u, w)",
                'print("broadcast shape =", bobj.shape)',
                'print("broadcasted pairs =", list(bobj))',
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout


def test_xp2f_math_number_theory_family(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xxmath.py"
    src.write_text(
        "\n".join(
            [
                "import math",
                "print(math.comb(5, 2))",
                "print(math.factorial(5))",
                "print(math.gcd(12, 18, 30))",
                "print(math.isqrt(17))",
                "print(math.lcm(12, 18, 30))",
                "print(math.perm(6, 3))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout


def test_xp2f_fails_fast_on_known_unsupported_import(tmp_path: Path) -> None:
    src = tmp_path / "xpil.py"
    src.write_text(
        "\n".join(
            [
                "from PIL import Image",
                "print('x')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "unsupported imported module: PIL" in proc.stdout


def test_xp2f_allows_local_sibling_import(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    (tmp_path / "mylocal.py").write_text("VALUE = 3\n", encoding="utf-8")
    src = tmp_path / "xlocal_import.py"
    src.write_text(
        "\n".join(
            [
                "import mylocal",
                "print(1)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout


def test_xp2f_does_not_force_real_compare_arg_complex_via_numpy_sqrt(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xordered_compare_real_arg.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(p):",
                "    if 0.0 < p and p < 1.0:",
                "        return np.sqrt(-np.log(1.0 - p))",
                "    return 0.0",
                "",
                "print(f(0.3))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_text = (tmp_path / "xordered_compare_real_arg_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), intent(in) :: p" in out_text


def test_xp2f_complex_zeros_dtype_preserves_complex_arrays(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xcomplex_zeros.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "b = np.zeros(3, dtype=np.complex64)",
                "b[0] = 1.0 - 2.0j",
                "b[1] = -3.0 + 4.0j",
                "b[2] = -5.0 - 6.0j",
                "for i in range(3):",
                "    print(b[i].real, b[i].imag)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout
    out_text = (tmp_path / "xcomplex_zeros_p.f90").read_text(encoding="utf-8")
    assert "complex(kind=dp), allocatable :: b(:)" in out_text


def test_xp2f_keeps_double_parens_for_complex_literal_imag(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "ximag_literal.py"
    src.write_text(
        "\n".join(
            [
                "print((1j).imag)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_text = (tmp_path / "ximag_literal_p.f90").read_text(encoding="utf-8")
    assert "aimag((0.0_dp, 1.0_dp))" in out_text


def test_xp2f_complex_isinf_isnan_lowering(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xcomplex_predicates.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "a = np.complex128(1.0 + 2.0j)",
                "print(np.isinf(a))",
                "print(np.isnan(a))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_text = (tmp_path / "xcomplex_predicates_p.f90").read_text(encoding="utf-8")
    assert "complex_isinf(a)" in out_text
    assert "complex_isnan(a)" in out_text


def test_xp2f_dictcomp_keys_argument_stays_integer_in_generated_print_table(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xma_persist.py"
    shutil.copy2(REPO_ROOT / "xma_persist.py", src)

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xma_persist_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "integer, intent(in) :: sharpe_vals_keys(:)" in out_text
    assert "integer :: i_sharpe_vals_230, k" in out_text
    assert 'write(*,"(a,f18.6,f18.6)") str_ljust(py_str(k), 6), mean_before, &' in out_text


def test_xp2f_can_compile_xfit_hv_with_conservative_stubbed_main(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xfit_hv.py"
    shutil.copy2(REPO_ROOT / "xfit_hv.py", src)

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_f90 = tmp_path / "xfit_hv_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert 'write(*,"(a)") "price-table analysis transpiled"' in out_text


def test_xp2f_xfit_hv_no_dates_matches_python_numeric_results(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    shutil.copy2(REPO_ROOT / "xfit_hv_no_dates.py", tmp_path / "xfit_hv_no_dates.py")
    shutil.copy2(REPO_ROOT / "prices_no_dates.csv", tmp_path / "prices_no_dates.csv")

    py_run = subprocess.run(
        [sys.executable, "xfit_hv_no_dates.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert py_run.returncode == 0, py_run.stdout + py_run.stderr
    shutil.copy2(tmp_path / "hv_fit_results.csv", tmp_path / "py_hv_fit_results.csv")

    ft_run = subprocess.run(
        [sys.executable, str(XP2F_PATH), "xfit_hv_no_dates.py", "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert ft_run.returncode == 0, ft_run.stdout + ft_run.stderr
    assert "Build: PASS" in ft_run.stdout
    assert "Run: PASS" in ft_run.stdout
    shutil.copy2(tmp_path / "hv_fit_results.csv", tmp_path / "ft_hv_fit_results.csv")

    py_rows = list(csv.DictReader((tmp_path / "py_hv_fit_results.csv").open(newline="", encoding="utf-8")))
    ft_rows = list(csv.DictReader((tmp_path / "ft_hv_fit_results.csv").open(newline="", encoding="utf-8")))
    assert len(py_rows) == len(ft_rows)

    for py_row, ft_row in zip(py_rows, ft_rows):
        assert py_row["asset"] == ft_row["asset"]

    cols = ["horizon", "a", "b", "r2", "corr", "rmse", "nobs"]
    for py_row, ft_row in zip(py_rows, ft_rows):
        for col in cols:
            assert math.isclose(
                float(py_row[col]),
                float(ft_row[col]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ), (col, py_row[col], ft_row[col])


def test_xp2f_preserves_integer_tuple_output_from_local_scalar_helper(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlocal_tuple_int_from_helper.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def rule_order(p):",
                "    order_vec = np.array([1, 6, 14])",
                "    order = order_vec[p]",
                "    return order",
                "",
                "def make_rule(p):",
                "    n = rule_order(p)",
                "    x = np.array([1.0, 2.0])",
                "    return n, x",
                "",
                "n, x = make_rule(1)",
                "print(n)",
                "print(x)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xlocal_tuple_int_from_helper_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "integer, intent(out) :: make_rule_out_1" in out_text


def test_xp2f_keeps_nested_integer_array_state_in_local_tuple_subroutine(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xnested_int_state_tuple.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def step(n, a, more, h, t):",
                "    if not more:",
                "        t = n",
                "        h = 0",
                "        a[0] = n",
                "        a[1] = 0",
                "    else:",
                "        t = a[h]",
                "        a[h] = 0",
                "        a[0] = t - 1",
                "        a[h+1] = a[h+1] + 1",
                "        h = h + 1",
                "    return a, more, h, t",
                "",
                "a = np.zeros(3, dtype=int)",
                "a, more, h, t = step(3, a, False, 0, 0)",
                "print(a)",
                "print(t)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xnested_int_state_tuple_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "integer, intent(inout) :: a(:)" in out_text
    assert "integer, intent(in) :: t" in out_text
    assert "integer, allocatable, intent(out) :: step_out_1(:)" in out_text
    assert "integer, intent(out) :: step_out_4" in out_text


def test_xp2f_keeps_scalar_integer_tuple_output_despite_real_sentinel(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xvalues_tuple_int.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def values(n_data):",
                "    d_vec = np.array([1, 2, 3])",
                "    volume_vec = np.array([1.0, 2.0, 3.0])",
                "    if n_data < 0:",
                "        n_data = 0",
                "    if 3 <= n_data:",
                "        n_data = 0",
                "        d = 0.0",
                "        volume = 0.0",
                "    else:",
                "        d = d_vec[n_data]",
                "        volume = volume_vec[n_data]",
                "        n_data = n_data + 1",
                "    return n_data, d, volume",
                "",
                "n_data = 0",
                "n_data, d, volume = values(n_data)",
                "print(n_data, d, volume)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xvalues_tuple_int_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "integer, intent(out) :: d" in out_text


def test_xp2f_keeps_wrapper_return_rank_for_scalar_times_local_array_call(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xscalar_times_local_array_wrapper.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def inner(d, n):",
                "    x = np.zeros((d, n), dtype=float)",
                "    return x",
                "",
                "def outer(d, r, n):",
                "    x = r * inner(d, n)",
                "    return x",
                "",
                "print(outer(2, 1.5, 3))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    out_f90 = tmp_path / "xscalar_times_local_array_wrapper_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "function outer(d, r, n) result(x)" in out_text
    assert "real(kind=dp), allocatable :: x(:,:)" in out_text


def test_xp2f_imports_eye_helper_for_np_identity(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xidentity.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "print(np.identity(3))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_f90 = tmp_path / "xidentity_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "use python_mod, only: eye, print_matrix" in out_text or "use python_mod, only: print_matrix, eye" in out_text


def test_xp2f_avoids_runtime_helper_name_collision_with_local_proc(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xrnorm.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def rnorm():",
                "    return 10.0, 20.0",
                "",
                "print(rnorm())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_f90 = tmp_path / "xrnorm_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "use xrnorm_proc_mod, only: dp, rnorm" in out_text
    assert "use python_mod, only: print_matrix, rnorm" not in out_text
    assert "use python_mod, only: rnorm, print_matrix" not in out_text
    assert "print *, rnorm()" not in out_text


def test_xp2f_aliases_local_tuple_proc_that_collides_with_runtime_helper(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xrnorm.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def rnorm():",
                "    return np.random.normal(), np.random.normal()",
                "",
                "print(rnorm())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xrnorm_p.f90").read_text(encoding="utf-8")
    assert "public :: dp, xrnorm" in out_text
    assert "subroutine xrnorm(" in out_text


def test_xp2f_structured_top_level_if_preserves_real_scalar_kinds(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xxif.py"
    src.write_text(
        "\n".join(
            [
                "y = 4.0",
                "if (y < 0):",
                "    print(\"abc\")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xxif_p.f90").read_text(encoding="utf-8")
    assert "integer, parameter :: dp = real64" in out_text
    assert "real(kind=dp) :: y" in out_text


def test_xp2f_keeps_negative_literal_comparisons_valid_in_if_chains(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xif_bug.py"
    src.write_text(
        "\n".join(
            [
                "i = 2",
                "j = 3",
                "",
                "if (i - j == 1):",
                "    print(\"a\")",
                "elif (i - j == 0):",
                "    print(\"b\")",
                "elif (i - j == -1):",
                "    print(\"c\")",
                "else:",
                "    print(\"d\")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xif_bug_p.f90").read_text(encoding="utf-8")
    assert "if (i - j) == (-1) then" not in out_text
    assert "if ((i - j) == (-1)) then" in out_text or "if ((i - j) == -1) then" in out_text


def test_xp2f_normalizes_removed_numpy_scalar_aliases_for_run_both(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xnan.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "print(np.NaN)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run (python): PASS" in proc.stdout
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xnan_p.f90").read_text(encoding="utf-8")
    assert "ieee_value(0.0_dp, ieee_quiet_nan)" in out_text


def test_xp2f_lowers_function_attribute_state_via_module_globals(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xfunc_attr_state.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def fisher_parameters(a_user=None):",
                "    if not hasattr(fisher_parameters, 'a_default'):",
                "        fisher_parameters.a_default = 2.0",
                "    if a_user is not None:",
                "        fisher_parameters.a_default = a_user",
                "    a = fisher_parameters.a_default",
                "    return a",
                "",
                "print(fisher_parameters())",
                "print(fisher_parameters(3.5))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xfunc_attr_state_p.f90").read_text(encoding="utf-8")
    assert "logical :: fisher_parameters_has_a_default = .false." in out_text
    assert "real(kind=dp) :: fisher_parameters_a_default" in out_text
    assert "pure function fisher_parameters" not in out_text
