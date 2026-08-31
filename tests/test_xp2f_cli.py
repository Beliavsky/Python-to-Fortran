from __future__ import annotations

import csv
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import fortran_output as fout
import fortran_post as fpost
import xp2f

XP2F_PATH = REPO_ROOT / "xp2f.py"
PYTHON_HELPER_PATH = REPO_ROOT / "python.f90"
DATAFRAME_HELPER_PATH = REPO_ROOT / "dataframe_index_date.f90"
EXAMPLES_DIR = REPO_ROOT / "examples"

SUPPORTED_PY_COMPILE_CASES = [
    "xoptions_pde.py",
    "xbs_monte_carlo.py",
]


def _join_fortran_continuations(text: str) -> str:
    """Join "&"-continued declaration (or other) statements back onto one
    logical line, so simple substring/per-line assertions don't need to
    know whether xp2f's declaration-coalescing passes merged several
    names onto a line long enough to trigger line-wrapping."""
    out_lines = []
    pending = None
    for raw in text.splitlines():
        stripped = raw.strip()
        cont = stripped[1:].strip() if stripped.startswith("&") else stripped
        if pending is not None:
            pending = f"{pending} {cont}"
        else:
            pending = raw
        if pending.rstrip().endswith("&"):
            pending = pending.rstrip()[:-1].rstrip()
            continue
        out_lines.append(pending)
        pending = None
    if pending is not None:
        out_lines.append(pending)
    return "\n".join(out_lines)


