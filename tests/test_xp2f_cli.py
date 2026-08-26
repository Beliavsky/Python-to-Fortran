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
    # arr1 and arr2 are both integer, allocatable (different rank), so
    # xp2f's declaration-coalescing pass may merge them onto one line.
    joined = _join_fortran_continuations(out_text)
    assert any(
        line.strip().startswith("integer, allocatable ::") and "arr2(:,:)" in line
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
    assert "integer, allocatable :: a(:), o(:)" in out_text
    assert "o = 1" in out_text


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
    assert "merge(real(1, kind=dp), b, (a > 2))" in out_text
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
    assert "a = [1, 2, 3]" in out_text
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
    assert "a = reshape([1, 2, 3, 4, 5, 6], [2, 3], order=[2, 1])" in out_text
    assert "b = reshape([1, 2, 3, 4, 5, 6], [2, 3])" in out_text
    assert "real(kind=dp), allocatable :: a(:,:), b(:,:)" in out_text
    assert "real(kind=dp), allocatable :: a(:,:)\n   real(kind=dp), allocatable :: b(:,:)" not in out_text
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
    assert "statistics_quantiles_real(real(x, kind=dp), int(4))" in out_text
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
    assert "random_randrange_int(int(0), int(100), int(5))" in out_text
    assert "random_choice_char(colors)" in out_text
    assert "random_choices_char(colors, int(5))" in out_text
    assert "random_sample_char(colors, int(3))" in out_text
    assert "rnorm(size(arange_int(0, 5, 1)))" in out_text
    assert "int(10) - int(1) + 1" in out_text


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
    assert 'write(*,"(a,f18.6,f18.6)") str_ljust(py_str(k), 6), mean_before, &' in out_text


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