def _run_xp2f_compile(tmp_path: Path, example_name: str) -> subprocess.CompletedProcess[str]:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    local_input = tmp_path / example_name
    shutil.copy2(EXAMPLES_DIR / example_name, local_input)
    return subprocess.run(
        [sys.executable, str(XP2F_PATH), str(local_input), "--compile"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fortran_post_spaces_units_and_procedures() -> None:
    lines = [
        "module m",
        "contains",
        "subroutine a()",
        "end subroutine a",
        "real(kind=dp) function b()",
        "end function b",
        "end module m",
        "program p",
        "end program p",
    ]

    text = "\n".join(fpost.ensure_blank_lines_around_units_and_procedures(lines))

    assert "contains\n\nsubroutine a()" in text
    assert "end subroutine a\n\nreal(kind=dp) function b()" in text
    assert "end function b\n\nend module m" in text
    assert "end module m\n\nprogram p" in text


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


def test_xp2f_avoids_program_name_variable_collision(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xsum.py"
    src.write_text(
        "\n".join(
            [
                "xsum = 0.0",
                "for i in range(10):",
                "    xsum = xsum + i",
                "print(xsum)",
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
    out_text = (tmp_path / "xsum_p.f90").read_text(encoding="utf-8")
    assert "program xsum_prog" in out_text
    assert "end program xsum_prog" in out_text
    assert "real(kind=dp) :: xsum" in out_text
    assert "use python_mod" not in out_text
    assert "use, intrinsic :: ieee_arithmetic" not in out_text
    assert "integer, parameter :: sp = real32" not in out_text
    assert "real32" not in out_text


def test_xp2f_keeps_module_parameter_used_by_later_procedure() -> None:
    lines = [
        "module m",
        "   use, intrinsic :: iso_fortran_env, only: real32, real64",
        "   implicit none",
        "   integer, parameter :: sp = real32",
        "   integer, parameter :: dp = real64",
        "contains",
        "subroutine a()",
        "end subroutine a",
        "subroutine b()",
        "   real(kind=sp) :: x",
        "   x = 1.0_sp",
        "end subroutine b",
        "end module m",
    ]

    out = xp2f.remove_unused_named_constants(lines)

    assert "   integer, parameter :: sp = real32" in out
    assert "   integer, parameter :: dp = real64" not in out


def test_xp2f_time_uses_optimized_compiler_unless_explicit(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xtime_small.py"
    src.write_text("print(42)\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--time"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Compile options: -O3 -march=native -Wfatal-errors" in proc.stdout

    proc = subprocess.run(
        [
            sys.executable,
            str(XP2F_PATH),
            str(src),
            "--time",
            "--compiler",
            "gfortran -O0 -Wfatal-errors",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Compile options: -O0 -Wfatal-errors" in proc.stdout
    assert "Compile options: -O3 -march=native -Wfatal-errors" not in proc.stdout


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
    assert "runif(3)" in out_text


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
    # Declarations of the same type/rank may be coalesced onto one line,
    # and (mixed-rank) possibly line-wrapped with "&" continuations if
    # that line got long (e.g.
    # "real(kind=dp), allocatable :: nk(:), amax(:), log_norm(:), &\n
    # & log_prob(:,:), resp(:,:), s(:)"), so join continuations first and
    # check each name is declared real(kind=dp) allocatable rank-1 rather
    # than requiring it alone on its own declaration line.
    rank1_real_alloc_names = set()
    for line in _join_fortran_continuations(out_text).splitlines():
        line = line.strip()
        if not line.startswith("real(kind=dp), allocatable ::"):
            continue
        for entity in line.split("::", 1)[1].split(","):
            entity = entity.strip()
            if entity.endswith("(:)"):
                rank1_real_alloc_names.add(entity[: -len("(:)")])
    for name in ("amax", "s", "log_norm", "nk"):
        assert name in rank1_real_alloc_names, (
            f"{name} not declared real(kind=dp), allocatable, rank-1 in:\n{out_text}"
        )
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


def test_xp2f_runs_lstsq_tuple_assignment_to_section(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xlstsq_section_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "q = np.zeros((2, 3))",
                "q[0:2, 0:2] = np.array([[2.0, 0.0], [0.0, 4.0]])",
                "q[0:2, 2] = np.array([4.0, 8.0])",
                "q[0:2, 2], res, rank, s = np.linalg.lstsq(q[0:2, 0:2], q[0:2, 2], rcond=None)",
                "print(q[:, 2])",
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


def test_xp2f_runs_numpy_shape_assignment_as_reshape_alias(tmp_path: Path) -> None:
    src = tmp_path / "xshape_assign_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x, m, n):",
                "    x.shape = (m, n)",
                "    return x[1, 0]",
                "",
                "print(f(np.array([1.0, 2.0, 3.0, 4.0]), 2, 2))",
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


def test_xp2f_shape_assignment_overrides_comment_rank_for_dummy(tmp_path: Path) -> None:
    src = tmp_path / "xshape_comment_rank_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def p00_f(m, n, x):",
                "    # real x(m,n)",
                "    x.shape = (m, n)",
                "    return x[1, 0]",
                "",
                "x = np.array([1.0, 2.0, 3.0, 4.0])",
                "print(p00_f(2, 2, x))",
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
    out_text = (tmp_path / "xshape_comment_rank_small_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), intent(in) :: x(:)" in out_text


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
    # scale and shift are both scalar real(kind=dp), intent(in) dummy args,
    # so xp2f's declaration-coalescing pass merges them onto one line.
    assert "real(kind=dp), intent(in) :: scale, shift" in out_text


def test_xp2f_runs_direct_numpy_array_import_with_integer_norm(tmp_path: Path) -> None:
    src = tmp_path / "xnorm_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy.linalg import norm",
                "from numpy import array",
                "",
                "arr1 = array([1, 2, 3, 4])",
                "nrm = norm(arr1)",
                "print(nrm)",
                "",
                "arr2 = array([[1, 2, 3, 4], [4, 3, 2, 1]])",
                "nrm2 = norm(arr2, axis=1)",
                "print(nrm2)",
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
    out_text = (tmp_path / "xnorm_direct_import_p.f90").read_text(encoding="utf-8")
    # arr2 is a rank-2 integer array literal that's never reassigned, so
    # xp2f's constant-promotion pass turns it into a named PARAMETER with
    # an explicit shape instead of an allocatable declaration.
    joined = _join_fortran_continuations(out_text)
    assert any(
        line.strip().startswith("integer, parameter ::") and "arr2(2,4)" in line
        for line in joined.splitlines()
    )
    assert "real(arr1, kind=dp)" in out_text
    assert "real(arr2, kind=dp)" in out_text


def test_xp2f_runs_direct_numpy_prod_import(tmp_path: Path) -> None:
    src = tmp_path / "xprod_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, prod",
                "",
                "arr = array([1, 2, 3, 4])",
                "prd = prod(arr)",
                "print('prd: ', prd)",
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
    out_text = (tmp_path / "xprod_direct_import_p.f90").read_text(encoding="utf-8")
    assert "prd = product(arr)" in out_text


def test_xp2f_runs_direct_numpy_mod_import(tmp_path: Path) -> None:
    src = tmp_path / "xmod_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, mod",
                "",
                "arr = array([1, 2, 3, 4])",
                "res = mod(arr, arr)",
                "print('res: ', res)",
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
    out_text = (tmp_path / "xmod_direct_import_p.f90").read_text(encoding="utf-8")
    assert "res = mod(arr, arr)" in out_text


def test_xp2f_runs_direct_numpy_empty_import(tmp_path: Path) -> None:
    src = tmp_path / "xempty_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, empty",
                "",
                "a = array([1, 2, 3, 4])",
                "b = empty(4)",
                "for i in range(len(a)):",
                "    b[i] = a[i] + 1",
                "print('b =', b)",
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
    out_text = (tmp_path / "xempty_direct_import_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp), allocatable :: b(:)" in out_text
    assert "allocate(b(4))" in out_text


def test_xp2f_runs_direct_numpy_ones_import_with_string_dtype(tmp_path: Path) -> None:
    src = tmp_path / "xones_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, ones, size, sum",
                "",
                "a = array([1, 2, 3, 4, 5])",
                "o = ones(size(a), dtype='int')",
                "print(sum(o[(a > 2) & (a < 5)]))",
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
    out_text = (tmp_path / "xones_direct_import_p.f90").read_text(encoding="utf-8")
    # `a` is a rank-1 integer literal that's never reassigned, so it's
    # promoted to a named PARAMETER; `o`'s allocate is immediately
    # followed by a whole-array scalar fill, so xp2f merges the two into
    # a single `allocate(..., source=...)` statement.
    assert "integer, parameter :: a(*) = [1, 2, 3, 4, 5]" in out_text
    assert "integer, allocatable :: o(:)" in out_text
    assert "allocate(o(size(a)), source=1)" in out_text


def test_xp2f_runs_direct_numpy_dot_import_for_matrices(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xdot_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, dot",
                "",
                "a = array([[1, 2], [3, 4]])",
                "b = array([[2, 3], [4, 5]])",
                "print(a * b)",
                "print(dot(a, b))",
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
    out_text = (tmp_path / "xdot_direct_import_p.f90").read_text(encoding="utf-8")
    assert "call print_matrix(matmul(a, b))" in out_text


def test_xp2f_runs_numpy_array_listcomps_with_direct_pi(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xarray_listcomp_direct_pi.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, pi",
                "",
                "a = array([i for i in range(1, 7)])",
                "b = array([(2 * i * pi + 1) / 2 for i in range(1, 7)])",
                "c = array([i for i in range(1, 7) for j in range(1, 4)])",
                "print('a =', a)",
                "print('b =', b)",
                "print('c =', c)",
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
    out_text = (tmp_path / "xarray_listcomp_direct_pi_p.f90").read_text(encoding="utf-8")
    assert "a = arange_int(1, 7, 1)" in out_text
    assert "acos(-1.0_dp)" in out_text
    assert "c = repeat_int(arange_int(1, 7, 1), size(arange_int(1, 4, 1)))" in out_text


def test_xp2f_runs_masked_assignment_into_numpy_empty_array(tmp_path: Path) -> None:
    src = tmp_path / "xmasked_empty_assign.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, empty",
                "",
                "a = array([1, 2, 3, 4, 5, 6])",
                "b = empty(6)",
                "b[:] = 0",
                "b[a > 2] = 1",
                "b[a > 5] = a[a > 5] - 3",
                "print('b =', b)",
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
    out_text = (tmp_path / "xmasked_empty_assign_p.f90").read_text(encoding="utf-8")
    assert "merge(real(1, kind=dp), b, a > 2)" in out_text
    assert "b = a - 3" in out_text
    assert "pack(a, (a > 5))" not in out_text


def test_xp2f_runs_direct_numpy_shape_size_min_max_sum_imports(tmp_path: Path) -> None:
    src = tmp_path / "xshape_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array, max, min, shape, size, sum",
                "",
                "a = array([1, 2, 3])",
                "print(shape(a))",
                "print(size(a))",
                "print(max(a))",
                "print(min(a))",
                "print(sum(a))",
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
    out_text = (tmp_path / "xshape_direct_import_p.f90").read_text(encoding="utf-8")
    assert "shape(a)" in out_text
    assert "size(a)" in out_text
    assert "maxval(a)" in out_text
    assert "minval(a)" in out_text
    assert "sum(a)" in out_text


def test_xp2f_uses_allocation_assignment_for_numeric_array_literals(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xarray_literal_alloc_assign.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import array",
                "",
                "a = array([1, 2, 3])",
                "b = array([[1.0, 2.0], [3.0, 4.0]])",
                "print(a)",
                "print(b)",
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
    out_text = (tmp_path / "xarray_literal_alloc_assign_p.f90").read_text(encoding="utf-8")
    assert "if (allocated(a)) deallocate(a)" not in out_text
    assert "allocate(a(1:3))" not in out_text
    # `a` is a rank-1 integer literal that's never reassigned, so it's
    # promoted to a named PARAMETER (no runtime allocate/assign at all).
    assert "integer, parameter :: a(*) = [1, 2, 3]" in out_text
    assert "if (allocated(b)) deallocate(b)" not in out_text
    assert "allocate(b(1:2,1:2))" not in out_text
    assert "b = reshape([1.0_dp, 2.0_dp, 3.0_dp, 4.0_dp], [2, 2], order=[2, 1])" in out_text


def test_xp2f_runs_direct_numpy_reshape_import_with_order(tmp_path: Path) -> None:
    src = tmp_path / "xreshape_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import reshape",
                "",
                "a = reshape([1, 2, 3, 4, 5, 6], (2, 3))",
                "b = reshape([1, 2, 3, 4, 5, 6], (2, 3), order='F')",
                "print(a[0, :])",
                "print(a[1, :])",
                "print()",
                "print(b[0, :])",
                "print(b[1, :])",
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
    out_text = (tmp_path / "xreshape_direct_import_p.f90").read_text(encoding="utf-8")
    # `a` and `b` are both rank-2 real literals (via reshape) that are
    # never reassigned, so xp2f's constant-promotion pass turns each into
    # a named PARAMETER with an explicit shape and the reshape() baked
    # directly into the declaration, rather than a separate allocatable +
    # assignment.
    joined = _join_fortran_continuations(out_text)
    assert "real(kind=dp), parameter :: a(2,3) = reshape([1, 2, 3, 4, 5, 6], [2, 3], order=[2, 1])" in joined
    assert "real(kind=dp), parameter :: b(2,3) = reshape([1, 2, 3, 4, 5, 6], [2, 3])" in joined
    assert "a(1, :)" in out_text
    assert "a((1), :)" not in out_text


def test_xp2f_simplifies_all_any_reduction_parentheses(tmp_path: Path) -> None:
    src = tmp_path / "xall_any_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import all, any, array",
                "",
                "i = array([1, 2, 3])",
                "print(all(i == [1, 2, 3]))",
                "print(any(i == [2, 2, 3]))",
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
    out_text = (tmp_path / "xall_any_direct_import_p.f90").read_text(encoding="utf-8")
    assert "print *, all(i == [1, 2, 3])" in out_text
    assert "print *, any(i == [2, 2, 3])" in out_text
    assert "all((i ==" not in out_text
    assert "any((i ==" not in out_text


def test_xp2f_runs_direct_numpy_real_imag_imports(tmp_path: Path) -> None:
    src = tmp_path / "xreal_imag_direct_import.py"
    src.write_text(
        "\n".join(
            [
                "from numpy import imag, real, array",
                "",
                "arr1 = array([1 + 1j, 2 + 1j, 3 + 1j, 4 + 1j])",
                "real_part = real(arr1)",
                "imag_part = imag(arr1)",
                "print(real_part)",
                "print(imag_part)",
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
    out_text = (tmp_path / "xreal_imag_direct_import_p.f90").read_text(encoding="utf-8")
    assert "complex(kind=dp), allocatable :: arr1(:)" in out_text
    assert "real_part = real(arr1, kind=dp)" in out_text
    assert "imag_part = aimag(arr1)" in out_text


def test_xp2f_resolves_explicit_lapack_helper_from_other_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "xneeds_lapack_p.f90"
    src.write_text(
        "\n".join(
            [
                "program xneeds_lapack",
                "   use python_mod, only: linalg_cond",
                "   implicit none",
                "   print *, linalg_cond(reshape([1.0d0], [1, 1]))",
                "end program xneeds_lapack",
                "",
            ]
        ),
        encoding="utf-8",
    )
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    helpers, _auto_added, missing = xp2f.resolve_helper_files_for_build(
        src,
        [str(PYTHON_HELPER_PATH), str(REPO_ROOT / "lapack_d.f90")],
    )

    assert not missing
    assert str(REPO_ROOT / "lapack_d.f90") in helpers


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
    # factors and powers are both integer, allocatable, intent(out), so
    # xp2f's declaration-coalescing pass may merge them onto one line.
    joined = _join_fortran_continuations(out_text)
    assert any(
        line.strip().startswith("integer, allocatable, intent(out) ::") and "factors(:)" in line
        for line in joined.splitlines()
    )
    assert any(
        line.strip().startswith("integer, allocatable, intent(out) ::") and "powers(:)" in line
        for line in joined.splitlines()
    )


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
    # xp2f's format-descriptor compaction pass folds the two identical
    # `a` descriptors into `2a`.
    assert 'write(*,"(2a, g0)") labels(i_zip), ": ", vals(i_zip)' in out_text


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
    shutil.copy2(EXAMPLES_DIR / "xnp_math_funcs.py", local_input)

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
    # xp2f's paren-flattening pass drops the now-redundant parens around
    # `size(prices,1) - 1` (a bare `+`/`-` chain right after a `:` slice
    # bound needs no grouping).
    assert "prices(1:size(prices,1) - 1, :)" in out_text


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
    # xp2f's format-descriptor compaction pass folds the two identical
    # `a` descriptors into `2a`, and the two identical `f18.6` descriptors
    # into `2f18.6`.
    assert 'write(*,"(2a)") "strategy_k_list: ", str_int_list(ks, size(ks))' in out_text
    assert 'write(*,"(a, 2f18.6)") str_ljust(py_str(k), 6), mean_before, mean_after' in out_text


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
    # xp2f's paren-simplification passes now fully strip the redundant
    # triple wrap around the where-mask condition.
    assert "where (.not. ieee_is_nan(x))" in out_text
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


def test_xp2f_keeps_dp_parameter_for_real_literal_kind_suffix(tmp_path: Path) -> None:
    src = tmp_path / "xmath_kind_suffix.py"
    src.write_text(
        "\n".join(
            [
                "import math",
                "print(math.sqrt(1.44))",
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

    out_text = (tmp_path / "xmath_kind_suffix_p.f90").read_text(encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "integer, parameter :: dp = real64" in out_text
    assert "sqrt(1.44_dp)" in out_text


def test_xp2f_runs_statistics_quantiles_and_means(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xstats_small.py"
    src.write_text(
        "\n".join(
            [
                "import statistics as stats",
                "",
                "x = [12, 15, 15, 18, 20, 22, 25, 25, 25, 30]",
                "print('quartiles:', stats.quantiles(x, n=4))",
                "print('geometric mean:', stats.geometric_mean(x))",
                "print('harmonic mean:', stats.harmonic_mean(x))",
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

    out_text = (tmp_path / "xstats_small_p.f90").read_text(encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    # xp2f strips the no-op `int(...)` wrap off an already-integer literal.
    assert "statistics_quantiles_real(real(x, kind=dp), 4)" in out_text
    assert "exp(mean_1d(log(real(x, kind=dp))))" in out_text
    assert "sum(1.0_dp / real(x, kind=dp))" in out_text


def test_xp2f_runs_statistics_mode_for_real_data(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xstats_real_mode.py"
    src.write_text(
        "\n".join(
            [
                "import statistics as stats",
                "",
                "x = [1.5, 2.5, 3.5]",
                "print('mode:', stats.mode(x))",
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

    out_text = (tmp_path / "xstats_real_mode_p.f90").read_text(encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout
    assert "mode_real(x)" in out_text


def test_xp2f_compiles_random_module_sequence_helpers(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrandom_sequence_small.py"
    src.write_text(
        "\n".join(
            [
                "import random",
                "",
                "random.seed(12345)",
                "colors = ['red', 'green', 'blue', 'yellow']",
                "print(random.randint(1, 10))",
                "print(random.randrange(0, 100, 5))",
                "print(random.choice(colors))",
                "print(random.choices(colors, k=5))",
                "print(random.sample(colors, k=3))",
                "normal_values = [random.gauss(mu=0.0, sigma=1.0) for _ in range(5)]",
                "print(normal_values)",
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

    out_text = (tmp_path / "xrandom_sequence_small_p.f90").read_text(encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    # xp2f strips the no-op `int(...)` wraps off already-integer literals.
    assert "random_randrange_int(0, 100, 5)" in out_text
    assert "random_choice_char(colors)" in out_text
    assert "random_choices_char(colors, 5)" in out_text
    assert "random_sample_char(colors, 3)" in out_text
    assert "rnorm(size(arange_int(0, 5, 1)))" in out_text
    assert "max(1, 10 - 1 + 1)" in out_text


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


def test_xp2f_inlines_local_sibling_from_import_function_and_constant(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "\n".join(
            [
                "i = 5",
                "",
                "def f(x):",
                "    return x + 5",
                "",
                "def g(x):",
                "    return x - 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    src = tmp_path / "xa.py"
    src.write_text(
        "\n".join(
            [
                "from a import f, i",
                "",
                "print(f(3))",
                "print(i)",
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
    out_text = (tmp_path / "xa_p.f90").read_text(encoding="utf-8")
    assert "function f" in out_text
    assert "print" in out_text


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


def test_xp2f_skips_constant_promotion_for_nested_block_reassignment(tmp_path: Path) -> None:
    # `n_data` is declared and immediately assigned a literal (0) at
    # program scope, which on its own looks like a promotable constant --
    # but a tuple-return call site further down reassigns it from inside
    # a `block ... end block` (the temp-holding wrapper generated for
    # unpacking a multi-value function result), a genuinely deeper scope
    # than the declaration. The constant-promotion passes must still see
    # that reassignment (not just same-depth ones), or `n_data` gets
    # wrongly turned into a PARAMETER and the build fails with "Named
    # constant ... in variable definition context".
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpromote_nested_block.py"
    src.write_text(
        "\n".join(
            [
                "def values(n_data):",
                "    if n_data >= 3:",
                "        n_data = 0",
                "        d = 0.0",
                "    else:",
                "        d = float(n_data)",
                "        n_data = n_data + 1",
                "    return n_data, d",
                "",
                "n_data = 0",
                "n_data, d = values(n_data)",
                "print(n_data, d)",
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
    out_text = (tmp_path / "xpromote_nested_block_p.f90").read_text(encoding="utf-8")
    assert "integer, parameter :: n_data" not in out_text
    assert "integer :: n_data" in out_text


def test_xp2f_promotes_constant_only_for_confirmed_intent_in_call_arg(tmp_path: Path) -> None:
    # `k` is passed to `show(x)`, whose dummy `x` is declared
    # intent(in) in this same file -- that's exactly as safe as any other
    # read, so `k` should still be promoted to a PARAMETER. A plain
    # text-only scan can't tell intent(in) from intent(out)/intent(inout)
    # just from `k` appearing inside `call show(k)`, so this needs the
    # promotion pass to actually resolve show's signature.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpromote_intent_in_call.py"
    src.write_text(
        "\n".join(
            [
                "def show(x):",
                "    print(x)",
                "",
                "k = 5",
                "show(k)",
                "show(k)",
                "print(k)",
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
    out_text = (tmp_path / "xpromote_intent_in_call_p.f90").read_text(encoding="utf-8")
    assert "integer, parameter :: k = 5" in out_text


def test_xp2f_does_not_merge_allocate_source_on_type_mismatch(tmp_path: Path) -> None:
    # `b` is a real array; the fill value `0` is a bare integer literal.
    # allocate(..., source=...) requires an EXACT type match (unlike a
    # plain assignment, which implicitly converts), so merging the
    # allocate and the fill into `allocate(b(5), source=0)` would fail to
    # compile ("Type of entity is type incompatible with source-expr").
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xallocate_source_type_mismatch.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "b = np.empty(5)",
                "b[:] = 0",
                "print(b)",
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
    out_text = (tmp_path / "xallocate_source_type_mismatch_p.f90").read_text(encoding="utf-8")
    assert "source=0" not in out_text
    assert "allocate(b(5))" in out_text
    assert "b = 0" in out_text


def test_xp2f_char_list_preallocation_starts_at_default_length_one(tmp_path: Path) -> None:
    # When xp2f can prove a count-mapped character list's final size
    # ahead of time (a `name = []` immediately followed by pure
    # range()-loop append nests), it pre-allocates that size up front --
    # but the starting declared character length must still default to 1
    # (matching grow_and_set_char's own bootstrap default) and widen only
    # as needed, not some larger fixed guess: a plain "a" edit descriptor
    # prints an argument's FULL declared length, so a too-generous
    # default would print as visible, incorrect trailing padding on every
    # value shorter than it.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xcharlist_default_length.py"
    src.write_text(
        "\n".join(
            [
                "k = 3",
                "names = []",
                "for i in range(k):",
                '    names.append(f"c[{i + 1}]")',
                "print(names)",
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
    out_text = (tmp_path / "xcharlist_default_length_p.f90").read_text(encoding="utf-8")
    assert "allocate(character(len=1) :: names(max(0, k)))" in out_text


def test_fortran_int_wrap_strips_nested_literal_inside_non_literal_int_call() -> None:
    # An outer int(...) whose content isn't a bare literal (a real cast
    # of a computed expression) must not be skipped over wholesale --
    # simplify_int_wrapped_integer_literals still needs to look INSIDE it
    # for a nested int(N) wrap around a genuine literal and strip that,
    # even though the outer int() itself stays.
    lines = [
        "   print *, 1 + int(runif() * real(max(1, int(10) - int(1) + 1), kind=dp))",
    ]

    out = xp2f.simplify_int_wrapped_integer_literals(lines)

    assert out == [
        "   print *, 1 + int(runif() * real(max(1, 10 - 1 + 1), kind=dp))",
    ]


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
    shutil.copy2(EXAMPLES_DIR / "xma_persist.py", src)

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
    # xp2f's format-descriptor compaction pass folds the two identical
    # `f18.6` descriptors into `2f18.6`, which now fits on one line
    # instead of needing a "&" continuation.
    assert 'write(*,"(a, 2f18.6)") str_ljust(py_str(k), 6), mean_before, mean_after' in out_text


def test_xp2f_can_compile_xfit_hv_with_conservative_stubbed_main(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xfit_hv.py"
    shutil.copy2(EXAMPLES_DIR / "xfit_hv.py", src)

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
    shutil.copy2(EXAMPLES_DIR / "xfit_hv_no_dates.py", tmp_path / "xfit_hv_no_dates.py")
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
    # "n" doesn't collide with make_rule's own parameter names, so it keeps
    # its natural name as the intent(out) dummy rather than being renamed to
    # a synthetic make_rule_out_1 (that renaming only happens to avoid a
    # collision with a parameter name).
    assert "integer, intent(out) :: n" in out_text


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
    # n, h and t are all scalar integer, intent(in) dummy args, so xp2f's
    # declaration-coalescing pass merges them onto one line together.
    joined = _join_fortran_continuations(out_text)
    assert any(
        line.strip().startswith("integer, intent(in) ::") and "h" in line and "t" in line
        for line in joined.splitlines()
    )
    assert "integer, allocatable, intent(out) :: step_out_1(:)" in out_text
    assert "integer, intent(out) :: step_out_3, step_out_4" in out_text


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
    # values_out_1 (n_data's tuple-output slot) and d are both scalar
    # integer, intent(out), so xp2f's declaration-coalescing pass merges
    # them onto one line.
    assert "integer, intent(out) :: values_out_1, d" in out_text


def test_xp2f_promotes_int_seeded_tuple_output_to_real_when_accumulated_from_real_array(
    tmp_path: Path,
) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xaccumulate_real_from_int_seed.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def total_value(n, v):",
                "    vmax = 0",
                "    for i in range(n):",
                "        vmax = vmax + v[i]",
                "    return n, vmax",
                "",
                "v = np.array([1.5, 2.5, 3.5])",
                "n, vmax = total_value(3, v)",
                "print(n, vmax)",
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
    out_f90 = tmp_path / "xaccumulate_real_from_int_seed_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "real(kind=dp), intent(out) :: vmax" in out_text


def test_xp2f_infers_rank_one_for_rng_permutation_result(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xrng_permutation_best.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "from numpy.random import default_rng",
                "",
                "def f(n):",
                "    rng = default_rng()",
                "    p_best = np.zeros(n)",
                "    cost_best = 0.0",
                "    for k in range(3):",
                "        p = rng.permutation(n)",
                "        cost = float(k)",
                "        if cost < cost_best:",
                "            p_best = p.copy()",
                "            cost_best = cost",
                "    print(p_best)",
                "",
                "f(5)",
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


def test_xp2f_does_not_guess_local_call_return_rank_from_first_argument(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlocal_call_return_rank_guess.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def triangle_xsi_to_xy(t, xsi):",
                "    p = np.zeros(2)",
                "    p[0] = t[0,0] * xsi[0] + t[0,1] * xsi[1] + t[0,2] * xsi[2]",
                "    p[1] = t[1,0] * xsi[0] + t[1,1] * xsi[1] + t[1,2] * xsi[2]",
                "    return p",
                "",
                "def triangle_xy_to_xsi(t, p):",
                "    xsi = np.zeros(3)",
                "    xsi[0] = (t[1,1] - t[1,2]) * (p[0] - t[0,2])",
                "    xsi[1] = (t[1,0] - t[1,2]) * (p[0] - t[0,2])",
                "    xsi[2] = 1.0 - xsi[0] - xsi[1]",
                "    return xsi",
                "",
                "def triangle_xsi_to_xy_test():",
                "    t = np.array([[4.0, 1.0, -2.0],[2.0, 5.0, 2.0]])",
                "    n = 1",
                "    p = np.zeros((2, n))",
                "    p[0,0] = 3.0",
                "    p[1,0] = 0.0",
                "    xsi = triangle_xy_to_xsi(t, p[:,0])",
                "    p2 = triangle_xsi_to_xy(t, xsi)",
                "    print('%8g %8g %8g %8g %8g' % (p[0,0], p[1,0], xsi[0], xsi[1], xsi[2]))",
                "",
                "triangle_xsi_to_xy_test()",
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


def test_xp2f_reports_unsupported_literal_instead_of_crashing_on_nested_none_shape(
    tmp_path: Path,
) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xnested_none_shape.py"
    src.write_text(
        "\n".join(
            [
                "x = [1, 2, 3]",
                "test_cases = [",
                '    ("a", x, [1, 2, 3], 1),',
                '    ("b", x, [4, 5], 2),',
                "]",
                "for case in test_cases:",
                "    print(case[0])",
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

    assert "Traceback (most recent call last)" not in proc.stderr, proc.stdout + proc.stderr
    assert "Transpile: FAIL" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_sanitizes_module_and_program_names_starting_with_a_digit(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "10001th_prime.py"
    src.write_text(
        "\n".join(
            [
                "def is_prime(n):",
                "    if n < 2:",
                "        return False",
                "    i = 2",
                "    while i * i <= n:",
                "        if n % i == 0:",
                "            return False",
                "        i = i + 1",
                "    return True",
                "",
                "count = 0",
                "n = 1",
                "while count < 5:",
                "    n = n + 1",
                "    if is_prime(n):",
                "        count = count + 1",
                "print(n)",
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
    out_f90 = tmp_path / "10001th_prime_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "module m_10001th_prime_proc_mod" in out_text
    assert "program m_10001th_prime" in out_text


def test_xp2f_does_not_crash_on_duplicate_def_with_mismatched_arity(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xduplicate_def_arity.py"
    src.write_text(
        "\n".join(
            [
                "def bellTriangle(n):",
                "    tri = [0] * n",
                "    tri[0] = 1",
                "    for i in range(1, n):",
                "        tri[i] = tri[i - 1] + i",
                "    return tri",
                "",
                "def main():",
                "    bt = bellTriangle(5)",
                "    print(bt[0])",
                "",
                "main()",
                "",
                "def bellTriangle():",
                "    return 0",
                "",
                "def main():",
                "    print(bellTriangle())",
                "",
                "main()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--flat"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "Traceback (most recent call last)" not in proc.stderr, proc.stdout + proc.stderr


def test_xp2f_treats_tuple_unpacked_param_as_array_across_sibling_functions(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xtuple_unpack_param.py"
    src.write_text(
        "\n".join(
            [
                "def monomial_to_bernstein_degree2(monomial_coefficients):",
                "    (a0, a1, a2) = monomial_coefficients",
                "    return (a0, a0 + (0.5 * a1), a0 + a1 + a2)",
                "",
                "def evaluate_bernstein_degree2(bernstein_coefficients, t):",
                "    (b0, b1, b2) = bernstein_coefficients",
                "    s = 1 - t",
                "    b01 = (s * b0) + (t * b1)",
                "    b12 = (s * b1) + (t * b2)",
                "    return (s * b01) + (t * b12)",
                "",
                "def bernstein_degree2_to_degree3(bernstein_coefficients):",
                "    (b0, b1, b2) = bernstein_coefficients",
                "    return (b0, b1, b2, b0 + b1 + b2)",
                "",
                "pmono2 = (1.0, 0.0, 0.0)",
                "pbern2 = monomial_to_bernstein_degree2(pmono2)",
                "print(evaluate_bernstein_degree2(pbern2, 0.25))",
                "print(bernstein_degree2_to_degree3(pbern2))",
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

    out_f90 = tmp_path / "xtuple_unpack_param_p.f90"
    out_text = out_f90.read_text(encoding="utf-8")
    assert "bernstein_coefficients(:)" in out_text, proc.stdout + proc.stderr


def test_xp2f_does_not_crash_printing_non_ascii_transpile_error(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xunicode_error.py"
    src.write_text(
        "\n".join(
            [
                "def f():",
                "    return dict(zip(['a'], [('甲乙丙丁', 'jiǎ yǐ')]))",
                "",
                "print(f())",
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

    assert "UnicodeEncodeError" not in proc.stderr, proc.stdout + proc.stderr
    assert "Transpile: FAIL" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_recognizes_name_in_main_guard_idiom(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xname_in_main.py"
    src.write_text(
        "\n".join(
            [
                "def main():",
                "    print('hello')",
                "",
                "if __name__ in \"__main__\":",
                "    main()",
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


def test_xp2f_reports_duplicate_top_level_function_definition(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xduplicate_top_level_def.py"
    src.write_text(
        "\n".join(
            [
                "def f():",
                "    return 1",
                "",
                "print(f())",
                "",
                "def f():",
                "    return 2",
                "",
                "print(f())",
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

    assert "Traceback (most recent call last)" not in proc.stderr, proc.stdout + proc.stderr
    assert "duplicate top-level function definition: f" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_gives_local_variable_its_own_declaration_despite_module_level_name_collision(
    tmp_path: Path,
) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xgcd.py"
    src.write_text(
        "\n".join(
            [
                "def Gcd(v1, v2):",
                "    a, b = v1, v2",
                "    if a < b:",
                "        a, b = v2, v1",
                "    r = 1",
                "    while r != 0:",
                "        r = a % b",
                "        if r != 0:",
                "            a = b",
                "            b = r",
                "    return b",
                "",
                "a = [1, 2]",
                "print(Gcd(12, 18))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_slices_negative_lower_bound_on_char_scalar_argument(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xstring_negative_slice.py"
    src.write_text(
        "\n".join(
            [
                "def conjugate(infinitive):",
                "    if not infinitive[-3:] == 'are':",
                "        print(infinitive, 'non prima coniugatio verbi.')",
                "        return False",
                "    print(infinitive, 'is prima coniugatio verbi.')",
                "    return True",
                "",
                "conjugate('amare')",
                "conjugate('videre')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_does_not_duplicate_local_function_comments_into_main_body(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xcomment_dup_repro.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "",
                "def helper(x):",
                "    # step one",
                "    y = x * 2",
                "    # step two",
                "    z = y + 1",
                "    return z",
                "",
                "",
                "# top level marker comment",
                "result = helper(3)",
                "print(result)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr
    out_text = (tmp_path / "xcomment_dup_repro_p.f90").read_text(encoding="utf-8")
    # `helper`'s own comments belong inside its module procedure body only --
    # they must not also leak into the top-level program body (a bug where
    # generate_flat's comment_map filtering didn't know about local_funcs'
    # line ranges once they were pulled out of the top-level tree).
    assert out_text.count("! step one") == 1
    assert out_text.count("! step two") == 1
    assert out_text.count("! top level marker comment") == 1


_PANDAS_TEST_CSV_ROWS = [
    "Date,SPY,EFA",
    "2007-12-19,103.6241,44.6112",
    "2007-12-20,104.2776,44.9292",
    "2007-12-21,105.5,45.1",
]


def test_xp2f_pandas_read_csv_len_matches_python(tmp_path: Path) -> None:
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    src = tmp_path / "xpandas_read_csv_len.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "dat = pd.read_csv('prices.csv')",
                "print(len(dat))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_column_membership_check(tmp_path: Path) -> None:
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    src = tmp_path / "xpandas_column_membership.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "dat = pd.read_csv('prices.csv')",
                "if 'Date' not in dat.columns:",
                "    print('no date column')",
                "else:",
                "    print('has date column')",
                "if 'SPY' not in dat.columns:",
                "    print('no SPY column')",
                "else:",
                "    print('has SPY column')",
                "if 'ZZZ' not in dat.columns:",
                "    print('no ZZZ column')",
                "else:",
                "    print('has ZZZ column')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_value_column_access(tmp_path: Path) -> None:
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    src = tmp_path / "xpandas_value_column.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "dat = pd.read_csv('prices.csv')",
                "spy = dat['SPY']",
                "print(len(spy))",
                "print(spy[0])",
                "print(spy[2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_timestamp_construction_and_comparison(tmp_path: Path) -> None:
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    src = tmp_path / "xpandas_timestamp.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "date_min = pd.Timestamp('2010-01-01')",
                "date_max = pd.Timestamp('2024-12-31')",
                "print(date_min <= date_max)",
                "print(date_max <= date_min)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_series_bare_assignment_aliases_and_mutates(tmp_path: Path) -> None:
    # Regression test: `ser_cp = ser` (bare Name-to-Name) must alias ser_cp
    # to ser's own Fortran variable at transpile time, matching Python's
    # object-aliasing semantics -- so a later `ser_cp *= 10` mutates ser
    # too. Previously ser_cp got its own separate copy, so the mutation
    # was invisible via ser (silently wrong, no compile error).
    src = tmp_path / "xseries_bare_alias.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "ser = pd.Series([4.0, 9.0, 16.0])",
                "print(ser[0], ser[1], ser[2])",
                "ser_cp = ser",
                "ser_cp *= 10",
                "print(ser[0], ser[1], ser[2])",
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
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_series_cumsum_method_call_survives_later_bare_alias(tmp_path: Path) -> None:
    # Regression test: the `.cumsum()` method-call form on a pd.Series(...)
    # must keep resolving to cumsum_real even when the same variable is
    # later bare-aliased and mutated in place (`ser_cp = ser; ser_cp *= 10`).
    # A prior fix for that alias mutation exposed a latent bug where
    # _mark_int (called by the generic AugAssign prescan handler on the
    # alias target) could downgrade the alias's already-known allocatable
    # real array to scalar int, making cumsum_int get selected instead.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xseries_cumsum_alias.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "rng = np.random.default_rng(12345)",
                "ser = pd.Series(rng.normal(size=5))",
                "print(ser.cumsum())",
                "ser_cp = ser",
                "ser_cp *= 10",
                "print(ser)",
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
    out_f90 = tmp_path / "xseries_cumsum_alias_p.f90"
    assert out_f90.exists()
    out_text = out_f90.read_text(encoding="utf-8")
    assert "cumsum_real(" in out_text
    assert "cumsum_int(" not in out_text


def test_xp2f_pandas_dataframe_bare_alias_mutates_original(tmp_path: Path) -> None:
    # Regression test: `dfz = df` (bare Name-to-Name) is pure Python object
    # aliasing, so a column grown through dfz (dfz["z"] = ...) must be
    # visible through df too. Mirrors the pd.Series bare-alias tests above
    # (pandas_df_aliases / _resolve_pandas_df_alias).
    src = tmp_path / "xdf_bare_alias.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [4.0, 5.0, 6.0]})",
                "dfz = df",
                "dfz['z'] = df['x'] + df['y']",
                "col = df['z']",
                "print(col[0], col[1], col[2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_dataframe_copy_does_not_mutate_original(tmp_path: Path) -> None:
    # Contrast case for the alias test above: `dfz = df.copy()` must be an
    # independent object, so growing a column on dfz leaves df's column
    # count -- and, per the has_col regression below, its `"z" in
    # df.columns` membership check too -- unchanged.
    src = tmp_path / "xdf_copy_independent.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [4.0, 5.0, 6.0]})",
                "dfz = df.copy()",
                "dfz['z'] = df['x'] + df['y']",
                "print(df.shape[1], dfz.shape[1])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_has_col_membership_check_on_dict_constructed_df(tmp_path: Path) -> None:
    # Regression test: `"col" not in df.columns` compiles to `df%has_col(...)`
    # regardless of DataFrame kind, but has_col was only ever defined on
    # DataFrame_index_date (the pd.read_csv-derived kind) -- a
    # DataFrame_str_index (RangeIndex/dict-constructed, e.g. plain
    # pd.DataFrame({...})) failed to compile with "'has_col' is not a
    # member of the 'dataframe_str_index' structure". Now defined on
    # DataFrame_str_index and DataFrame_index_datetime too.
    src = tmp_path / "xdf_has_col_dict.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [4.0, 5.0, 6.0]})",
                "dfz = df.copy()",
                "dfz['z'] = df['x'] + df['y']",
                "if 'z' not in df.columns:",
                "    print('df has no z')",
                "else:",
                "    print('df has z')",
                "if 'z' not in dfz.columns:",
                "    print('dfz has no z')",
                "else:",
                "    print('dfz has z')",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_rangeidx_dict_df_column_growth_ordering(tmp_path: Path) -> None:
    # Regression test for the column-growth-ordering bug: df["new_col"] = expr
    # must genuinely append at runtime (append_col_str) rather than
    # pre-allocating %values to the column count the variable eventually
    # reaches by end of script, which previously corrupted earlier uses.
    src = tmp_path / "xdf_rangeidx_growth.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [4.0, 5.0, 6.0]})",
                "df['sum'] = df['x'] + df['y']",
                "df['ratio'] = df['x'] / df['y']",
                "s = df['sum']",
                "r = df['ratio']",
                "print(s[0], s[1], s[2])",
                "print(r[0], r[1], r[2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_dropna_rows_and_columns(tmp_path: Path) -> None:
    src = tmp_path / "xdf_dropna_shapes.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x1': [1.0, np.nan, 3.0], 'x2': [4.0, 5.0, np.nan]})",
                "d_rows = df.dropna()",
                "d_cols = df.dropna(axis=1)",
                "print(d_rows.shape[0], d_rows.shape[1])",
                "print(d_cols.shape[0], d_cols.shape[1])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_concat_ignore_index(tmp_path: Path) -> None:
    src = tmp_path / "xdf_concat.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df1 = pd.DataFrame({'x': [1.0, 2.0]})",
                "df2 = pd.DataFrame({'x': [3.0, 4.0]})",
                "both = pd.concat([df1, df2], ignore_index=True)",
                "x = both['x']",
                "print(x[0], x[1], x[2], x[3])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_rolling_mean(tmp_path: Path) -> None:
    src = tmp_path / "xdf_rolling.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0, 4.0, 5.0]})",
                "r = df.rolling(2).mean()",
                "x = r['x']",
                "print(x[1], x[2], x[3], x[4])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_iloc_fancy_negative_literal_columns(tmp_path: Path) -> None:
    # Regression test for the negative-integer-literal AST shape
    # (UnaryOp(USub, Constant(positive_int)), not a single negative
    # Constant) in .iloc[[...], [0, -1]] column-position extraction.
    src = tmp_path / "xdf_iloc_neg_cols.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [4.0, 5.0, 6.0], 'c': [7.0, 8.0, 9.0]})",
                "sub = df.iloc[[0, -1], [0, -1]]",
                "print(sub['a'].sum(), sub['c'].sum())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_series_from_fancy_row_selection_preserves_row_labels(tmp_path: Path) -> None:
    # Regression test: a Series extracted (col = df["name"]) from a
    # fancy-row-selected DataFrame (df.iloc[[...]] / df.loc[[...]]) is
    # just a plain array copy in the SELECTED row order, which no longer
    # lines up with the original 0-based row positions -- e.g. after
    # sub = df.iloc[[0, -1]], sub's rows keep pandas' original row labels
    # 0 and 2 (not renumbered to 0 and 1), so real pandas' sub["a"][2] is
    # the correct/only valid access, and sub["a"][1] raises KeyError.
    # Previously xp2f treated every integer subscript as a direct 0-based
    # position, silently returning the WRONG value for label 2 (and
    # crashing with an out-of-bounds array index for anything beyond the
    # frame's own length) -- fixed via pandas_series_reindexed_source /
    # pandas_df_reindexed_ids, resolving a literal integer subscript
    # through the source frame's row_pos() instead.
    src = tmp_path / "xdf_fancy_row_series_labels.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'c': [7.0, 8.0, 9.0]})",
                "sub = df.iloc[[0, -1]]",
                "a = sub['a']",
                "c = sub['c']",
                "print(a[0], a[2], c[0], c[2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_series_from_fancy_row_selection_rejects_dynamic_index(tmp_path: Path) -> None:
    # A runtime (non-literal) subscript on such a series can't be resolved
    # correctly at transpile time -- must raise a clear error rather than
    # silently compute against the wrong row (see the test above).
    src = tmp_path / "xdf_fancy_row_series_dynamic_index.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0]})",
                "sub = df.iloc[[0, -1]]",
                "a = sub['a']",
                "i = 0",
                "print(a[i])",
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
    assert "Transpile: FAIL" in proc.stdout
    assert "fancy-row-selected" in proc.stdout


def test_xp2f_pandas_dataframe_chained_iloc_fancy_display(tmp_path: Path) -> None:
    # Regression test for the gfortran limitation where a type-bound
    # subroutine call chained directly onto the result of another
    # type-bound function call ("leftmost part-ref in a data-ref cannot be
    # a function reference") is invalid Fortran -- fixed by materializing
    # into a block-scoped temp first (_pandas_df_materialize_decl/_assign).
    src = tmp_path / "xdf_chained_iloc_display.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0], 'b': [3.0, 4.0], 'c': [5.0, 6.0]})",
                "print(df.iloc[[0, 1], [0, 2]])",
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


def test_xp2f_pandas_list_abc_columns_kwarg(tmp_path: Path) -> None:
    # Regression test for the `list("abc")` Python idiom (split a string
    # into a list of its individual characters) used as a columns= kwarg.
    src = tmp_path / "xdf_list_abc_columns.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0], 'b': [2.0], 'c': [3.0]}, columns=list('abc'))",
                "a = df['a']",
                "b = df['b']",
                "c = df['c']",
                "print(a[0], b[0], c[0])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_loc_fancy_row_selection_by_label(tmp_path: Path) -> None:
    src = tmp_path / "xdf_loc_fancy_rows.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "mat = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])",
                "df = pd.DataFrame(mat, columns=['a', 'b'], index=['d', 'e', 'f'])",
                "sub = df.loc[['d', 'f']]",
                "print(sub['a'].sum(), sub['b'].sum())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_iloc_row_as_series(tmp_path: Path) -> None:
    # df.iloc[row, :] -- a single row as a Series (_pandas_df_iloc_row_series_spec).
    src = tmp_path / "xdf_iloc_row_series.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0], 'b': [3.0, 4.0]})",
                "row = df.iloc[0, :]",
                "print(row.sum())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_mean_reduction_to_labeled_series(tmp_path: Path) -> None:
    # df.mean()/.std() -- a plain real array (one value per df column) plus
    # a static label list for m["col"]-style reads (_pandas_df_reduction_series_spec).
    src = tmp_path / "xdf_mean_reduction_series.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0], 'y': [4.0, 5.0, 6.0]})",
                "m = df.mean()",
                "print(m['x'], m['y'])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_dataframe_construct_from_series(tmp_path: Path) -> None:
    # Regression test: pd.DataFrame(ser) for a rank-1 array/Series argument
    # -- a single-column frame with pandas' own default column label (the
    # stringified integer 0) and a RangeIndex matching ser's own length.
    # _pandas_matrix_df_construct_spec_rangeidx previously required rank 2
    # (a real matrix) unconditionally, so this raised "unsupported call".
    src = tmp_path / "xdf_construct_from_series.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "ser = pd.Series([4.0, 9.0, 16.0])",
                "df = pd.DataFrame(ser)",
                "print(df.shape[0], df.shape[1])",
                "s = df.sum()",
                "print(s.sum())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_dataframe_construct_from_index_and_columns_only(tmp_path: Path) -> None:
    # Regression test: pd.DataFrame(index=[...], columns=[...]) -- no
    # positional data argument at all -- previously raised "unsupported
    # call" (no construct-spec matched it). Now an all-NaN frame of the
    # given shape (_pandas_empty_df_construct_spec). Also exercises a
    # second, independent gap this exposed: _tree_uses_pandas_dict_dataframe
    # (which decides whether to `use dataframe_str_index_mod` and link
    # dataframe_str_index.f90 at all) required at least one positional
    # arg, so this construct compiled with the module/type entirely
    # undeclared ("used before it is defined") even once the construct
    # itself was supported.
    src = tmp_path / "xdf_construct_index_columns_only.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame(index=list('abc'), columns=list('tuvwx'))",
                "print(df.shape[0], df.shape[1])",
                "print(df.isna().sum().sum())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_dataframe_augassign_scalar_multiply(tmp_path: Path) -> None:
    # Regression test: `df *= 10` (target is a DataFrame, RHS an integer
    # literal) previously hand-built "{lhs} = {lhs} * {rhs}" directly in
    # visit_AugAssign without the real-scalar coercion that expr()'s own
    # DataFrame-arithmetic BinOp handling already does for e.g.
    # print(df * 10) -- the vendored DataFrame_str_index operator(*)
    # overload only accepts a real scalar, so gfortran rejected the bare
    # integer literal ("Unexpected derived-type entities in binary
    # intrinsic numeric operator '*'"). Also exercises df_cp = df (bare
    # alias) mutating the original df in place via *=, mirroring the
    # Series alias tests above.
    src = tmp_path / "xdf_augassign_mult.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0]})",
                "df_cp = df",
                "df_cp *= 10",
                "x = df['x']",
                "print(x[0], x[1], x[2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_series_alias_passed_as_minimize_args(tmp_path: Path) -> None:
    # Regression test: scipy.optimize.minimize(f, x0, args=(r,)) where `r`
    # is a bare Name-to-Name alias of a pd.Series (`r = vals`). xp2f
    # synthesizes a single-argument wrapper function that references `r`
    # directly and hoists it into a module-shared variable -- but `r`
    # being a true alias means xp2f's own pure-alias codegen never
    # assigns a separate value into `r` at all (every reference resolves
    # straight through to `vals`'s own storage), so the hoisted module
    # variable `r` stayed permanently unallocated, segfaulting at runtime.
    # Fixed by resolving a simple top-level Name-to-Name alias chain to
    # its root BEFORE synthesizing the wrapper, so it references `vals`
    # directly instead.
    src = tmp_path / "xminimize_series_alias.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "from scipy.optimize import minimize",
                "",
                "def neg_sum_sq(params, r):",
                "    mu = params[0]",
                "    return np.sum((r - mu) ** 2)",
                "",
                "vals = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])",
                "r = vals",
                "x0 = np.array([0.0])",
                "result = minimize(neg_sum_sq, x0, args=(r,))",
                "print(result.x[0])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable, str(XP2F_PATH), str(src),
            "--compile", "--run-diff", "--numeric-diff", "--numeric-diff-tol", "1e-5",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    # A loose numeric tolerance: xp2f's own BFGS bridge and scipy's BFGS
    # converge to slightly different floating-point values for the same
    # minimum (this test's whole point is that it no longer segfaults, not
    # bit-for-bit optimizer agreement) -- both should still land near the
    # true minimizer (mean of vals = 3.0).
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run numeric diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_print_trailing_dataframe_arg(tmp_path: Path) -> None:
    # Regression test: print("label:", df) -- a DataFrame reference as the
    # LAST of several print() arguments (the pre-existing DataFrame print
    # special-casing only covered print(df) alone). Fortran can't print a
    # derived type with allocatable components inline via `print *, ...,
    # df` ("Data transfer element ... cannot have ALLOCATABLE components
    # unless it is processed by a defined input/output procedure") -- now
    # the leading args are printed first, then the DataFrame via its own
    # %display().
    src = tmp_path / "xdf_print_trailing.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'x': [1.0, 2.0, 3.0]})",
                "print('df =', df)",
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


def test_xp2f_ternary_char_result_padding_survives_max_zero_len_cleanup(tmp_path: Path) -> None:
    # Regression test: Fortran's MERGE requires both character operands of
    # an IfExp to share the exact same length, so each branch is padded
    # with `// repeat(' ', max(0, len(other) - len(self)))`. A separate
    # text-level cleanup pass (simplify_max_zero_len) strips a genuinely
    # no-op `max(0, len(...))` down to bare `len(...)` -- but its bare-call
    # detection used to be a naive "starts with len( and ends with )" regex,
    # which also matched (and wrongly stripped the clamp from) the
    # subtraction `len(a) - len(b)`, reintroducing "Argument NCOPIES of
    # REPEAT intrinsic is negative" whenever the "none" branch was longer
    # than the actual runtime string.
    src = tmp_path / "xternary_char_padding.py"
    src.write_text(
        "\n".join(
            [
                "date_min = ''",
                "print('none' if date_min == '' else str(date_min))",
                "date_min2 = '2020-01-15'",
                "print('none' if date_min2 == '' else str(date_min2))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_extend_inline_list_literal_after_count_mapped_growth(tmp_path: Path) -> None:
    # Regression test: extend() with an inline list-literal argument (after
    # count-mapped growth via append()) previously repeatedly subscripted
    # the raw argument text, invalid Fortran when the argument is itself an
    # array-constructor literal like [10, 20, 30] (constructors can't be
    # directly indexed) -- fixed by materializing it into a real temp array.
    src = tmp_path / "xextend_inline_literal.py"
    src.write_text(
        "\n".join(
            [
                "nums = []",
                "for i in range(3):",
                "    nums.append(i)",
                "nums.extend([10, 20, 30])",
                "print(nums)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


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
    # `y` is a real literal that's never reassigned, so xp2f's
    # constant-promotion pass turns it into a named PARAMETER.
    assert "real(kind=dp), parameter :: y = 4.0_dp" in out_text


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


def test_xp2f_lowers_legacy_np_nan_call_as_constant(tmp_path: Path) -> None:
    src = tmp_path / "xnp_nan_call.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "x = np.nan()",
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
    assert "Build: PASS" in proc.stdout
    out_text = (tmp_path / "xnp_nan_call_p.f90").read_text(encoding="utf-8")
    assert "ieee_value(0.0_dp, ieee_quiet_nan)" in out_text


def test_xp2f_runs_np_append_axis0_rank2_rows(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xappend_axis0_rank2.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "x = np.empty((0, 2), dtype=int)",
                "x = np.append(x, [[1, 2]], axis=0)",
                "x = np.append(x, [[3, 4], [5, 6]], axis=0)",
                "print(x)",
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
    out_text = (tmp_path / "xappend_axis0_rank2_p.f90").read_text(encoding="utf-8")
    assert "xp2f_append_tmp_" in out_text


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


def test_xp2f_does_not_emit_unused_global_presence_flags(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xsum_small.py"
    src.write_text(
        "\n".join(
            [
                "ysum = 0.0",
                "for i in range(10):",
                "    ysum = ysum + i",
                "print(ysum)",
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
    out_text = (tmp_path / "xsum_small_p.f90").read_text(encoding="utf-8")
    assert "xp2f_has_global_ysum" not in out_text


def test_xp2f_initializes_top_level_globals_membership_flags(tmp_path: Path) -> None:
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xglobals_membership_small.py"
    src.write_text(
        "\n".join(
            [
                "if 'x' in globals():",
                "    print(1)",
                "else:",
                "    print(0)",
                "x = 2",
                "if 'x' in globals():",
                "    print(x)",
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
    out_text = (tmp_path / "xglobals_membership_small_p.f90").read_text(encoding="utf-8")
    assert "xp2f_has_global_x = .false." in out_text


def test_xp2f_declares_reserved_word_for_loop_variable(tmp_path: Path) -> None:
    # "dim" is a Fortran intrinsic; the for-loop header, the loop body, and
    # the declaration list must all agree on the aliased name ("xdim") or
    # the variable ends up used but never declared.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xreserved_loop_var_small.py"
    src.write_text(
        "\n".join(
            [
                "def f(dim_num):",
                "    total = 0",
                "    for dim in range(0, dim_num):",
                "        total = total + dim",
                "    return total",
                "",
                "print(f(5))",
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


def test_xp2f_avoids_intrinsic_name_collision_for_local_variables(tmp_path: Path) -> None:
    # "index" and "shape" are Fortran intrinsics but extremely common
    # variable names in numerical Python; both must be usable as plain
    # local scalars/arrays without colliding with the intrinsic.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xreserved_var_names_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(a, target):",
                "    index = 0",
                "    for i in range(len(a)):",
                "        if a[i] == target:",
                "            index = i",
                "    shape = a.shape",
                "    return index + shape[0]",
                "",
                "a = np.array([3, 1, 4, 1, 5])",
                "print(f(a, 4))",
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


def test_xp2f_handles_self_referential_np_sort(tmp_path: Path) -> None:
    # x = np.sort(x): x is already allocated at the right size, so
    # deallocating it before sizing the new allocation from size(x) would
    # reference an already-deallocated array.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    shutil.copy2(REPO_ROOT / "lapack_d.f90", tmp_path / "lapack_d.f90")
    src = tmp_path / "xself_sort_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x):",
                "    x = np.sort(x)",
                "    return x",
                "",
                "a = np.array([3.0, 1.0, 4.0, 1.0, 5.0])",
                "print(f(a))",
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


def test_xp2f_flips_result_of_nested_numpy_call(tmp_path: Path) -> None:
    # np.flipud(np.transpose(x)): the argument isn't a simple name or
    # slice, so it must be materialized into a temporary before being
    # reversed -- chaining a reversed section directly onto the
    # transpose() call result (transpose(x)(size(...):1:-1, :)) isn't
    # valid Fortran.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xflip_nested_small.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(x):",
                "    y = np.flipud(np.transpose(x))",
                "    return y",
                "",
                "x = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])",
                "print(f(x))",
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


def test_xp2f_pandas_df_shift_and_arithmetic_on_date_indexed_frame(tmp_path: Path) -> None:
    # Regression test bundling three related fixes surfaced together by a
    # trend-following strategy script (weights.shift(1) * asset_rets on a
    # date-indexed DataFrame):
    #   1. df.shift()/.pct_change()/.cumsum()/.cumprod()/.diff()/.abs() are
    #      pure functions on the vendored DataFrame types, but were only
    #      ever reachable as a standalone `X = df.shift(n)` statement or
    #      directly inside print() -- not as a general expression (e.g.
    #      nested inside DataFrame arithmetic). See
    #      _pandas_df_simple_method_expr_text.
    #   2. DataFrame arithmetic (scalar and DataFrame-DataFrame) was wired
    #      up only for DataFrame_str_index, even though DataFrame_index_date
    #      (the pd.read_csv-derived kind) has an equivalent, richer
    #      operator(+/-/*//) set already in dataframe_index_date.f90.
    #   3. Once DataFrame_index_date arithmetic became reachable, its own
    #      `use dataframe_index_date_mod, only: ...` line turned out to
    #      never import operator(+/-/*//) at all (only the comparison
    #      operators) -- gfortran rejected `dat%shift(1) + dat` with
    #      "Unexpected derived-type entities in binary intrinsic numeric
    #      operator '+'" even though the module-level overload exists.
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    src = tmp_path / "xdf_shift_arith.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "dat = pd.read_csv('prices.csv', index_col='Date')",
                "combined = dat.shift(1) + dat",
                "spy = combined['SPY']",
                "print(spy[1], spy[2])",
                "scaled = dat * 2.0",
                "spy2 = scaled['SPY']",
                "print(spy2[0], spy2[1], spy2[2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Compared by hand below (Python and Fortran stdout captured
    # separately), not via --run-diff: an integer subscript on a
    # date-indexed Series (spy[1], not spy.iloc[1]) triggers pandas' own
    # "Series.__getitem__ treating keys as positions is deprecated"
    # FutureWarning, and xp2f's own --run-diff captures the reference
    # Python run's stdout+stderr together for comparison, so the warning
    # text (an extra line, and -- with --numeric-diff -- spurious numeric
    # tokens from the pytest tmp_path in its traceback) perturbs the
    # comparison. Reads spy[1]/spy[2], skipping the NaN-producing warm-up
    # row (spy[0], from shift(1)).
    py_proc = subprocess.run(
        [sys.executable, str(src)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert py_proc.returncode == 0, py_proc.stdout + py_proc.stderr
    py_values = [float(x) for x in py_proc.stdout.split()]

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    ft_values = [float(x) for x in proc.stdout.rsplit("Run: PASS", 1)[1].split()]

    assert len(py_values) == 5, py_values
    assert len(ft_values) == 5, ft_values
    for py_v, ft_v in zip(py_values, ft_values):
        assert abs(py_v - ft_v) < 1.0e-6, (py_values, ft_values)


def test_xp2f_pandas_df_column_selection_via_resolved_name_list(tmp_path: Path) -> None:
    # Regression test: df[names] where `names` is a variable already
    # resolved to a static list of strings (most notably `names = [c for
    # c in dat.columns if c != "Date"]`, see the df.columns-list-
    # comprehension prescan branch / pandas_str_list_values) -- previously
    # only a LITERAL list (df[["colA", "colB"]]) was recognized as
    # multi-column selection; a Name reference fell through to being
    # treated as a plain (non-DataFrame) array, silently losing all
    # DataFrame-ness for everything derived from it.
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    src = tmp_path / "xdf_select_via_name_list.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "dat = pd.read_csv('prices.csv', index_col='Date')",
                "names = [c for c in dat.columns if c != 'Date']",
                "sub = dat[names]",
                "print(sub['SPY'].sum(), sub['EFA'].sum())",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_numpy_ones_full_shape_and_fill_value_kwargs(tmp_path: Path) -> None:
    # Regression test: np.ones(shape=[...])/np.full(shape=[...],
    # fill_value=...) -- shape (and full's fill value) passed as a
    # keyword rather than positionally. Every consumer of these calls
    # (expr()'s codegen, _rank_expr, _expr_kind, prescan's own shape
    # inference) only ever looked at node.args[0]/node.args[1], even
    # though real numpy accepts either calling convention -- fixed by
    # normalize_numpy_shape_kwarg_calls, an AST pass that rewrites the
    # keyword form into the equivalent positional-args call up front.
    # Also exercises the column count of np.ones(shape=[nrow, ncol])
    # resolving through a top-level int constant (ncol = 4), not just a
    # literal int inline -- see _ncols_from_shape_call.
    src = tmp_path / "xnp_shape_kwarg.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "nrow = 3",
                "ncol = 4",
                "x = np.ones(shape=[nrow, ncol])",
                "y = np.full(shape=[nrow, ncol], fill_value=7.0)",
                "print(x[0, 0], x[2, 3])",
                "print(y[0, 0], y[1, 2])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_sum_axis1_reduces_rows_not_columns(tmp_path: Path) -> None:
    # Regression test: print(df.sum(axis=1)) silently computed COLUMN
    # sums (axis=0, the default) instead of ROW sums -- the print
    # dispatcher matched on len(args) == 0 alone, ignoring an axis=
    # keyword entirely, so _emit_pandas_df_series_reduction_print always
    # ran its hardcoded one-value-per-column loop regardless of what was
    # actually requested. Fixed by threading an axis argument through and
    # adding a genuine row-wise (reduce across columns, one value per
    # row, printed against df's own row labels) code path for axis=1.
    # Distinct per-row/per-column values (not e.g. all-ones) so a wrong
    # axis would be caught, not accidentally masked by symmetry.
    src = tmp_path / "xdf_sum_axis1.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [10.0, 20.0, 30.0], 'c': [100.0, 200.0, 300.0]})",
                "print(df.sum(axis=1))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff", "--numeric-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run numeric diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_prod_axis0_and_axis1(tmp_path: Path) -> None:
    # Regression test: df.prod(axis=0)/.prod(axis=1) -- .prod() wasn't
    # in the DataFrame reduction method set at all (only mean/median/std/
    # min/max/sum), so print(df.prod(...)) fell through to a completely
    # different, generic "call product() on some array-like base"
    # handler that just emitted `product(df, dim=...)` -- invalid
    # Fortran, since df is a derived type, not a numeric array. Added
    # "prod" alongside the other reduction methods, in both the
    # column-wise (axis=0, default) and row-wise (axis=1) code paths.
    src = tmp_path / "xdf_prod.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [2.0, 2.0, 2.0], 'c': [1.0, 5.0, 1.0]})",
                "print(df.prod(axis=0))",
                "print(df.prod(axis=1))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff", "--numeric-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run numeric diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_var_ddof1_axis0_and_axis1(tmp_path: Path) -> None:
    # Regression test: df.var()/.var(axis=0)/.var(axis=1) -- "var" wasn't
    # in the DataFrame reduction method set either, and df.var(axis=...)
    # specifically fell through to a different, generic .var(axis=...)
    # handler (shared with plain numpy arrays) that explicitly raises
    # "var(..., axis=...) not yet supported" for ANY axis= argument,
    # DataFrame or not. Uses ddof=1 (var_1d(expr, 1)) to match pandas'
    # own default (sample variance) -- unlike numpy's np.var() default of
    # ddof=0, which is why the generic handler needs an explicit ddof= to
    # get this same value; a bare df.var() always means ddof=1. Verified
    # with fixed (non-random) data so the exact ddof=1 formula, not just
    # "some" variance, is checked.
    src = tmp_path / "xdf_var.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0, 4.0], 'b': [10.0, 20.0, 30.0, 45.0]})",
                "print(df.var())",
                "print(df.var(axis=0))",
                "print(df.var(axis=1))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff", "--numeric-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run numeric diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_shift_on_rangeidx_frame_and_axis1(tmp_path: Path) -> None:
    # Regression test: df.shift(n) on a DataFrame_str_index (RangeIndex/
    # dict-constructed) frame -- shift/pct_change were type-bound
    # procedures on DataFrame_index_date only (dataframe_index_date.f90),
    # never ported to dataframe_str_index.f90, so gfortran rejected
    # `df%shift(1)` as "'shift' is not a member of the 'dataframe_str_index'
    # structure". Ported shift_str/pct_change_str, and along the way added
    # genuine axis=1 support (shift across columns, not rows) to both
    # DataFrame kinds -- previously axis= was silently ignored entirely
    # (any axis value behaved like axis=0), which this also checks
    # (including a negative-periods axis=1 shift) with non-uniform,
    # per-row/per-column-distinct data so a wrong axis or sign would be
    # caught, not accidentally masked by symmetry.
    # Column extraction + specific (non-NaN) positions, not print(df) of
    # the whole shifted frame -- a full-frame print's "[N rows x M
    # columns]" footer and header-name line don't tokenize consistently
    # between run-diff/numeric-diff's python-side and fortran-side
    # captures (an unrelated harness quirk, not a real output mismatch;
    # established by other DataFrame print tests in this file).
    src = tmp_path / "xdf_shift_rangeidx.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0, 4.0], 'b': [10.0, 20.0, 30.0, 45.0], 'c': [100.0, 200.0, 300.0, 450.0]})",
                "s1 = df.shift(1)",
                "a1 = s1['a']",
                "print(a1[1], a1[2], a1[3])",
                "s2 = df.shift(1, axis=1)",
                "b2 = s2['b']",
                "c2 = s2['c']",
                "print(b2[0], b2[1], c2[0], c2[1])",
                "s3 = df.shift(-1, axis=1)",
                "a3 = s3['a']",
                "b3 = s3['b']",
                "print(a3[0], a3[1], b3[0], b3[1])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_divide_fillna_row_reduction_and_iloc_slice(tmp_path: Path) -> None:
    # Regression test for the trend-following-strategy chain in
    # examples/xtrend_ma.py: `weights = signal.divide(n_active,
    # axis=0).fillna(0.0)` where n_active = (signal != 0.0).sum(axis=1)
    # (a per-row count, ASSIGNED not printed -- see
    # _pandas_df_row_reduction_spec), followed by `(weights.shift(1) *
    # rets).sum(axis=1)` (same row-reduction spec, but with a BinOp
    # DataFrame-arithmetic expression as the base rather than a bare
    # Name or a Compare) and finally `port_ret.iloc[n:]` (a slice of a
    # plain rank-1 array, not a DataFrame or pandas date-array -- see
    # _plain_array_iloc_slice_spec).
    #
    # This combination surfaced three separate bugs, all fixed together:
    # 1. _rank_expr/_expr_kind had no idea `X.sum(axis=1)` on a
    #    DataFrame-shaped base (a Compare or DataFrame-arithmetic BinOp,
    #    neither tracked via alloc_reals/etc since DataFrames use a
    #    separate tracking mechanism entirely) is itself a real, rank-1
    #    value -- the generic reduction-rank/-kind fallback (meant for
    #    ordinary numpy arrays) computed the wrong answer (rank 0,
    #    kind 'logical') by recursing into the base's own wrong rank/kind,
    #    which silently corrupted a *later* statement's type stability
    #    check into scheduling a bogus type-rebind for n_active partway
    #    through the script.
    # 2. `signal.divide(n_active, axis=0)` with n_active containing a
    #    genuine 0 (no active positions that day, so the corresponding
    #    signal row is entirely 0.0 too) computed a literal 0.0/0.0
    #    division, tripping -ffpe-trap=invalid/zero (SIGFPE) before the
    #    .fillna(0.0) chained after it ever ran -- fixed by guarding the
    #    divisor to 1 (giving the same 0.0 result) whenever it's 0.
    # 3. `.sum(axis=1)` on a row with some (but not all) NaN entries (the
    #    very first row here, from .shift(1)/.pct_change() both having no
    #    antecedent value) used a plain, non-NaN-skipping `sum()`,
    #    whereas pandas' default is skipna=True (an all-NaN row sums to
    #    0.0, not NaN) -- fixed by using the nan*-prefixed helpers for
    #    this specific (assigned, axis=1) row-reduction codegen.
    src = tmp_path / "xdf_divide_fillna_chain.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df1 = pd.DataFrame({'a': [1.0, 5.0, 3.0], 'b': [2.0, 2.0, 6.0]})",
                "df2 = pd.DataFrame({'a': [2.0, 2.0, 2.0], 'b': [2.0, 2.0, 2.0]})",
                "above = df1 > df2",
                "signal = above.astype(float)",
                "n_active = (signal != 0.0).sum(axis=1)",
                "weights = signal.divide(n_active, axis=0).fillna(0.0)",
                "rets = df1.pct_change()",
                "port_ret = (weights.shift(1) * rets).sum(axis=1)",
                "trimmed = port_ret.iloc[1:]",
                "print(port_ret[0], port_ret[1], port_ret[2])",
                "print(trimmed.iloc[0], trimmed.iloc[1])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def _run_xp2f_compile_diff(tmp_path: Path, filename: str, lines: list) -> None:
    # Shared helper for the DataFrame-stats regression tests below: write
    # `lines` as a script, transpile+compile+run it, and assert its
    # output matches real Python's exactly.
    src = tmp_path / filename
    src.write_text("\n".join(lines + [""]), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_df_cummax_cummin(tmp_path: Path) -> None:
    # Regression test: df.cummax()/df.cummin() -- new DataFrame_str_index/
    # DataFrame_index_date type-bound procedures (cummax_str/cummin_str
    # and cummax/cummin respectively), mirroring the pre-existing cumsum/
    # cumprod.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_cummax.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 5.0, 3.0, 8.0, 2.0], 'b': [9.0, 2.0, 6.0, 1.0, 4.0]})",
            "cmax = df.cummax()",
            "cmin = df.cummin()",
            "cmax_a = cmax['a']",
            "cmax_b = cmax['b']",
            "cmin_a = cmin['a']",
            "cmin_b = cmin['b']",
            "print(cmax_a[0], cmax_a[4], cmax_b[2])",
            "print(cmin_a[0], cmin_a[4], cmin_b[2])",
        ],
    )


def test_xp2f_pandas_df_cov(tmp_path: Path) -> None:
    # Regression test: df.cov() -- new print codegen (mirroring the
    # pre-existing df.corr(), swapping corrcoef_matrix_rows_real for the
    # cov_matrix_rows_real helper that already existed but was unused by
    # any DataFrame method), including the round(df.cov(), n) form.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_cov.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 5.0, 3.0, 8.0, 2.0], 'b': [9.0, 2.0, 6.0, 1.0, 4.0], "
            "'c': [1.0, 1.0, 2.0, 2.0, 3.0]})",
            "print(df.cov())",
            "print(df.cov().round(3))",
        ],
    )


def test_xp2f_pandas_df_sem_skew_kurt(tmp_path: Path) -> None:
    # Regression test: df.sem()/df.skew()/df.kurt() -- sem is std/sqrt(n)
    # (no new Fortran helper); skew/kurt are new skew_1d/kurt_1d helpers
    # implementing pandas' adjusted (bias-corrected) Fisher-Pearson
    # formulas, verified against real pandas' own output (not
    # independently re-derived).
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_semskewkurt.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 5.0, 3.0, 8.0, 2.0, 9.0, 4.0], "
            "'b': [9.0, 2.0, 6.0, 1.0, 4.0, 3.0, 7.0]})",
            "print(df.sem())",
            "print(df.skew())",
            "print(df.kurt())",
        ],
    )


def test_xp2f_pandas_df_idxmax_idxmin(tmp_path: Path) -> None:
    # Regression test: df.idxmax()/df.idxmin() -- new print-only codegen
    # (_emit_pandas_df_idxreduce_print), using maxloc/minloc for the row
    # position and printing the row's index LABEL, not the value. Checks
    # both the RangeIndex-default case (pandas reports dtype: int64 for
    # the result, not object, since the "labels" are row positions --
    # see pandas_rangeidx_df_ids) exercised here.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_idxmax.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 5.0, 3.0, 8.0, 2.0], 'b': [9.0, 2.0, 6.0, 1.0, 4.0]})",
            "print(df.idxmax())",
            "print(df.idxmin())",
        ],
    )


def test_xp2f_series_autocorr(tmp_path: Path) -> None:
    # Regression test: Series.autocorr()/.autocorr(lag=k) -- new
    # autocorr_1d Fortran helper (lag-k serial correlation via the
    # existing corrcoef2_real, wrapped since its 2x2-matrix result can't
    # be subscripted inline in the same expression as the call).
    _run_xp2f_compile_diff(
        tmp_path,
        "xautocorr.py",
        [
            "import pandas as pd",
            "",
            "s = pd.Series([1.0, 2.5, 2.0, 3.5, 3.0, 4.5, 4.0, 5.5])",
            "print(s.autocorr())",
            "print(s.autocorr(lag=2))",
        ],
    )


def test_xp2f_pandas_df_corrwith(tmp_path: Path) -> None:
    # Regression test: df.corrwith(other) -- new print codegen
    # (_emit_pandas_df_corrwith_print), one Pearson correlation per
    # column of df against a plain rank-1 `other` array, via the new
    # corr2_1d helper (also shared by autocorr_1d after a refactor).
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_corrwith.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 5.0, 3.0, 8.0, 2.0], 'b': [9.0, 2.0, 6.0, 1.0, 4.0], "
            "'c': [2.0, 4.0, 5.0, 9.0, 1.0]})",
            "other = pd.Series([2.0, 4.0, 3.0, 7.0, 1.0])",
            "print(df.corrwith(other))",
        ],
    )


def test_xp2f_pandas_df_expanding(tmp_path: Path) -> None:
    # Regression test: df.expanding().mean()/.std() -- new
    # expanding_mean_1d/expanding_std_1d Fortran helpers (Welford's
    # online update with no fixed trailing window, unlike the pre-
    # existing rolling_mean_1d/rolling_std_1d) -- checks both the
    # min_periods=1 mean (a value from row 1 on) and the std (NaN for
    # row 1 alone, a value from row 2 on).
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_expanding.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 3.0, 2.0, 5.0, 4.0], 'b': [10.0, 8.0, 12.0, 9.0, 11.0]})",
            "em = df.expanding().mean()",
            "es = df.expanding().std()",
            "em_a = em['a']",
            "em_b = em['b']",
            "es_a = es['a']",
            "es_b = es['b']",
            "print(em_a[0], em_a[2], em_a[4], em_b[1], em_b[3])",
            "print(es_a[0], es_a[2], es_a[4], es_b[1], es_b[3])",
        ],
    )


def test_xp2f_pandas_df_ewm(tmp_path: Path) -> None:
    # Regression test: df.ewm(span=...).mean()/.std() and
    # df.ewm(alpha=...).mean() -- new ewm_mean_1d/ewm_std_1d Fortran
    # helpers (adjust=True, bias=False, both pandas' defaults). The std
    # formula (a Bessel-corrected exponentially weighted sample
    # variance) was verified by direct numeric comparison against
    # pandas' own ewm(...).std() output during development, not
    # independently re-derived -- see ewm_std_1d's docstring.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_ewm.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 3.0, 2.0, 5.0, 4.0, 6.0], "
            "'b': [10.0, 8.0, 12.0, 9.0, 11.0, 7.0]})",
            "em = df.ewm(span=3).mean()",
            "es = df.ewm(span=3).std()",
            "ea = df.ewm(alpha=0.3).mean()",
            "em_a = em['a']",
            "em_b = em['b']",
            "es_a = es['a']",
            "es_b = es['b']",
            "ea_a = ea['a']",
            "print(em_a[0], em_a[2], em_a[5], em_b[1], em_b[4])",
            "print(es_a[0], es_a[1], es_a[3], es_b[2], es_b[5])",
            "print(ea_a[0], ea_a[2], ea_a[5])",
        ],
    )


def test_xp2f_pandas_df_astype_binop_and_nan_safe_compare(tmp_path: Path) -> None:
    # Regression test for examples/xtrend_ma.py's trend-signal
    # construction: `signal = above.astype(float) - below.astype(float)`
    # (a BinOp of two .astype(float) calls, neither a bare df Name) was
    # NEVER recognized as producing a DataFrame at all -- prescan's own
    # "X = df1 op df2" registration branch and _is_pandas_df_arith_value
    # (used by expr()'s BinOp codegen too) both only recognized a bare
    # Name operand, not a chained call -- so `signal` silently fell
    # through to a completely unrelated generic (non-DataFrame) codegen
    # path, producing wrong/invalid Fortran with no error at transpile
    # time (only surfaced once printed). Fixed by teaching
    # _is_pandas_df_arith_value/_pandas_df_arith_kind_cols to recognize
    # _pandas_df_astype_spec the same way they already did for
    # .shift()/.cumsum()/etc, and generalizing both the prescan and
    # codegen "X = df1 op df2" branches to use them instead of a bare-
    # Name-only check.
    #
    # Also exercises the DataFrame comparison (`prices > ma`) that feeds
    # this: ma = prices.rolling(n).mean() is NaN for the window's warm-up
    # rows, and comparing against NaN used to trip -ffpe-trap=invalid
    # (Fortran's ordered comparisons all signal on NaN, unlike pandas
    # where a NaN comparison quietly evaluates to False) -- now guarded.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_astype_binop_signal.py",
        [
            "import pandas as pd",
            "",
            "prices = pd.DataFrame({'a': [10.0, 11.0, 9.0, 12.0, 13.0], "
            "'b': [5.0, 4.0, 6.0, 5.5, 5.2]})",
            "ma = prices.rolling(2).mean()",
            "above = prices > ma",
            "below = prices < ma",
            "signal = above.astype(float) - below.astype(float)",
            "sig_a = signal['a']",
            "sig_b = signal['b']",
            "print(sig_a[0], sig_a[1], sig_a[2], sig_a[3], sig_a[4])",
            "print(sig_b[0], sig_b[1], sig_b[2], sig_b[3], sig_b[4])",
        ],
    )


def test_xp2f_dynamic_column_series_shift_and_nan_safe_generic_compare(tmp_path: Path) -> None:
    # Regression test for examples/xtrend_ma.py's per-asset loop:
    #   for name in asset_names:
    #       sig = signal[name].iloc[n:]
    #       ret = asset_rets[name].shift(-1).iloc[n:]
    #       active = sig != 0.0
    #       correct = ((sig > 0.0) & (ret > 0.0)) | ((sig < 0.0) & (ret < 0.0))
    #       pct_long = (sig[active] > 0.0).mean()
    # Three separate new/fixed pieces, all exercised together:
    # 1. df[name] -- a single column selected by a RUNTIME character-
    #    scalar expression (a `for name in ...:` loop variable), not a
    #    literal string -- new Subscript branch in expr()'s dispatch.
    # 2. Series.shift(periods) (as opposed to DataFrame.shift(), a type-
    #    bound procedure) on a plain rank-1 array -- new shift_1d helper,
    #    and _plain_series_expr_text/_plain_array_iloc_slice_spec
    #    generalized to chain .iloc[lo:hi] onto either of the above.
    # 3. `ret > 0.0` where ret's last element is NaN (from .shift(-1)
    #    having no value to shift in) previously tripped
    #    -ffpe-trap=invalid the same way DataFrame comparisons did --
    #    the GENERIC (non-DataFrame) comparison codegen needed the same
    #    NaN guard.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdyncol_shift_compare.py",
        [
            "import pandas as pd",
            "",
            "signal = pd.DataFrame({'a': [1.0, -1.0, 0.0, 1.0, -1.0], "
            "'b': [0.0, 1.0, -1.0, 1.0, 0.0]})",
            "rets = pd.DataFrame({'a': [0.01, -0.02, 0.03, -0.01, 0.02], "
            "'b': [-0.01, 0.02, 0.01, -0.03, 0.01]})",
            "names = ['a', 'b']",
            "n = 1",
            "for name in names:",
            "    sig = signal[name].iloc[n:]",
            "    ret = rets[name].shift(-1).iloc[n:]",
            "    active = sig != 0.0",
            "    correct = ((sig > 0.0) & (ret > 0.0)) | ((sig < 0.0) & (ret < 0.0))",
            "    pct_long = (sig[active] > 0.0).mean()",
            "    hit = correct[active].mean()",
            "    print(name, pct_long, hit)",
        ],
    )


def test_xp2f_pandas_date_iloc_runtime_index(tmp_path: Path) -> None:
    # Regression test: dates.iloc[n] where n is a variable (not a
    # literal) -- _pandas_date_scalar_expr only handled a literal
    # (possibly negative) integer index; extended to also emit a general
    # runtime (assumed non-negative) index expression.
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdate_iloc_runtime.py",
        [
            "import pandas as pd",
            "",
            "n = 2",
            "dat = pd.read_csv('prices.csv')",
            "dates = pd.to_datetime(dat['Date'], errors='coerce')",
            "print(str(dates.iloc[n].date()))",
            "print(str(dates.iloc[0].date()))",
            "print(str(dates.iloc[-1].date()))",
        ],
    )


def test_xp2f_pandas_df_single_column_to_numpy(tmp_path: Path) -> None:
    # Regression test: df["col"].to_numpy() -- a single column selected
    # by a literal string, then .to_numpy() -- raised "unsupported call"
    # entirely. Only two to_numpy() shapes were recognized (a whole
    # DataFrame, and a multi-column selection via a resolved name-list
    # variable); a single df["col"].to_numpy() is a pure passthrough
    # (self.expr() already resolves the subscript itself to a plain real
    # array), but needed its own rank/kind recognition in _rank_expr/
    # _expr_kind too -- the assigned variable was otherwise declared as a
    # rank-0 scalar (the prescan fallback's default for an unrecognized
    # Call shape), causing an "Incompatible ranks 0 and 1" compile error.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_single_col_to_numpy.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'x1': [1.5, -2.5, 3.5, -4.5, 5.5], "
            "'x2': [0.1, 0.2, 0.3, 0.4, 0.5]})",
            "x1 = df['x1'].to_numpy()",
            "print(x1[0], x1[2], x1[4])",
        ],
    )


def test_xp2f_pandas_df_multi_column_and_whole_df_to_numpy(tmp_path: Path) -> None:
    # Regression test: .to_numpy() should work on any expression that
    # resolves to a DataFrame -- not just the specific shapes previously
    # special-cased one at a time. Generalized by (1) extending
    # _pandas_df_match's "select_names" recognition (previously a df[[
    # "A","B"]] LITERAL list only) to use the already-general
    # _resolve_str_list_literal (also covers a resolved name-list
    # variable and list("abc")), and (2) routing .to_numpy() through
    # _is_pandas_df_ref_node/_pandas_df_ref -- the same general
    # DataFrame-reference recognition used elsewhere (corr()/cov()/
    # print(), etc.) -- instead of three separate ad hoc Call shapes.
    # Also exercises a genuinely new statement-level codegen branch:
    # _pandas_df_ref's resolved expression for a multi-column selection
    # is a type-bound-function-call result (df%icol([1,2])), and
    # gfortran rejects %values chained directly onto that ("leftmost
    # part-ref in a data-ref cannot be a function reference") -- fixed
    # by materializing it into a block-scoped temp first (see
    # _pandas_df_materialize_decl), the same pattern already used by
    # corr()/cov()/the reduction prints.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_multi_col_to_numpy.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'x1': [1.5, -2.5, 3.5, -4.5, 5.5], "
            "'x2': [0.1, 0.2, 0.3, 0.4, 0.5]})",
            "x = df[['x1', 'x2']].to_numpy()",
            "y = df.to_numpy()",
            "print(x[0, 0], x[4, 1])",
            "print(y[0, 0], y[4, 1])",
        ],
    )


def test_xp2f_numpy_std_var_axis_reduction(tmp_path: Path) -> None:
    # Regression test: np.std(x, axis=N, ddof=...) on a rank-2 array
    # previously silently ignored axis= entirely and always called the
    # scalar/1D std(x, ddof) helper, which gfortran rejects outright for
    # a rank>1 x ("Rank mismatch in argument 'x'... (rank-1 and rank-2)")
    # -- examples/xequicorr.py's `np.std(x, axis=0, ddof=1)`.
    # np.var(x, axis=N, ...) had the same gap but *silently computed the
    # wrong (flattened, scalar) result* instead of failing to build, since
    # its axis=None case already flattens via reshape() -- no rank
    # mismatch to catch it. Both now do a proper per-axis reduction (a
    # sum(x, dim=)-based mean, spread back and subtracted, mirroring how
    # np.mean(x, axis=...) already worked). Also exercises the
    # axis=None case for both (which, for std specifically, had its own
    # separate pre-existing rank-mismatch bug: std(x) never flattened x
    # first at all, unlike var's own axis=None case).
    _run_xp2f_compile_diff(
        tmp_path,
        "xnumpy_std_var_axis.py",
        [
            "import numpy as np",
            "",
            "x = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 9.0, 2.0], [2.0, 1.0, 8.0]])",
            "s0 = np.std(x, axis=0, ddof=1)",
            "s1 = np.std(x, axis=1)",
            "v0 = np.var(x, axis=0, ddof=1)",
            "v1 = np.var(x, axis=1)",
            "print(s0[0], s0[1], s0[2])",
            "print(s1[0], s1[1], s1[2], s1[3])",
            "print(v0[0], v0[1], v0[2])",
            "print(v1[0], v1[1], v1[2], v1[3])",
            "print(np.std(x))",
            "print(np.var(x, ddof=1))",
        ],
    )


def test_xp2f_rng_multivariate_normal_in_binop_and_local_function(tmp_path: Path) -> None:
    # Regression test: rng.multivariate_normal(...) used as part of a
    # larger expression (e.g. `rng.multivariate_normal(...) / 100.0`,
    # from examples/xequicorr_turnover.py) raised "unsupported call" --
    # every recognized shape required the call to be the WHOLE right-hand
    # side of an assignment (X = rng.multivariate_normal(...)), since its
    # codegen fills a preallocated array in place via a subroutine call
    # (random_mvn_samples), not a pure function usable inline. Fixed via
    # _is_mvn_call/_materialize_mvn_call, the same "materialize a nested
    # call into a real temp variable first" approach used elsewhere in
    # this file for other subroutine-backed calls.
    #
    # Also exercises this from inside a local function with `rng` passed
    # in as a parameter (not the top-level Name that created it) -- the
    # prescan branch for this had to be positioned *before* the generic
    # _rank_expr/_expr_kind-based fallback (which already infers the
    # right rank/kind for this shape via _rank_expr's own
    # multivariate_normal recognition and would otherwise `continue`
    # first, silently skipping the materialization a local-function-scope
    # temp variable needs a declaration for).
    #
    # Does not assert exact values against real Python's output: xp2f's
    # random number generation is a separate, independent implementation
    # from numpy's Generator API (PCG64) and doesn't reproduce its exact
    # draws bit-for-bit -- only that the transpile/build/run pipeline
    # completes successfully (Build/Run: PASS) for this call shape.
    src = tmp_path / "xmvn_binop_local_fn.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def draw(p, n, rng):",
                "    cov = np.eye(p) * 4.0",
                "    x = rng.multivariate_normal(mean=np.zeros(p), cov=cov, size=n) / 100.0",
                "    return x",
                "",
                "rng = np.random.default_rng(12345)",
                "x = draw(3, 5, rng)",
                "print(x.shape)",
                "",
                "for i in range(3):",
                "    rng_i = np.random.default_rng(12345 + i)",
                "    xi = draw(3, 5, rng_i)",
                "    print(i, xi.shape)",
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
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_does_not_hoist_array_realloc_read_before_reassignment(tmp_path: Path) -> None:
    # Regression test for a silent data-corruption bug found while
    # debugging examples/xequicorr_turnover.py's runtime SIGFPE crash:
    # hoist_loop_invariant_array_realloc moves a loop-body
    # `if (allocated(x)) deallocate(x); allocate(x(shape))` pair out to
    # just before the loop whenever `shape` doesn't depend on the loop
    # variable or anything the loop reassigns -- but it never checked
    # whether `x`'s value coming INTO the loop (from before it, or
    # carried from the previous iteration) is actually read anywhere,
    # e.g. a stateful "d_new = d * (...); ...; d = np.full(p, target)"
    # rebalancing pattern (`d_new` reads `d` *before* `d` gets
    # reassigned at the end of the same iteration). Hoisting the
    # reallocation drops the array's contents (deallocate+allocate gives
    # uninitialized memory, not a preserved value) -- so it silently fed
    # garbage into the first iteration's read, corrupting every later
    # value derived from it. The corruption was invisible whenever the
    # freshly-allocated memory happened to still be zero-filled (why
    # examples/xequicorr_turnover.py's first few simulate_turnover()
    # calls looked fine and only a later one, reusing already-used
    # memory, went visibly wrong and eventually crashed with SIGFPE from
    # a resulting zero/negative portfolio value).
    #
    # Fixed by refusing to hoist whenever the array name appears
    # anywhere else at all in the loop body (conservative, like the rest
    # of this pass -- may leave some genuinely-safe cases unhoisted too,
    # but never incorrect).
    _run_xp2f_compile_diff(
        tmp_path,
        "xhoist_realloc_carried_state.py",
        [
            "import numpy as np",
            "",
            "p = 3",
            "n = 4",
            "d = np.full(p, 2.0)",
            "out = np.zeros(n)",
            "for t in range(n):",
            "    d_new = d * 2.0",
            "    out[t] = d_new.sum()",
            "    d = np.full(p, float(t + 1))",
            "print(out[0], out[1], out[2], out[3])",
        ],
    )


def test_xp2f_local_function_mvn_only_called_from_a_loop(tmp_path: Path) -> None:
    # Regression test: a local function using rng.multivariate_normal(...)
    # (rng passed in as a parameter, not the top-level Name that created
    # it -- see test_xp2f_rng_multivariate_normal_in_binop_and_local_fn)
    # failed differently, and for reasons unrelated to that call shape,
    # when its ONLY call site is inside a `for` loop (no bare top-level
    # call anywhere) -- found while debugging
    # examples/xequicorr_turnover.py, which happens to have a bare call
    # before its own sweep loop and so never hit either bug. Three
    # separate gaps, all in call-site-driven local-function inference,
    # fixed together:
    # 1. "unsupported call" for the multivariate_normal call itself --
    #    _is_mvn_call requires the receiver's name to be in self.rng_vars,
    #    which is populated purely by NAME from actual
    #    `X = default_rng(...)` assignments prescan has seen; a
    #    same-named receiver at the call site (e.g. both called "rng")
    #    made this work only by coincidence. Fixed by having the local-
    #    function arg-kind-hint pass add a parameter to rng_vars whenever
    #    _arg_used_as_rng_receiver structurally recognizes it (extended
    #    to also recognize multivariate_normal, which it didn't before).
    # 2. "Type mismatch ... passed REAL(8) to INTEGER(4)" for a SECOND
    #    local function called only via a pass-through parameter (e.g.
    #    equicorr_cov(rho, ...) inside simulate_turnover(rho, ...,
    #    rng), simulate_turnover itself only ever called with a
    #    loop-derived real value) -- the pass-through parameter's own
    #    within-body usage gave no int-vs-real evidence on its own, so
    #    the callee's arg-kind inference had nothing to go on. Fixed by
    #    preferring the enclosing function's own already-inferred
    #    call-site kind (call_kind_hints) for that parameter over a
    #    purely local, usage-based guess.
    # 3. A linker error ("undefined reference to random_mvn_samples_")
    #    from detect_needed_helpers missing the `use python_mod, only:
    #    random_mvn_samples` it needs -- detect_needed_helpers runs
    #    per-function on just that function's own body, so its own
    #    (separate, module-level) rng-name scan never sees the
    #    assignment that actually created the generator, which lives in
    #    the caller. Fixed by recognizing the multivariate_normal method
    #    name itself as sufficient evidence, regardless of the receiver.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlocal_fn_mvn_loop_only.py",
        [
            "import numpy as np",
            "",
            "",
            "def equicorr_cov(rho, xsd, p):",
            "    corr = np.full((p, p), rho)",
            "    np.fill_diagonal(corr, 1.0)",
            "    return xsd**2 * corr",
            "",
            "",
            "def simulate_turnover(rho, xsd, p, n, rng):",
            "    cov = equicorr_cov(rho, xsd, p)",
            "    rets = rng.multivariate_normal(mean=np.zeros(p), cov=cov, size=n) / 100.0",
            "    return rets.shape",
            "",
            "",
            "n = 20",
            "p = 3",
            "xsd = 0.02",
            "for i, rho_i in enumerate([0.0, 0.2]):",
            "    rng_i = np.random.default_rng(12345 + i)",
            "    shp = simulate_turnover(rho_i, xsd, p, n, rng_i)",
            "    print(rho_i, shp[0], shp[1])",
        ],
    )


def test_xp2f_len_on_2d_array_and_column_stack_with_multi_column_input(
    tmp_path: Path,
) -> None:
    # Regression test, surfaced by examples/xreg.py's
    # `np.column_stack((np.ones(len(X)), X))` where X is (n, 2):
    #
    # 1. len() on a rank>=2 array must give shape[0] (the row count),
    #    matching Fortran's size(x, 1) -- not the old codegen, which
    #    used the generic size(x) (total element count). len(X) below
    #    is 3, not 6.
    #
    # 2. np.column_stack's reshape-shape computation must sum each
    #    input's own column contribution (1 for a rank-1 input,
    #    size(_, 2) for a rank>=2 input) -- not just the count of input
    #    arrays, which silently under-counts whenever an input is
    #    itself multi-column. column_stack((ones(3), X)) with X (3, 2)
    #    must produce a (3, 3) result, not (3, 2).
    #
    # Both bugs together previously produced a mis-shaped array caught
    # only later at runtime (a MATMUL extent mismatch in xreg.py, once
    # the mis-shaped array was used in a matrix computation) rather
    # than at the point of construction.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlen_column_stack_2d.py",
        [
            "import numpy as np",
            "",
            "X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])",
            "print(len(X))",
            "Y = np.column_stack((np.ones(len(X)), X))",
            "print(Y.shape[0], Y.shape[1])",
            "print(Y[0, 0], Y[0, 1], Y[0, 2])",
            "print(Y[1, 0], Y[1, 1], Y[1, 2])",
            "print(Y[2, 0], Y[2, 1], Y[2, 2])",
        ],
    )


def test_xp2f_ieee_is_nan_in_program_body_with_local_function(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_root_bisection.py:
    # a NaN-safe comparison guard (merge(...)/ieee_is_nan(...), emitted
    # for a bare `<=` comparison) can be generated directly in the main
    # PROGRAM body, not just inside a helper/local function living in a
    # proc module. The program's own `use, intrinsic :: ieee_arithmetic`
    # line was only ever written when the source had NO local functions
    # (`if not use_proc_module`) -- wrongly assuming ieee symbols could
    # only be needed inside a proc module (which already gets its own
    # unconditional ieee_arithmetic use). Once a script has both (a)
    # some other local function forcing proc-module mode and (b) a
    # NaN-safe comparison directly in the main body, the program unit
    # compiled with "Function 'ieee_is_nan' has no IMPLICIT type".
    #
    # Fixed by always emitting the ieee_arithmetic use line for the
    # program unit (matching how the module case already does it) and
    # relying on remove_unused_ieee_arithmetic_use's existing per-unit
    # pruning to drop it back out when genuinely unused.
    _run_xp2f_compile_diff(
        tmp_path,
        "xieee_is_nan_program_body_with_local_fn.py",
        [
            "import numpy as np",
            "",
            "",
            "def f(x):",
            "    return x**3 - 2.0 * x - 5.0",
            "",
            "",
            "lo = 2.0",
            "hi = 3.0",
            "n_iter = 30",
            "",
            "for k in range(n_iter):",
            "    mid = 0.5 * (lo + hi)",
            "    fmid = f(mid)",
            "    if f(lo) * fmid <= 0.0:",
            "        hi = mid",
            "    else:",
            "        lo = mid",
            "",
            "root = 0.5 * (lo + hi)",
            "print('root =', root)",
            "print('f(root) =', f(root))",
        ],
    )


def test_xp2f_np_polynomial_legendre_leggauss(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_quadrature.py: adds
    # support for np.polynomial.legendre.leggauss(n) (Gauss-Legendre
    # quadrature nodes/weights on [-1, 1]), previously an unsupported
    # call ("unsupported assign: nodes, weights = ..."). Implemented via
    # a new leggauss(n, x, w) subroutine in python.f90 using the classic
    # Newton-iteration algorithm (roots of the degree-n Legendre
    # polynomial via its three-term recurrence), which converges to
    # full double precision and so matches numpy's own (eigenvalue-
    # based) implementation within run-diff's numeric tolerance.
    #
    # Checks both a degree with an exact closed form (n=3: nodes 0,
    # +/-sqrt(3/5); weights 8/9, 5/9, 5/9) and an odd/even-length-
    # agnostic n=5 case, plus using the nodes/weights to integrate
    # sin(x) over [0, pi] (exact value 2.0) as an end-to-end check.
    _run_xp2f_compile_diff(
        tmp_path,
        "xleggauss.py",
        [
            "import numpy as np",
            "",
            "nodes3, weights3 = np.polynomial.legendre.leggauss(3)",
            "print(nodes3[0], nodes3[1], nodes3[2])",
            "print(weights3[0], weights3[1], weights3[2])",
            "",
            "nodes5, weights5 = np.polynomial.legendre.leggauss(5)",
            "print(nodes5[0], nodes5[1], nodes5[2], nodes5[3], nodes5[4])",
            "print(weights5[0], weights5[1], weights5[2], weights5[3], weights5[4])",
            "",
            "a = 0.0",
            "b = np.pi",
            "xm = 0.5 * (b - a) * nodes5 + 0.5 * (b + a)",
            "integral = 0.5 * (b - a) * (weights5 * np.sin(xm)).sum()",
            "print('integral =', integral)",
        ],
    )


def test_xp2f_svd_full_matrices_false_uses_economy_shapes(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_linalg_svd.py:
    # np.linalg.svd(a, full_matrices=False) silently ignored the kwarg --
    # the generated linalg_svd helper always called LAPACK dgesvd with
    # jobu='A', jobvt='A' (numpy's *full* SVD: U is (m, m), Vt is
    # (n, n)) regardless of the kwarg, so U's column count (m) never
    # matched S's economy size (k = min(m, n)), causing a MATMUL extent
    # mismatch at runtime once U was used with S (e.g. U @ diag(s)) for
    # an m != n input.
    #
    # Fixed by adding a separate linalg_svd_econ helper (jobu='S',
    # jobvt='S': U is (m, k), Vt is (k, n)) and dispatching to it at
    # transpile time when full_matrices=False is a literal keyword
    # argument on the call, leaving the default (full_matrices omitted,
    # or =True) path unchanged.
    #
    # A (4, 3) input's economy SVD should give U (4, 3), s (3,), Vt
    # (3, 3) -- checked both by shape and by reconstructing A via
    # U @ diag(s) @ Vt.
    _run_xp2f_compile_diff(
        tmp_path,
        "xsvd_econ.py",
        [
            "import numpy as np",
            "",
            "A = np.array(",
            "    [",
            "        [1.0, 2.0, 3.0],",
            "        [4.0, 5.0, 6.0],",
            "        [7.0, 8.0, 10.0],",
            "        [1.0, 0.0, 1.0],",
            "    ]",
            ")",
            "",
            "U, s, Vt = np.linalg.svd(A, full_matrices=False)",
            "print(U.shape[0], U.shape[1])",
            "print(s.shape[0])",
            "print(Vt.shape[0], Vt.shape[1])",
            "",
            "S = np.diag(s)",
            "recon = U.dot(S).dot(Vt)",
            "err = recon - A",
            "err_norm = np.sqrt((err * err).sum())",
            "print('reconstruction error norm =', err_norm)",
        ],
    )


def test_xp2f_linalg_eig_eigh_underscore_discard_target(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_power_iteration.py's
    # `w_eigh, _ = np.linalg.eigh(A)`: a literal `_` discard target is a
    # plain ast.Name (not ast.Starred), so the eig/eigh/svd tuple-unpack
    # codegen's outs-builder ran it through _aliased_name like any real
    # variable -- which mangles a bare "_" into a synthetic "v_name"
    # identifier (base.lstrip('_') or 'name') that is never declared,
    # since _mark_alloc_real's prescan pass correctly treats "_" as a
    # no-op to skip. The mismatch (codegen emits a reference to
    # "v_name"; nothing ever declares it) produced "Symbol 'v_name' has
    # no IMPLICIT type" at build time.
    #
    # Fixed by keeping a literal `_` Name target as the same "_"
    # sentinel already used for ast.Starred, and extending the
    # already-existing (from np.linalg.qr) "some outputs discarded"
    # block pattern -- call into real temp variables, then assign only
    # the non-discarded outputs -- to eig, eigh, and svd as well.
    #
    # Covers both eigh (2 outputs, second discarded) and eig (2
    # outputs, first discarded) in one script.
    _run_xp2f_compile_diff(
        tmp_path,
        "xeig_eigh_underscore.py",
        [
            "import numpy as np",
            "",
            "A = np.array([[4.0, 1.0, 1.0], [1.0, 3.0, 0.5], [1.0, 0.5, 2.0]])",
            "w, _ = np.linalg.eigh(A)",
            "print(w[0], w[1], w[2])",
            "",
            "B = np.array([[2.0, 0.0], [0.0, 3.0]])",
            "_, v = np.linalg.eig(B)",
            "print(v.shape[0], v.shape[1])",
        ],
    )


def test_xp2f_np_correlate_modes(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_convolve_correlate.py:
    # np.correlate(a, v[, mode]) was unsupported ("unsupported call").
    # Fixed by recognizing it as np.convolve(a, v[::-1], mode) under the
    # hood -- reusing the existing correlate_real helper (already used
    # for scipy.signal.correlate), but with np.correlate's own default
    # mode ("valid", vs scipy's "full") passed explicitly when the
    # Python source omits the mode argument.
    #
    # Checks all three modes (default/"valid", "full", "same") against
    # the same fixed inputs.
    _run_xp2f_compile_diff(
        tmp_path,
        "xcorrelate_modes.py",
        [
            "import numpy as np",
            "",
            "a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])",
            "k = np.array([1.0, 0.0, -1.0])",
            "",
            "c_valid = np.correlate(a, k)",
            "c_full = np.correlate(a, k, mode='full')",
            "c_same = np.correlate(a, k, mode='same')",
            "",
            "print(c_valid.shape[0], c_full.shape[0], c_same.shape[0])",
            "print(c_valid[0], c_valid[1], c_valid[2])",
            "print(c_full[0], c_full[1], c_full[2], c_full[3], c_full[4], c_full[5], c_full[6])",
            "print(c_same[0], c_same[1], c_same[2], c_same[3], c_same[4])",
        ],
    )


def test_xp2f_polyfit_poly1d_roots(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_polyfit.py:
    #
    # 1. np.polyfit(x, y, deg) was unsupported. Fixed via a new
    #    polyfit_real Fortran helper (Vandermonde matrix + normal
    #    equations via the existing linalg_solve, matching numpy's
    #    SVD-based least-squares fit closely for well-conditioned data).
    #
    # 2. np.poly1d(coeffs) was unsupported. Fixed by tracking the
    #    assigned variable as a "poly1d" name (poly1d_vars) -- treated
    #    as a plain coefficient array, identical to `p = coeffs` -- and
    #    recognizing a later call p(x) in expr()'s Call dispatch,
    #    rewriting it to polyval(p, x) (same call shape as np.polyval,
    #    same highest-degree-first coefficient convention).
    #
    # np.roots was already supported; included here for an end-to-end
    # check alongside the two new features.
    _run_xp2f_compile_diff(
        tmp_path,
        "xpolyfit_poly1d_roots.py",
        [
            "import numpy as np",
            "",
            "x = np.array([-2.0, -1.0, 0.0, 1.0, 2.0, 3.0])",
            "y = 2.0 * x**2 - 3.0 * x + 1.0",
            "",
            "coeffs = np.polyfit(x, y, 2)",
            "print(coeffs[0], coeffs[1], coeffs[2])",
            "",
            "p = np.poly1d(coeffs)",
            "print(p(0.0), p(2.0), p(-1.0))",
            "",
            "cubic_coeffs = np.array([1.0, -6.0, 11.0, -6.0])",
            "r = np.sort(np.roots(cubic_coeffs))",
            "print(r[0], r[1], r[2])",
        ],
    )


def test_xp2f_linalg_pinv_and_matrix_power(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_pinv_matrix_power.py:
    # np.linalg.pinv (new linalg_pinv helper: V * diag(1/s) * U^T via the
    # existing economy-SVD helper) and np.linalg.matrix_power (new
    # linalg_matrix_power helper: identity at p=0, repeated matmul for
    # p>0, repeated matmul of inv(a) for p<0) were both unsupported.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlinalg_pinv_matrix_power.py",
        [
            "import numpy as np",
            "",
            "A = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])",
            "Ap = np.linalg.pinv(A)",
            "recon = A.dot(Ap).dot(A)",
            "err_norm = np.sqrt(((recon - A) * (recon - A)).sum())",
            "print(Ap.shape[0], Ap.shape[1])",
            "print(err_norm)",
            "",
            "B = np.array([[2.0, 1.0], [0.0, 2.0]])",
            "B3 = np.linalg.matrix_power(B, 3)",
            "B0 = np.linalg.matrix_power(B, 0)",
            "print(B3[0, 0], B3[0, 1], B3[1, 0], B3[1, 1])",
            "print(B0[0, 0], B0[0, 1], B0[1, 0], B0[1, 1])",
        ],
    )


def test_xp2f_linalg_eigvalsh_and_multi_dot(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_eigvalsh_multidot.py:
    # np.linalg.eigvalsh (new linalg_eigvalsh helper: LAPACK DSYEV with
    # jobz='N', eigenvalues only) and np.linalg.multi_dot (a literal
    # list of matrices, chained left-to-right via matmul) were both
    # unsupported.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlinalg_eigvalsh_multidot.py",
        [
            "import numpy as np",
            "",
            "A = np.array([[4.0, 1.0, 1.0], [1.0, 3.0, 0.5], [1.0, 0.5, 2.0]])",
            "w = np.linalg.eigvalsh(A)",
            "print(w[0], w[1], w[2])",
            "",
            "X = np.array([[1.0, 2.0], [3.0, 4.0]])",
            "Y = np.array([[5.0, 6.0], [7.0, 8.0]])",
            "Z = np.array([[1.0, 0.0], [0.0, 1.0]])",
            "M = np.linalg.multi_dot([X, Y, Z])",
            "print(M[0, 0], M[0, 1], M[1, 0], M[1, 1])",
        ],
    )


def test_xp2f_tensordot(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_tensordot.py:
    # np.tensordot was unsupported; added for the 2D-input subset
    # (axes=1 -- same as matmul; axes=2 -- full elementwise-product sum,
    # a scalar).
    _run_xp2f_compile_diff(
        tmp_path,
        "xtensordot.py",
        [
            "import numpy as np",
            "",
            "A = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])",
            "B = np.array([[7.0, 8.0], [9.0, 10.0], [11.0, 12.0]])",
            "t1 = np.tensordot(A, B, axes=1)",
            "print(t1[0, 0], t1[0, 1], t1[1, 0], t1[1, 1])",
            "",
            "C = np.array([[1.0, 2.0], [3.0, 4.0]])",
            "D = np.array([[5.0, 6.0], [7.0, 8.0]])",
            "t2 = np.tensordot(C, D, axes=2)",
            "print(t2)",
        ],
    )


def test_xp2f_select_piecewise_digitize(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_select_piecewise_digitize.py:
    # np.select, np.piecewise, and np.digitize were all unsupported.
    #
    # select/piecewise are lowered as a merge() chain over condlist,
    # processed last-to-first so the highest-priority (first) condition
    # wins; both require condlist/choicelist (or funclist) as literal
    # lists at the call site.
    #
    # piecewise additionally needed a fix beyond the merge-chain codegen
    # itself: funclist[i](x) is synthesized as call text rather than a
    # literal ast.Call node, so the normal call-hint scan that infers a
    # local function's own parameter type never saw it as evidence --
    # each function's parameter defaulted to INTEGER regardless of x's
    # real type, causing a build-time type mismatch. Fixed by a
    # dedicated _record_piecewise_call_hints pass that seeds the same
    # call-hint structures directly for this call shape.
    #
    # digitize is a new digitize_real helper (right=False, increasing
    # bins: count of bin edges <= x(i)).
    _run_xp2f_compile_diff(
        tmp_path,
        "xselect_piecewise_digitize.py",
        [
            "import numpy as np",
            "",
            "x = np.array([-3.0, -1.0, 0.0, 2.0, 5.0])",
            "",
            "sel = np.select(",
            "    [x < -2.0, (x >= -2.0) & (x < 1.0), x >= 1.0],",
            "    [x * 10.0, x * 100.0, x * 1000.0],",
            ")",
            "print(sel[0], sel[1], sel[2], sel[3], sel[4])",
            "",
            "",
            "def neg_branch(v):",
            "    return -v",
            "",
            "",
            "def pos_branch(v):",
            "    return v * v",
            "",
            "",
            "pw = np.piecewise(x, [x < 0.0, x >= 0.0], [neg_branch, pos_branch])",
            "print(pw[0], pw[1], pw[2], pw[3], pw[4])",
            "",
            "bins = np.array([-2.0, 0.0, 2.0, 4.0])",
            "idx = np.digitize(x, bins)",
            "print(idx[0], idx[1], idx[2], idx[3], idx[4])",
        ],
    )


def test_xp2f_histogram2d(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_histogram2d.py:
    # np.histogram2d(x, y, bins=[xedges, yedges]) was unsupported
    # (tuple-unpack assign). Added via a new histogram2d_real_edges
    # helper, mirroring the existing 1D histogram_real_edges helper's
    # right-inclusive-last-bin convention applied independently on
    # each axis, and requires bins as a literal [xedges, yedges] list
    # at the call site (matching this codebase's scoping convention for
    # other literal-list-argument features).
    _run_xp2f_compile_diff(
        tmp_path,
        "xhistogram2d.py",
        [
            "import numpy as np",
            "",
            "x = np.array([0.5, 1.5, 1.5, 2.5, 0.5, 2.5])",
            "y = np.array([0.5, 0.5, 1.5, 1.5, 1.5, 0.5])",
            "xedges = np.array([0.0, 1.0, 2.0, 3.0])",
            "yedges = np.array([0.0, 1.0, 2.0])",
            "H, xe, ye = np.histogram2d(x, y, bins=[xedges, yedges])",
            "print(H.shape[0], H.shape[1])",
            "for i in range(3):",
            "    print(H[i, 0], H[i, 1])",
            "print(H.sum())",
        ],
    )


def test_xp2f_apply_along_axis(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_apply_along_axis.py:
    # np.apply_along_axis was unsupported. Added for the 2D-array
    # subset where func returns a scalar per row/column slice -- lowered
    # as an explicit block+do-loop (not a Fortran implied-DO array
    # constructor, since that construct's index variable is not
    # auto-declared under implicit none and a first attempt at that hit
    # exactly that "no IMPLICIT type" build failure), only supported as
    # the entire right-hand side of a direct assignment.
    #
    # Also exercises a second, independent pre-existing bug this
    # surfaced: `arr.max(axis=1) - arr.min(axis=1)` (and the analogous
    # `.min`) was wrongly inferred as a scalar (rank 0) by _rank_expr,
    # because a generic "bare .max()/.min() with zero args -> scalar"
    # branch only checked positional arg count and didn't exclude calls
    # that have an `axis=` keyword (which have zero positional args
    # too), so it wrongly intercepted `.max(axis=1)` before the correct,
    # later axis-aware reduction-rank branch was ever reached. Fixed by
    # also requiring `not node.keywords` on that early branch.
    _run_xp2f_compile_diff(
        tmp_path,
        "xapply_along_axis.py",
        [
            "import numpy as np",
            "",
            "",
            "def value_range(v):",
            "    return v.max() - v.min()",
            "",
            "",
            "A = np.array([[1.0, 5.0, 3.0], [4.0, 2.0, 8.0], [7.0, 6.0, 0.0]])",
            "r_rows = np.apply_along_axis(value_range, 1, A)",
            "r_cols = np.apply_along_axis(value_range, 0, A)",
            "print(r_rows[0], r_rows[1], r_rows[2])",
            "print(r_cols[0], r_cols[1], r_cols[2])",
            "",
            "r_rows_direct = A.max(axis=1) - A.min(axis=1)",
            "r_cols_direct = A.max(axis=0) - A.min(axis=0)",
            "print(r_rows_direct[0], r_rows_direct[1], r_rows_direct[2])",
            "print(r_cols_direct[0], r_cols_direct[1], r_cols_direct[2])",
        ],
    )


def test_xp2f_np_save_load_1d_real_npy_roundtrip(tmp_path: Path) -> None:
    # Regression test, surfaced by numpy_examples/x_save_load.py:
    # np.save/np.load (binary .npy files) were unsupported -- only
    # text-based loadtxt/genfromtxt/savetxt existed. Added new
    # np_save_1d_real/np_load_1d_real helpers implementing the real
    # NumPy .npy binary format (magic + version + header dict padded to
    # a 64-byte-aligned preamble + raw float64 data) for the 1D-real-
    # array subset, verified as genuinely interoperable with real numpy
    # in both directions (not just self-consistent): a file numpy wrote
    # was read correctly by the transpiled binary, and a file the
    # transpiled binary wrote was read correctly by real numpy.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_save_load.py",
        [
            "import numpy as np",
            "",
            "a = np.array([1.5, -2.25, 3.0, 0.0, 42.75])",
            "np.save('xnp_save_load_scratch.npy', a)",
            "b = np.load('xnp_save_load_scratch.npy')",
            "diff = np.abs(a - b).sum()",
            "print(b.shape[0])",
            "print(diff)",
            "print(b[0], b[1], b[2], b[3], b[4])",
        ],
    )


def test_xp2f_df_column_selection_reports_unsupported_instead_of_crashing(
    tmp_path: Path,
) -> None:
    # Regression test, surfaced by option_pricing/xquad_option.py (a
    # stripped copy of the public-domain Non-lognormal-option-pricing
    # repo's xquad_option.py): `curve_df[["distribution", "strike", ...]]`
    # where curve_df = pd.DataFrame(curve_records) and curve_records is a
    # list of dicts returned by a called function -- xp2f's static
    # column-name tracking for pd.DataFrame(...) can't trace dict keys
    # through a function call, so it silently under-tracks the columns.
    # The df[[...]] column-selection prescan logic then did
    # `_src_cols.index(_nm)` unconditionally, which previously raised an
    # UNHANDLED `ValueError: 'distribution' is not in list` -- a raw
    # traceback rather than xp2f's usual clean "Transpile: FAIL" message.
    #
    # Fixed by checking for any selected column missing from the tracked
    # set first and raising a clear NotImplementedError instead. This
    # does not add real support for tracing columns through a function
    # call (a much bigger undertaking) -- only replaces a crash with a
    # graceful, clearly-worded rejection.
    src = tmp_path / "xdf_select_from_fn_returned_records.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "",
                "def make_records():",
                "    return [",
                "        {'name': 'a', 'value': 1.0},",
                "        {'name': 'b', 'value': 2.0},",
                "    ]",
                "",
                "",
                "records = make_records()",
                "df = pd.DataFrame(records)",
                "view = df[['name', 'value']]",
                "print(view)",
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

    assert "Traceback (most recent call last)" not in proc.stderr, proc.stdout + proc.stderr
    assert "Transpile: FAIL" in proc.stdout, proc.stdout + proc.stderr
    assert "not found in xp2f's tracked columns" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_np_isclose_array_and_scalar(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py: `arr[start:end] =
    # np.isclose(batch_max, initial_price)` failed with "unsupported
    # call: np.isclose(...)" -- np.isclose (element-wise, array-
    # returning) was never implemented at all; only the unrelated
    # scalar math.isclose/cmath.isclose were supported.
    #
    # Fixed via a direct inline formula (no helper function needed):
    # abs(a - b) <= atol + rtol * abs(b), the same tolerance test
    # np.allclose already used, but element-wise instead of aggregated
    # with .all(). Fortran's abs/+/*/<= are all elemental, so this
    # broadcasts a scalar against an array exactly like numpy's own
    # broadcasting for this call shape.
    #
    # Covers array-vs-array, array-vs-scalar (the exact xpaths.py
    # shape), and explicit rtol/atol.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_isclose.py",
        [
            "import numpy as np",
            "",
            "a = np.array([1.0, 2.0000001, 3.0, 100.00005])",
            "b = np.array([1.0, 2.0, 3.1, 100.0])",
            "c = np.isclose(a, b)",
            "print(c[0], c[1], c[2], c[3])",
            "",
            "x = np.array([5.0, 5.0001, 6.0])",
            "d = np.isclose(x, 5.0)",
            "print(d[0], d[1], d[2])",
            "",
            "e = np.isclose(a, b, rtol=1e-3, atol=1e-6)",
            "print(e[0], e[1], e[2], e[3])",
        ],
    )


def test_xp2f_np_isclose_nan_does_not_crash(tmp_path: Path) -> None:
    # Regression test for a bug in the np.isclose fix itself: comparing
    # a NaN element with `<=` under this project's -ffpe-trap=invalid
    # build raises IEEE's invalid-operation exception -> SIGFPE, and
    # Fortran's `.and.` is not guaranteed to short-circuit, so a naive
    # "not-NaN .and. (abs(a-b) <= tol)" elemental expression still
    # evaluates the unsafe comparison on the NaN element. Fixed by
    # routing np.isclose through a new isclose_real Fortran helper (a
    # loop with explicit if/else control flow, like the existing
    # allclose_real helper already uses) instead of an inline elemental
    # expression, so the comparison genuinely never runs on a NaN value.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_isclose_nan.py",
        [
            "import numpy as np",
            "",
            "a = np.array([1.0, np.nan, 3.0])",
            "b = np.array([1.0, np.nan, 3.0])",
            "c = np.isclose(a, b)",
            "print(c[0], c[1], c[2])",
        ],
    )


def test_xp2f_np_logical_not(tmp_path: Path) -> None:
    # Regression test: np.logical_not was missing even though
    # logical_and/logical_or/logical_xor were all already supported --
    # the one sibling of that function family left unimplemented.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_logical_not.py",
        [
            "import numpy as np",
            "",
            "x = np.array([True, False, True])",
            "y = np.logical_not(x)",
            "print(y[0], y[1], y[2])",
        ],
    )


def test_xp2f_np_isreal_iscomplex(tmp_path: Path) -> None:
    # Regression test: np.isreal/np.iscomplex were both unsupported.
    # For a complex-typed array this is a rank-correct elemental
    # aimag(x) == 0 / /= 0 comparison; for a non-complex array every
    # element is (trivially) real, reusing the existing ones_logical/
    # zeros_logical helpers already used elsewhere for zeros_like/
    # ones_like (same known rank>=2 flattening limitation those share).
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_isreal_iscomplex.py",
        [
            "import numpy as np",
            "",
            "r = np.array([1.0, 2.0, 3.0])",
            "c = np.array([1.0 + 0.0j, 2.0 + 1.0j, 0.0 - 3.0j])",
            "print(np.isreal(r)[0], np.isreal(r)[1])",
            "print(np.iscomplex(r)[0], np.iscomplex(r)[1])",
            "print(np.isreal(c)[0], np.isreal(c)[1], np.isreal(c)[2])",
            "print(np.iscomplex(c)[0], np.iscomplex(c)[1], np.iscomplex(c)[2])",
        ],
    )


def test_xp2f_np_isposinf_isneginf(tmp_path: Path) -> None:
    # Regression test: np.isposinf/np.isneginf were both unsupported
    # (siblings of the already-supported np.isinf). Uses a real np.inf/
    # -np.inf array literal (see test_xp2f_np_inf_literal_is_real_ieee_infinity
    # for the fix that made this representable at all).
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_isposinf_isneginf.py",
        [
            "import numpy as np",
            "",
            "a = np.array([1.0, np.inf, -np.inf, np.nan, -5.0])",
            "print(np.isposinf(a)[0], np.isposinf(a)[1], np.isposinf(a)[2], np.isposinf(a)[3], np.isposinf(a)[4])",
            "print(np.isneginf(a)[0], np.isneginf(a)[1], np.isneginf(a)[2], np.isneginf(a)[3], np.isneginf(a)[4])",
        ],
    )


def test_xp2f_np_comparison_ufuncs(tmp_path: Path) -> None:
    # Regression test: the explicit ufunc-call forms np.equal/
    # not_equal/greater/greater_equal/less/less_equal were all
    # unsupported (only the operator forms ==, !=, >, etc. worked).
    # Implemented by building a synthetic ast.Compare node from the two
    # call arguments and reusing the existing, already-correct Compare-
    # node codegen, rather than duplicating its type-promotion logic.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_comparison_ufuncs.py",
        [
            "import numpy as np",
            "",
            "a = np.array([1.0, 2.0, 3.0, 4.0])",
            "b = np.array([4.0, 3.0, 2.0, 1.0])",
            "print(np.equal(a, b)[0], np.equal(a, b)[3])",
            "print(np.not_equal(a, b)[0], np.not_equal(a, b)[3])",
            "print(np.greater(a, b)[0], np.greater(a, b)[3])",
            "print(np.greater_equal(a, b)[1], np.greater_equal(a, b)[2])",
            "print(np.less(a, b)[0], np.less(a, b)[3])",
            "print(np.less_equal(a, b)[1], np.less_equal(a, b)[2])",
        ],
    )


def test_xp2f_np_isin_and_in1d(tmp_path: Path) -> None:
    # Regression test: np.isin (and its older alias np.in1d) were both
    # unsupported. New isin_real/isin_int Fortran helpers ("is each
    # element of a present in b", rank-1 inputs), dispatched on
    # int-vs-real element kind.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_isin.py",
        [
            "import numpy as np",
            "",
            "ai = np.array([1, 2, 3, 4, 5])",
            "bi = np.array([2, 4, 6])",
            "mask = np.isin(ai, bi)",
            "print(mask[0], mask[1], mask[2], mask[3], mask[4])",
            "",
            "af = np.array([1.5, 2.5, 3.5])",
            "bf = np.array([2.5, 9.0])",
            "maskf = np.isin(af, bf)",
            "print(maskf[0], maskf[1], maskf[2])",
        ],
    )


def test_xp2f_np_array_equiv(tmp_path: Path) -> None:
    # Regression test: np.array_equiv (array_equal's broadcasting-aware
    # sibling) was unsupported. Scoped narrowly -- same-rank-and-shape
    # (delegates to the same check np.array_equal already uses) or one
    # operand a scalar (trivial broadcast); full N-D broadcast-shape
    # compatibility is not attempted.
    #
    # Also exercises a fix to np.array_equal itself, found while adding
    # array_equiv: array_equal's own codegen had the identical bug this
    # test's shape-check formula would otherwise trigger -- a redundant
    # extra layer of parens around each shape-check clause made a
    # pre-existing print-argument paren-stripping pass
    # (_peel_print_arg_parens) peel a second, mismatched "outer" layer
    # after correctly stripping array_equal's own single wrap,
    # corrupting the expression into a syntax error. Fixed in both
    # functions by dropping the (unnecessary -- relational operators
    # already bind tighter than .and. in Fortran) per-clause parens.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_array_equiv.py",
        [
            "import numpy as np",
            "",
            "m1 = np.array([[1.0, 2.0], [3.0, 4.0]])",
            "m2 = np.array([[1.0, 2.0], [3.0, 4.0]])",
            "m3 = np.array([[1.0, 2.0], [3.0, 5.0]])",
            "print(np.array_equiv(m1, m2))",
            "print(np.array_equiv(m1, m3))",
            "print(np.array_equiv(np.array([2.0, 2.0, 2.0]), 2.0))",
            "print(np.array_equiv(np.array([2.0, 2.0, 3.0]), 2.0))",
            "print(np.array_equal(m1, m2))",
        ],
    )


def test_xp2f_np_inf_literal_is_real_ieee_infinity(tmp_path: Path) -> None:
    # Regression test for a significant pre-existing gap found while
    # adding np.isposinf/np.isneginf: np.inf (and np.Inf/np.NINF, and
    # `from numpy import inf`) was ALWAYS lowered to huge(1.0_dp) -- the
    # largest finite double -- rather than genuine IEEE infinity
    # (ieee_value(0.0_dp, ieee_positive_inf), the same intrinsic
    # np.nan already used for ieee_quiet_nan). Since huge(1.0_dp) is
    # finite, ieee_is_finite/np.isinf/np.isfinite (already-existing,
    # separately-implemented features) were silently wrong for any
    # value that originated as an np.inf source literal -- e.g.
    # np.isinf(np.array([np.inf]))[0] transpiled to False.
    #
    # Fixed by emitting real ieee_value(...)-constructed infinity
    # instead (both codegen sites: the Attribute form np.inf and the
    # `from numpy import inf` Name-alias form), and adding
    # ieee_positive_inf/ieee_negative_inf to the ieee_arithmetic
    # use-only import lists (and the matching unused-import pruning
    # pass's tracked symbol set) alongside the symbols already used for
    # np.nan.
    #
    # Verified this doesn't reintroduce an FPE crash under this
    # project's -ffpe-trap=invalid,zero,overflow build: constructing
    # infinity via ieee_value (not via an actual overflowing
    # computation like 1.0/0.0) and ordinary arithmetic/comparisons on
    # an already-infinite value do not raise IEEE exceptions.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_inf_literal.py",
        [
            "import numpy as np",
            "",
            "x = np.inf",
            "y = -np.inf",
            "print(x, y)",
            "",
            "a = np.array([1.0, np.inf, -np.inf, np.nan, -5.0])",
            "print(np.isinf(a)[0], np.isinf(a)[1], np.isinf(a)[2], np.isinf(a)[3], np.isinf(a)[4])",
            "print(np.isfinite(a)[0], np.isfinite(a)[1], np.isfinite(a)[2], np.isfinite(a)[3], np.isfinite(a)[4])",
            "",
            "b = 5.0 + x",
            "c = x - 3.0",
            "d = -x",
            "print(b, c, d)",
            "print(x > 1e300)",
            "print(y < -1e300)",
            "",
            "vals = np.array([1.0, 50.0, -10.0])",
            "clipped = np.clip(vals, 0.0, np.inf)",
            "print(clipped[0], clipped[1], clipped[2])",
        ],
    )


def test_xp2f_pandas_df_dict_of_axis0_reductions_construct(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py:
    #   summary = pd.DataFrame({
    #       "mean": price_paths.mean(axis=0),
    #       "median": price_paths.median(axis=0),
    #       "std": price_paths.std(axis=0, ddof=0),
    #       "min": price_paths.min(axis=0),
    #       "q1": price_paths.quantile(0.25, axis=0),
    #       "q3": price_paths.quantile(0.75, axis=0),
    #       "max": price_paths.max(axis=0),
    #   })
    # was unsupported -- the transposed-orientation sibling of the
    # already-supported pd.DataFrame([df.mean(), df.std()],
    # index=[...]) list form (_pandas_df_reduction_rows_construct_spec):
    # here each DICT VALUE is a whole-DataFrame axis=0 column-wise
    # reduction (dict key -> new column name, price_paths' own columns
    # -> new row labels), rather than each LIST ELEMENT being one.
    #
    # New _pandas_df_reduction_cols_construct_spec recognizes this dict
    # shape; also extends the shared _pandas_df_reduction_expr helper
    # with two things the list form never needed: df.quantile(q, axis=0)
    # (new "quantile" method, via the existing quantile_linear helper --
    # same one df.median() already uses with q=0.5) and an explicit
    # ddof= override for std/var (previously hardcoded to pandas'
    # default ddof=1).
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_summary_cols.py",
        [
            "import numpy as np",
            "import pandas as pd",
            "",
            "price_paths = pd.DataFrame(",
            "    {",
            "        'Maximum': np.array([105.0, 110.0, 98.0, 120.0, 101.0]),",
            "        'Minimum': np.array([95.0, 90.0, 88.0, 100.0, 97.0]),",
            "        'Terminal': np.array([100.0, 105.0, 92.0, 115.0, 99.0]),",
            "    }",
            ")",
            "",
            "summary = pd.DataFrame(",
            "    {",
            "        'mean': price_paths.mean(axis=0),",
            "        'median': price_paths.median(axis=0),",
            "        'std': price_paths.std(axis=0, ddof=0),",
            "        'min': price_paths.min(axis=0),",
            "        'q1': price_paths.quantile(0.25, axis=0),",
            "        'q3': price_paths.quantile(0.75, axis=0),",
            "        'max': price_paths.max(axis=0),",
            "    }",
            ")",
            "mean_col = summary['mean'].to_numpy()",
            "std_col = summary['std'].to_numpy()",
            "q1_col = summary['q1'].to_numpy()",
            "print(mean_col[0], mean_col[1], mean_col[2])",
            "print(std_col[0], std_col[1], std_col[2])",
            "print(q1_col[0], q1_col[1], q1_col[2])",
        ],
    )


def test_xp2f_dict_comprehension_over_list_consumed_via_items(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py:
    #   threshold_probs = {
    #       threshold: (terminals > threshold).mean()
    #       for threshold in TERMINAL_THRESHOLDS
    #   }
    #   for threshold, probability in threshold_probs.items():
    #       ...
    # was unsupported (dict comprehensions weren't supported at all).
    #
    # Narrow support added: a single-generator DictComp with no `if`
    # filter, where the key is exactly the loop variable (the common
    # `{k: f(k) for k in items}` idiom) -- modeled as a materialized
    # values array (dict_comp_vars), not a real dict type, and only
    # consumable later via `for k, v in D.items():` (not arbitrary key
    # lookup D[key]). The value expression is evaluated inside a real
    # Fortran DO loop (not the pre-existing, narrower ListComp
    # machinery's vectorized-elemental-map strategy, which can't
    # express a per-element reduction like `.mean()` at all).
    #
    # This exercises the dict-comprehension feature itself at the top
    # level; see test_xp2f_dict_comprehension_in_local_function_over_
    # module_global_list for the exact xpaths.py shape (same
    # comprehension, but inside a local function iterating a module-
    # level list global -- which needed a separate fix, see
    # test_xp2f_local_function_iterates_module_level_list_global).
    _run_xp2f_compile_diff(
        tmp_path,
        "xdictcomp_items.py",
        [
            "import numpy as np",
            "",
            "terminals = np.array([98.0, 101.0, 105.0, 99.0, 110.0])",
            "TERMINAL_THRESHOLDS = [100.0, 104.0]",
            "",
            "threshold_probs = {",
            "    threshold: (terminals > threshold).mean()",
            "    for threshold in TERMINAL_THRESHOLDS",
            "}",
            "",
            "for threshold, probability in threshold_probs.items():",
            "    print(threshold, probability)",
        ],
    )


def test_xp2f_local_function_iterates_module_level_list_global(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py: a local function (def
    # main():) iterating a module-level list global it never locally
    # assigns -- `for t in TERMINAL_THRESHOLDS:` -- failed even as a
    # BARE for-loop, with no dict comprehension involved:
    #   Transpile: FAIL (only for .. in range(..) or for .. in
    #   sorted(..) supported)
    # despite the exact same top-level list working fine in a for-loop
    # outside any function, and despite a SCALAR module-level global
    # already working fine inside a local function (e.g. `X = 5.0`
    # read inside main()) -- that scalar case only "worked" because an
    # unrecognized name already defaults to rank-0 real, which happens
    # to be correct for a scalar but wrong for a list/array.
    #
    # Root cause: _emit_local_function builds each local function's own
    # translator instance from scratch, with no visibility into a
    # module-level global's actual type/rank unless it's the (much
    # narrower) target of an explicit Python `global` statement inside
    # some local function -- collect_top_level_shared_decls already
    # computed the right (kind, rank) info per name (merged into
    # module_global_decls when use_proc_module, i.e. whenever there are
    # any local functions at all) for a *different* purpose (avoiding
    # duplicate local Fortran declarations), but that info was never
    # used to seed the new translator instance's own rank/kind-inference
    # state before visiting the function body.
    #
    # Fixed by threading module_global_decls into _emit_local_function
    # as toplevel_shared_specs and seeding tr's own alloc_real/etc.
    # state with it (skipping any name the function locally reassigns
    # itself, so genuine local shadowing -- e.g. a same-named local
    # variable -- still works correctly via normal prescan).
    _run_xp2f_compile_diff(
        tmp_path,
        "xlocal_fn_global_list_iter.py",
        [
            "TERMINAL_THRESHOLDS = [100.0, 104.0]",
            "",
            "",
            "def main():",
            "    total = 0.0",
            "    for t in TERMINAL_THRESHOLDS:",
            "        total = total + t",
            "    print(total)",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ],
    )


def test_xp2f_local_function_shadows_module_level_list_global(tmp_path: Path) -> None:
    # Regression test for the seeding fix above: a local variable that
    # shares a name with a module-level list global (but is never that
    # global -- pure name collision, reassigned to something else
    # entirely inside the function) must not be wrongly treated as the
    # global. toplevel_shared_specs seeding skips any name the function
    # locally (re)assigns, so this stays governed by normal local
    # prescan.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlocal_fn_shadows_global_list.py",
        [
            "VALUES = [1.0, 2.0, 3.0]",
            "",
            "",
            "def main():",
            "    VALUES = 42.0",
            "    print(VALUES)",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ],
    )


def test_xp2f_dict_comprehension_in_local_function_over_module_global_list(
    tmp_path: Path,
) -> None:
    # Regression test: the exact xpaths.py shape -- a dict comprehension
    # (test_xp2f_dict_comprehension_over_list_consumed_via_items) inside
    # a local function (test_xp2f_local_function_iterates_module_level_
    # list_global) iterating a module-level list global. Both fixes
    # combined, exercised together.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdictcomp_in_local_fn.py",
        [
            "import numpy as np",
            "",
            "TERMINAL_THRESHOLDS = [100.0, 104.0]",
            "",
            "",
            "def main():",
            "    terminals = np.array([98.0, 101.0, 105.0, 99.0, 110.0])",
            "    threshold_probs = {",
            "        threshold: (terminals > threshold).mean()",
            "        for threshold in TERMINAL_THRESHOLDS",
            "    }",
            "    for threshold, probability in threshold_probs.items():",
            "        print(threshold, probability)",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ],
    )


def test_xp2f_df_to_string_float_format_fixed_decimals_recognized(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py:
    #   print(summary.to_string(float_format=lambda x: f"{x:.4f}"))
    # was originally unsupported (only a bare, no-keyword .to_string()
    # was recognized as the existing print-helpers' no-op wrapper).
    #
    # The common "fixed N decimal places" float_format idiom (this
    # lambda's f-string form, plus its "{:.Nf}".format(x) and "%.Nf" % x
    # siblings -- see _extract_float_format_ndigits) is recognized and
    # honored directly by threading N through as the print helper's
    # existing ndigits= parameter (the same mechanism print(df.round(n))
    # already uses), so no warning is emitted and the rounded values
    # match Python's f"{x:.4f}" rounding exactly.
    #
    # Not run through _run_xp2f_compile_diff/--run-diff: to_string()
    # output has a known, pre-existing cosmetic gap from Python's exact
    # column widths/"[N rows x M columns]" footer (same gap plain
    # print(df) and bare to_string() already have) -- unrelated to
    # float_format, so this checks the rounded values textually instead.
    src = tmp_path / "xdf_to_string_float_format_fixed.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "price_paths = pd.DataFrame(",
                "    {",
                "        'Maximum': np.array([105.0, 110.0, 98.0, 120.0, 101.0]),",
                "        'Minimum': np.array([95.0, 90.0, 88.0, 100.0, 97.0]),",
                "        'Terminal': np.array([100.0, 105.0, 92.0, 115.0, 99.0]),",
                "    }",
                ")",
                "",
                "summary = pd.DataFrame(",
                "    {",
                "        'mean': price_paths.mean(axis=0),",
                "        'std': price_paths.std(axis=0, ddof=0),",
                "    }",
                ")",
                "print(summary.to_string(float_format=lambda x: f'{x:.4f}'))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "ignoring unsupported to_string(float_format=...)" not in proc.stderr, proc.stdout + proc.stderr
    # Fortran's own unrounded stat (7.730459...) rounds to "7.7305" --
    # confirms ndigits=4 was actually threaded through, not just that
    # the call happened to compile.
    assert "7.7305" in proc.stdout, proc.stdout + proc.stderr
    assert "4.4272" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_df_to_string_float_format_unrecognized_ignored_with_warning(tmp_path: Path) -> None:
    # An unrecognized float_format shape (anything other than the fixed
    # N-decimal-places idioms handled above -- e.g. a percentage format)
    # can't be evaluated at transpile time. It's silently ignored
    # (falling back to the print helper's own fixed numeric formatting)
    # with a warning on stderr explaining the fallback, instead of
    # rejecting the whole statement. Any *other* .to_string() keyword
    # argument is still unsupported (not touched by this fix).
    #
    # Checks Build/Run: PASS and the warning text, not an exact
    # Run diff: MATCH -- ignoring float_format's formatting entirely is
    # expected to show up as a cosmetic numeric-formatting difference in
    # the run-diff comparison, not a real value mismatch.
    src = tmp_path / "xdf_to_string_float_format_unrecognized.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "df = pd.DataFrame(",
                "    {",
                "        'a': np.array([1.5, 2.5]),",
                "        'b': np.array([3.5, 4.5]),",
                "    }",
                ")",
                "print(df.to_string(float_format=lambda x: f'{x:.2%}'))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "ignoring unsupported to_string(float_format=...)" in proc.stderr, proc.stdout + proc.stderr


def test_xp2f_rng_normal_positional_loc_scale_applied(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py's
    #   log_returns = rng.normal(mean, std, size=(current_batch, num_steps))
    # rng.normal(loc, scale, size=...) called with loc/scale passed
    # POSITIONALLY (not as loc=/scale= keywords) previously dropped the
    # affine transform entirely in the `X = rng.normal(...)` statement-
    # level codegen path (distinct from an expression-level sibling,
    # which already handled positional loc/scale correctly): v.args[0]
    # was wrongly treated as size_node instead of loc_node, and
    # loc_node/scale_node were only ever populated from loc=/scale=
    # keywords -- so a positional call silently emitted bare rnorm(...)
    # (mean=0, std=1) instead of loc + scale * rnorm(...).
    #
    # std=0.0 makes this an exact, deterministic check without depending
    # on matching numpy's RNG bit-for-bit: every draw collapses to
    # exactly `mean` regardless of the underlying random values, in both
    # Python and Fortran, so a real diff would show up as anything other
    # than the same constant.
    _run_xp2f_compile_diff(
        tmp_path,
        "xrng_normal_positional_loc_scale.py",
        [
            "import numpy as np",
            "",
            "rng = np.random.default_rng(42)",
            "mean = 5.0",
            "std = 0.0",
            "x = rng.normal(mean, std, size=(4, 3))",
            "print(x.min(), x.max())",
        ],
    )


def test_xp2f_module_global_none_seed_gets_sentinel_not_uninitialized(tmp_path: Path) -> None:
    # Regression test, surfaced by xpaths.py's `RNG_SEED = None` module
    # global fed into `simulate_extrema(..., seed=RNG_SEED, ...)` ->
    # `rng = np.random.default_rng(seed)`. `X = None` at module level
    # previously produced NO Fortran initializer at all (visit_Assign's
    # generic "None sentinel assignment" branch is a deliberate no-op:
    # "preserve None in state only"), leaving the real(kind=dp) variable
    # uninitialized -- undefined behavior (whatever garbage happened to
    # be in memory becomes the seed), not "use entropy" semantics. Fixed
    # by giving such globals an explicit -1 sentinel (RNG seeds are
    # always non-negative, so it's unambiguous) plus a matching runtime
    # `if (seed < 0) then call seed_rng() else call seed_rng(int(seed))`
    # guard in the default_rng/random.Random seeding codegen.
    #
    # Can't assert an exact value (the whole point is it's now genuinely
    # entropy-seeded), so this checks Build/Run: PASS plus, structurally,
    # that the generated source carries the -1 sentinel and the runtime
    # guard rather than an unconditional call.
    src = tmp_path / "xrng_seed_none_sentinel.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "RNG_SEED = None",
                "",
                "",
                "def simulate(seed):",
                "    rng = np.random.default_rng(seed)",
                "    x = rng.normal(0.0, 1.0, size=5)",
                "    return x",
                "",
                "",
                "def main():",
                "    x = simulate(RNG_SEED)",
                "    print(len(x))",
                "",
                "",
                "if __name__ == '__main__':",
                "    main()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    f90_text = (tmp_path / "xrng_seed_none_sentinel_p.f90").read_text(encoding="utf-8")
    assert "-1.0_dp" in f90_text, f90_text
    # `simulate` is simple enough to get inlined into main(), so the
    # runtime guard ends up keyed on RNG_SEED directly rather than a
    # `seed` dummy argument -- match the shape, not the exact name.
    assert "< 0) then" in f90_text, f90_text
    assert "call seed_rng()" in f90_text, f90_text
    assert "call seed_rng(int(" in f90_text, f90_text


def test_xp2f_local_function_param_case_insensitive_collision_with_module_global(
    tmp_path: Path,
) -> None:
    # Regression test, surfaced by xpaths.py's simulate_extrema(initial_price,
    # ...) -- a local function's own parameter (`initial_price`)
    # case-insensitively colliding with an unrelated module-level global
    # (`INITIAL_PRICE`) that this SAME function never reads (Fortran is
    # case-insensitive, so the two are the same identifier there).
    #
    # Triggered by the toplevel_shared_specs seeding (see
    # test_xp2f_local_function_iterates_module_level_list_global): before
    # this fix, seeding was applied for every global in the whole
    # script's merged module_global_decls, not just the ones this
    # particular function actually reads, so seeding INITIAL_PRICE
    # (needed only by main(), never by this unrelated local helper)
    # still ran _mark_real -> _aliased_name('INITIAL_PRICE'), claiming
    # the lowercased "initial_price" spelling in this function's own
    # alias table before its actual parameter got a turn. That silently
    # renamed the parameter's body references to initial_price_2, while
    # the subroutine signature/declaration (and every call site) kept
    # the unaliased name -- leaving initial_price_2 permanently
    # unassigned (reads as 0.0), even though Fortran's normal lexical
    # scoping already lets a dummy argument safely shadow a
    # host-associated global of the same case-insensitive name with no
    # rename needed at all. Fixed by restricting seeding to globals this
    # function's body actually reads (Load context), not just "not
    # locally bound".
    _run_xp2f_compile_diff(
        tmp_path,
        "xparam_global_case_collision.py",
        [
            "INITIAL_PRICE = 100.0",
            "",
            "",
            "def scale_price(initial_price, factor):",
            "    return initial_price * factor",
            "",
            "",
            "def main():",
            "    print(INITIAL_PRICE)",
            "    print(scale_price(50.0, 2.0))",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ],
    )


def test_xp2f_sort_correctness_after_merge_sort_rewrite(tmp_path: Path) -> None:
    # Regression test, surfaced by a user's timing report on xpaths.py:
    # at NUM_PATHS=10**5 (with quantile_linear -- used for median/q1/q3
    # in the summary DataFrame -- called 9 times on 100,000-element
    # arrays), the Fortran run took ~4x longer than a 10x-smaller input
    # would predict under linear scaling. Root cause: sort_real_vec/
    # sort_int_vec/sort_char_vec (the shared `sort_vec` implementation
    # behind quantile_linear, median, unique, np.sort, etc.) were plain
    # insertion sort -- O(n^2) -- ~2.5e9 compare/shift operations to
    # sort 100,000 elements, vs ~1.7e6 for an O(n log n) sort.
    # (argsort_real/argsort_int had already been fixed for this exact
    # issue at some earlier point; these sibling routines were missed.)
    # Rewritten as a bottom-up iterative merge sort, matching the
    # existing argsort_msort_real precedent.
    #
    # This checks correctness (exact match against Python) across
    # shapes a merge sort's recursive/iterative merging can get subtly
    # wrong if broken: already-sorted, reverse-sorted, many duplicates,
    # single-element, and a larger randomized array with repeats.
    _run_xp2f_compile_diff(
        tmp_path,
        "xsort_merge_sort_correctness.py",
        [
            "import numpy as np",
            "",
            "a = np.array([5.0, 3.0, 3.0, 1.0, 9.0, 2.0, 2.0, 8.0, 0.0, 7.0, 3.0])",
            "a_sorted = np.sort(a)",
            "print(a_sorted)",
            "",
            "b = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])",
            "b_sorted = np.sort(b)",
            "print(b_sorted)",
            "",
            "c = np.array([6.0, 5.0, 4.0, 3.0, 2.0, 1.0])",
            "c_sorted = np.sort(c)",
            "print(c_sorted)",
            "",
            "d = np.array([1.0])",
            "d_sorted = np.sort(d)",
            "print(d_sorted)",
            "",
            "e = np.array([2.0, 2.0, 2.0, 2.0, 2.0])",
            "e_sorted = np.sort(e)",
            "print(e_sorted)",
            "",
            # A deterministic (not RNG-derived) larger array with many
            # duplicates -- avoids relying on Fortran's own RNG matching
            # numpy's draws bit-for-bit, which it doesn't (different
            # algorithms) without the separate --rng-replay mechanism.
            "f = (np.arange(2000, dtype=np.float64) * 37.0) % 100.0",
            "f_sorted = np.sort(f)",
            "print(f_sorted.min(), f_sorted.max(), f_sorted.sum())",
        ],
    )


def test_xp2f_np_full_1d_uses_spread_not_explicit_realloc(tmp_path: Path) -> None:
    # Code-quality/correctness fix, flagged from xpaths.py's generated
    # `if (allocated(batch_max)) deallocate(batch_max); allocate(
    # batch_max(current_batch)); batch_max = initial_price` (the
    # `X = np.full(n, value)` codegen) -- three lines where one would
    # do, since an array-valued RHS assigned to an allocatable LHS
    # always auto-(re)allocates to match in Fortran, regardless of
    # whether the LHS was previously unallocated or a different size.
    # Rewritten as `X = spread(value, dim=1, ncopies=n)` for the 1D
    # shape case (2D+ shapes still use the explicit allocate, since
    # spread only adds one dimension at a time).
    #
    # This exercises exactly the case the explicit deallocate+allocate
    # was needed for -- repeated calls with a first-ever (unallocated),
    # then a smaller, then a larger n -- to confirm spread's automatic
    # reallocation handles all three without it.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_full_1d_spread.py",
        [
            "import numpy as np",
            "",
            "def f(n):",
            "    x = np.full(n, 3.5, dtype=np.float64)",
            "    return x",
            "",
            "",
            "def main():",
            "    print(f(5))",
            "    print(f(3))",
            "    print(f(7))",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ],
    )


def test_xp2f_wrapped_declaration_keeps_trailing_comma_on_first_line(tmp_path: Path) -> None:
    # Regression test, flagged from xpaths.py's generated
    #   integer :: i_threshold_probs_130, i_threshold_probs_143, price_paths_ridx_i &
    #      & , rng
    # -- a long `integer ::`/`real(kind=dp) ::` declaration list wrapped
    # with the separating comma leading the continuation line instead
    # of trailing the line it belongs to. Root cause was in
    # _break_candidates_for_wrap (fortran_scan.py): a comma's break
    # candidate was recorded at the comma's own index, so
    # wrap_long_fortran_line's `cur[:cut]` / `cur[cut:]` slice put the
    # comma on the continuation side. Fixed by recording the candidate
    # one past the comma instead, so it stays attached to the item
    # before it -- `... item, &` / `& next`, not `... item &` / `& , next`.
    #
    # Forces a wrap via many long local-variable names, then checks the
    # generated source directly: no line may start a continuation with
    # a leading comma, and no continuation line may be the empty
    # `& &` artifact (a related bug this same investigation surfaced:
    # see test_xp2f_allocate_merge_self_wraps_without_corrupting_file).
    _run_xp2f_compile_diff(
        tmp_path,
        "xwrap_decl_trailing_comma.py",
        [
            "def compute(aaaaaaaaaa, bbbbbbbbbb, cccccccccc, dddddddddd, eeeeeeeeee):",
            "    return aaaaaaaaaa + bbbbbbbbbb + cccccccccc + dddddddddd + eeeeeeeeee",
            "",
            "",
            "def main():",
            "    print(compute(1.0, 2.0, 3.0, 4.0, 5.0))",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
        ],
    )
    f90_text = (tmp_path / "xwrap_decl_trailing_comma_p.f90").read_text(encoding="utf-8")
    assert not re.search(r"^\s*&\s*,", f90_text, re.MULTILINE), f90_text
    assert "& &" not in f90_text, f90_text


def test_xp2f_allocate_merge_self_wraps_without_corrupting_file(tmp_path: Path) -> None:
    # Regression test: combine_consecutive_simple_allocates (see
    # test_xp2f_sort_correctness_after_merge_sort_rewrite's sibling
    # allocate-merge fix) can produce a single merged `allocate(...)`
    # line longer than the 80-column wrap width when several sibling
    # np.empty(...)-style arrays with long names get combined. The
    # first fix for that re-ran the WHOLE-FILE wrap_long_lines pass a
    # second time afterward -- which corrupted already-wrapped lines
    # elsewhere in the file whose trailing " &" pushed them 1-2
    # characters over the limit (wrap_long_fortran_line isn't designed
    # to receive an already-wrapped continuation line as fresh input,
    # and produced a stray empty `& &` continuation). Fixed by having
    # combine_consecutive_simple_allocates re-wrap only the one new
    # line it just produced, never re-scanning the rest of the file.
    #
    # Uses enough long array names that the merged allocate line must
    # wrap, and checks Build/Run: PASS plus the same "no leading-comma
    # continuation, no stray & &" invariants on the whole generated file.
    src = tmp_path / "xallocate_merge_self_wrap.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def make_arrays(n):",
                "    array_one_long_name = np.empty(n, dtype=np.float64)",
                "    array_two_long_name = np.empty(n, dtype=np.float64)",
                "    array_three_long_name = np.empty(n, dtype=np.float64)",
                "    array_four_long_name = np.empty(n, dtype=np.float64)",
                "    array_one_long_name[:] = 1.0",
                "    array_two_long_name[:] = 2.0",
                "    array_three_long_name[:] = 3.0",
                "    array_four_long_name[:] = 4.0",
                "    return array_one_long_name, array_two_long_name, array_three_long_name, array_four_long_name",
                "",
                "",
                "def main():",
                "    a, b, c, d = make_arrays(3)",
                "    print(a)",
                "    print(b)",
                "    print(c)",
                "    print(d)",
                "",
                "",
                "if __name__ == '__main__':",
                "    main()",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    f90_text = (tmp_path / "xallocate_merge_self_wrap_p.f90").read_text(encoding="utf-8")
    assert not re.search(r"^\s*&\s*,", f90_text, re.MULTILINE), f90_text
    assert "& &" not in f90_text, f90_text


def test_xp2f_pandas_df_print_helpers_skip_block_for_bare_df_name(tmp_path: Path) -> None:
    # Regression test: several DataFrame print/reduction codegen helpers
    # (_emit_pandas_df_print's DataFrame_str_index %display() path,
    # X = df.to_numpy(), df.mean()/df.sum(axis=1) reduction printing,
    # df.corrwith()) unconditionally wrapped their generated statements
    # in `block ... end block`, needed only when the resolved DataFrame
    # reference is itself a function-call expression (e.g.
    # `df[["a","b"]]` renders as `df%icol([...])`, which can't have
    # %display()/%values chained directly onto it -- gfortran: "leftmost
    # part-ref in a data-ref cannot be a function reference"). For a
    # bare DataFrame variable name, _pandas_df_materialize_decl declares
    # nothing at all, so the block ends up wrapping only the single
    # statement with no declarations of its own -- pure overhead. Fixed
    # by checking whether the resolved reference actually needs
    # materializing (contains "(") before opening the block, at every
    # site with this pattern; axis=1 reductions still always need a
    # block (they always declare their own loop variable), so that path
    # is intentionally left wrapped.
    #
    # Exercises both shapes for to_numpy()/mean(): a bare df (no block
    # needed) and a df[["a","b"]] column-selected reference (still
    # needs one) -- checked directly against the generated source.
    _run_xp2f_compile_diff(
        tmp_path,
        "xpandas_block_skip.py",
        [
            "import pandas as pd",
            "",
            "df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [4.0, 5.0, 6.0]})",
            "",
            "x = df.to_numpy()",
            "print(x)",
            "print(df.mean())",
            "print(df.sum(axis=1))",
            "",
            "y = df[['a', 'b']].to_numpy()",
            "print(y)",
            "print(df[['a', 'b']].mean())",
        ],
    )
    f90_text = (tmp_path / "xpandas_block_skip_p.f90").read_text(encoding="utf-8")
    assert "x = df%values" in f90_text, f90_text
    assert '"a", mean_1d(df%values' in f90_text, f90_text
    assert "block" in f90_text, f90_text  # axis=1 and the df[["a","b"]] cases still need one
    assert "pdf_src" in f90_text, f90_text  # the materialized-temp path is still exercised
