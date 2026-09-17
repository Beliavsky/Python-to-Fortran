from __future__ import annotations

import ast
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
import fortran_purity as fpurity
import fortran_scan as fscan
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


def test_fortran_post_hoist_module_use_only_falls_back_to_any_use_line_indent() -> None:
    # User-reported real bug (xdelta_gamma.py): the indentation detected
    # for a newly-hoisted `use mod, only: sym` line only ever came from
    # an EXISTING module-level use-only line that ALSO qualifies as
    # mergeable (parseable syms, not `use, intrinsic ::`) -- but a
    # module header can easily have only NON-qualifying use lines (one
    # importing operator(+) overloads, one `use, intrinsic ::`), in
    # which case the indentation fell all the way back to matching
    # `contains`'s own indentation -- unindented, at column 0, in this
    # project's own style -- producing a hoisted `use` line with NO
    # leading whitespace at all, unlike every sibling use/implicit/
    # declaration line around it.
    lines = [
        "module m",
        "   use dataframe_str_index_mod, only: operator(+), operator(-)",
        "   use, intrinsic :: iso_fortran_env, only: real64",
        "   implicit none",
        "   private",
        "contains",
        "pure function f(x) result(y)",
        "   real(kind=8), intent(in) :: x",
        "   real(kind=8) :: y",
        "   use python_mod, only: optval",
        "   y = optval(x, 0.0_8)",
        "end function f",
        "end module m",
    ]

    out = fpost.hoist_module_use_only_imports(lines)
    joined = "\n".join(out)

    assert "\n   use python_mod, only: optval\n" in joined, joined
    assert "\nuse python_mod, only: optval\n" not in joined, joined


def test_fortran_post_keeps_callback_interface_body_tight() -> None:
    # User-reported real gap: ensure_blank_lines_around_units_and_
    # procedures pads a blank line before/after every function/
    # subroutine declaration line it sees -- but it had no notion of
    # being INSIDE an `interface ... end interface` block, so a
    # callback's own abstract interface (e.g. v_bisect_root's `interface
    # / pure function v_bisect_root_f_cb_if(x) result(r) / ... / end
    # function v_bisect_root_f_cb_if / end interface`) got the SAME
    # padding as a real top-level procedure: a blank line right after
    # "interface" and another right before "end interface", even though
    # that whole block is a tight, purely declarative unit.
    #
    # Fixed by tracking interface nesting and skipping the spacing logic
    # while inside one -- and, since the padding this pass DOES still
    # want (a blank line separating the enclosing procedure's own
    # signature from its interface block) was otherwise missing, a
    # blank line is now inserted before "interface" itself instead.
    lines = [
        "pure function v_bisect_root(f, a, b) result(v_bisect_root_result)",
        "   interface",
        "      pure function v_bisect_root_f_cb_if(x) result(r)",
        "         import dp",
        "         real(kind=dp), intent(in) :: x",
        "         real(kind=dp) :: r",
        "      end function v_bisect_root_f_cb_if",
        "   end interface",
        "   procedure(v_bisect_root_f_cb_if) :: f",
        "   real(kind=dp), intent(in) :: a, b",
        "   real(kind=dp) :: v_bisect_root_result",
        "   v_bisect_root_result = f(a) + f(b)",
        "end function v_bisect_root",
    ]

    text = "\n".join(fpost.ensure_blank_lines_around_units_and_procedures(lines))

    assert "\n\n   interface\n      pure function v_bisect_root_f_cb_if(x)" in text, text
    assert "end function v_bisect_root_f_cb_if\n   end interface" in text, text
    assert "interface\n\n" not in text, text
    assert "\n\n   end interface" not in text, text


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
    # `c` is a variable, not a string literal, so the default separator
    # can't be folded into it at compile time and stays its own item.
    assert 'print *, "name:", " ", c' in out_text


def test_xp2f_multiarg_print_folds_default_separator_into_next_literal(tmp_path: Path) -> None:
    # User-reported real example, from xdelta_gamma.py: a run of
    # label/value pairs like `print("V0 =", V0, "delta0 =", delta0,
    # "gamma0 =", gamma0)` used to emit a bare `" "` as its own print
    # item before each label (needed only to separate it from the
    # previous numeric value, which Fortran's own list-directed output
    # doesn't do for adjacent character items the way it does for
    # numerics). Since the label right after the separator is ALWAYS a
    # compile-time string literal here, the space can be folded directly
    # into that literal instead -- `"V0 =", V0, " ", "delta0 =", delta0`
    # simplifies to `"V0 =", V0, " delta0 =", delta0`, same output, one
    # fewer print item.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xprint_fold_sep_small.py"
    src.write_text(
        "\n".join(
            [
                "V0 = 1.23",
                "delta0 = 4.56",
                "gamma0 = 7.89",
                'print("V0 =", V0, "delta0 =", delta0, "gamma0 =", gamma0)',
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
    out_text = (tmp_path / "xprint_fold_sep_small_p.f90").read_text(encoding="utf-8")
    assert 'print *, "V0 =", V0, " delta0 =", delta0, " gamma0 =", gamma0' in out_text


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
    # The ";;" separator before "y" is a literal-to-literal join, so it's
    # folded directly into the following string literal rather than
    # emitted as its own print item (see the "name:" test below).
    assert '";;y"' in out_text
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


def test_xp2f_function_result_variable_uses_short_generic_name(tmp_path: Path) -> None:
    # User-requested style change: a function's own RESULT variable is
    # named short and generic (`func_res`) rather than the old, verbose
    # `{fn_name}_result` scheme -- unreadable for a long/compound
    # function name like `pnl_piecewise_quad_linear_two_sided_result`.
    # Reusing `func_res` across every function in the file is safe: it
    # only needs to be unique within each function's own scope.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfunc_res_name.py"
    src.write_text(
        "\n".join(
            [
                "def square(x):",
                "    return x * x",
                "",
                "def cube(y):",
                "    return y * y * y",
                "",
                "print(square(3.0))",
                "print(cube(2.0))",
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
    out_text = (tmp_path / "xfunc_res_name_p.f90").read_text(encoding="utf-8")
    assert out_text.count("result(func_res)") == 2, out_text
    assert "_result" not in out_text


def test_xp2f_function_result_variable_avoids_colliding_with_own_arg(tmp_path: Path) -> None:
    # If a function's OWN dummy argument is literally named `func_res`,
    # the synthesized result variable must fall back to `func_res_1`
    # rather than colliding with it -- unlike the old `{fn_name}_result`
    # scheme, `func_res` is no longer automatically unique.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfunc_res_collision.py"
    src.write_text(
        "\n".join(
            [
                "def double_it(func_res):",
                "    return func_res * 2.0",
                "",
                "print(double_it(3.0))",
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
    out_text = (tmp_path / "xfunc_res_collision_p.f90").read_text(encoding="utf-8")
    assert "result(func_res_1)" in out_text, out_text


def test_xp2f_np_linspace_uses_dedicated_helper_function(tmp_path: Path) -> None:
    # User-reported real example (xdelta_gamma.py): `np.linspace(60.0,
    # 140.0, 161)` used to expand inline into a hand-derived
    # `start + (stop - start) * real(arange_int(...), kind=dp) /
    # real(max(1, num - 1), kind=dp)` formula -- unreadable, and an
    # outlier among its own sibling numpy generators (logspace,
    # geomspace, cumsum, cumprod all already get a dedicated python.f90
    # helper function). Now calls a real `linspace(start, stop, num)`
    # helper directly, matching that established pattern.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlinspace_helper.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "S = np.linspace(60.0, 140.0, 161)",
                "print(S[0])",
                "print(S[-1])",
                "print(len(S))",
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
    out_f90 = (tmp_path / "xlinspace_helper_p.f90").read_text(encoding="utf-8")
    assert "S = linspace(60.0_dp, 140.0_dp, 161)" in out_f90, out_f90
    assert "arange_int" not in out_f90, out_f90


def test_xp2f_np_linspace_helper_handles_single_point_and_int_literals(tmp_path: Path) -> None:
    # Edge cases the dedicated helper must reproduce exactly from the
    # old inline formula's own behavior: num=1 returns just `start`
    # (matching numpy's own linspace semantics), and integer-literal
    # start/stop get coerced to real rather than passed as integers to
    # a real dummy argument (a genuine type mismatch, unlike an
    # ordinary arithmetic expression where Fortran converts implicitly).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlinspace_edge_cases.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "a = np.linspace(0, 10, 5)",
                "b = np.linspace(2.5, 2.5, 1)",
                "print(a)",
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
    out_f90 = (tmp_path / "xlinspace_edge_cases_p.f90").read_text(encoding="utf-8")
    assert "linspace(real(0, kind=dp), real(10, kind=dp), 5)" in out_f90, out_f90
    assert "linspace(2.5_dp, 2.5_dp, 1)" in out_f90, out_f90


def test_xp2f_removes_allocated_guard_for_fresh_dataframe_component(tmp_path: Path) -> None:
    # User-reported real example (xdelta_gamma.py): a freshly built
    # DataFrame's own `df%values`/`df%index` allocation is preceded by
    # a provably-always-false `if (allocated(...))` guard -- nothing
    # earlier in the procedure could possibly have already allocated
    # them. The guard (and now-unreachable deallocate) is dropped,
    # leaving just the allocate.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xdf_fresh_guard.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "import numpy as np",
                "",
                "df = pd.DataFrame({'a': np.array([1.0, 2.0, 3.0])})",
                "print(df)",
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
    out_f90 = (tmp_path / "xdf_fresh_guard_p.f90").read_text(encoding="utf-8")
    assert "allocated(df" not in out_f90, out_f90
    # The two now-guardless allocates end up genuinely adjacent, so a
    # separate pass (see test_xp2f_combines_consecutive_single_entity_
    # allocates) fuses them into one statement.
    assert "allocate(df%values(" in out_f90, out_f90
    assert ", df%index(" in out_f90, out_f90


def test_xp2f_keeps_allocated_guard_when_dataframe_reassigned(tmp_path: Path) -> None:
    # Safety case for the above: a SECOND construction of the same
    # DataFrame variable (after a whole-variable reassignment) must
    # keep its guard -- the base `df = ...` reassignment could have
    # copied in an already-allocated component from elsewhere, so the
    # "provably first allocation" argument no longer holds.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xdf_reassign_guard.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "import numpy as np",
                "",
                "def make_df(vals):",
                "    return pd.DataFrame({'a': vals})",
                "",
                "df = make_df(np.array([1.0, 2.0, 3.0]))",
                "df = make_df(np.array([4.0, 5.0]))",
                "print(df)",
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
    out_f90 = (tmp_path / "xdf_reassign_guard_p.f90").read_text(encoding="utf-8")
    assert out_f90.count("if (allocated(df%values)) deallocate(df%values)") == 1, out_f90
    assert out_f90.count("if (allocated(df%index)) deallocate(df%index)") == 1, out_f90


def test_xp2f_combines_consecutive_single_entity_allocates(tmp_path: Path) -> None:
    # User-reported real example (xdelta_gamma.py): once the guards
    # above are dropped, a freshly built DataFrame's `df%values`/
    # `df%index` allocations become two genuinely adjacent, otherwise-
    # untouched single-entity `allocate(...)` statements -- Fortran's
    # ALLOCATE accepts any number of comma-separated allocate-objects
    # in one statement, executing identically to allocating them one at
    # a time, so the two fuse into
    # `allocate(df%values(...), df%index(...))`.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xdf_combine_allocates.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "import numpy as np",
                "",
                "df = pd.DataFrame({'a': np.array([1.0, 2.0]), 'b': np.array([3.0, 4.0])})",
                "print(df)",
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
    out_f90 = (tmp_path / "xdf_combine_allocates_p.f90").read_text(encoding="utf-8")
    assert "allocate(df%values(size(df_a), 2), df%index(size(df_a)))" in out_f90, out_f90


def test_xp2f_does_not_combine_allocates_with_source_keyword(tmp_path: Path) -> None:
    # Safety case: allocate statements carrying a source=/mold=/stat=
    # keyword argument apply that option to the WHOLE statement, so
    # they can't be blindly fused if they'd otherwise differ -- three
    # separate np.zeros(...) allocations (each with its own source=)
    # must stay three separate allocate statements.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xalloc_source_kw.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "a = np.zeros(3)",
                "b = np.zeros(4)",
                "a[0] = 1.0",
                "b[0] = 2.0",
                "print(a, b)",
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
    out_f90 = (tmp_path / "xalloc_source_kw_p.f90").read_text(encoding="utf-8")
    assert "allocate(a(3), source=0.0_dp)" in out_f90, out_f90
    assert "allocate(b(4), source=0.0_dp)" in out_f90, out_f90


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


def test_xp2f_falls_back_to_loop_for_listcomp_calling_local_function(tmp_path: Path) -> None:
    # User-reported real failure: `pnl_exact = np.array([bs_straddle_
    # value(float(Si), K, T, sigma, r=r, q=q) - V0 for Si in S])` failed
    # transpilation with "ListComp currently supports only single-
    # generator form" -- a misleading message: it's not about multiple
    # generators at all (this comprehension has exactly one). The
    # inline elementwise ListComp lowering (self.expr()'s ast.Call
    # handling for a ListComp element) only ever accepts a few narrow
    # call shapes (str/int/float/bool applied directly to the bare loop
    # variable, max/min, or a bare 0-arg strip method) -- calling ANY
    # user-defined function fails identically, even the simplest
    # `[f(v) for v in arr]`, since that inline path relies on every
    # operator/call in the element being Fortran-ELEMENTAL, which a
    # local function generally isn't (elemental promotion is opt-in,
    # postprocessing-only, and not decided yet this early anyway).
    #
    # Fixed with a new EARLY (pre-prescan) tree-rewrite pass,
    # rewrite_listcomp_array_assign_calls_to_loop: when a `TARGET =
    # np.array([ELT for VAR in ITERABLE])` assignment's ELT contains a
    # call the inline lowering can't possibly support, it's rewritten
    # into the equivalent explicit loop
    #     TARGET = np.empty(len(ITERABLE))
    #     for LC_IDX, VAR in enumerate(ITERABLE):
    #         TARGET[LC_IDX] = ELT
    # reusing this project's own already-correct enumerate/For/
    # Subscript-assignment codegen. Must run BEFORE this project's own
    # prescan (which decides every local variable's Fortran declaration
    # from the ORIGINAL tree) -- doing this synthesis later, live during
    # codegen, was tried first and produces a variable with no IMPLICIT
    # type, since prescan never saw it.
    #
    # Deliberately uses non-case-colliding names (`Sv`/`si`, not `S`/
    # `s`): Fortran is case-insensitive, and this project has a
    # SEPARATE, pre-existing, unrelated bug where a for-loop variable
    # differing from another in-scope name ONLY by case silently reads
    # as zero -- not this fix's concern, and reproducible with a bare
    # `for s in S: total = total + s` with no list comprehension
    # involved at all.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xlistcomp_local_func_call.py",
        [
            "import numpy as np",
            "",
            "def f(x, y=1.0):",
            "    return x + y",
            "",
            "Sv = np.linspace(1.0, 5.0, 5)",
            "out = np.array([f(float(si), y=2.0) for si in Sv])",
            "print(out)",
        ],
    )
    out_f90 = (tmp_path / "xlistcomp_local_func_call_p.f90").read_text(encoding="utf-8")
    # User-reported further simplification: when this rewrite's whole
    # generated loop body is still exactly the one `TARGET[idx] = ELT`
    # statement it produces, idx (and the enumerate value variable) are
    # both single-use, read-only aliases for values already directly
    # expressible via the Fortran loop counter itself -- so they're
    # fused away entirely rather than synthesized as their own
    # variables: `out_(i) = f(x=Sv(i), y=2.0_dp)`, no idx_N and no
    # separate `si = ...` assignment at all. Sv itself is never
    # mutated anywhere in this program, so on top of that fusion, the
    # `iter_tmp` materialization step is ALSO skipped entirely (a
    # second, independent user-reported simplification) -- Sv is
    # indexed directly rather than through a defensive copy of it.
    assert "idx_" not in out_f90
    assert "iter_tmp" not in out_f90
    assert re.search(r"\bout_\(i\) = f\(x=Sv\(i\),\s*y=2\.0_dp\)", out_f90, re.IGNORECASE), out_f90
    # User-reported preference: the block-local do-loop counter that
    # walks the source array should be a short, simple name ("i")
    # rather than a Python-source-line-number-derived one
    # ("i_iter_175") -- it's a synthesized helper that has nothing to
    # do with the original source, so a line number embedded in it is
    # just noise.
    assert re.search(r"\bdo i = 1, size\(Sv\)", out_f90), out_f90
    assert "i_iter_" not in out_f90


def test_xp2f_block_local_loop_counter_avoids_colliding_with_outer_i(tmp_path: Path) -> None:
    # The short "i" name picked for a block-local do-loop counter (see
    # the test above) must never collide with a REAL variable already
    # named "i" in the enclosing procedure -- falls back to "i_1"
    # instead of silently shadowing it.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xlistcomp_i_collision.py",
        [
            "import numpy as np",
            "",
            "def f(v):",
            "    return v * 2.0",
            "",
            "i = 7",
            "arr = np.array([1.0, 2.0, 3.0])",
            "out = np.array([f(x) for x in arr])",
            "print(i)",
            "print(out)",
        ],
    )
    out_f90 = (tmp_path / "xlistcomp_i_collision_p.f90").read_text(encoding="utf-8")
    # arr is a compile-time constant (never mutated), so the source
    # array is indexed directly rather than through a defensive
    # `iter_tmp` copy of it (a separate, later optimization).
    assert re.search(r"\bdo i_1 = 1, size\(arr\)", out_f90), out_f90


def test_xp2f_listcomp_loop_fusion_handles_multiple_uses_of_loop_var(tmp_path: Path) -> None:
    # The loop-variable value is substituted at EVERY occurrence in the
    # element expression, not just a first/single one.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlistcomp_fuse_multiuse.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(v):",
                "    return v * 2.0",
                "",
                "arr = np.array([1.0, 2.0, 3.0])",
                "out = np.array([f(v) + v for v in arr])",
                "print(out)",
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
    out_f90 = (tmp_path / "xlistcomp_fuse_multiuse_p.f90").read_text(encoding="utf-8")
    # arr is never mutated anywhere in this program, so on top of the
    # idx/val fusion, the `iter_tmp` materialization step is ALSO
    # skipped entirely -- arr is indexed directly.
    assert "iter_tmp" not in out_f90
    assert re.search(
        r"\bout_\(i\) = f\(arr\(i\)\) \+ arr\(i\)", out_f90, re.IGNORECASE
    ), out_f90


def test_xp2f_hand_written_enumerate_loop_never_fuses_away_its_variables(tmp_path: Path) -> None:
    # The single-statement-body fusion above is restricted to loops the
    # listcomp-array-assign rewrite itself generates (marked internally
    # via `_synth_single_assign_loop`) -- a HAND-WRITTEN `for idx, val in
    # enumerate(arr):` loop, even one with the exact same single-
    # statement-body shape, must keep its own idx/val variables, since
    # unlike the rewrite's synthetic names, a user's own loop variables
    # can legally be read again after the loop ends (as this test does).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xhandwritten_enumerate.py"
    src.write_text(
        "\n".join(
            [
                "arr = [1.0, 2.0, 3.0]",
                "out = [0.0, 0.0, 0.0]",
                "for idx, val in enumerate(arr):",
                "    out[idx] = val * 2.0",
                "print(idx)",
                "print(out)",
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
    out_f90 = (tmp_path / "xhandwritten_enumerate_p.f90").read_text(encoding="utf-8")
    assert re.search(r"\bidx = i - 1\b", out_f90), out_f90
    # arr is never mutated anywhere in this program either, so (a
    # separate, independent optimization from the idx/val fusion this
    # test is actually about) it's indexed directly rather than through
    # a defensive `iter_tmp` copy of it.
    assert "iter_tmp" not in out_f90
    assert re.search(r"\bval = arr\(i\)", out_f90), out_f90
    assert re.search(r"\bprint \*, idx\b", out_f90), out_f90


def test_xp2f_iter_source_array_copy_kept_when_mutated_in_loop_body(tmp_path: Path) -> None:
    # User-reported real example (xdelta_gamma.py): iterating a plain
    # array variable never mutated anywhere in the loop needs no
    # defensive `iter_tmp` copy -- it's indexed directly. But when the
    # SAME array IS written to somewhere in the loop's own body (here,
    # `arr[idx] = ...`), the copy must be kept: without it, later
    # iterations would read back values already overwritten by earlier
    # ones instead of the array's original contents, changing the
    # answer -- confirmed by --run-both matching Python's own semantics
    # exactly (Python's `enumerate(arr)` also iterates a live view, but
    # every value here is read into `val` before `arr` is written, so
    # a real behavior change would show up as a genuine PASS/FAIL
    # divergence, not just cosmetic).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xiter_src_mutated_in_body.py"
    src.write_text(
        "\n".join(
            [
                "arr = [1.0, 2.0, 3.0]",
                "out = [0.0, 0.0, 0.0]",
                "for idx, val in enumerate(arr):",
                "    out[idx] = val * 2.0",
                "    arr[idx] = val + 100.0",
                "print(out)",
                "print(arr)",
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
    out_f90 = (tmp_path / "xiter_src_mutated_in_body_p.f90").read_text(encoding="utf-8")
    assert "iter_tmp = arr" in out_f90, out_f90


def test_xp2f_elemental_call_loop_vectorizes_with_elemental_flag(tmp_path: Path) -> None:
    # User-reported real example (xdelta_gamma.py --elemental): once
    # bs_straddle_value gets promoted to `pure elemental`, the whole
    # per-element loop this project's own listcomp-array-assign rewrite
    # produces collapses to a single vectorized statement -- Fortran
    # elemental calls broadcast automatically over a whole array
    # argument, with IDENTICAL syntax to the scalar case. The `allocate`
    # this rewrite also emits becomes unnecessary too (an allocatable
    # array auto-allocates on assignment from a conformable RHS shape)
    # and is dropped along with the loop.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xelem_vectorize.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def f(v):",
                "    return v * 2.0 - 1.0",
                "",
                "arr = np.array([1.0, 2.0, 3.0])",
                "out = np.array([f(v) for v in arr])",
                "print(out)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--elemental", "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    out_f90 = (tmp_path / "xelem_vectorize_p.f90").read_text(encoding="utf-8")
    assert "pure elemental function f" in out_f90, out_f90
    assert "allocate(out" not in out_f90, out_f90
    assert "do i" not in out_f90, out_f90
    assert re.search(r"\bout_\s*=\s*f\(arr\)", out_f90, re.IGNORECASE), out_f90


def test_xp2f_elemental_call_loop_vectorizes_nested_all_elemental_chain(tmp_path: Path) -> None:
    # A call whose OWN argument is itself another call is still safe to
    # vectorize as long as EVERY level of nesting, all the way out to
    # the loop body's top level, is a confirmed-elemental function --
    # `combiner(helper(v), 5.0)` becomes `combiner(helper(arr), 5.0_dp)`.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xelem_nested_safe.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def helper(v):",
                "    return v + 1.0",
                "",
                "def combiner(a, b):",
                "    return a * 2.0 + b",
                "",
                "arr = np.array([1.0, 2.0, 3.0])",
                "out = np.array([combiner(helper(v), 5.0) for v in arr])",
                "print(out)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--elemental", "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    out_f90 = (tmp_path / "xelem_nested_safe_p.f90").read_text(encoding="utf-8")
    assert "do i" not in out_f90, out_f90
    assert re.search(r"\bout_\s*=\s*combiner\(helper\(arr\),\s*5\.0_dp\)", out_f90, re.IGNORECASE), out_f90


def test_xp2f_elemental_call_loop_declines_when_outer_call_not_elemental(tmp_path: Path) -> None:
    # The mirror-image safety case: `not_elemental(helper(v), fixed)` --
    # helper() alone looks safe (it IS elemental), but it's wrapped by
    # not_elemental(), which takes an array argument (fixed) and so can
    # never itself be elemental. Vectorizing would pass an array where
    # not_elemental expects a scalar -- correctly declined, keeping the
    # safe per-element loop. (Regression test for a bug caught and fixed
    # before shipping: an earlier version of this check only verified
    # the INNERMOST enclosing call, missing that the call it's nested
    # inside also needs to be safe.)
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xelem_nested_unsafe.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def helper(v):",
                "    return v + 1.0",
                "",
                "def not_elemental(a, arr2):",
                "    return a + arr2[0]",
                "",
                "fixed = np.array([100.0, 200.0])",
                "arr = np.array([1.0, 2.0, 3.0])",
                "out = np.array([not_elemental(helper(v), fixed) for v in arr])",
                "print(out)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--elemental", "--run-both"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout
    out_f90 = (tmp_path / "xelem_nested_unsafe_p.f90").read_text(encoding="utf-8")
    assert "pure elemental function helper" in out_f90, out_f90
    assert "pure function not_elemental" in out_f90, out_f90
    assert "elemental function not_elemental" not in out_f90, out_f90
    assert re.search(r"\bdo i = 1, size\(arr\)", out_f90), out_f90


def test_fortran_rewrite_listcomp_array_assign_preserves_vectorized_form_when_possible() -> None:
    # Regression test (direct unit test of rewrite_listcomp_array_assign_
    # calls_to_loop): confirms the new explicit-loop fallback is used
    # ONLY when genuinely needed -- a pure-arithmetic comprehension
    # (already fully supported by the existing inline elementwise
    # lowering) must be left completely untouched by this rewrite, so it
    # still gets the more idiomatic vectorized Fortran form
    # (`out = S + 1.0`) instead of an unnecessary loop.
    src = "S = [0.0]\nout = np.array([s + 1.0 for s in S])\n"
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_listcomp_array_assign_calls_to_loop(tree)
    dumped = ast.dump(new_tree)
    assert "ListComp" in dumped, dumped
    assert "For(" not in dumped, dumped


def test_fortran_rewrite_listcomp_array_assign_rewrites_unsupported_call() -> None:
    # Companion direct unit test: a comprehension calling an arbitrary
    # (non-builtin) function IS rewritten into the explicit alloc + for/
    # enumerate/Subscript-assign form.
    src = "S = [0.0]\nout = np.array([f(s) for s in S])\n"
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_listcomp_array_assign_calls_to_loop(tree)
    dumped = ast.dump(new_tree)
    assert "ListComp" not in dumped, dumped
    assert "For(" in dumped, dumped
    assert "enumerate" in dumped, dumped


def test_xp2f_runs_return_of_unsupported_call_listcomp_array(tmp_path: Path) -> None:
    # User-reported real failure: `return np.array([np.dot(x[k:], x[:-k])
    # / denom for k in range(1, nacf + 1)])` (an autocorrelation function)
    # failed with the same misleading "ListComp currently supports only
    # single-generator form" message -- this ONE IS single-generator; the
    # real cause is the SAME one rewrite_listcomp_array_assign_calls_to_
    # loop already handles for a plain assignment (an ELT the inline
    # elementwise lowering can't support, here np.dot with two slice
    # arguments), except this occurrence is the value of a `return`
    # statement rather than an assignment's RHS, which the rewrite didn't
    # cover yet. Fixed by adding a visit_Return alongside visit_Assign,
    # sharing the same detection/loop-building helpers: a synthesized
    # result variable (`lc_res_N`, avoiding collision with real names)
    # takes the assignment target's place, followed by `return` of it.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlistcomp_return_unsupported_call.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def acf(x, nacf):",
                "    x = np.asarray(x, dtype=float)",
                "    x = x - x.mean()",
                "    denom = np.dot(x, x)",
                "    return np.array([",
                "        np.dot(x[k:], x[:-k]) / denom",
                "        for k in range(1, nacf + 1)",
                "    ])",
                "",
                "x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0, 2.0])",
                "rho = acf(x, 4)",
                "print(rho)",
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
    out_f90 = (tmp_path / "xlistcomp_return_unsupported_call_p.f90").read_text(encoding="utf-8")
    assert "result(lc_res_1)" in out_f90, out_f90


def test_fortran_rewrite_listcomp_array_return_rewrites_unsupported_call() -> None:
    # Direct unit test mirroring test_fortran_rewrite_listcomp_array_
    # assign_rewrites_unsupported_call, but for a `return` statement.
    src = "def g(S):\n    return np.array([f(s) for s in S])\n"
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_listcomp_array_assign_calls_to_loop(tree)
    dumped = ast.dump(new_tree)
    assert "ListComp" not in dumped, dumped
    assert "For(" in dumped, dumped
    assert "enumerate" in dumped, dumped
    assert "Return(" in dumped, dumped


def test_xp2f_percent_format_constant_var_in_multi_arg_print(tmp_path: Path) -> None:
    # User-reported real failure: `fmt_s = "%10s"` then a MULTI-argument
    # print, each argument formatting a piece with it --
    # `print(fmt_s % "lag", fmt_s % "sample", fmt_s % "true")` -- produced
    # invalid Fortran (`modulo(fmt_s, "lag")`): the two already-correct
    # Python-%-style-format code paths (the general BinOp Mod lowering,
    # and print()'s single-argument fast path) both only recognize the
    # LEFT operand of `%` as string formatting when it's a literal
    # ast.Constant string -- an opaque Name, even one statically known
    # (via a single top-level assignment) to hold a string, fell straight
    # through to the *arithmetic* modulo() codegen instead, which
    # requires INTEGER/REAL operands.
    #
    # Fixed with a new early tree rewrite, inline_percent_format_
    # constant_vars: a module-level `NAME = "literal string"` assigned
    # exactly once anywhere at module level has every `NAME % ARGS`
    # rewritten to `"literal string" % ARGS`, so the two already-correct
    # sites see the literal they already know how to handle.
    #
    # A SEPARATE bug surfaced once this one was fixed: detect_needed_
    # helpers' own %-format scan only added "py_str" (needed by the
    # substitution codegen for EVERY conversion char, not just %g/%G)
    # when the format string matched a %g/%G specifier specifically --
    # any other spec (here %s) left `use python_mod, only: ...` missing
    # py_str entirely, a "no IMPLICIT type" build failure. Fixed by
    # broadening that check to the full conv_chars set the codegen
    # itself recognizes.
    #
    # A THIRD, width/precision-fidelity gap surfaced once THAT was
    # fixed: this shape (a %-format expression as one of several print()
    # arguments) fell to the generic BinOp Mod lowering's naive py_str(
    # value) wrapping, which ignores width/precision entirely ("%10s" %
    # "lag" produced unpadded "lag", not Python's "       lag") --
    # _fortran_write_for_percent_format (used only for the single-
    # argument `print(fmt % args)` fast path) already builds proper,
    # width/precision-aware Fortran edit descriptors, just never wired
    # up for a %-format argument sharing a print() call with others.
    # Fixed by extracting its descriptor-building loop into a reusable
    # _percent_format_parts helper and giving a %-format argument its
    # own dedicated, descriptor-aware write() in the multi-argument
    # print loop (mirroring how a char-array argument already gets its
    # own dedicated write() there), instead of falling through to the
    # generic, width-blind expression lowering.
    #
    # A related, narrower gap in that SAME shared descriptor builder was
    # caught (via a pre-existing test regressing) and fixed alongside
    # it: the %s/%c/%r conversion branch never used its own parsed width
    # at all (always a bare Fortran `a` descriptor, no padding). A first
    # attempt used a fixed-width `aW` descriptor directly -- WRONG,
    # since Fortran's `aW` output editing TRUNCATES a value longer than
    # W to its leftmost W characters, whereas Python's %Ns only ever
    # pads a SHORTER value and never truncates a longer one (confirmed
    # by test_xp2f_simplifies_format_string_space_literals_end_to_end's
    # own "%10s" % "theoretical" regressing to "theoretica"). Fixed
    # properly by routing through this project's own str_rjust helper
    # (pads to max(width, actual length) -- can only ever pad) with a
    # bare, width-less `a` descriptor around its already-correctly-sized
    # result, instead of a fixed-width descriptor on the raw value.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpercent_format_const_var.py"
    src.write_text(
        "\n".join(
            [
                "fmt_s = '%10s'",
                "print(fmt_s % 'lag', fmt_s % 'sample', fmt_s % 'true')",
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
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr
    out_f90 = (tmp_path / "xpercent_format_const_var_p.f90").read_text(encoding="utf-8")
    assert "modulo(fmt_s" not in out_f90, out_f90
    assert re.search(r"\buse python_mod, only:[^\n]*\bstr_rjust\b", out_f90), out_f90
    assert 'str_rjust("lag", 10)' in out_f90, out_f90


def test_xp2f_multi_arg_print_percent_format_mixed_numeric_width_precision(tmp_path: Path) -> None:
    # Companion regression test for the same width/precision-fidelity
    # fix, exercising the mixed int/float-with-width-and-precision case
    # from the ORIGINAL user-reported script (examples/xar_acf.py):
    # `print("%10d" % (i + 1), "%10.4f" % x, "%10.4f" % y)` -- three
    # %-format arguments in one print() call, none of them the print()
    # call's sole argument.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xpercent_format_mixed_numeric.py",
        [
            "for i in range(3):",
            "    print('%10d' % (i + 1), '%10.4f' % (i * 1.5), '%10.4f' % (i * 2.5))",
        ],
    )


def test_fortran_inline_percent_format_constant_vars_rewrites_name_operand() -> None:
    # Direct unit test of inline_percent_format_constant_vars: a
    # module-level, single-assignment string constant used as the LEFT
    # operand of `%` is replaced by its literal value.
    src = "fmt_s = '%10s'\nout = fmt_s % 'lag'\n"
    tree = ast.parse(src)
    new_tree = xp2f.inline_percent_format_constant_vars(tree)
    dumped = ast.dump(new_tree)
    assert "Constant(value='%10s')" in dumped, dumped
    # Reassigned anywhere -> no longer safe to inline (left untouched).
    src2 = "fmt_s = '%10s'\nfmt_s = '%5d'\nout = fmt_s % 'lag'\n"
    tree2 = ast.parse(src2)
    new_tree2 = xp2f.inline_percent_format_constant_vars(tree2)
    dumped2 = ast.dump(new_tree2)
    assert "BinOp(left=Name(id='fmt_s'" in dumped2, dumped2


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
    # `a` and `b` are both rank-2 INTEGER literals (via reshape of a
    # plain int list -- numpy's own reshape([1,...,6], (2,3)) gives an
    # int64 array, not real) that are never reassigned, so xp2f's
    # constant-promotion pass turns each into a named PARAMETER with an
    # explicit shape and the reshape() baked directly into the
    # declaration, rather than a separate allocatable + assignment.
    # `a` (no explicit order=, numpy's own row-major default) gets an
    # explicit order=[2, 1] (Fortran's RESHAPE fills its own native
    # column-major way otherwise); `b` (explicit order='F') doesn't.
    joined = _join_fortran_continuations(out_text)
    assert "integer, parameter :: a(2,3) = reshape([1, 2, 3, 4, 5, 6], [2, 3], order=[2, 1])" in joined
    assert "integer, parameter :: b(2,3) = reshape([1, 2, 3, 4, 5, 6], [2, 3])" in joined
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


def test_xp2f_rename_conflicting_call_variable_preserves_call_statement_keyword(tmp_path: Path) -> None:
    # Regression test: user-reported real example -- a Python function
    # with a LOCAL VARIABLE (here, one of a tuple return's elements)
    # literally named `call` (a valid Python identifier, but a reserved
    # Fortran keyword) gets renamed to `call_` by rename_conflicting_
    # identifiers, correctly, everywhere `call` appears as a VARIABLE
    # reference. But that rename is a blanket, word-boundary text
    # substitution with no guard excluding the actual Fortran CALL
    # STATEMENT keyword (`call subname(...)`) -- which is ALSO just the
    # bare word "call" followed by whitespace then an identifier. Every
    # call site invoking such a function got corrupted from
    # `call subname(...)` into the syntactically invalid `call_
    # subname(...)`. Fixed by recognizing "call" immediately followed by
    # "IDENTIFIER(" as always being the statement keyword, never a
    # variable reference, and leaving it untouched.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xcall_keyword_var.py",
        [
            "def split_call_put(x):",
            "    call = x + 1.0",
            "    put = x - 1.0",
            "    return call, put",
            "",
            "def total(x):",
            "    c, p = split_call_put(x)",
            "    return c + p",
            "",
            "print(total(5.0))",
        ],
    )
    out_f90 = (tmp_path / "xcall_keyword_var_p.f90").read_text(encoding="utf-8")
    assert re.search(r"^\s*call\s+split_call_put\(", out_f90, re.MULTILINE), out_f90
    assert "call_ split_call_put" not in out_f90, out_f90


def test_xp2f_disambiguates_tuple_return_repeating_same_variable_name(tmp_path: Path) -> None:
    # Regression test: user-reported real example -- `return S0 + x_L,
    # S0 + x_R, gamma0, gamma0` (the SAME local variable returned twice
    # in one tuple, legal Python) produced a Fortran subroutine
    # declaring the SAME dummy-argument name ("gamma0") twice in its own
    # formal argument list -- "Duplicate symbol 'gamma0' in formal
    # argument list", a compile error. The out-parameter-naming logic
    # (in two parallel places: the pre-pass that predicts a local
    # function's out-names for call sites processed before it, and the
    # pass that actually emits its signature) already guarded against a
    # returned name colliding with one of the function's OWN parameters,
    # but never against colliding with an EARLIER tuple element's own
    # chosen out-name. Fixed by falling back to the same disambiguated
    # `funcname_out_N` name already used for the args-collision case.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xtuple_return_dup_name.py",
        [
            "def bounds(x0, dx):",
            "    lo = x0 - dx",
            "    hi = x0 + dx",
            "    gamma0 = dx * 2.0",
            "    return lo, hi, gamma0, gamma0",
            "",
            "a, b, g1, g2 = bounds(10.0, 2.0)",
            "print(a, b, g1, g2)",
        ],
    )
    out_f90 = (tmp_path / "xtuple_return_dup_name_p.f90").read_text(encoding="utf-8")
    m = re.search(r"subroutine bounds\(([^)]*)\)", out_f90)
    assert m, out_f90
    formals = [p.strip() for p in m.group(1).split(",")]
    assert len(formals) == len(set(formals)), out_f90


def test_xp2f_renames_case_only_collision_between_global_and_loop_variable(tmp_path: Path) -> None:
    # User-reported real bug (found while verifying an earlier fix, on a
    # SEPARATE file where the user's own array/loop-variable naming
    # happened to collide only by case) -- Fortran is case-insensitive,
    # Python isn't. Bare reproduction: `for s in S: total = total + s`,
    # where `S` (module-level array) and `s` (for-loop variable) both
    # resolve to the SAME Fortran identifier, silently gave 0.0 instead
    # of the correct sum -- no compile error, just a silently wrong
    # answer.
    #
    # Root cause: the codegen's own case-insensitive name-collision
    # table (_aliased_name) already exists and, used consistently,
    # already prevents this -- but a for-loop's own target-variable
    # assignment writes the raw Python name directly rather than
    # resolving it through that same table, so the loop var's every
    # OTHER reference resolved to a disambiguated alias while its own
    # loop-bound write silently landed on a different, never-otherwise-
    # touched Fortran variable.
    #
    # User's own suggestion (rather than hunting down every possibly-
    # incomplete emission site individually): "maybe the python code
    # should be rewritten internally ... before translation." Fixed
    # exactly that way: a new early tree-rewrite pass,
    # rewrite_case_insensitive_name_collisions, renames every spelling
    # but the first-bound one within each of this project's own actual
    # Fortran scopes (the module-level script becomes one PROGRAM; each
    # function its own separate procedure) whenever two Python names in
    # the SAME such scope differ only by case -- guaranteeing the
    # ORIGINAL tree this codegen ever sees never contains the collision
    # to begin with, regardless of which emission sites do or don't
    # consistently use the alias table.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xcase_collision_loop.py",
        [
            "import numpy as np",
            "",
            "S = np.linspace(1.0, 5.0, 5)",
            "total = 0.0",
            "for s in S:",
            "    total = total + s",
            "print(total)",
        ],
    )
    out_f90 = (tmp_path / "xcase_collision_loop_p.f90").read_text(encoding="utf-8")
    assert re.search(r"\bS\(", out_f90) or re.search(r"\bS\b", out_f90), out_f90


def test_fortran_rewrite_case_insensitive_name_collisions_leaves_unrelated_scopes_alone() -> None:
    # Companion direct unit test: a case-only collision is renamed ONLY
    # when both spellings are bound in the SAME scope this project's own
    # codegen actually creates (module-level script body, or one
    # function's own params+locals) -- a function parameter that only
    # case-insensitively collides with an UNRELATED module-level global
    # (different, non-overlapping Fortran program units; Fortran's own
    # scoping already lets a dummy argument safely shadow a host-
    # associated global of the same name with no rename needed, per the
    # existing, separate test
    # test_xp2f_local_function_param_case_insensitive_collision_with_
    # module_global) must be left untouched by this pass.
    src = (
        "PRICE = 100.0\n"
        "def scale(price, factor):\n"
        "    return price * factor\n"
    )
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_case_insensitive_name_collisions(tree)
    dumped = ast.dump(new_tree)
    assert "_cs" not in dumped, dumped

    # But two names colliding WITHIN the same scope (both module-level,
    # here) ARE renamed, with the first-bound spelling (source order)
    # left untouched.
    src2 = "S = 1.0\nfor s in [1, 2, 3]:\n    print(s)\n"
    tree2 = ast.parse(src2)
    new_tree2 = xp2f.rewrite_case_insensitive_name_collisions(tree2)
    dumped2 = ast.dump(new_tree2)
    assert "id='S'" in dumped2, dumped2
    assert "id='s'" not in dumped2, dumped2
    assert "s_cs" in dumped2, dumped2


def test_xp2f_local_function_param_same_name_as_unrelated_global_array_stays_scalar(
    tmp_path: Path,
) -> None:
    # User-reported real failure (xdelta_gamma.py's bs_call_put_price/
    # bs_straddle_value): a local function's OWN parameter can share a
    # spelling with an entirely unrelated top-level global array (here,
    # both named "S") without the two ever being the same binding --
    # Python scoping means the parameter always shadows the global
    # within the function's own body. This project's own call-site rank-
    # inference (used to guess an UNANNOTATED local function's parameter
    # ranks) had a name-based fallback that ignored that scoping rule: a
    # helper (`_name_direct_assign_spec`, inside `_local_return_maps`'s
    # caller in xp2f.py) checked "is this name a known module-level
    # constant?" BEFORE checking "is this name actually one of the
    # CALLING function's own parameters?" -- so whenever a local
    # function's parameter happened to share a spelling with a genuine
    # top-level global, the global's rank leaked onto the (unrelated)
    # parameter's inferred rank, even though the function was never
    # called with an array anywhere. That corrupted the function's own
    # Fortran signature (S(:) instead of scalar S), which then cascaded
    # into every caller passing it a scalar -- including a tuple-return
    # helper's own local variables receiving the promoted callee's
    # output, producing "Rank mismatch in argument ... (rank-1 and
    # scalar)" at compile time. Fixed by checking "is `_name` one of
    # fn_node's own parameters?" FIRST, unconditionally ahead of the
    # same-named-global fallback.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xlocal_param_global_name_collision.py",
        [
            "import numpy as np",
            "",
            "def bs_call_put_price(S, K):",
            "    call = S + K",
            "    put = K - S",
            "    return call, put",
            "",
            "def bs_straddle_value(S, K):",
            "    c, p = bs_call_put_price(S, K)",
            "    return c + p",
            "",
            "S0 = 100.0",
            "K = 100.0",
            "V0 = bs_straddle_value(S0, K)",
            "",
            "S = np.linspace(60.0, 140.0, 5)",
            "pnl = np.array([bs_straddle_value(float(Si), K) - V0 for Si in S])",
            "print(V0)",
            "print(pnl)",
        ],
    )


def test_xp2f_rename_conflicting_call_variable_preserves_type_bound_call_statement(
    tmp_path: Path,
) -> None:
    # Real trigger found alongside the rank-collision fix above, in the
    # same file (xdelta_gamma.py): a Python local variable literally
    # named "call" (from `call, put = ...`) forces
    # rename_conflicting_identifiers to rewrite every reference to
    # "call" as "call_" -- including, wrongly, a TYPE-BOUND procedure
    # invocation elsewhere in the same file (`print(df)` emitted as
    # `call df%display(...)`), corrupting the Fortran CALL STATEMENT
    # keyword into "call_ df%display(...)" (invalid syntax). The
    # existing guard against this (added earlier this session for the
    # plain `call subname(...)` shape) only matched a bare
    # "IDENTIFIER(" tail, missing the "IDENTIFIER%member(" shape a
    # type-bound call uses. Fixed by extending that guard's regex to
    # allow one or more `%member` segments before the final `(`.
    #
    # Checks the generated source and a plain compile directly (rather
    # than the usual _run_xp2f_compile_diff run-diff comparison): pandas'
    # own DataFrame repr and this project's df%display use different
    # float formatting for a printed DataFrame, a separate, pre-existing,
    # purely cosmetic display difference unrelated to this fix.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xcall_var_type_bound_call.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "def bs_price(S, K):",
                "    call = S + K",
                "    put = K - S",
                "    return call, put",
                "",
                "df = pd.DataFrame({'a': [1.0, 2.0, 3.0]})",
                "print(df)",
                "c, p = bs_price(1.0, 2.0)",
                "print(c, p)",
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
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    out_f90 = (tmp_path / "xcall_var_type_bound_call_p.f90").read_text(encoding="utf-8")
    assert re.search(r"\bcall\s+df\s*%\s*display\s*\(", out_f90), out_f90
    assert "call_ df" not in out_f90, out_f90
    assert re.search(r"\bcall_\s*=", out_f90), out_f90


def test_xp2f_compiles_nested_function_used_as_callback(tmp_path: Path) -> None:
    # User-reported real failure (xdelta_gamma.py's f_right/f_left, nested
    # inside piecewise_breakpoints_straddle and passed BY NAME to a
    # root-finder): a Python function defined INSIDE another function and
    # later passed as a bare callback VALUE (not called immediately) is a
    # closure this transpiler previously had no notion of at all -- the
    # codegen silently dropped the nested function's whole body (down to
    # a valueless `return`) while call sites still referenced the never-
    # defined procedure name, producing both "no IMPLICIT type" compile
    # errors and separately-corrupted control flow.
    #
    # Fixed with a new early tree-rewrite,
    # rewrite_nested_callback_functions_to_toplevel: the nested def is
    # hoisted to a fresh top-level sibling, its free (closure) variables
    # renamed to fresh module-level globals (closure_{enclosing}_{var}),
    # and a `global ...; closure_... = local_value` snapshot is inserted
    # right before each call site that hands the nested def off as a
    # value -- reusing this project's own pre-existing, already-correct
    # `global`-write-to-module-variable codegen. This mirrors Python's
    # own late-binding closure semantics (the callback sees whatever the
    # enclosing local held at hand-off time).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xnested_callback_closure.py",
        [
            "def bisect_root(f, a, b):",
            "    fa = f(a)",
            "    for i in range(60):",
            "        mid = (a + b) / 2.0",
            "        fm = f(mid)",
            "        if fa * fm > 0.0:",
            "            a = mid",
            "            fa = fm",
            "        else:",
            "            b = mid",
            "    return (a + b) / 2.0",
            "",
            "def find_root_near(target, lo, hi):",
            "    def diff(x):",
            "        return x * x - target",
            "    return bisect_root(diff, lo, hi)",
            "",
            "result = find_root_near(2.0, 0.0, 10.0)",
            "print(result)",
        ],
    )


def test_xp2f_compiles_minimize_callback_capturing_array_and_shadowed_scalar(
    tmp_path: Path,
) -> None:
    # A fit function naturally closes its one-argument scipy callback over
    # both the observations and fit options.  Exercise three linked pieces:
    # array-valued closure globals retain their rank, an enclosing formal
    # shadows an identically named module variable, and a thin objective
    # wrapper inherits the rank-1 signature of the likelihood's parameter
    # vector.
    for helper_name in ("python.f90", "lbfgsb.f90", "lbfgsb_bridge.f90"):
        shutil.copy2(REPO_ROOT / helper_name, tmp_path / helper_name)
    src = tmp_path / "xminimize_nested_array_closure.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "from scipy.optimize import minimize",
                "",
                "def loss(params, values, fixed):",
                "    mu, = params",
                "    return np.sum((values - mu) ** 2) + fixed",
                "",
                "fixed = 100.0",
                "",
                "def fit(values, fixed=0.0):",
                "    def objective(params):",
                "        return loss(params, values, fixed)",
                "    x0 = np.array([0.0])",
                "    result = minimize(",
                "        objective, x0, method='L-BFGS-B', bounds=[(-10.0, 10.0)]",
                "    )",
                "    return result.x",
                "",
                "values = np.array([1.0, 2.0, 3.0])",
                "print(fit(values, 0.0)[0])",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(XP2F_PATH),
            str(src),
            str(tmp_path / "python.f90"),
            str(tmp_path / "lbfgsb.f90"),
            str(tmp_path / "lbfgsb_bridge.f90"),
            "--compile",
            "--run",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert "Run: PASS" in proc.stdout, proc.stdout + proc.stderr
    out_f90 = (tmp_path / "xminimize_nested_array_closure_p.f90").read_text(
        encoding="utf-8"
    )
    assert re.search(
        r"real\(kind=dp\), allocatable :: closure_fit_values\(:\)", out_f90
    ), out_f90
    assert re.search(r"real\(kind=dp\) :: closure_fit_fixed\b", out_f90), out_f90
    assert re.search(r"function objective\(params\)", out_f90), out_f90
    assert re.search(r"intent\(in\) :: params\(:\)", out_f90), out_f90


def test_fortran_rewrite_nested_callback_functions_hoists_and_threads_closure() -> None:
    # Companion direct unit test: confirms the rewrite actually fires --
    # the nested def moves to module (tree.body) scope, its closure
    # variable is renamed consistently inside the hoisted body, and the
    # enclosing function gets a `global` + snapshot-assignment statement
    # inserted before the call site that hands the callback off.
    src = (
        "def outer(target, lo, hi):\n"
        "    def diff(x):\n"
        "        return x - target\n"
        "    return solve(diff, lo, hi)\n"
    )
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_nested_callback_functions_to_toplevel(tree)
    top_level_names = [
        s.name for s in new_tree.body if isinstance(s, ast.FunctionDef)
    ]
    assert "diff" in top_level_names, top_level_names
    assert top_level_names.index("diff") < top_level_names.index("outer"), top_level_names

    hoisted = next(s for s in new_tree.body if isinstance(s, ast.FunctionDef) and s.name == "diff")
    dumped_hoisted = ast.dump(hoisted)
    assert "closure_outer_target" in dumped_hoisted, dumped_hoisted
    assert "id='target'" not in dumped_hoisted, dumped_hoisted

    outer_fn = next(s for s in new_tree.body if isinstance(s, ast.FunctionDef) and s.name == "outer")
    dumped_outer = ast.dump(outer_fn)
    assert "Global(names=['closure_outer_target'])" in dumped_outer, dumped_outer
    assert "closure_outer_target" in dumped_outer, dumped_outer


def test_fortran_rewrite_nested_callback_functions_leaves_directly_called_nested_def_alone() -> None:
    # A nested def that's only ever CALLED directly (never handed off as
    # a bare value) is left completely untouched -- this is the existing,
    # already-working local-nested-function path, and must not be
    # disturbed by the new closure-hoisting rewrite.
    src = (
        "def outer(x):\n"
        "    def helper(y):\n"
        "        return y * 2.0\n"
        "    return helper(x)\n"
    )
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_nested_callback_functions_to_toplevel(tree)
    top_level_names = [
        s.name for s in new_tree.body if isinstance(s, ast.FunctionDef)
    ]
    assert top_level_names == ["outer"], top_level_names
    outer_fn = new_tree.body[0]
    nested_names = [s.name for s in outer_fn.body if isinstance(s, ast.FunctionDef)]
    assert nested_names == ["helper"], nested_names


def test_fortran_rewrite_nested_callback_functions_declines_on_further_nesting() -> None:
    # Deliberately narrow (matching this session's established pattern):
    # a nested def that itself contains a further nested def/lambda/
    # comprehension is left completely untouched rather than risk an
    # unsound hoist -- it still fails exactly as before, no silent
    # miscompile.
    src = (
        "def outer(target, lo, hi):\n"
        "    def diff(x):\n"
        "        def inner():\n"
        "            return 1.0\n"
        "        return x - target + inner()\n"
        "    return solve(diff, lo, hi)\n"
    )
    tree = ast.parse(src)
    new_tree = xp2f.rewrite_nested_callback_functions_to_toplevel(tree)
    top_level_names = [
        s.name for s in new_tree.body if isinstance(s, ast.FunctionDef)
    ]
    assert top_level_names == ["outer"], top_level_names


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
    # simplify_format_string_space_literals_and_fold_repeats (added
    # later, per a separate user request) now converts each literal
    # `'  '`/`' '` space run into the equivalent `Nx` edit descriptor and
    # folds the resulting repeated `2x, i2` pair -- byte-for-byte the
    # same output, confirmed by this test's own successful --compile
    # (and, more directly, by that pass's own dedicated regression
    # tests' run-diff checks).
    assert 'write(*,"(2(2x, i2), 2x, f10.4, 2x, g14.6, 1x)")' in out_text
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
    call = re.search(r"call f\((tmp_out_1_\d+), (tmp_out_2_\d+), (tmp_out_3_\d+), (tmp_out_4_\d+)\)", _join_fortran_continuations(out_text))
    assert call is not None, out_text
    tz, tx1, tx2, ty = call.groups()
    assert f"z = {tz}" in out_text
    assert f"y = {ty}" in out_text
    # The postprocessor combines adjacent element assignments into a section.
    assert f"x(1:2) = [{tx1}, {tx2}]" in out_text


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
    # simplify_redundant_nested_arith_parens (pre-existing, unrelated to
    # any recent change) flattens a call's own redundant argument-
    # wrapping parens -- `sqrt((a**2 + b**2))` -> `sqrt(a**2 + b**2)`,
    # mathematically identical, just without the doubled-up parens this
    # assertion was originally written against.
    assert "sqrt(a**2 + b**2)" in out_text, out_text


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


def test_xp2f_run_diff_tolerates_close_values_in_label_equals_value_tokens(tmp_path: Path) -> None:
    # Regression test: a "label=value" printed token (e.g. Python's
    # "omega=%.6g" % omega -> "omega=0.1") stays fused as ONE token in
    # run-diff's line tokenizer (it only splits on whitespace/comma, not
    # "="). Fortran's default g0-formatted equivalent prints the SAME
    # underlying value at full precision ("omega=0.10000000000000001"),
    # and _tok_close's numeric comparison requires the WHOLE token to
    # parse as a number -- "omega=0.1" fails that check on both sides, so
    # the pair fell straight through to a raw string-inequality mismatch
    # even though 0.1 and 0.10000000000000001 are identical within
    # run-diff's own default tolerance. Real-world trigger: garch_acf.py
    # (a GARCH ACF/autocov helper library on GitHub) prints "omega=%.6g
    # alpha=%.6g beta=%.6g" % (...), which reported "Run diff: DIFF" even
    # though the actual simulated values were bit-for-bit deterministic
    # and identical. Fixed by peeling off a matching "label=" prefix (an
    # IDENTICAL prefix on both sides only -- a differing label, or a
    # label on only one side, is still correctly reported as a mismatch)
    # before the existing numeric-tolerance comparison runs on the
    # trailing value.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xlabeled_float_fmt.py"
    src.write_text(
        "\n".join(
            [
                "omega = 0.1",
                "alpha = 0.1",
                "beta = 0.85",
                'print("omega=%.6g alpha=%.6g beta=%.6g" % (omega, alpha, beta))',
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


def test_xp2f_run_diff_first_mismatch_line_skips_merely_close_lines(tmp_path: Path) -> None:
    # Regression test: the "first mismatch line" diagnostic printed
    # alongside "Run diff: DIFF" used raw `py_lines[i] != ft_lines[i]`
    # string inequality, completely bypassing the tolerance-aware
    # _lines_close/_tok_close comparison the overall MATCH/DIFF verdict
    # already uses. A script whose FIRST line happens to be only
    # numerically-close (e.g. the "label=value" precision case fixed
    # just above) but whose output genuinely diverges further down (the
    # realistic trigger: Python's random/numpy RNG and this transpiler's
    # Fortran RNG runtime are different algorithms, so any
    # Monte-Carlo-style script's later lines are expected to differ even
    # in a perfectly-correct transpile) pointed this diagnostic at the
    # harmless close-but-not-identical first line instead of the actual
    # first genuine divergence -- misleading when debugging a real
    # mismatch. Fixed by skipping a line pair the tolerance-aware
    # _lines_close (applied to just that one line) already considers
    # close, so the diagnostic reports the real divergence instead.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xfirst_mismatch_skips_close.py"
    src.write_text(
        "\n".join(
            [
                "import random",
                "",
                "omega = 0.1",
                'print("omega=%.6g" % omega)',
                "random.seed(1)",
                "print(random.random())",
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
    assert "Run diff: DIFF" in proc.stdout, proc.stdout + proc.stderr
    # Python's random and the Fortran RNG runtime are different
    # algorithms -- line 2 (the random draw) is expected to genuinely
    # differ, and that's what "first mismatch line" should point at, NOT
    # line 1 (the omega= line, merely a formatting-precision difference).
    assert "first mismatch line: 2" in proc.stdout, proc.stdout + proc.stderr


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


def test_xp2f_inlined_sibling_function_using_math_module(tmp_path: Path) -> None:
    # Regression test: a sibling module's own `import math` statement was
    # silently dropped when inline_local_from_imports copied a FunctionDef
    # using math.sqrt(...) into the main script -- collect_math_aliases
    # only ever ast.walk()s the FINAL merged tree, never re-parses the
    # source module a function was inlined from, so it never learned
    # "math" was imported at all unless the importing script *also*
    # happened to write `import math` itself. The identical function
    # defined directly in the main script (no cross-module import
    # involved) always worked; only the inlined-from-a-sibling-module
    # case raised "unsupported call: math.sqrt(...)". Fixed by having
    # inline_local_from_imports also carry the source module's own
    # math/cmath import statement into the merged tree (deduplicated)
    # whenever it actually inlines something from that module.
    (tmp_path / "mathmod.py").write_text(
        "\n".join(
            [
                "import math",
                "",
                "def hypot2(a, b):",
                "    return math.sqrt(a * a + b * b)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    src = tmp_path / "xmathmod.py"
    src.write_text(
        "\n".join(
            [
                "from mathmod import hypot2",
                "",
                "print(hypot2(3.0, 4.0))",
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


def test_xp2f_inlines_transitively_called_sibling_helper(tmp_path: Path) -> None:
    # Regression test: `from module import used_fn` only ever inlined
    # used_fn's own FunctionDef -- if used_fn's body calls ANOTHER
    # function defined in the same sibling module (e.g. a private helper
    # never itself named in the import statement), that callee was never
    # inlined at all, leaving an unqualified call to a name nothing
    # resolves to -- flatly "unsupported call: helper(...)". Fixed by
    # having inline_local_from_imports transitively pull in any other
    # same-module function/constant an inlined function's body
    # references, walking the dependency graph to a fixed point (kept
    # under each dependency's original, unaliased name, matching how the
    # calling function's body already references it unqualified).
    (tmp_path / "transmod.py").write_text(
        "\n".join(
            [
                "def helper(x):",
                "    return x * 2.0",
                "",
                "def used_fn(x):",
                "    return helper(x) + 1.0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    src = tmp_path / "xtransitive.py"
    src.write_text(
        "\n".join(
            [
                "from transmod import used_fn",
                "",
                "print(used_fn(3.0))",
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


def test_xp2f_marks_pure_from_emitted_fortran_not_python_source(tmp_path: Path) -> None:
    # Regression test: purity was determined by a Python-AST heuristic
    # (function_is_pure) that has two concrete gaps, both real-world
    # (from garch_acf.py, a GARCH ACF/autocov helper library on GitHub):
    # (1) it has a dedicated np.X(...) recognition path but nothing for
    # math.X(...) -- bare math.sqrt(...)/math.erf(...) etc. fell straight
    # to the "unknown attribute call -> impure" fallback, even though
    # they're genuinely pure and lower to Fortran's own pure intrinsics;
    # (2) it conservatively disqualifies ANY assignment whose target is
    # one of the function's own argument names (e.g. `x = np.asarray(x,
    # ...)`), on the theory that it might translate into writing an
    # INTENT(IN) dummy -- but the codegen already ALWAYS shadow-copies
    # such reassignment into a fresh `x_local`, so the dummy is never
    # actually touched, making the check needlessly conservative.
    #
    # Fixed not by patching those two gaps in the Python-side heuristic
    # (which would just be two more entries in a structurally open-ended
    # list), but by adding a SEPARATE, additive post-processing pass
    # (fortran_purity.py, ported from the sibling xpure.py static
    # analyzer) that determines purity from the EMITTED FORTRAN directly
    # -- a small, fixed vocabulary (no write to an INTENT(IN) dummy, no
    # I/O, no call to a known-impure procedure) that needs no per-Python-
    # feature special-casing at all, and catches both gaps for free. Only
    # ever ADDS `pure `, on top of whatever the existing Python-AST pass
    # already decided -- never removes one.
    #
    # This one function combines both original gaps: math.sqrt (gap 1)
    # applied to a reassigned argument (gap 2, via mean_1d-analogous
    # numpy .mean()... kept plain here to avoid a pandas/numpy runtime-
    # helper dependency) -- neither gap alone was needed for the old
    # heuristic to reject it; either one was already sufficient.
    src = tmp_path / "xpure_from_fortran.py"
    src.write_text(
        "\n".join(
            [
                "import math",
                "",
                "def f(x):",
                "    x = x + 0.0",
                "    return math.sqrt(x * x)",
                "",
                "print(f(4.0))",
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
    out_f90 = (tmp_path / "xpure_from_fortran_p.f90").read_text(encoding="utf-8")
    assert "pure function f(" in out_f90, out_f90


def test_xp2f_elemental_flag_promotes_scalar_pure_functions_only(tmp_path: Path) -> None:
    # Regression test for the --elemental flag: a PURE procedure with
    # only scalar dummy arguments (and, for a function, a scalar result)
    # is eligible for the further PURE ELEMENTAL promotion -- letting
    # callers invoke it directly on whole arrays via Fortran's automatic
    # elemental broadcasting -- but one with an ARRAY dummy is not
    # (ELEMENTAL requires every dummy to be scalar). --elemental is
    # opt-in (unlike the always-on PURE pass): unlike PURE, ELEMENTAL
    # carries a real usage constraint (an elemental procedure can never
    # be supplied as a callback/procedure actual argument), so it's
    # offered as a choice rather than applied automatically. Also checks
    # that --elemental produces IDENTICAL program output to the default
    # (non-elemental) build -- it's purely a declaration-level
    # annotation, never a computation change.
    src = tmp_path / "xelemental_flag.py"
    src.write_text(
        "\n".join(
            [
                "def scalar_fn(x):",
                "    return x * x + 1.0",
                "",
                "def array_sum(x):",
                "    total = 0.0",
                "    for i in range(len(x)):",
                "        total = total + x[i]",
                "    return total",
                "",
                "print(scalar_fn(3.0))",
                "print(array_sum([1.0, 2.0, 3.0]))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc_default = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_default.returncode == 0, proc_default.stdout + proc_default.stderr
    assert "Run diff: MATCH" in proc_default.stdout, proc_default.stdout + proc_default.stderr
    default_f90 = (tmp_path / "xelemental_flag_p.f90").read_text(encoding="utf-8")
    assert "pure function scalar_fn(" in default_f90, default_f90
    assert "pure elemental" not in default_f90.lower(), default_f90

    proc_elem = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff", "--elemental"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_elem.returncode == 0, proc_elem.stdout + proc_elem.stderr
    assert "Run diff: MATCH" in proc_elem.stdout, proc_elem.stdout + proc_elem.stderr
    elem_f90 = (tmp_path / "xelemental_flag_p.f90").read_text(encoding="utf-8")
    assert "pure elemental function scalar_fn(" in elem_f90, elem_f90
    # array_sum takes a rank-1 array dummy -- must stay plain pure, never
    # promoted to elemental.
    assert re.search(r"pure elemental function array_sum\(", elem_f90) is None, elem_f90
    assert re.search(r"pure function array_sum\(", elem_f90) is not None, elem_f90


def test_xp2f_purity_registry_resolves_generic_interface_names(tmp_path: Path) -> None:
    # Regression test: load_external_purity_registry only ever walked
    # TOP-LEVEL concrete function/subroutine bodies in the vendored
    # runtime helper files -- but python.f90's `optval` (needed by any
    # function using a Python default-argument value) is a GENERIC
    # INTERFACE name (`interface optval / module procedure optval_int,
    # optval_real, optval_logical, optval_char / end interface`), never
    # itself a concrete procedure with a body. Generated code only ever
    # calls the generic name `optval(...)`, never `optval_real(...)`
    # directly, so the registry never had an entry for the name actually
    # used -- every caller of `optval` was rejected as "invokes imported
    # entity 'optval' whose purity is unknown", even though all four of
    # its real implementations are pure. Real-world trigger: this
    # affected EVERY function using a Python default-argument value in a
    # GARCH ACF/autocov helper library on GitHub (garch_acf.py) --
    # v_egarch_expx_moment_normal among them, confirmed to compile fine
    # when manually marked pure. Fixed by also parsing named `interface
    # NAME ... module procedure ... end interface` blocks in each
    # vendored file and registering the generic NAME as pure only when
    # ALL of its constituent targets are.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xoptval_purity.py",
        [
            "def f(a, b=1.0):",
            "    return a + b",
            "",
            "print(f(3.0))",
            "print(f(3.0, 5.0))",
        ],
    )
    out_f90 = (tmp_path / "xoptval_purity_p.f90").read_text(encoding="utf-8")
    assert "pure function f(" in out_f90, out_f90


def test_xp2f_forwards_none_default_optional_without_premature_default(tmp_path: Path) -> None:
    # Regression test: a function that does NOTHING with its own
    # None-default parameter except forward it unchanged as a keyword
    # argument to another function's OWN same-named None-default
    # parameter (`def wrapper(x, ez=None): return inner(x, ez=ez)`) had
    # `ez` PREMATURELY resolved to a generic numeric placeholder
    # (`ez_opt = optval(ez, 0.0_dp)`) inside `wrapper`, and THAT
    # always-present local -- not the original possibly-absent dummy --
    # got forwarded to `inner`. This defeated `inner`'s own, correct `if
    # ez is None: ez = <real default>` resolution, since `present(ez)`
    # inside `inner` then always saw "supplied" and silently used the
    # wrong value (0.0) instead of inner's real default -- no compile
    # error, just a wrong number. Real-world trigger: a GARCH ACF/autocov
    # helper library on GitHub (garch_acf.py)'s autocov_abs_garch_1_1(...,
    # ez_abs=None) forwarding straight to autocov_abs_from_pq(...,
    # ez_abs=ez_abs), which produced degenerate th=0.0/th=2.0 theoretical
    # values (correct: ~1.0965/~0.7978) whenever the top-level caller
    # never supplied ez_abs itself. Fixed by skipping the local alias/
    # materialization entirely for a None-default parameter whose body
    # never does anything with it except a direct, unmodified forward --
    # the raw (still-optional, still-absence-tracking) Fortran dummy is
    # used wherever it's referenced instead.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xforward_none_default.py",
        [
            "import math",
            "",
            "def inner(x, ez=None):",
            "    if ez is None:",
            "        ez = math.sqrt(2.0)",
            "    return x * ez",
            "",
            "def wrapper(x, ez=None):",
            "    return inner(x, ez=ez)",
            "",
            "print(wrapper(3.0))",
            "print(wrapper(3.0, 5.0))",
        ],
    )
    out_f90 = (tmp_path / "xforward_none_default_p.f90").read_text(encoding="utf-8")
    # `inner` genuinely uses ez (the `if ez is None:` check), so it
    # legitimately keeps its own ez_opt materialization -- only
    # `wrapper`'s (a pure forward) should be gone, and it should forward
    # the raw `ez` dummy, not a locally-resolved `ez_opt`.
    wrapper_body = out_f90.split("function wrapper(", 1)[1].split("end function wrapper", 1)[0]
    assert "ez_opt" not in wrapper_body, out_f90
    assert re.search(r"inner\(x=x,\s*ez=ez\)", wrapper_body), out_f90


def test_xp2f_hoists_duplicate_use_only_optval_to_module_scope(tmp_path: Path) -> None:
    # Regression test: `use python_mod, only: optval` (needed by any
    # function using a Python default-argument value) was emitted once
    # per PROCEDURE that needs it -- fpost.hoist_module_use_only_imports
    # already existed and already fixes exactly this, but only ran under
    # the opt-in --postprocess flag; the default path never hoisted
    # anything, so the same duplicate line appeared once per function.
    # Now runs in the default path too (purely structural -- Fortran
    # scoping means a locally-declared entity always shadows a host-
    # associated one of the same name, so hoisting duplicates to module
    # scope can't change what any OTHER procedure sees).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xhoist_optval.py",
        [
            "def f(a, b=1):",
            "    return a + b",
            "",
            "def g(a, b=2):",
            "    return a - b",
            "",
            "print(f(3), g(3))",
        ],
    )
    out_f90 = (tmp_path / "xhoist_optval_p.f90").read_text(encoding="utf-8")
    assert out_f90.count("use python_mod, only:") == 1, out_f90
    assert "optval" in out_f90.split("use python_mod, only:", 1)[1].split("\n", 1)[0], out_f90


def test_xp2f_removes_same_named_dead_constant_in_separate_procedures(tmp_path: Path) -> None:
    # Regression test: remove_unused_named_constants's outer unit-scan
    # matched "module ... end module" FIRST (since it's outermost),
    # swallowing every contained procedure's body into ONE flat scan --
    # "keep first declaration if duplicates appear" then kept only the
    # FIRST procedure's copy of a same-named dead local constant, and
    # every OTHER procedure's own (individually genuinely dead) copy of
    # it was misread as a "use" of that first one, since it's just
    # another line containing the same token. Two DIFFERENT functions
    # here each get an identically-named, individually-dead local
    # constant (mirroring garch_acf.py's `integer, parameter :: rng = 0`
    # placeholder, repeated once per simulate_* function). Fixed by
    # recursing into each nested subroutine/function as its own
    # independent scope before scanning the enclosing unit.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdead_dup_const.py",
        [
            "import numpy as np",
            "",
            "def f(seed):",
            "    rng = np.random.default_rng(seed)",
            "    return float(rng.standard_normal())",
            "",
            "def g(seed):",
            "    rng = np.random.default_rng(seed)",
            "    return float(rng.standard_normal())",
            "",
            "print(f(1) == f(1))",
            "print(g(2) == g(2))",
        ],
    )
    out_f90 = (tmp_path / "xdead_dup_const_p.f90").read_text(encoding="utf-8")
    assert "rng" not in out_f90.lower() or "parameter :: rng" not in out_f90.lower(), out_f90


def test_xp2f_fuses_bare_copy_into_self_referential_assignment(tmp_path: Path) -> None:
    # Regression test: `x = np.asarray(x, dtype=float)` followed by
    # `x = x - x.mean()` (both reassigning the same argument -- lowered
    # onto the same locally-shadowed `x_local`, since an intent(in) dummy
    # can't be written) generated two adjacent Fortran statements,
    # `x_local = x` then `x_local = x_local - mean_1d(x_local)`, where
    # the first line's ENTIRE purpose is to seed the second line's own
    # self-reference. Fixed by fusing them into one statement whenever
    # the source of the first assignment is a single bare identifier
    # (never needs parenthesizing when substituted in).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xfuse_bare_copy.py",
        [
            "import numpy as np",
            "",
            "def demean(x):",
            "    x = np.asarray(x, dtype=float)",
            "    x = x - x.mean()",
            "    return x",
            "",
            "def make_arr():",
            "    a = np.empty(4, dtype=float)",
            "    a[0] = 1.0",
            "    a[1] = 2.0",
            "    a[2] = 3.0",
            "    a[3] = 4.0",
            "    return a",
            "",
            "arr = make_arr()",
            "print(demean(arr))",
        ],
    )
    out_f90 = (tmp_path / "xfuse_bare_copy_p.f90").read_text(encoding="utf-8")
    assert re.search(r"x_local\s*=\s*x\s*$", out_f90, re.MULTILINE) is None, out_f90


def test_xp2f_eliminates_shadow_copy_of_never_reassigned_param(tmp_path: Path) -> None:
    # Regression test: user-reported example from a real GARCH ACF/autocov
    # helper library on GitHub (garch_acf.py)'s `_autocov_biased`:
    #     def _autocov_biased(x, nlags):
    #         x = np.asarray(x, dtype=float)
    #         x0 = x - x.mean()
    #         ...
    # `x = np.asarray(x, dtype=float)` reassigns the parameter, which the
    # codegen ALWAYS routes through a fresh `x_local` shadow (an
    # intent(in) dummy can't be written directly) -- producing
    # `x_local = x` followed by every later use of `x` rewritten to
    # `x_local`. But `x` is never reassigned again after that first
    # (no-op, for a real(dp) array) cast/copy, so `x_local` ends up a
    # pure read-only alias for `x`: an entire unnecessary array copy.
    # User pointed this out directly ("you can use x directly and do not
    # need to define x_local. Agree?"). Fixed with a new pass,
    # eliminate_redundant_readonly_param_shadow_copies, that removes a
    # `NAME_local` shadow (and its seed copy) whenever it's written
    # exactly once via a bare `NAME_local = NAME` and never appears
    # anywhere else except as a pure read (never reassigned, never
    # passed to a `call`, `allocate`/`deallocate`, or `allocated()`),
    # rewriting every remaining use back onto `NAME` directly.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xshadow_copy_elim.py",
        [
            "import numpy as np",
            "",
            "def autocov_biased(x, nlags):",
            "    x = np.asarray(x, dtype=float)",
            "    x0 = x - x.mean()",
            "    out = np.empty(nlags + 1, dtype=float)",
            "    out[0] = np.mean(x0 * x0)",
            "    for k in range(1, nlags + 1):",
            "        out[k] = np.mean(x0[:-k] * x0[k:])",
            "    return out",
            "",
            "def make_arr():",
            "    a = np.empty(5, dtype=float)",
            "    a[0] = 1.0",
            "    a[1] = 2.0",
            "    a[2] = 3.0",
            "    a[3] = 4.0",
            "    a[4] = 5.0",
            "    return a",
            "",
            "arr = make_arr()",
            "result = autocov_biased(arr, 3)",
            "for v in result:",
            "    print(v)",
        ],
    )
    out_f90 = (tmp_path / "xshadow_copy_elim_p.f90").read_text(encoding="utf-8")
    assert "x_local" not in out_f90, out_f90
    assert re.search(r"\bx0\s*=\s*x\s*-\s*mean_1d\s*\(\s*x\s*\)", out_f90), out_f90


def test_xp2f_skips_nan_guard_on_literal_comparison_operand(tmp_path: Path) -> None:
    # Regression test: a NaN-safe comparison (needed under this project's
    # -ffpe-trap=invalid builds, where an ordered comparison against NaN
    # would otherwise trap/crash rather than quietly evaluate to False
    # like Python) wrapped BOTH operands in the same merge()/
    # ieee_is_nan() guard machinery even when one operand was a literal
    # numeric constant that can never be NaN -- producing a needless
    # `merge(0.0_dp, 0.0_dp, ieee_is_nan(0.0_dp))` sub-expression (always
    # just 0.0_dp, true/false sources identical regardless of the
    # condition) plus its own redundant `ieee_is_nan(0.0_dp)` (always
    # false) in the OR-mask. Fixed by only guarding an operand that's
    # NOT a compile-time-safe literal.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xnan_guard_literal.py",
        [
            "def f(x):",
            "    if x <= 0.0:",
            "        return -1.0",
            "    return x",
            "",
            "print(f(2.0), f(-3.0), f(0.0))",
        ],
    )
    out_f90 = (tmp_path / "xnan_guard_literal_p.f90").read_text(encoding="utf-8")
    assert "ieee_is_nan(0.0_dp)" not in out_f90, out_f90


def test_xp2f_wrap_long_lines_never_strands_bare_closing_paren(tmp_path: Path) -> None:
    # Regression test: the long-line wrapper's break-candidate scan
    # allowed cutting immediately BEFORE a ")"/"]", putting it alone at
    # the start of the continuation line (`... &` / `& ) + ...`) -- valid
    # Fortran, but poor style. Moving that candidate to just AFTER the
    # closing delimiter (mirroring the pre-existing rule for a trailing
    # comma) fixed the simple case, but a RUN of several consecutive
    # closing parens (e.g. "theta * theta)))") could still strand the
    # LAST one alone if the ideal cut fell in the middle of the run --
    # each ")" independently contributes an "after me" candidate, so the
    # width-based choice needed its own fallback: walk backward through
    # candidates for the first one that doesn't leave the continuation
    # starting with ")"/"]".
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xwrap_no_stranded_paren.py",
        [
            "def f(theta, alpha, beta):",
            "    p2 = (beta * beta + (((2.0 * alpha) * beta) * (1.0 + (theta * theta)))) + (",
            "        (alpha * alpha) * (3.0 + ((6.0 * theta) * theta) + (theta ** 4))",
            "    )",
            "    return p2",
            "",
            "print(f(0.2, 0.1, 0.85))",
        ],
    )
    out_f90 = (tmp_path / "xwrap_no_stranded_paren_p.f90").read_text(encoding="utf-8")
    for line in out_f90.splitlines():
        stripped = line.strip()
        if stripped.startswith("&"):
            after_amp = stripped[1:].strip()
            assert not after_amp.startswith((")", "]")), out_f90


def test_fortran_wrap_splits_inside_long_string_literal_without_corruption() -> None:
    # Regression test (direct unit test of wrap_long_fortran_line): a
    # `write(*, "(...)")` format descriptor long enough on its own that
    # NO safe break point exists outside the quotes within the column
    # budget returned None (left completely unwrapped, however long) --
    # user-reported real example from a GARCH ACF/autocov helper library
    # on GitHub, a >200-column `write(*,"('kappa=',g0,...)") kappa, ...`
    # line sitting right next to other statements that WERE wrapped to
    # 80 columns, an inconsistency the user flagged directly. Fixed by
    # adding a last-resort fallback that splits INSIDE the string using
    # Fortran's own string-continuation rule: end the line with "&"
    # while still inside the quotes, resume on a line whose first
    # non-blank character is also "&" -- content resumes IMMEDIATELY
    # after that second "&", with NO inserted characters (unlike an
    # ordinary code continuation's "& " convention, which SPACES after
    # the "&" and would corrupt string content if reused verbatim here).
    # The interior cut point is also never placed between the two halves
    # of a doubled ''/"" escaped quote.
    line = (
        "   write(*,\"('kappa=',g0,'  mean(|eps|): emp=',g0,' th=',g0,"
        "'  var(|eps|): emp=',g0,' th=',g0)\") kappa, real(mean_1d(abs_eps), "
        "kind=dp), th_mean_abs, real(var_1d(reshape(abs_eps, [size(abs_eps)])), "
        "kind=dp), th_var_abs"
    )
    result = fscan.wrap_long_fortran_line(line, max_len=80)
    assert result is not None, "expected a fallback string-internal wrap, got None"
    assert all(len(ln) <= 80 for ln in result), result
    assert len(result) > 1, result
    joined = "\n".join(result)
    assert joined.count('"') == 2, joined  # the format string's own open/close quote, nothing extra
    # Reconstruct the STRING LITERAL's own content exactly as Fortran's
    # continuation rule defines it: from the line starting the string,
    # everything up to (and not including) a trailing "&" is real
    # content; on every following line that's STILL part of the string
    # (i.e. doesn't yet contain the closing quote), content resumes
    # IMMEDIATELY after that line's own leading "&" -- no lstrip, no
    # space, unlike an ordinary code continuation. This must exactly
    # reproduce the original quoted text, proving no characters were
    # dropped, added, or reordered inside the literal by the split
    # (whitespace-insensitive CODE around the split, e.g. extra spaces
    # where an ordinary code-level break also lands, is not checked here
    # -- Fortran doesn't care, and that's covered by an actual compile
    # + run-diff in the companion end-to-end test).
    orig_str_start = line.index('"')
    orig_str_end = line.index('"', orig_str_start + 1)
    orig_content = line[orig_str_start:orig_str_end + 1]

    rebuilt_content = ""
    in_string = False
    for ln in result:
        if not in_string:
            if '"' not in ln:
                continue
            q = ln.index('"')
            text = ln[q:]
            in_string = True
        else:
            stripped = ln.lstrip()
            assert stripped.startswith("&"), result
            text = stripped[1:]
        if '"' in text[1:]:
            # the string closes somewhere in this fragment -- keep only
            # up through the closing quote; anything after it is CODE
            # (e.g. this line's own trailing "&", if any, is then an
            # ordinary code continuation, not part of the string).
            close_rel = text.index('"', 1)
            rebuilt_content += text[: close_rel + 1]
            break
        # still open: this fragment must end with "&" (string continues
        # on the next physical line).
        assert text.endswith("&"), result
        rebuilt_content += text[:-1]
    assert rebuilt_content == orig_content, (rebuilt_content, orig_content)


def test_xp2f_wraps_long_format_string_print_consistently(tmp_path: Path) -> None:
    # Companion end-to-end test to test_fortran_wrap_splits_inside_long_
    # string_literal_without_corruption, exercising the same fallback
    # through the full pipeline with the user's actual real-world
    # trigger shape: a Python %-format print whose generated Fortran
    # `write` statement's format descriptor alone is too long to fit
    # inside the column budget outside the quotes.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xwrap_long_format_string.py",
        [
            "kappa = 3.0",
            "mean_abs = 1.0965",
            "th_mean_abs = 1.0965",
            "var_abs = 0.7978",
            "th_var_abs = 0.7978",
            "print(",
            "    'kappa=%.6g  mean(|eps|): emp=%.8g th=%.8g  "
            "var(|eps|): emp=%.8g th=%.8g'",
            "    % (kappa, mean_abs, th_mean_abs, var_abs, th_var_abs)",
            ")",
        ],
    )
    out_f90 = (tmp_path / "xwrap_long_format_string_p.f90").read_text(encoding="utf-8")
    for line in out_f90.splitlines():
        assert len(line) <= 80, out_f90


def test_xp2f_max_use_only_collapses_large_import_list(tmp_path: Path) -> None:
    # User request: a `use foo_mod, only: a, b, c, ...` importing dozens
    # of names (a real generated program's own proc-module import list
    # ran to 30 names) is hard to scan even correctly wrapped across
    # many continuation lines. New opt-in --max-use-only N flag collapses
    # it to `use foo_mod ! imports N entities` once the list exceeds N.
    # This end-to-end test just confirms the flag is wired through the
    # CLI and produces a collapsed line with a correct count for a
    # program with more than a couple of module-level functions, and
    # that program behavior is unaffected (byte-identical run output is
    # implied by _run_xp2f_compile_diff's own run-diff check). The
    # underlying safety guard itself (never collapse when doing so could
    # collide with something else visible in scope) is unit-tested
    # directly in test_xp2f_max_use_only_declines_on_name_collision,
    # since it needs a hand-crafted Fortran collision the transpiler
    # itself wouldn't naturally produce.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmax_use_only.py"
    helper_lines = []
    for i in range(1, 6):
        helper_lines += [f"def helper{i:02d}(x):", f"    return x + {i}.0", ""]
    # Call every helper DIRECTLY from top-level program code (not
    # through one intermediate wrapper function) -- only names the
    # PROGRAM itself references directly end up in its own `use ...,
    # only:` list; a call routed through one module-internal wrapper
    # function would only ever import that one wrapper name.
    main_lines = ["total = 0.0"] + [f"total = total + helper{i:02d}(1.0)" for i in range(1, 6)] + ["print(total)"]
    src.write_text("\n".join(helper_lines + main_lines), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run-diff", "--max-use-only", "3"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr
    out_f90 = (tmp_path / "xmax_use_only_p.f90").read_text(encoding="utf-8")
    m = re.search(r"^\s*use xmax_use_only_proc_mod(.*)$", out_f90, re.MULTILINE)
    assert m, out_f90
    assert re.match(r"\s*! imports \d+ entit(y|ies)\s*$", m.group(1)), out_f90


def test_xp2f_max_use_only_declines_on_name_collision() -> None:
    # Regression test for collapse_large_use_only_imports's safety
    # guard: `use MOD, only: wrapper` is left UNTOUCHED (not collapsed
    # to a bare `use MOD`) when the importing scope already declares
    # something (here a local variable) with the exact same name as one
    # of MOD's OTHER public entities that a bare `use MOD` would newly
    # expose -- exactly the collision `only:` exists to prevent. A
    # sibling program with no such name anywhere in scope DOES collapse,
    # confirming the guard is name-specific, not a blanket refusal.
    collides = """\
module foo_proc_mod
   implicit none
   private
   public :: dp, wrapper, helper_extra
contains
   function wrapper(x) result(y)
      real :: x, y
      y = x + 1.0
   end function wrapper
   function helper_extra(x) result(y)
      real :: x, y
      y = x + 2.0
   end function helper_extra
end module foo_proc_mod
program main
   use foo_proc_mod, only: wrapper
   implicit none
   real :: helper_extra
   helper_extra = 5.0
   print *, wrapper(1.0) + helper_extra
end program main
""".splitlines(keepends=True)
    out_collides = xp2f.collapse_large_use_only_imports(collides, max_entities=0)
    assert "use foo_proc_mod, only: wrapper" in "".join(out_collides), "".join(out_collides)

    clean = """\
module foo_proc_mod
   implicit none
   private
   public :: dp, wrapper, helper_extra
contains
   function wrapper(x) result(y)
      real :: x, y
      y = x + 1.0
   end function wrapper
   function helper_extra(x) result(y)
      real :: x, y
      y = x + 2.0
   end function helper_extra
end module foo_proc_mod
program main
   use foo_proc_mod, only: wrapper
   implicit none
   real :: z
   z = 5.0
   print *, wrapper(1.0) + z
end program main
""".splitlines(keepends=True)
    out_clean = xp2f.collapse_large_use_only_imports(clean, max_entities=0)
    assert "use foo_proc_mod ! imports 1 entity" in "".join(out_clean), "".join(out_clean)


def test_xp2f_max_use_only_preserves_blank_lines() -> None:
    # Regression test: user-reported real example -- `xp2f.py ... --out
    # temp.f90 --compile --elemental --max-use-only 10` produced
    #     end function v_autocov_biased
    #     end module xgarch_acf_proc_mod
    #     program xgarch_acf
    # with NO blank line between "end module" and "program" (present
    # without --max-use-only). Root cause: collapse_large_use_only_
    # imports's deleted-continuation-line sentinel was "" -- but
    # f90_lines represents a genuine BLANK line as bare "" too (the
    # pipeline only joins lines with "\n" at the very end, so no element
    # carries its own newline), and this pass runs LATE, after the
    # pipeline's own blank-line normalization (ensure_blank_lines_
    # around_units_and_procedures) -- so its final `[ln for ln in out if
    # ln != ""]` filter silently stripped EVERY blank line in the WHOLE
    # FILE, not just its own deleted lines, with nothing running
    # afterward to restore them. Fixed by using `None` as the deletion
    # sentinel instead (filtering `is not None`), which can never
    # collide with a real blank line. This is a direct unit test (using
    # bare, no-trailing-newline line strings, matching f90_lines' own
    # convention -- unlike a plain .splitlines(keepends=True) fixture,
    # which wouldn't reproduce the bug since a blank line there is "\n",
    # not "") since the CLI's own compile+run-diff path doesn't inspect
    # blank-line counts.
    lines = [
        "module foo_proc_mod",
        "   implicit none",
        "   private",
        "   public :: dp, wrapper, helper_extra",
        "contains",
        "   function wrapper(x) result(y)",
        "      real :: x, y",
        "      y = x + 1.0",
        "   end function wrapper",
        "end module foo_proc_mod",
        "",  # <- must survive
        "program main",
        "   use foo_proc_mod, only: wrapper",
        "   implicit none",
        "   real :: z",
        "   z = 5.0",
        "",  # <- must survive
        "   print *, wrapper(1.0) + z",
        "end program main",
    ]
    out = xp2f.collapse_large_use_only_imports(lines, max_entities=0)
    assert any("use foo_proc_mod ! imports 1 entity" in ln for ln in out), out
    end_idx = out.index("end module foo_proc_mod")
    assert out[end_idx + 1] == "", out
    z_idx = out.index("   z = 5.0")
    assert out[z_idx + 1] == "", out


def test_xp2f_simplifies_redundant_dp_cast_around_dot_product(tmp_path: Path) -> None:
    # Regression test: user-reported real example from a GARCH ACF/
    # autocov helper library on GitHub (garch_acf.py) -- a sample
    # autocovariance computed as `np.dot(x0[k:], x0[:n-k]) / (n-k)`
    # produced
    #     emp_autocov_abs(1) = real(dot_product(absc, absc), &
    #        & kind=dp) / real(size(absc), kind=dp)
    # -- two redundant `real(..., kind=dp)` casts. (1) dot_product's
    # result already has the same type/kind as its (matching)
    # real(kind=dp) array arguments, so wrapping it in another cast to
    # that SAME kind is a no-op. (2) Fortran's mixed real/integer
    # division always promotes the integer operand to (at least) the
    # real operand's own kind, so once the numerator is confirmed
    # real(kind=dp), wrapping the divisor in a cast to that same kind
    # changes nothing about the division's result either. User: "since
    # dot_product(x, x) is real(kind=dp) if x is real(kind=dp) and
    # denominator can be just size(absc) since real(kind=dp)/integer is
    # converted to real(kind=dp)". Verified (outside this test, since
    # run-diff alone wouldn't distinguish the two casting routes) to
    # produce BYTE-IDENTICAL runtime output with the pass disabled.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdot_product_cast.py",
        [
            "import numpy as np",
            "",
            "def autocov0(x):",
            "    x = np.asarray(x, dtype=float)",
            "    n = x.shape[0]",
            "    return np.dot(x, x) / n",
            "",
            "def make_arr():",
            "    a = np.empty(4, dtype=float)",
            "    a[0] = 1.0",
            "    a[1] = 2.0",
            "    a[2] = 3.0",
            "    a[3] = 4.0",
            "    return a",
            "",
            "print(autocov0(make_arr()))",
        ],
    )
    out_f90 = (tmp_path / "xdot_product_cast_p.f90").read_text(encoding="utf-8")
    assert "real(dot_product" not in out_f90, out_f90
    assert re.search(r"dot_product\([a-z_]\w*,\s*[a-z_]\w*\)\s*/\s*[a-z_]\w*\b", out_f90, re.IGNORECASE), out_f90


def test_xp2f_simplify_redundant_int_casts_runs_in_default_path(tmp_path: Path) -> None:
    # Regression test: user-reported real example -- generated code had
    # several `int(k)`/`int(n_terms)`/`int(n)` casts around variables
    # ALREADY declared integer (Python's own `int(...)` calls on values
    # already integer-typed at the Fortran level are pure noise). The
    # function that strips exactly this, simplify_redundant_int_casts,
    # already existed and is scoped per procedure/program unit (so a
    # same-named integer in one unit can never wrongly strip a genuinely
    # -needed int() cast in another unit where that name is real) -- but
    # it only ran under the opt-in --postprocess flag, so it never fired
    # for a default-path build (which is what produced the user's
    # temp.f90). Moved to the always-on default path too.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdefault_int_cast.py",
        [
            "def f(k, n):",
            "    total = 0",
            "    for i in range(k):",
            "        total = total + i",
            "    print(k, n, total)",
            "",
            "f(3, 5)",
        ],
    )
    out_f90 = (tmp_path / "xdefault_int_cast_p.f90").read_text(encoding="utf-8")
    assert "int(k)" not in out_f90, out_f90
    assert "int(n)" not in out_f90, out_f90


def test_xp2f_simplifies_redundant_dp_cast_around_known_dp_returning_call(tmp_path: Path) -> None:
    # Regression test: user-reported real example --
    #     eh32 = real(mean_1d(h ** 1.5_dp), kind=dp)
    # -- a redundant cast around a call to mean_1d, which python.f90
    # already declares `pure real(kind=dp) function mean_1d(x)`, so its
    # result is ALREADY real(kind=dp). User: "In general do not use
    # int() or real(..., kind=dp) when the expression inside already has
    # that type." Also exercises the SAME-FILE half of the registry
    # (fortran_purity.collect_dp_returning_function_names) via a local
    # helper function using the `result(...)` + separate scalar
    # real(kind=dp) declaration shape this project's own codegen emits,
    # not just the vendored inline-type shape mean_1d itself uses. The
    # argument to mean_1d here (`h ** 1.5_dp`) is a compound expression,
    # not a bare identifier -- exercises the real-paren-depth-tracking
    # scan (not a fixed-nesting regex) that replaced an earlier, buggier
    # attempt.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdp_returning_call_cast.py",
        [
            "import numpy as np",
            "",
            "def make_arr():",
            "    a = np.empty(3, dtype=float)",
            "    a[0] = 1.0",
            "    a[1] = 2.0",
            "    a[2] = 4.0",
            "    return a",
            "",
            "h = make_arr()",
            "eh32 = np.mean(h ** 1.5)",
            "print(eh32)",
        ],
    )
    out_f90 = (tmp_path / "xdp_returning_call_cast_p.f90").read_text(encoding="utf-8")
    assert "real(mean_1d" not in out_f90, out_f90


def test_fortran_simplify_redundant_dp_cast_general_covers_compound_expressions() -> None:
    # Regression test (direct unit test): user-reported real examples,
    # a further generalization beyond simplify_redundant_dp_cast_around_
    # dot_product/_dp_returning_calls (which only strip a cast around a
    # single BARE call) --
    #     eh = real(exp(mean_x + 0.5_dp * var_x), kind=dp)
    #         --> eh = exp(mean_x + 0.5_dp * var_x)          [kind-preserving intrinsic]
    #     emp_var_r2 = real(emp_acv_r2(1), kind=dp)
    #         --> emp_var_r2 = emp_acv_r2(1)                  [bare dp array element, no call at all]
    #     emp_kurt = real(mean_1d(eps**4) / (mean_1d(eps**2)**2), kind=dp)
    #         --> emp_kurt = mean_1d(eps**4) / (mean_1d(eps**2)**2)  [compound expression, incl. `**`]
    # The third case caught a real bug during development: the top-
    # level-operand splitter treated "**" as something to skip over
    # entirely rather than as a valid split point, so "A ** B" was never
    # split into two operands -- a compound expression containing "**"
    # that wasn't ALSO a single bare call/name/literal silently fell
    # through to "unknown" (correctly conservative, but missed this
    # case) until fixed to register "**" as a genuine (two-character)
    # split point, exactly like the single-character operators.
    lines = [
        "pure function f(mean_x, var_x, eps, emp_acv_r2) result(z)",
        "   real(kind=dp), intent(in) :: mean_x, var_x",
        "   real(kind=dp), intent(in) :: eps(:)",
        "   real(kind=dp), intent(in) :: emp_acv_r2(:)",
        "   real(kind=dp) :: eh, eh2, emp_var_r2, emp_kurt, z",
        "   eh = real(exp(mean_x + 0.5_dp * var_x), kind=dp)",
        "   eh2 = real(exp(2.0_dp * mean_x + 2.0_dp * var_x), kind=dp)",
        "   emp_var_r2 = real(emp_acv_r2(1), kind=dp)",
        "   emp_kurt = real(mean_1d(eps ** 4) / (mean_1d(eps ** 2) ** 2), kind=dp)",
        "   z = eh + eh2 + emp_var_r2 + emp_kurt",
        "end function f",
    ]
    # mean_1d isn't defined in this snippet -- register it directly the
    # way the real pipeline would via the vendored-helper registry, by
    # monkeypatching xp2f's cache for the duration of this call.
    orig_cache = xp2f._vendored_dp_returning_registry_cache
    xp2f._vendored_dp_returning_registry_cache = {"mean_1d"}
    try:
        out = xp2f.simplify_redundant_dp_cast_general(lines)
    finally:
        xp2f._vendored_dp_returning_registry_cache = orig_cache
    joined = "\n".join(out)
    assert "eh = exp(mean_x + 0.5_dp * var_x)" in joined, joined
    assert "eh2 = exp(2.0_dp * mean_x + 2.0_dp * var_x)" in joined, joined
    assert "emp_var_r2 = emp_acv_r2(1)" in joined, joined
    assert "emp_kurt = mean_1d(eps ** 4) / (mean_1d(eps ** 2) ** 2)" in joined, joined
    # No cast remains on any of the four rewritten ASSIGNMENT lines
    # (declarations legitimately still say "real(kind=dp) ::").
    for name in ("eh", "eh2", "emp_var_r2", "emp_kurt"):
        assign_line = next(ln for ln in out if re.match(rf"^\s*{name}\s*=", ln))
        assert "real(" not in assign_line, assign_line


def test_fortran_simplify_redundant_dp_cast_general_covers_min_max_mod() -> None:
    # Regression test: _DP_KIND_PRESERVING_INTRINSICS originally omitted
    # min/max/mod (multi-arg intrinsics, more type-mixing risk than a
    # single-arg one like exp/sqrt) out of caution. They belong: this
    # pass's own job is only "does removing the OUTER real(..., kind=dp)
    # cast change the expression's result kind" -- it never touches the
    # call's own arguments, so whatever type-mixing risk the inner call
    # already carried is a pre-existing property of the generated code,
    # completely unaffected by whether the redundant outer cast stays or
    # goes. Also confirms the cast is correctly PRESERVED when every
    # argument is genuinely integer (the cast is then doing real work,
    # not wrapping an already-dp value).
    lines = [
        "pure function f(a, b, c) result(z)",
        "   real(kind=dp), intent(in) :: a, b, c",
        "   real(kind=dp) :: z",
        "   z = real(min(a, b), kind=dp)",
        "   z = real(max(a, b), kind=dp) + real(mod(a, c), kind=dp)",
        "end function f",
        "pure function g(a, b) result(z)",
        "   integer, intent(in) :: a, b",
        "   real(kind=dp) :: z",
        "   z = real(min(a, b), kind=dp)",
        "end function g",
    ]
    out = xp2f.simplify_redundant_dp_cast_general(lines)
    joined = "\n".join(out)
    assert "z = min(a, b)" in joined, joined
    assert "z = max(a, b) + mod(a, c)" in joined, joined
    # The all-integer case in g() keeps its cast -- min(a,b) there is
    # genuinely integer-typed, so the cast is doing real work.
    assert "real(min(a, b), kind=dp)" in joined, joined


@pytest.mark.parametrize("outer_type", ["complex(kind=dp)", "integer"])
@pytest.mark.parametrize("continued", [False, True])
def test_redundant_dp_cast_preserves_shadowed_variable(outer_type, continued) -> None:
    declaration = ([f"   {outer_type} :: other, &", "      & c"] if continued
                   else [f"   {outer_type} :: c"])
    lines = [
        "function f() result(z)",
        *declaration,
        "   real(kind=dp) :: z, unshadowed",
        "   block",
        "      real(kind=dp) :: c",
        "      c = 1.0_dp",
        "      z = real(c, kind=dp)",
        "   end block",
        "   z = real(c, kind=dp)",
        "   z = real(unshadowed, kind=dp)",
        "end function f",
    ]
    out = "\n".join(xp2f.simplify_redundant_dp_cast_general(lines))
    assert out.count("real(c, kind=dp)") == 2, out
    assert "z = unshadowed" in out, out


def test_xp2f_real_part_after_branch_type_rebinding(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xreal_rebound.py", [
        "import numpy as np",
        "def largest(flag):",
        "    if flag:",
        "        c = np.array([1.0, 2.0])",
        "        result = np.max(np.real(c))",
        "    else:",
        "        c = np.array([3.0 + 8.0j, 4.0 - 9.0j])",
        "        result = np.max(np.real(c))",
        "    return result",
        "print(largest(True))",
        "print(largest(False))",
    ])


def test_xp2f_simplifies_redundant_dp_cast_general_end_to_end(tmp_path: Path) -> None:
    # Companion end-to-end test: real(exp(...), kind=dp) and
    # real(array_element, kind=dp) shapes, run through the full
    # pipeline, confirming build success and byte-identical run output
    # (via _run_xp2f_compile_diff's own run-diff check).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdp_cast_general.py",
        [
            "import math",
            "",
            "def make_arr():",
            "    a = [0.0] * 3",
            "    a[0] = 1.0",
            "    a[1] = 2.0",
            "    a[2] = 3.0",
            "    return a",
            "",
            "def f(mean_x, var_x):",
            "    return math.exp(mean_x + 0.5 * var_x)",
            "",
            "arr = make_arr()",
            "eh = f(0.1, 0.2)",
            "first = arr[0]",
            "print(eh, first)",
        ],
    )
    out_f90 = (tmp_path / "xdp_cast_general_p.f90").read_text(encoding="utf-8")
    assert "real(exp(" not in out_f90, out_f90


def test_fortran_narrow_paren_simplification_never_strips_mandatory_if_where_parens() -> None:
    # Regression test: user's own full-suite `pytest -q` run surfaced a
    # real, invalid-Fortran-producing bug in simplify_narrow_redundant_
    # arith_parens' bare-atom rule (added for `size(x) - (k)` -> `size(x)
    # - k`, earlier this same session): it doesn't distinguish a
    # decorative grouping paren from the MANDATORY condition/mask
    # delimiter Fortran's own `if (...)`, `where (...)`, `elsewhere
    # (...)`, `do while (...)`, `select case (...)` statement syntax
    # requires -- `if (x) then` -> `if x then` isn't a style
    # simplification, it's a syntax error (confirmed: this exact bug
    # broke real generated code from a `globals()` membership check, a
    # `where`-masked array assignment, and a `result.success`-style
    # optimizer-result check -- none involving anything unusual, just an
    # ordinary single bare-name condition). Fixed by never stripping a
    # bare-atom (or negated-atom) paren immediately preceded by one of
    # those statement keywords, while every genuinely-decorative case
    # (arithmetic grouping, a call's own argument-list parens) is still
    # simplified exactly as before.
    lines = [
        "   if (xp2f_has_global_x) then",
        "      print *, 1",
        "   end if",
        "   where (keep)",
        "      out = raw",
        "   end where",
        "   elsewhere (mask)",
        "      out = 0",
        "   end where",
        "   do while (n)",
        "      n = n - 1",
        "   end do",
        "   if (result_success) print *, 1",
        "   x = size(y) - (k)",
        "   z = (-w)",
    ]
    out = xp2f.simplify_narrow_redundant_arith_parens(lines)
    assert out[0] == "   if (xp2f_has_global_x) then", out
    assert out[3] == "   where (keep)", out
    assert out[6] == "   elsewhere (mask)", out
    assert out[9] == "   do while (n)", out
    assert out[12] == "   if (result_success) print *, 1", out
    # Genuinely decorative parens are still simplified.
    assert out[13] == "   x = size(y) - k", out
    assert out[14] == "   z = -w", out


def test_fortran_narrow_paren_simplification_strips_comparison_operand_parens() -> None:
    # User-reported real examples, from xdelta_gamma.py's generated
    # bisect_root: `if ((0.5_dp * (b_local - a_local)) < tol_opt) then`
    # and `if ((fa * fm) <= 0) then` -- parens wrapping an ENTIRE operand
    # of a relational operator (<, <=, >, >=, ==, /=), on either side.
    # Every arithmetic operator binds tighter than every relational one
    # in Fortran, so these outer parens are always redundant regardless
    # of what's inside them (+, -, *, or / at the operand's own top
    # level) -- unlike the `*`/`/`-as-RHS-of-+/-` rule above, this
    # carries no floating-point-reordering risk at all, since nothing
    # about the wrapped operand's own internal grouping changes.
    lines = [
        "         if ((0.5_dp * (b_local - a_local)) < tol_opt) then",
        "      if ((fa * fm) <= 0) then",
        "   if (x < (y)) then",
        "   x = (a - b) < (c + d)",
        # Declined: a function/array call's own argument-list parens.
        "   if (x < sqrt(y)) then",
        "   if (sqrt(x) < y) then",
        # Declined: the wrapped content itself has a relational/logical
        # operator or a top-level comma (conservative substring check,
        # not depth-aware -- matches this function's established style).
        "   if ((a .and. b) < c) then",
        "   if ((merge(0.0_dp, x, y < z)) < w) then",
        # Untouched: no parens to strip, including the MANDATORY `if (`.
        "   if (x < y) then",
    ]
    out = xp2f.simplify_narrow_redundant_arith_parens(lines)
    assert out[0] == "         if (0.5_dp * (b_local - a_local) < tol_opt) then", out
    assert out[1] == "      if (fa * fm <= 0) then", out
    assert out[2] == "   if (x < y) then", out
    assert out[3] == "   x = a - b < c + d", out
    assert out[4] == "   if (x < sqrt(y)) then", out
    assert out[5] == "   if (sqrt(x) < y) then", out
    assert out[6] == "   if ((a .and. b) < c) then", out
    assert out[7] == "   if ((merge(0.0_dp, x, y < z)) < w) then", out
    assert out[8] == "   if (x < y) then", out


def test_fortran_narrow_paren_simplification_strips_group_before_addsub() -> None:
    # User-reported real example, from xdelta_gamma.py:
    # `pnl_dg = (delta0 * x) + ((0.5_dp * gamma0) * x) * x`. The FIRST
    # group is immediately followed by `+`, so rule (5) drops its parens
    # regardless of its own content. The SECOND group is followed by `*`
    # (out of rule (5)'s scope, which only fires right before a genuine
    # +/-) but is itself the RHS operand of that same `+` with `*`-only
    # content -- pre-existing rule (2) drops ITS outer parens too, so
    # both groups end up unwrapped here.
    lines = [
        "   pnl_dg = (delta0 * x) + ((0.5_dp * gamma0) * x) * x",
        # Safe: preceded by "-", but inner has no top-level +/-, so
        # subtracting the whole group needs no sign distribution.
        "   y = x - (a * b) + c",
        # UNSAFE and must be left alone: preceded by "-" with inner
        # +/- content -- stripping would require flipping every term's
        # sign, which plain paren removal does not do. Regression for a
        # bug caught before shipping: `x - (a - b) + c` was being
        # rewritten to `x - a - b + c`, silently changing the computed
        # value (10 vs 6 for x=10,a=3,b=2,c=1).
        "   y = x - (a - b) + c",
        "   y = x - (a + b) + c",
    ]
    out = xp2f.simplify_narrow_redundant_arith_parens(lines)
    assert out[0] == "   pnl_dg = delta0 * x + (0.5_dp * gamma0) * x * x", out
    assert out[1] == "   y = x - a * b + c", out
    assert out[2] == "   y = x - (a - b) + c", out
    assert out[3] == "   y = x - (a + b) + c", out


def test_fortran_simplify_additive_zero_identity() -> None:
    # User-reported real example, from xdelta_gamma.py:
    # `idx_1 = 0 + (i_iter_175 - 1)` simplifies to
    # `idx_1 = i_iter_175 - 1`.
    lines = [
        "   idx_1 = 0 + (i_iter_175 - 1)",
        # Something follows on the line: parens are kept (can't just
        # concatenate the bare expression into the middle of the line).
        "   x = 0 + (a - b) + 5",
        # Declined: real zero, not a bare integer literal -- IEEE-754
        # has 0.0 + (-0.0) = +0.0, which is NOT the same value as -0.0,
        # so this transform must not apply to real operands.
        "   x = 0.0_dp + (a - b)",
        # Declined: kind-suffixed integer zero looks textually similar
        # but isn't matched by the bare-"0" pattern.
        "   x = 0_dp + (a - b)",
        # Declined: not a zero literal at all.
        "   x = 1 + (a - b)",
    ]
    out = xp2f.simplify_additive_zero_identity(lines)
    assert out[0] == "   idx_1 = i_iter_175 - 1", out
    assert out[1] == "   x = (a - b) + 5", out
    assert out[2] == "   x = 0.0_dp + (a - b)", out
    assert out[3] == "   x = 0_dp + (a - b)", out
    assert out[4] == "   x = 1 + (a - b)", out


def test_fortran_wrap_never_splits_two_character_comparison_operator() -> None:
    # Regression test: user's own full-suite run surfaced a second real
    # bug -- the long-line wrapper's break-candidate scan offered "="
    # as a break point whenever it appeared, without checking whether it
    # was actually the SECOND character of a two-character comparison
    # operator ("<=", ">=", "==", "/="). Splitting there stranded the
    # operator's own first character ("<", ">", "=", "/") alone at the
    # end of one line and its second character ("=") alone at the start
    # of the next -- e.g. a `parity_error <= tolerance` comparison
    # emitted as `... <\n   & = tolerance ...`, a syntax error, not
    # merely a style regression (confirmed against a real generated
    # `merge(...) <= merge(...)` NaN-safe comparison guard). Fixed by
    # never offering "=" as a break point when the character right
    # before it is "<", ">", "=", or "/".
    long_expr = (
        "   if (merge(.false., merge(0.0_dp, parity_error, ieee_is_nan(parity_error)) "
        "<= merge(0.0_dp, tolerance, ieee_is_nan(tolerance)), ieee_is_nan(parity_error) "
        '.or. ieee_is_nan(tolerance))) write(*,"(a)") "ok"'
    )
    wrapped = fscan.wrap_long_fortran_line(long_expr, max_len=80)
    assert wrapped is not None, long_expr
    for ln in wrapped:
        assert len(ln) <= 80, wrapped
    joined = " ".join(s.strip().lstrip("&").strip() for s in wrapped)
    assert "< =" not in joined and "<=" in joined.replace("< =", "<="), wrapped
    # No line's own trailing "&" leaves a bare "<", ">", "=", or "/"
    # dangling as the very last non-"&" character (i.e. never the sole
    # first half of a two-char operator stranded alone).
    for ln in wrapped[:-1]:
        stripped = ln.rstrip()
        assert stripped.endswith("&")
        before_amp = stripped[:-1].rstrip()
        assert not (before_amp and before_amp[-1] in "<>=/" and not before_amp.endswith(("<=", ">=", "==", "/="))), wrapped


def test_xp2f_removes_unused_entity_from_combined_parameter_declaration(tmp_path: Path) -> None:
    # Regression test: user's own full-suite run surfaced a third real
    # issue -- combining same-type `parameter` declarations onto one
    # line (this session's own earlier "should named constants of the
    # same type be combined" fix) interacted badly with remove_unused_
    # named_constants, which only ever recognized a SINGLE-entity
    # `parameter` declaration as a removal candidate (`if len(items) !=
    # 1: continue`). Once `sp`/`dp` (or any other pair) landed on one
    # combined line, an unused `sp` sitting next to a used `dp` could
    # never be pruned again -- not a compile error, just permanently
    # reintroduced dead code the SAME pass used to correctly clean up.
    # Fixed by tracking each entity on a multi-entity `parameter` line as
    # its own independent candidate (by line + position), so an unused
    # one is surgically removed from the comma list while a used sibling
    # on the SAME line is left in place.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xunused_sp_removal.py",
        [
            "xsum = 0.0",
            "for i in range(10):",
            "    xsum = xsum + i",
            "print(xsum)",
        ],
    )
    out_f90 = (tmp_path / "xunused_sp_removal_p.f90").read_text(encoding="utf-8")
    assert "sp = real32" not in out_f90, out_f90
    assert "dp = real64" in out_f90, out_f90


def test_fortran_format_string_space_literals_convert_and_fold() -> None:
    # Regression test (direct unit test): user-reported real example --
    #     write(*,"(a,'  ',a,'  ',a,'  ',a)") "lag", "empirical", ...
    # -- a comma-item that's a literal string of N spaces is equivalent
    # to Fortran's own `Nx` edit descriptor (outputs N blanks, byte-for-
    # byte the same as printing the literal), and once every item is a
    # plain edit descriptor, a run of L items repeating R times (R>=2)
    # folds into `R(item1, item2, ...)`. User: "(a,'  ',a,'  ',a,'  ',a)"
    # can be "(a, 2x, a, 2x, a, 2x,a)" and then "(3(a, 2x), a)"'. Also
    # exercises: (a) an item that ISN'T pure spaces (`'kappa='`) is left
    # as a literal, never converted; (b) an `i3` edit descriptor
    # interleaved with repeated `2x, f14.8` pairs folds correctly
    # (`i3, 3(2x, f14.8)`) -- the leading non-repeating item is kept
    # bare, only the REPEATING tail is grouped.
    lines = [
        "   write(*,\"(a,'  ',a,'  ',a,'  ',a)\") \"lag\", \"empirical\", "
        '"theoretical", "emp-th"',
        "   write(*,\"(i3,'  ',f14.8,'  ',f14.8,'  ',f14.8)\") k, a, b, c",
        "   write(*,\"('kappa=',g0)\") kappa",
    ]
    out = xp2f.simplify_format_string_space_literals_and_fold_repeats(lines)
    assert '"(3(a, 2x), a)"' in out[0], out
    assert '"(i3, 3(2x, f14.8))"' in out[1], out
    # A non-space literal is never touched.
    assert "'kappa='" in out[2], out


def test_xp2f_simplifies_format_string_space_literals_end_to_end(tmp_path: Path) -> None:
    # Companion end-to-end test: an old-style "%" print format (this
    # project's own real-world trigger shape, per xgarch_acf.py's own
    # `print("%3s  %14s  %14s  %14s" % (...))`) generates a Fortran
    # format string with multi-space literal items between numeric
    # fields -- confirms the simplification fires through the full
    # pipeline and preserves output exactly (run-diff MATCH), plus a
    # direct check that the emitted format string was actually folded.
    #
    # Also caught a real regression from a LATER, unrelated fix: an
    # initial attempt at honoring %s's width used a fixed-width Fortran
    # `aW` edit descriptor directly, which -- unlike Python's own %Ns --
    # TRUNCATES a value longer than W ("theoretical" % "%10s" silently
    # became "theoretica"). This test's own run-diff MATCH is what
    # caught it; see the str_rjust-based fix in
    # test_xp2f_percent_format_constant_var_in_multi_arg_print.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xformat_fold.py",
        [
            "print('%3s  %10s  %10s' % ('lag', 'empirical', 'theoretical'))",
            "for k in range(1, 4):",
            "    print('%3d  %10.4f  %10.4f' % (k, float(k), float(k) * 2.0))",
        ],
    )
    out_f90 = (tmp_path / "xformat_fold_p.f90").read_text(encoding="utf-8")
    assert "'  '" not in out_f90, out_f90
    assert re.search(r"\d+x\b", out_f90, re.IGNORECASE), out_f90


def test_xp2f_narrow_paren_simplification_preserves_call_and_division_grouping(tmp_path: Path) -> None:
    # Regression test: an initial attempt at simplifying `exp((-a) *
    # ez_abs)` -> `exp(-a * ez_abs)` and `1.0 + (c * a)` -> `1.0 + c * a`
    # reused fortran_scan's pre-existing (but never previously wired in
    # anywhere) simplify_redundant_parens_in_line -- wiring it in
    # surfaced TWO real, silent correctness bugs: (1) it stripped parens
    # around a `*`/`/` group regardless of what operator preceded it,
    # turning `eh2 / (eh * eh)` into `eh2 / eh * eh` -- division is
    # left-associative at the SAME precedence as multiplication, so
    # `/eh * eh` cancels to a no-op instead of dividing by eh squared;
    # (2) its negated-atom handling didn't check whether the "(" it was
    # about to strip was actually a FUNCTION CALL's own mandatory
    # argument-list paren, turning `acos(-1.0_dp)` into the syntactically
    # invalid `acos-1.0_dp`. Replaced with a narrower, hand-verified
    # simplification restricted to two provably-safe shapes: a negated
    # bare atom (unary minus has no associativity to disturb) unwrapped
    # anywhere except immediately after another +/- or inside a call's
    # own parens, and a `*`/`/`-only group unwrapped ONLY as the operand
    # of a genuinely binary `+`/`-` (never `*`/`/`, which is exactly the
    # unsafe division-reordering case above).
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xnarrow_paren.py",
        [
            "import math",
            "",
            "def f(a, ez_abs, c, kappa, eh, eh2):",
            "    m = math.exp((-a) * ez_abs)",
            "    x = 1.0 + (c * a)",
            "    kurt = (kappa * eh2) / (eh * eh)",
            "    pi_val = math.sqrt(2.0 / math.acos(-1.0))",
            "    return m, x, kurt, pi_val",
            "",
            "m, x, kurt, pi_val = f(0.3, 1.2, 0.5, 3.0, 1.1, 2.4)",
            "print(m, x, kurt, pi_val)",
        ],
    )
    out_f90 = (tmp_path / "xnarrow_paren_p.f90").read_text(encoding="utf-8")
    assert "acos-1.0" not in out_f90, out_f90
    assert re.search(r"eh2\s*/\s*eh\s*\*\s*eh\b", out_f90) is None, out_f90


def test_xp2f_strips_parens_around_bare_atom() -> None:
    # Regression test: user-reported example from a real cross-
    # correlation routine's generated Fortran --
    #     out_(k + 1) = dot_product(x_local(1:size(x_local) - (k)), ...)
    # -- a single bare, unsigned variable/number wrapped in redundant
    # parens. Unlike the `*`/`/`-group case above, a LONE token has no
    # internal structure or associativity to disturb no matter what
    # operator precedes it, so this is safe to strip unconditionally
    # (rule 3 of simplify_narrow_redundant_arith_parens), not just after
    # a binary +/-. Also verifies the fix doesn't touch: (a) a genuine
    # function/array-call's own argument-list parens (`size(k)`), and
    # (b) a "(" that's really just literal text inside a quoted string
    # (e.g. a `write(*, "(a)")` format descriptor) -- an early version of
    # this fix, tried without a string-literal guard, corrupted exactly
    # that into the syntactically invalid `write(*, "a")`.
    lines = [
        "      out_(k + 1) = dot_product(x_local(1:size(x_local) - (k)), y_local(k + &",
        "         & 1:size(y_local))) / denom",
        "      x = (5)",
        "      n = size(k)",
        '      write(*,"(a)") "symmetric garch(1,1)"',
    ]

    out = xp2f.simplify_narrow_redundant_arith_parens(lines)

    assert "size(x_local) - k)" in out[0], out
    assert "x = 5" in out[2], out
    assert "n = size(k)" in out[3], out
    assert out[4] == lines[4], out


def test_fortran_reorder_arg_decls_places_result_variable_before_locals() -> None:
    # User-requested: a function's own `result(...)` variable should be
    # declared right after the dummy arguments and before ordinary
    # locals -- it's conceptually part of the signature, not a working
    # variable. reorder_arg_decls_before_locals already grouped intent(
    # ...) dummies ahead of locals; extended to also recognize a dummy
    # PROCEDURE argument (`procedure(iface) :: f`, no POINTER attribute
    # -- the only way that shape is legal Fortran) as belonging with the
    # other arguments, and to carve the result variable into its own
    # group positioned right after them.
    #
    # Also covers the same interface-block-awareness gap found in
    # coalesce_nonadjacent_declarations: the declaration-section-boundary
    # scan didn't recognize "interface" as declaration-ish (stopping the
    # whole pass dead at the very first line for any callback-taking
    # procedure), and the procedure's own end was found by searching for
    # the first "end function"/"end subroutine", which matched the
    # callback interface's OWN nested "end function" line first. Fixed
    # the same way, plus: the interface block is now kept bundled with
    # whichever declaration follows it (its own `procedure(iface) :: f`)
    # so reordering can never separate the two.
    lines = [
        "pure function v_bisect_root(f, a, b, tol, max_iter) result(v_bisect_root_result)",
        "   interface",
        "      pure function v_bisect_root_f_cb_if(x) result(r)",
        "         import dp",
        "         real(kind=dp), intent(in) :: x",
        "         real(kind=dp) :: r",
        "      end function v_bisect_root_f_cb_if",
        "   end interface",
        "   procedure(v_bisect_root_f_cb_if) :: f",
        "   real(kind=dp), intent(in) :: a, b",
        "   real(kind=dp), intent(in), optional :: tol",
        "   integer, intent(in), optional :: max_iter",
        "   real(kind=dp) :: tol_opt",
        "   integer :: max_iter_opt",
        "   real(kind=dp) :: v_bisect_root_result",
        "   real(kind=dp) :: fa, fb, fm, m",
        "   integer :: i_",
        "   real(kind=dp) :: a_local, b_local",
        "   a_local = a",
        "end function v_bisect_root",
    ]

    out = xp2f.reorder_arg_decls_before_locals(lines)
    joined = "\n".join(out)

    # The interface block travels with its own procedure(...) :: f line,
    # both still positioned right after the function's own signature.
    assert "\n".join(lines[1:9]) in joined, joined
    # The result variable now comes right after the dummy args (interface
    # block + procedure(...) :: f + the intent(...) ones), before ANY
    # local -- specifically before tol_opt, which appears earlier than it
    # in the ORIGINAL, unreordered source.
    result_idx = out.index("   real(kind=dp) :: v_bisect_root_result")
    tol_idx = out.index("   real(kind=dp) :: tol_opt")
    max_iter_idx = out.index("   integer, intent(in), optional :: max_iter")
    assert max_iter_idx < result_idx < tol_idx, joined


def test_xp2f_coalesces_adjacent_scalar_parameter_declarations() -> None:
    # Regression test: user-reported example from a real generated
    # program --
    #     real(kind=dp), parameter :: d = 0.3_dp
    #     real(kind=dp), parameter :: mu = 0.0_dp
    #     real(kind=dp), parameter :: phi = 0.97_dp
    #     real(kind=dp), parameter :: sigma_eta = 0.2_dp
    #     real(kind=dp), parameter :: theta = 0.2_dp
    # -- five same-type `parameter` declarations left unmerged, even
    # though ordinary (non-parameter) same-type locals were already
    # combined by this same pass. coalesce_nonadjacent_declarations
    # blanket-excluded ANY initialized entity (`= ...`) from merging.
    # First fix narrowed the exclusion to `parameter`-only; user then
    # pointed out this is needlessly narrow -- `real, save :: x = 1.0, y
    # = 2.0` is equally valid Fortran, and so is mixing bare and
    # initialized entities on one line (`real :: x, y, z = 3.0`), since
    # Fortran applies (implicit or explicit) SAVE per-entity, not per-
    # statement: an uninitialized entity sharing a merged line with an
    # initialized one never itself acquires SAVE. Generalized to allow
    # ANY scalar initialized entity to merge with anything of the same
    # type-spec, dropping the parameter-only gate entirely -- only an
    # ARRAY-shaped initialized entity (shape+initializer ordering isn't
    # attempted) is still left alone.
    lines = [
        "program p",
        "   implicit none",
        "   real(kind=dp), parameter :: d = 0.3_dp",
        "   real(kind=dp), parameter :: mu = 0.0_dp",
        "   real(kind=dp), parameter :: phi = 0.97_dp",
        "   real(kind=dp), parameter :: sigma_eta = 0.2_dp",
        "   real(kind=dp), parameter :: theta = 0.2_dp",
        "   integer, parameter :: shape_arr(2) = [1, 2]",
        "   integer, parameter :: shape_arr2(2) = [3, 4]",
        "   integer, save :: counter",
        "   integer, save :: total = 0",
        "   real :: x",
        "   real :: y",
        "   real :: z = 3.0",
        "   print *, d, mu, phi, sigma_eta, theta, x, y, z",
        "end program p",
    ]

    out = xp2f.coalesce_nonadjacent_declarations(lines)
    joined = "\n".join(out)

    assert (
        "real(kind=dp), parameter :: d = 0.3_dp, mu = 0.0_dp, phi = 0.97_dp, "
        "sigma_eta = 0.2_dp, theta = 0.2_dp" in joined
    ), joined
    # Array-shaped parameter entities are never merged (no attempt made
    # to line up a shape spec with a merged initializer list).
    assert "integer, parameter :: shape_arr(2) = [1, 2]" in joined, joined
    assert "integer, parameter :: shape_arr2(2) = [3, 4]" in joined, joined
    # A bare entity ("counter") merges with an initialized one of the
    # same spec ("total = 0") -- SAVE still only applies to "total".
    assert "integer, save :: counter, total = 0" in joined, joined
    # Two bare entities merge with a trailing initialized one, all on
    # one line, exactly as the user described for a main-program context
    # where SAVE isn't a consideration.
    assert "real :: x, y, z = 3.0" in joined, joined


def test_xp2f_coalesce_nonadjacent_declarations_merges_past_callback_interface() -> None:
    # User-reported real gap: a procedure taking a dummy PROCEDURE
    # argument declares its callback's own abstract interface right at
    # the top of its declaration section (e.g. v_bisect_root's
    # `interface / pure function v_bisect_root_f_cb_if(x) result(r) /
    # ... / end interface`) -- but the section-boundary scan didn't
    # recognize "interface" as declaration-ish at all, so it stopped
    # dead on the very FIRST line, treating the section as completely
    # empty and leaving every real declaration after it (tol_opt,
    # v_bisect_root_result, fa/fb/fm/m, a_local/b_local, ...) untouched.
    # Worse, a SEPARATE bug in the same pass located the procedure's own
    # end by searching for the first "end function"/"end subroutine" --
    # which matched the callback interface's OWN nested "end function"
    # line first, truncating the pass's view of the procedure's body
    # entirely.
    #
    # Fixed by tracking interface nesting in both the end-of-procedure
    # search and the declaration-section-boundary scan (walking straight
    # past an entire interface block rather than stopping at it or
    # inside it), and by keeping the interface block itself as one
    # opaque, position-preserving unit that's never parsed as a merge
    # candidate (so nothing inside it -- e.g. its own `real(kind=dp),
    # intent(in) :: x` -- gets mixed into the OUTER function's locals).
    lines = [
        "pure function v_bisect_root(f, a, b, tol, max_iter) result(v_bisect_root_result)",
        "   interface",
        "      pure function v_bisect_root_f_cb_if(x) result(r)",
        "         import dp",
        "         real(kind=dp), intent(in) :: x",
        "         real(kind=dp) :: r",
        "      end function v_bisect_root_f_cb_if",
        "   end interface",
        "   procedure(v_bisect_root_f_cb_if) :: f",
        "   real(kind=dp), intent(in) :: a, b",
        "   real(kind=dp), intent(in), optional :: tol",
        "   integer, intent(in), optional :: max_iter",
        "   real(kind=dp) :: tol_opt",
        "   integer :: max_iter_opt",
        "   real(kind=dp) :: v_bisect_root_result",
        "   real(kind=dp) :: fa, fb, fm, m",
        "   integer :: i_",
        "   real(kind=dp) :: a_local, b_local",
        "   a_local = a",
        "end function v_bisect_root",
    ]

    out = xp2f.coalesce_nonadjacent_declarations(lines, max_len=10**9)
    joined = "\n".join(out)

    # The interface block itself is completely untouched, in place.
    assert "\n".join(lines[1:8]) in joined, joined
    # Everything after it (dummy args aside) merges by type-spec.
    assert "real(kind=dp) :: tol_opt, fa, fb, fm, m, a_local, b_local" in joined, joined
    assert "integer :: max_iter_opt, i_" in joined, joined
    # The function's own result variable stays on its own line.
    assert "real(kind=dp) :: v_bisect_root_result" in joined, joined


def test_xp2f_module_global_merges_despite_unrelated_callback_result_name_collision(
    tmp_path: Path,
) -> None:
    # User-reported real gap (xdelta_gamma.py): a callback's own abstract
    # interface stub always names its result "r" (hardcoded, see
    # `result(r)` in _emit_local_function), completely unrelated to
    # anything else in the file -- but _result_names, computed as a
    # single FILE-WIDE scan for every `result(NAME)` occurrence, doesn't
    # distinguish "a real procedure's own result variable" (which
    # legitimately must never be merged with its locals) from "some
    # unrelated callback interface's hardcoded result name" -- so it
    # wrongly protected the module-level global variable `r` from ever
    # being merged with its sibling globals, breaking the merge chain
    # for a variable right after it too (nothing left to merge into).
    # Fixed by excluding `result(...)` matches found inside an
    # `interface ... end interface` block from _result_names.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xmodule_global_r_collision.py"
    src.write_text(
        "\n".join(
            [
                "def bisect(f, a, b):",
                "    for _ in range(60):",
                "        m = (a + b) / 2.0",
                "        if f(a) * f(m) <= 0.0:",
                "            b = m",
                "        else:",
                "            a = m",
                "    return (a + b) / 2.0",
                "",
                "def g(x, k, r=0.0):",
                "    return x * k + r",
                "",
                "def h(x, k, r=0.0):",
                "    return x - k - r",
                "",
                "k = 2.0",
                "r = 0.5",
                "",
                "def _cb(x):",
                "    return g(x, k, r=r)",
                "",
                "root = bisect(_cb, -10.0, 10.0)",
                "print(root)",
                "print(h(1.0, k, r=r))",
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
    out_f90 = (tmp_path / "xmodule_global_r_collision_p.f90").read_text(encoding="utf-8")
    assert "real(kind=dp) :: k, r" in out_f90, out_f90
    # The unrelated callback interface stub keeps its own hardcoded name.
    assert "result(r)" in out_f90, out_f90


def test_xp2f_coalesce_simple_declarations_merges_scalar_initializer() -> None:
    # Companion to test_xp2f_coalesces_adjacent_scalar_parameter_
    # declarations, but for fortran_scan.coalesce_simple_declarations --
    # the simpler, adjacent-only, single-entity-per-line sibling pass
    # that runs right after coalesce_nonadjacent_declarations in the
    # default pipeline (covers declarations coalesce_nonadjacent_
    # declarations doesn't reach, e.g. module-level declarations outside
    # any function/subroutine/program unit). Its own decl_re previously
    # had no way to even match a "NAME = VALUE" entity, so the "skip
    # initialized entities" check was dead code; extended the regex to
    # capture an optional scalar initializer and merge it like any other
    # entity of the same type-spec, while still declining to merge an
    # ARRAY-shaped initialized entity.
    lines = [
        "real, save :: x = 1.0",
        "real, save :: y = 2.0",
        "real, save :: z = 3.0",
        "integer, parameter :: shape_arr(2) = [1, 2]",
    ]

    out = xp2f.coalesce_simple_declarations(lines, max_len=10**9)
    joined = "\n".join(out)

    assert "real, save :: x = 1.0, y = 2.0, z = 3.0" in joined, joined
    assert "integer, parameter :: shape_arr(2) = [1, 2]" in joined, joined


def test_xp2f_math_module_constants(tmp_path: Path) -> None:
    # Regression test: math.pi (and math.e/math.tau/math.nan/math.inf)
    # weren't recognized as expressions at all -- "unsupported attribute
    # expr: math.pi" -- even though the identical np.pi/cmath.pi/cmath.e/
    # cmath.tau were already supported. Extended the existing np/cmath
    # Attribute-dispatch branches (in expr() and _expr_kind) to also
    # match "math".
    _run_xp2f_compile_diff(
        tmp_path,
        "xmath_consts.py",
        [
            "import math",
            "",
            "print(math.sqrt(2.0 / math.pi))",
            "print(math.e)",
            "print(math.tau)",
        ],
    )


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


def test_xp2f_unpacks_tuple_return_passthrough_wrapper(tmp_path: Path) -> None:
    # Regression test: a thin wrapper whose ONLY return statement forwards
    # another local function's tuple return directly (`def wrapper(a, b):
    # return inner(a, b)`, as opposed to a literal `return a, b, c` tuple
    # built from wrapper's own locals) was invisible to the whole-program
    # tuple_return_funcs classification entirely -- its return value is
    # an ast.Call, not an ast.Tuple/List, which is all that classification
    # scanned for. A call-site tuple-unpack of wrapper's result
    # (`x, y, z = wrapper(3.0, 2.0)`) then raised a flat "unsupported
    # assign", and even after threading the classification through (see
    # _local_return_maps's own separate, now-fixed passthrough case),
    # wrapper's generated subroutine body came out completely EMPTY --
    # the dedicated ast.Return handling inside _emit_local_function's own
    # body-visiting loop (a second, separate copy of the same
    # Tuple/List-only check, not translator.visit_Return) silently
    # skipped a Call-valued return with no assignment to wrapper's own
    # out-args at all, leaving them uninitialized. Real-world pattern
    # this came from: garch_acf.py's acf_abs_garch_1_1(...) -> return
    # acf_abs_from_pq(...) (a GARCH ACF/autocov helper library on
    # GitHub). Fixed with three changes: (1) the whole-program
    # tuple_return_funcs/local_tuple_return_out_names classification now
    # recognizes this passthrough shape via a fixed-point pass (handles
    # a chain of wrappers regardless of local_funcs ordering); (2)
    # _emit_local_function's own tuple_return_seed derivation falls back
    # to the precomputed out-names for a passthrough function instead of
    # trying to walk .elts on a non-existent literal tuple; (3) BOTH the
    # dedicated ast.Return handling inside _emit_local_function's body
    # loop AND translator.visit_Return itself now recognize a passthrough
    # Call and synthesize an Assign straight into the function's own
    # already-declared intent(out) dummy arguments, reusing the general
    # tuple-unpack-from-call codegen in visit_Assign.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xtuple_passthrough_wrapper.py",
        [
            "def inner(a, b):",
            "    return a + b, a - b, a * b",
            "",
            "def wrapper(a, b):",
            "    return inner(a, b)",
            "",
            "x, y, z = wrapper(3.0, 2.0)",
            "print(x, y, z)",
        ],
    )


def test_xp2f_matches_out_names_across_multiple_tuple_return_statements(tmp_path: Path) -> None:
    # Regression test: a function with TWO value-returning tuple Return
    # statements at different AST nesting depths (an early guard-clause
    # `if burn: return eps[burn:], h[burn:]` followed by a final, plain
    # `return eps, h`) desynced two independent whole-program scans that
    # are each supposed to agree on the function's out-argument names:
    # the classification loop feeding local_tuple_return_out_names (used
    # to build the keyword argument names at every CALL site) walked
    # ast.walk(fn)'s BREADTH-first order, which visits a LATER top-level
    # Return before an EARLIER but more deeply nested one -- picking
    # `return eps, h` (Name elts -> out_names ["eps", "h"]) as "first".
    # _emit_local_function's own out-name derivation (used for the
    # actual subroutine's dummy-argument declarations) instead uses
    # _value_returns_excluding_nested, true DEPTH-first SOURCE order --
    # picking the textually-earlier `return eps[burn:], h[burn:]` (
    # Subscript elts -> out_names ["sim_out_1", "sim_out_2"]) as "first".
    # The call site then emitted `call sim(..., eps=eps, h=h)` against a
    # subroutine whose real dummy arguments were named sim_out_1/
    # sim_out_2 -- a hard gfortran "Keyword argument ... is not in the
    # procedure" compile error. Fixed by switching the classification
    # loop to the same _value_returns_excluding_nested source-order scan
    # _emit_local_function already uses, so both agree on which Return
    # is "first" regardless of AST nesting depth.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    _run_xp2f_compile_diff(
        tmp_path,
        "xmultiret_order.py",
        [
            "import numpy as np",
            "",
            "def sim(n, burn=0):",
            "    eps = np.empty(n + burn, dtype=float)",
            "    h = np.empty(n + burn, dtype=float)",
            "    for i in range(n + burn):",
            "        eps[i] = float(i)",
            "        h[i] = float(i) * 2.0",
            "    if burn:",
            "        return eps[burn:], h[burn:]",
            "    return eps, h",
            "",
            "eps, h = sim(5, burn=2)",
            "print(eps)",
            "print(h)",
        ],
    )


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
    # The MANDATORY outer `if (...)` wrapper around the whole condition
    # must never be stripped -- this exact shape (missing it) would be
    # invalid Fortran syntax.
    assert "if (i - j) == (-1) then" not in out_text
    # The redundant inner parens around each comparison operand (and the
    # negated literal) ARE safe to strip and now are (a later, separate
    # simplification) -- so the fully-parenthesized form is no longer
    # the only accepted shape, just still a valid one.
    assert (
        "if ((i - j) == (-1)) then" in out_text
        or "if ((i - j) == -1) then" in out_text
        or "if (i - j == -1) then" in out_text
    )


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


def test_xp2f_pandas_df_print_truncates_and_to_string_prints_everything(tmp_path: Path) -> None:
    # User-asked-for feature, surfaced while diagnosing xdelta_gamma.py:
    # this project's DataFrame display() procedures already ATTEMPTED
    # pandas-style truncation for plain print(df), but two things were
    # wrong: (1) the trigger was "more than 10 rows", not pandas' actual
    # default (display.max_rows=60) -- any 11-60 row frame was wrongly
    # truncated; (2) the "[N rows x M columns]" footer was printed
    # UNCONDITIONALLY, even for an untruncated frame, where real pandas
    # never shows it. Separately, df.to_string() -- which real pandas
    # always prints in FULL, no truncation, no footer -- was a no-op
    # unwrap straight into the same (buggy) truncating print path, so it
    # didn't actually behave like to_string() at all once a frame grew
    # past the wrong 10-row trigger.
    #
    # Fixed: the trigger is now pdf_n > 60 (matching pandas' default
    # max_rows), the footer only prints in the truncating branch, and
    # print(df.to_string()) threads a new full=.true. argument through
    # display()/display_pdf()/display_datetime() (all three DataFrame
    # kinds' runtime procedures, plus xp2f.py's own inline codegen path
    # for a known-column-list frame) to always print every row with no
    # footer, regardless of row count.
    #
    # Not run through _run_xp2f_compile_diff/--run-diff: DataFrame print
    # output has a known, pre-existing cosmetic float-formatting gap from
    # Python's exact column widths (e.g. "1.0" vs "1.000000") -- unrelated
    # to truncation, so this checks the truncation/footer/full-row
    # structure directly instead.
    # Two separate scripts (rather than one with both print(df_big) and
    # print(df_big.to_string())): row 30 needs to be checked ABSENT from
    # the plain-print output and PRESENT in the to_string() output, which
    # a single concatenated stdout can't distinguish once both calls have
    # run.
    src_plain = tmp_path / "xdf_print_truncation_plain.py"
    src_plain.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "df_small = pd.DataFrame({'a': np.arange(30, dtype=float)})",
                "print(df_small)",
                "df_big = pd.DataFrame({'a': np.arange(70, dtype=float)})",
                "print(df_big)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc_plain = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src_plain), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_plain.returncode == 0, proc_plain.stdout + proc_plain.stderr
    assert "Build: PASS" in proc_plain.stdout, proc_plain.stdout + proc_plain.stderr
    assert "Run: PASS" in proc_plain.stdout, proc_plain.stdout + proc_plain.stderr
    out_plain = proc_plain.stdout

    # df_small (30 rows, <= max_rows=60): printed in full, no footer --
    # e.g. row 15 (a value this session's earlier bug would have cut,
    # since it wrongly truncated past 10 rows) is present.
    assert "15.000000" in out_plain, out_plain
    assert "29.000000" in out_plain, out_plain
    assert "[30 rows" not in out_plain, out_plain

    # df_big (70 rows > 60): truncated to first/last 5, WITH the footer,
    # and a row from the omitted middle (row 30) absent.
    assert "[70 rows x 1 columns]" in out_plain, out_plain
    assert "4.000000" in out_plain, out_plain
    assert "65.000000" in out_plain, out_plain
    assert "30.000000" not in out_plain, out_plain

    src_tostr = tmp_path / "xdf_print_truncation_to_string.py"
    src_tostr.write_text(
        "\n".join(
            [
                "import numpy as np",
                "import pandas as pd",
                "",
                "df_big = pd.DataFrame({'a': np.arange(70, dtype=float)})",
                "print(df_big.to_string())",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc_tostr = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src_tostr), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_tostr.returncode == 0, proc_tostr.stdout + proc_tostr.stderr
    assert "Build: PASS" in proc_tostr.stdout, proc_tostr.stdout + proc_tostr.stderr
    assert "Run: PASS" in proc_tostr.stdout, proc_tostr.stdout + proc_tostr.stderr
    out_tostr = proc_tostr.stdout

    # df_big.to_string(): every row present (row 30, cut from the plain
    # print(df) above, now appears), and no footer at all.
    assert "30.000000" in out_tostr, out_tostr
    assert "69.000000" in out_tostr, out_tostr
    assert "[70 rows" not in out_tostr, out_tostr


def test_xp2f_no_nan_safe_compare_flag_emits_plain_comparisons(tmp_path: Path) -> None:
    # User-requested feature: by default, a real-valued comparison (<, <=,
    # >, >=, ==, /=) is wrapped in a merge()/ieee_is_nan() guard so a NaN
    # operand quietly evaluates the way Python/pandas would (False, True
    # for !=) instead of tripping -ffpe-trap=invalid -- but for a function
    # with several such comparisons (e.g. a piecewise PnL helper with
    # `if x <= x_L: ... if x >= x_R: ...`), that guard buries the actual
    # branching logic under several lines of merge()/ieee_is_nan() noise
    # per condition. --no-nan-safe-compare (NAN_SAFE_COMPARISONS) opts out:
    # plain `if (x <= x_L) then`, idiomatic and human-readable, at the
    # cost of NaN-safety (a NaN operand can then crash a strict-FPE
    # build). Default (flag absent) behavior is unchanged -- checked here
    # too, so a regression in either direction is caught.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xno_nan_safe_compare.py"
    src.write_text(
        "\n".join(
            [
                "def f(x, x_L, x_R):",
                "    if x <= x_L:",
                "        return -1.0",
                "    if x >= x_R:",
                "        return 1.0",
                "    return 0.0",
                "",
                "print(f(-2.0, -1.0, 1.0))",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc_default = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_default.returncode == 0, proc_default.stdout + proc_default.stderr
    assert "Build: PASS" in proc_default.stdout, proc_default.stdout + proc_default.stderr
    assert "Run: PASS" in proc_default.stdout, proc_default.stdout + proc_default.stderr
    out_f90_default = (tmp_path / "xno_nan_safe_compare_p.f90").read_text(encoding="utf-8")
    assert "ieee_is_nan" in out_f90_default, out_f90_default
    assert re.search(r"if\s*\(x\s*<=\s*x_L\)", out_f90_default) is None, out_f90_default

    proc_flag = subprocess.run(
        [sys.executable, str(XP2F_PATH), str(src), "--no-nan-safe-compare", "--compile", "--run"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_flag.returncode == 0, proc_flag.stdout + proc_flag.stderr
    assert "Build: PASS" in proc_flag.stdout, proc_flag.stdout + proc_flag.stderr
    assert "Run: PASS" in proc_flag.stdout, proc_flag.stdout + proc_flag.stderr
    out_f90_flag = (tmp_path / "xno_nan_safe_compare_p.f90").read_text(encoding="utf-8")
    assert "ieee_is_nan" not in out_f90_flag, out_f90_flag
    assert re.search(r"if\s*\(x\s*<=\s*x_L\)", out_f90_flag), out_f90_flag
    assert re.search(r"if\s*\(x\s*>=\s*x_R\)", out_f90_flag), out_f90_flag
    # Same output either way -- the flag only changes HOW the comparison
    # is emitted, never the result for non-NaN inputs.
    assert "-1.0" in proc_default.stdout, proc_default.stdout
    assert "-1.0" in proc_flag.stdout, proc_flag.stdout


def test_fortran_elemental_promotion_repacks_whole_wrapped_signature() -> None:
    # User-reported real gap: `apply_decl_edit_at_or_continuation`
    # (fortran_purity.py, used by both --elemental's promotion and the
    # always-on `pure` promotion) used to edit only the ONE physical line
    # of an already-`&`-wrapped multi-line signature that matched the
    # editor's own regex, then leave the OTHER physical lines of that
    # same statement untouched. Inserting "elemental " lengthens that one
    # line just enough to need re-wrapping on its own, producing a
    # locally-valid but needlessly fragmented split (an extra, under-
    # filled continuation line) instead of the same statement's single,
    # cleanly repacked wrap -- e.g.
    #   pure elemental function f(x, delta0, &
    #      & delta_L, delta_R, &
    #      & x_L, x_R, gamma_L, gamma_R) &
    #      & result(f_result)
    # where "delta_L, delta_R, x_L, x_R, gamma_L, gamma_R) &" would
    # easily fit on ONE continuation line. Fixed by rejoining the whole
    # statement into one flat logical line before editing, then re-
    # wrapping that fresh from scratch.
    lines = [
        "pure function pnl_piecewise_quad_linear_two_sided(x, delta0, delta_L, delta_R, &",
        "   & x_L, x_R, gamma_L, gamma_R) &",
        "   & result(pnl_piecewise_quad_linear_two_sided_result)",
        "   real(kind=dp), intent(in) :: x",
        "end function pnl_piecewise_quad_linear_two_sided",
    ]
    changed = fpurity.apply_decl_edit_at_or_continuation(lines, 0, fpurity.add_elemental_to_declaration)
    assert changed
    joined = " ".join(
        ln.strip().lstrip("&").strip() for ln in lines[:3] if "function" in ln or ln.strip().startswith("&")
    )
    assert "pure elemental function" in joined, lines
    assert "delta_L, delta_R, x_L, x_R, gamma_L, gamma_R" in joined, lines
    for ln in lines[:3]:
        assert len(ln) <= 80, lines
    # Exactly 3 physical lines for the signature (matching a fresh wrap
    # of the whole edited statement), not 4 (the old, fragmented split).
    assert lines[3].strip().startswith("real"), lines


def test_fortran_pure_promotion_allows_provably_pure_callback_chain() -> None:
    # User-discussed real gap: a procedure taking a dummy PROCEDURE
    # argument (a callback, e.g. xdelta_gamma.py's v_bisect_root/f) was
    # UNCONDITIONALLY excluded from `pure` promotion, regardless of
    # whether the callback could be proven pure -- Fortran actually
    # allows a pure procedure to take a procedure dummy argument, IF the
    # dummy's own abstract interface is ALSO declared pure (12.6/
    # C1592), which in turn requires every actual argument ever passed
    # for it, anywhere in the file, to itself be provably pure.
    #
    # This covers the harder, real-world shape: bisect's OWN callback
    # is never called with a concrete name directly -- bracket (itself
    # taking a callback) just hands ITS OWN "f" straight through to
    # bisect. Proving bisect's interface safe therefore depends,
    # transitively, on bracket's OWN interface also being safe, which in
    # turn depends on caller's actual argument (sq, an ordinary already-
    # pure function) -- exactly xdelta_gamma.py's f_right/f_left ->
    # v_bracket_and_solve_positive_root -> v_bisect_root chain.
    lines = [
        "module m",
        "   implicit none",
        "contains",
        "",
        "   function bisect(f, a, b) result(r)",
        "      interface",
        "         function bisect_f_cb_if(x) result(y)",
        "            real(kind=8), intent(in) :: x",
        "            real(kind=8) :: y",
        "         end function bisect_f_cb_if",
        "      end interface",
        "      procedure(bisect_f_cb_if) :: f",
        "      real(kind=8), intent(in) :: a, b",
        "      real(kind=8) :: r",
        "      r = f(a) + f(b)",
        "   end function bisect",
        "",
        "   function bracket(f, a, b) result(r)",
        "      interface",
        "         function bracket_f_cb_if(x) result(y)",
        "            real(kind=8), intent(in) :: x",
        "            real(kind=8) :: y",
        "         end function bracket_f_cb_if",
        "      end interface",
        "      procedure(bracket_f_cb_if) :: f",
        "      real(kind=8), intent(in) :: a, b",
        "      real(kind=8) :: r",
        "      r = bisect(f, a, b)",
        "   end function bracket",
        "",
        "   pure function sq(x) result(y)",
        "      real(kind=8), intent(in) :: x",
        "      real(kind=8) :: y",
        "      y = x * x",
        "   end function sq",
        "",
        "   function caller(a, b) result(r)",
        "      real(kind=8), intent(in) :: a, b",
        "      real(kind=8) :: r",
        "      r = bracket(sq, a, b)",
        "   end function caller",
        "",
        "end module m",
    ]
    updated = fpurity.mark_pure_where_provable(lines)
    text = "\n".join(updated)
    assert re.search(r"^\s*pure function bisect\(", text, re.MULTILINE), text
    assert re.search(r"^\s*pure function bracket\(", text, re.MULTILINE), text
    assert re.search(r"^\s*pure function bisect_f_cb_if\(", text, re.MULTILINE), text
    assert re.search(r"^\s*pure function bracket_f_cb_if\(", text, re.MULTILINE), text


def test_fortran_pure_promotion_declines_callback_with_unresolvable_actual() -> None:
    # Companion negative case: when a callback's actual argument at some
    # call site can't be resolved to a provably-pure name at all (here,
    # an expression rather than a bare name), the analysis must decline
    # to mark the interface (or the procedure taking it) pure -- staying
    # exactly as conservative as before this feature existed, never
    # guessing wrong in the unsafe direction.
    lines = [
        "module m",
        "   implicit none",
        "contains",
        "",
        "   function apply(f, a) result(r)",
        "      interface",
        "         function apply_f_cb_if(x) result(y)",
        "            real(kind=8), intent(in) :: x",
        "            real(kind=8) :: y",
        "         end function apply_f_cb_if",
        "      end interface",
        "      procedure(apply_f_cb_if) :: f",
        "      real(kind=8), intent(in) :: a",
        "      real(kind=8) :: r",
        "      r = f(a)",
        "   end function apply",
        "",
        "   pure function sq(x) result(y)",
        "      real(kind=8), intent(in) :: x",
        "      real(kind=8) :: y",
        "      y = x * x",
        "   end function sq",
        "",
        "   function caller(a) result(r)",
        "      real(kind=8), intent(in) :: a",
        "      real(kind=8) :: r",
        "      r = apply(pick(a), a)",
        "   end function caller",
        "",
        "   function pick(a) result(f_out)",
        "      real(kind=8), intent(in) :: a",
        "      procedure(sq), pointer :: f_out",
        "      f_out => sq",
        "   end function pick",
        "",
        "end module m",
    ]
    updated = fpurity.mark_pure_where_provable(lines)
    text = "\n".join(updated)
    assert not re.search(r"^\s*pure function apply\(", text, re.MULTILINE), text
    assert not re.search(r"^\s*pure function apply_f_cb_if\(", text, re.MULTILINE), text


def test_xp2f_compiles_pure_callback_chain_end_to_end(tmp_path: Path) -> None:
    # End-to-end companion to the two direct-analysis tests above,
    # through the real xp2f.py pipeline (the hand-crafted-Fortran tests
    # cover the harder MULTI-level pass-through case directly against
    # mark_pure_where_provable itself): a local function taking a
    # callback (bisect_root) reached from a nested-closure callback
    # (diff) that's already pure should come out `pure` in the generated
    # Fortran, and the program must still build and run to the correct
    # answer.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpure_callback_chain.py"
    src.write_text(
        "\n".join(
            [
                "def bisect_root(f, a, b):",
                "    fa = f(a)",
                "    for i in range(60):",
                "        mid = (a + b) / 2.0",
                "        fm = f(mid)",
                "        if fa * fm > 0.0:",
                "            a = mid",
                "            fa = fm",
                "        else:",
                "            b = mid",
                "    return (a + b) / 2.0",
                "",
                "def find_root_near(target, lo, hi):",
                "    def diff(x):",
                "        return x * x - target",
                "    return bisect_root(diff, lo, hi)",
                "",
                "result = find_root_near(2.0, 0.0, 10.0)",
                "print(result)",
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
    assert "1.4142135" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "xpure_callback_chain_p.f90").read_text(encoding="utf-8")
    assert re.search(r"^\s*pure function bisect_root\(", out_f90, re.MULTILINE), out_f90
    assert re.search(r"^\s*pure function bisect_root_f_cb_if\(", out_f90, re.MULTILINE), out_f90


def test_xp2f_passthrough_callback_interface_infers_scalar_not_array(tmp_path: Path) -> None:
    # Real bug, surfaced while building the pure-callback-chain feature
    # above: a wrapper function that hands its OWN callback parameter
    # straight through to another local function's callback parameter,
    # never calling it directly itself (e.g. bracket_and_solve(f, x0,
    # x1): a = x0; b = x1; return bisect_root(f, a, b)), had its
    # callback interface's parameter wrongly inferred as an ARRAY
    # (`x(:)`) instead of scalar. Two compounding bugs:
    #
    # 1. The pass-through rank fallback (xp2f.py, callback_specs
    #    computation) blindly guessed rank 1 whenever a callback
    #    parameter was never called directly in the wrapper's own body,
    #    without first checking local_callback_actual_specs -- which
    #    already tracks, from a whole-program scan, the ACTUAL rank of
    #    whatever concrete function gets passed for that parameter at
    #    the wrapper's own call sites (diff, here -- a plain scalar
    #    function). Fixed to prefer that real evidence, falling back to
    #    the rank-1 guess only when no such evidence exists at all.
    #
    # 2. That real evidence never got recorded in the first place for a
    #    callback closing over a module-level global it only READS
    #    (never assigns) -- e.g. a closure-hoisted `closure_..._target`
    #    global (see the closure-hoisting feature above): the scan
    #    context built for exactly this analysis (_callback_scan_tr)
    #    only prescans the one function's own body, which never
    #    registers a name it never assigns, cascading into an
    #    unresolved return-KIND for the whole function and discarding
    #    an otherwise-fine return-RANK inference right alongside it.
    #    Fixed by seeding that scan context with every known module-
    #    level global's kind before prescanning.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xpassthrough_callback_rank.py"
    src.write_text(
        "\n".join(
            [
                "def bisect_root(f, a, b):",
                "    fa = f(a)",
                "    for i in range(60):",
                "        mid = (a + b) / 2.0",
                "        fm = f(mid)",
                "        if fa * fm > 0.0:",
                "            a = mid",
                "            fa = fm",
                "        else:",
                "            b = mid",
                "    return (a + b) / 2.0",
                "",
                "def bracket_and_solve(f, x0, x1):",
                "    a = x0",
                "    b = x1",
                "    return bisect_root(f, a, b)",
                "",
                "def find_root_near(target, lo, hi):",
                "    def diff(x):",
                "        return x * x - target",
                "    return bracket_and_solve(diff, lo, hi)",
                "",
                "result = find_root_near(2.0, 0.0, 10.0)",
                "print(result)",
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
    assert "1.4142135" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "xpassthrough_callback_rank_p.f90").read_text(encoding="utf-8")
    assert re.search(r"function bracket_and_solve_f_cb_if\(x\)", out_f90), out_f90
    assert "x(:)" not in out_f90, out_f90


def test_xp2f_closure_hoisting_deduplicates_repeated_snapshot_and_seed(tmp_path: Path) -> None:
    # User-reported real gap: two nested defs hoisted from the SAME
    # enclosing function, closing over the SAME free variable (e.g.
    # xdelta_gamma.py's f_right/f_left, both closing over piecewise_
    # breakpoints_straddle's own "delta0"), each independently
    # contributed their own top-level `closure_..._delta0 = 0.0_dp` seed
    # AND their own `global closure_..._delta0; closure_..._delta0 =
    # delta0` snapshot right before their respective call sites -- two
    # back-to-back, byte-identical lines each, since nothing between them
    # could have changed the shared source value. Fixed: the top-level
    # seed is now emitted once per unique closure_... name, and a
    # snapshot already known up to date from an earlier statement in the
    # SAME straight-line block is skipped rather than re-emitted.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xclosure_dedup.py"
    src.write_text(
        "\n".join(
            [
                "def bisect_root(f, a, b):",
                "    fa = f(a)",
                "    for i in range(60):",
                "        mid = (a + b) / 2.0",
                "        fm = f(mid)",
                "        if fa * fm > 0.0:",
                "            a = mid",
                "            fa = fm",
                "        else:",
                "            b = mid",
                "    return (a + b) / 2.0",
                "",
                "def two_roots(target, lo, hi):",
                "    def f_right(x):",
                "        return x * x - target",
                "    def f_left(y):",
                "        return y * y - target",
                "    r = bisect_root(f_right, lo, hi)",
                "    l = bisect_root(f_left, lo, hi)",
                "    return r, l",
                "",
                "a, b = two_roots(4.0, 0.0, 10.0)",
                "print(a, b)",
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
    out_f90 = (tmp_path / "xclosure_dedup_p.f90").read_text(encoding="utf-8")
    seed_lines = [ln for ln in out_f90.splitlines() if re.match(r"\s*closure_two_roots_target\s*=\s*0\.0_dp\s*$", ln)]
    assert len(seed_lines) == 1, out_f90
    snapshot_lines = [
        ln for ln in out_f90.splitlines() if re.match(r"\s*closure_two_roots_target\s*=\s*target\s*$", ln)
    ]
    assert len(snapshot_lines) == 1, out_f90


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


def test_xp2f_local_function_pd_dataframe_typed_parameter(tmp_path: Path) -> None:
    # Regression test: a local function parameter annotated `pd.DataFrame`
    # was not tracked in the callee's own translator instance at all --
    # `_pandas_df_match`/`_pandas_df_ref` (the DataFrame-reference codegen
    # path) only ever populates `self.pandas_df_vars`/`pandas_df_columns`
    # from assignment-site inference, so a bare parameter name was invisible
    # to it. The parameter got declared as a plain real(8) dummy, which
    # built fine in isolation but failed at Fortran build time as soon as
    # the caller passed an actual DataFrame value in:
    #   Error: Type mismatch in argument 'df' at (1);
    #   passed TYPE(dataframe_str_index) to REAL(8)
    # Fixed with `_df_arg_types_for_fn`, which detects `pd.DataFrame`-
    # annotated params and seeds `tr.pandas_df_vars`/`tr.pandas_df_columns`
    # for the callee up front (mirroring the existing `dict_arg_types`
    # mechanism for synthesized dict-typed params), plus a new declaration
    # branch emitting `type(DataFrame_str_index), intent(in) :: df`.
    #
    # Uses literal column-name subscripting inside the function body
    # (df["a"]) -- dynamic/runtime column-name lookup (df[col] where col
    # is itself a str parameter) is a separate, harder, not-yet-supported
    # gap (needs a runtime %columns search) and is deliberately not
    # exercised here.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_param.py",
        [
            "import pandas as pd",
            "",
            "",
            "def show_col(df: pd.DataFrame) -> None:",
            "    col = df['a']",
            "    print(col[0], col[1], col[2])",
            "    print(df['a'].sum())",
            "",
            "",
            "def main():",
            "    d = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [4.0, 5.0, 6.0]})",
            "    show_col(d)",
            "",
            "",
            "main()",
        ],
    )
    f90_text = (tmp_path / "xdf_param_p.f90").read_text(encoding="utf-8")
    assert "type(DataFrame_str_index), intent(in) :: df" in f90_text, f90_text


def test_xp2f_pd_dataframe_param_iloc_dynamic_slice_with_unknown_columns(tmp_path: Path) -> None:
    # Regression test, discovered testing the pd.DataFrame-typed-parameter
    # fix above against real code: a local variable assigned from
    # `data.iloc[lo:hi]` where `lo`/`hi` are runtime expressions (not
    # literals) crashed the transpiler entirely -- not just for a
    # DataFrame-typed parameter, but for any DataFrame whose column list
    # isn't statically known at the assignment site (e.g. `data` here is
    # a parameter whose body only reads columns via dynamic f-string
    # keys, so nothing seeds `pandas_df_columns["data"]`):
    #   NotImplementedError: unsupported attribute expr: data.iloc
    # Root causes, both in the type-inference prescan pass (a separate,
    # earlier walk from the actual codegen pass that already handled this
    # fine): (1) prescan's own `iloc`/`select_names` DataFrame-tracking
    # branch required `pandas_df_columns.get(df_id)` to already be
    # non-None before registering the assigned name as a DataFrame at
    # all, so an unknown-columns source fell through to the generic
    # `_extent_expr` numeric-size fallback, which can't handle a bare
    # `df.iloc` attribute; (2) a separate cross-function-call rank-
    # propagation helper (`_promote_name_rank`, used by the same prescan
    # pass to size a caller's local variable from a callee's expected
    # parameter rank) didn't know about `pandas_df_vars`/`dict_typed_vars`
    # either, so it could layer a spurious `real(kind=dp), allocatable`
    # declaration on top of an already-correctly-typed DataFrame variable.
    # Fixed by (1) registering the assigned name in `pandas_df_vars`
    # unconditionally on an "iloc"/"select_names" match, only skipping the
    # (still nice-to-have) `pandas_df_columns` entry when the source
    # columns are unknown, and (2) making `_promote_name_rank` skip any
    # name already known as a DataFrame/dict-typed variable. Also added
    # the `iloc` type-bound procedure to `dataframe_str_index.f90` itself
    # (ported from `dataframe_index_datetime.f90`'s `iloc_datetime`) --
    # `_df_arg_types_for_fn` always defaults a DataFrame-typed parameter
    # to the `DataFrame_str_index` kind, which previously had no `%iloc`
    # at all.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_iloc_dynamic.py",
        [
            "import pandas as pd",
            "",
            "",
            "def running_window_sum(data: pd.DataFrame, lo: int, hi: int) -> float:",
            "    chunk = data.iloc[lo:hi]",
            "    return float(chunk['a'].sum())",
            "",
            "",
            "def main():",
            "    d = pd.DataFrame({'a': [1.0, 2.0, 3.0, 4.0, 5.0], 'b': [5.0, 4.0, 3.0, 2.0, 1.0]})",
            "    start = 1",
            "    end = 3",
            "    print(running_window_sum(d, start, end))",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pd_loc_single_dynamic_column(tmp_path: Path) -> None:
    # Regression test: df.loc[:, col] -- every row, a single (not a
    # list-wrapped) column -- is semantically the same as df[col] (both
    # return a Series/1D array, unlike df.loc[:, ["A","B"]] which stays a
    # DataFrame), but was entirely unrecognized: _pandas_df_match only
    # matched a .loc column-spec that resolves as a string-list literal,
    # so a single column (literal or, as here, a runtime character-
    # scalar expression like a str function parameter) fell all the way
    # through to the generic Subscript fallback and crashed:
    #   NotImplementedError: unsupported attribute expr: data.loc
    # Fixed with a delegating rewrite in expr() -- df.loc[:, col] is
    # rebuilt as the equivalent df[col] Subscript node and handed back
    # to self.expr(), reusing the existing df[col] codegen (already
    # correct for both a literal string and a runtime character-scalar
    # column name) instead of duplicating it. Also had to harden
    # _extent_expr's ast.Tuple-slice branch the same way its ast.Slice
    # branch was hardened for df.iloc[lo:hi] above -- df.loc[:, col]'s
    # slice is an ast.Tuple (Slice, col), and the un-guarded fallback
    # there crashed the same prescan translator instances the same way.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_loc_single.py",
        [
            "import pandas as pd",
            "",
            "",
            "def get_col(data: pd.DataFrame, symbol: str) -> pd.Series:",
            "    return data.loc[:, symbol]",
            "",
            "",
            "def main():",
            "    d = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [4.0, 5.0, 6.0]})",
            "    s = get_col(d, 'a')",
            "    print(s[0], s[1], s[2])",
            "    t = d.loc[:, 'b']",
            "    print(t[0], t[1], t[2])",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pd_dynamic_column_key_str_param_and_to_numpy(tmp_path: Path) -> None:
    # Regression test: df[col] where col is a runtime character-scalar
    # expression (typically a str function parameter) -- as opposed to
    # df["literal"] -- surfaced three separate bugs while chasing
    # .to_numpy(dtype=...) support for the OHLC-Correlation scripts
    # (both scripts' first .to_numpy(dtype=float) usages turned out to
    # already work; dtype= was never the actual blocker):
    #
    # 1. `_arg_used_as_index_or_range` (decides whether an unannotated-
    #    by-usage-evidence argument should be forced to "int") treated
    #    ANY Subscript slice mentioning the argument as integer-index
    #    evidence, with no exception for a DataFrame/dict base -- so a
    #    str-annotated parameter used only as `df[symbol]` got its
    #    explicit `: str` annotation silently overridden to `integer`:
    #    the parameter declared `integer, intent(in) :: symbol`, the
    #    call site passed a string literal into it, and the column
    #    lookup itself came out as raw array indexing. Fixed by
    #    excluding a pandas_df_vars/dict_typed_vars-based subscript.
    # 2. Even with (1) fixed, `col = df[symbol]` (assigning a dynamically
    #    selected column to a plain variable) still declared `col` as a
    #    scalar because prescan's DataFrame-assignment branches all key
    #    off _pandas_df_match, which deliberately only covers shapes
    #    that themselves produce ANOTHER DataFrame (name/iloc/
    #    select_names/head_tail) -- df[col] produces a Series (a plain
    #    real array), a different, uncovered shape. Fixed with a
    #    dedicated prescan branch mirroring the existing df["literal"]
    #    one.
    # 3. Even with (1) and (2) fixed, the live per-statement
    #    _expr_kind/_rank_expr calls used by visit_Assign's type-rebind-
    #    detection (a *different* code path from prescan) still didn't
    #    recognize df[col]'s kind/rank, so it "corrected" the (by then
    #    correct) outer declaration with a wrong on-the-fly scalar
    #    integer declaration inside a block:
    #      Error: Syntax error in argument list
    #    (`col(1)` doesn't parse when `col` resolves to a scalar in that
    #    scope). Fixed by adding the same df[col]-recognizing branch to
    #    _expr_kind and _rank_expr themselves, mirroring their existing
    #    df["literal"] branches.
    #
    # Also exercises the actual to_numpy(dtype=float) shape from the
    # target scripts once (1)-(3) let it transpile at all -- to_numpy's
    # own dynamic-single-column recognition (in _expr_kind, _rank_expr,
    # and expr()'s codegen) was extended alongside the fixes above.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_dyncol.py",
        [
            "import pandas as pd",
            "",
            "",
            "def get_eps(raw_returns: pd.DataFrame, symbol: str) -> float:",
            "    col = raw_returns[symbol]",
            "    eps = raw_returns[symbol].to_numpy(dtype=float) - 1.0",
            "    return float(col[0]) + float(eps[1])",
            "",
            "",
            "def main():",
            "    df = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [4.0, 5.0, 6.0]})",
            "    print(get_eps(df, 'a'))",
            "",
            "",
            "main()",
        ],
    )
    f90_text = (tmp_path / "xdf_dyncol_p.f90").read_text(encoding="utf-8")
    assert "character(len=*), intent(in) :: symbol" in f90_text, f90_text


def test_xp2f_pd_series_rank_all_methods(tmp_path: Path) -> None:
    # Regression test: Series.rank(method=...) for all 5 pandas
    # tie-breaking methods -- "average" (the default, used whether
    # method= is omitted entirely or passed explicitly), "min", "max",
    # "first", "dense". Each lowers to its own rank_*_real helper in
    # python.f90 (RANK_METHOD_HELPERS maps method name -> helper name);
    # all O(n**2), fine for the small per-model/per-symbol comparison
    # tables .rank() is actually used on, not large simulation arrays.
    # For [3.0, 1.0, 2.0, 1.0] (a value with a 2-way tie at the bottom):
    #   average: [4.0, 1.5, 3.0, 1.5]  (tied values share the mean of
    #            the ranks they'd occupy -- equivalently (min+max)/2)
    #   min:     [4.0, 1.0, 3.0, 1.0]  (ties get the smallest rank)
    #   max:     [4.0, 2.0, 3.0, 2.0]  (ties get the largest rank)
    #   first:   [4.0, 1.0, 3.0, 2.0]  (ties broken by original order)
    #   dense:   [3.0, 1.0, 2.0, 1.0]  (like min, but no gaps between
    #            tie groups -- rank = 1 + count of distinct smaller
    #            values, not count of smaller elements)
    #
    # Wired up in three places mirroring the existing df["col"].shift(
    # ...) support: _plain_series_expr_text (codegen text), _expr_kind,
    # and _rank_expr (both needed so `df["new_col"] = df["col"].rank(
    # ...)` -- a NEW dict-DataFrame column -- infers real/rank-1
    # correctly instead of raising "currently supports only real/int
    # columns" or declaring a rank-mismatched temp). Also needed a new
    # _series_base_or_literal_col_text helper: _plain_series_expr_text
    # deliberately excludes the literal-string single-column case
    # (df["col"], as opposed to a runtime-dynamic df[col]) since that
    # has "more specific handling elsewhere" for its OTHER caller
    # (.shift()) -- but .rank() is exercised on exactly that literal-
    # column shape in real code, so its own resolution needed both.
    #
    # A dynamic (non-literal) method= and the grouped
    # df.groupby(...)["col"].rank(...) form are still not supported.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_rank.py",
        [
            "import pandas as pd",
            "",
            "d = pd.DataFrame({'aic': [3.0, 1.0, 2.0, 1.0]})",
            "d['r_avg'] = d['aic'].rank()",
            "d['r_min'] = d['aic'].rank(method='min')",
            "d['r_max'] = d['aic'].rank(method='max')",
            "d['r_first'] = d['aic'].rank(method='first')",
            "d['r_dense'] = d['aic'].rank(method='dense')",
            "ravg = d['r_avg']",
            "rmin = d['r_min']",
            "rmax = d['r_max']",
            "rfirst = d['r_first']",
            "rdense = d['r_dense']",
            "for i in range(4):",
            "    print(ravg[i], rmin[i], rmax[i], rfirst[i], rdense[i])",
        ],
    )


def test_xp2f_pd_dict_df_construct_rangeidx_from_appended_list(tmp_path: Path) -> None:
    # Regression test: pd.DataFrame({"col": vals}) (no index= kwarg, so
    # the RangeIndex/dict-construct codegen path) where `vals` is itself
    # a variable built via .append() in a loop, not a list literal.
    # Codegen synthesizes a per-column temp assignment (`z_a = vals` for
    # column "a" of a DataFrame assigned to `z`) via a recursive
    # self.visit_Assign(ast.Assign(...)) call -- but visit_Assign has
    # its own "Python list aliasing semantics: x = v binds to the same
    # list object" branch, which fires here (since `vals` is itself
    # Python-list-tracked) and just records the alias without emitting
    # any actual Fortran assignment, on the assumption every later
    # reference to the synthetic name goes through the same alias
    # resolution. The %values/%index construction right after did not
    # do that -- it referenced the raw synthetic temp name directly, so
    # it silently read a never-assigned variable:
    #   real(kind=dp), allocatable :: z_a(:)   ! declared...
    #   allocate(z%values(size(z_a), 1))       ! ...but never assigned
    # which happened to build (uninitialized array size/contents) rather
    # than fail loudly. Fixed by resolving each synthesized temp name
    # through the same alias chain the rest of the file already uses
    # (self._aliased_name(self._resolve_list_alias(name))) right after
    # each synthetic assignment, so the construction code that follows
    # references whatever name actually holds the data.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_dictdf_append.py",
        [
            "import pandas as pd",
            "",
            "",
            "def show_df(n: int) -> None:",
            "    a_vals = []",
            "    b_vals = []",
            "    for i in range(n):",
            "        a_vals.append(float(i) * 2.0)",
            "        b_vals.append(float(i) + 10.0)",
            "    z = pd.DataFrame({'a': a_vals, 'b': b_vals})",
            "    ca = z['a']",
            "    cb = z['b']",
            "    print(ca[0], ca[1], ca[2])",
            "    print(cb[0], cb[1], cb[2])",
            "",
            "",
            "def main():",
            "    show_df(3)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pd_starred_unpack_module_list_in_column_selection(tmp_path: Path) -> None:
    # Regression test: df[["date", *ESTIMATORS]] -- splicing a module-
    # level list-of-strings constant into a column-selection list
    # literal via Python's starred-unpack syntax. Surfaced two separate
    # bugs, chased down together:
    #
    # 1. Even the simpler, non-starred df[ESTIMATORS] (selecting columns
    #    by a bare module-level list-of-strings variable) was silently
    #    broken: toplevel_shared_specs only ever taught a local
    #    function's own fresh translator instance that ESTIMATORS is a
    #    char ARRAY (for _rank_expr/_expr_kind's sake), never what its
    #    actual literal VALUES are -- so _resolve_str_list_literal's
    #    bare-Name branch (which needs self.pandas_str_list_values)
    #    could never resolve it, _pandas_df_match's column-selection
    #    matcher never fired, and it fell through to a generic, wrong
    #    "subscript a DataFrame by an integer-array index" fallback --
    #    `df(ESTIMATORS + 1)`, adding 1 to a string array. New
    #    _toplevel_str_list_values() scans the top-level module body for
    #    NAME = [str_literal, ...] assignments and seeds
    #    self.pandas_str_list_values from it in _emit_local_function,
    #    mirroring how df_arg_types/dict_arg_types already get seeded.
    # 2. _resolve_str_list_literal itself only recognized a list/tuple
    #    literal where EVERY element was a string constant -- a Starred
    #    element made the whole match fail outright, even once (1) was
    #    fixed. Extended it to accept a Starred element too, resolving
    #    its inner value recursively through the same function (so it
    #    can itself be a literal list, list("abc"), or -- thanks to (1)
    #    -- a resolvable module-level list variable) and splicing the
    #    result in.
    # 3. Even with (1) and (2) fixed, prescan's Assign-handling still
    #    crashed on this shape in scan-only translator instances that
    #    predate the codegen tr instance's own (1)-fix seeding:
    #    _extent_expr's "vector subscript" fallback (`size(self.expr(
    #    node.slice))`) evaluates the whole List-with-Starred slice
    #    directly rather than going through _pandas_df_match, hitting
    #    the generic array-constructor code's own "unsupported expr:
    #    Starred". Hardened with the same try/except-degrade-to-None
    #    pattern already used for this function's Slice/Tuple branches
    #    (see the df.iloc[lo:hi] and df.loc[:, col] regression tests
    #    above).
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_starred_cols.py",
        [
            "import pandas as pd",
            "",
            "ESTIMATORS = ['cc', 'co', 'oc']",
            "",
            "",
            "def make_sub(df: pd.DataFrame) -> pd.DataFrame:",
            "    return df[['date', *ESTIMATORS]]",
            "",
            "",
            "def main():",
            "    d = pd.DataFrame(",
            "        {'date': [1.0, 2.0], 'cc': [3.0, 4.0], 'co': [5.0, 6.0], 'oc': [7.0, 8.0]}",
            "    )",
            "    sub = make_sub(d)",
            "    col = sub['cc']",
            "    print(col[0], col[1])",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pd_dataframe_return_propagation(tmp_path: Path) -> None:
    # Regression test: a local (non-inlined) function's pd.DataFrame
    # return value wasn't tracked by the caller at all -- neither a
    # plain `result = make_df(...)` nor a tuple-unpacked
    # `z, k = make_stuff(...)`. A small enough helper gets fully inlined
    # (the function boundary disappears, sidestepping the problem), but
    # the moment it's complex enough to actually get emitted (a loop,
    # here), the callee's own return type was declared correctly while
    # the caller silently declared the assigned name plain int/real and
    # generated nonsense for any subsequent use (`result("a" + 1)`,
    # treating a DataFrame reference as an integer-indexed array).
    #
    # Root-caused to a chain of gaps, all fixed together:
    # - local_df_return_info (existing machinery, previously scoped only
    #   to a `pd.read_csv(...)`-traced return) is now also seeded from a
    #   plain `-> pd.DataFrame` return annotation (_scan_local_df_return_
    #   info's new fallback), covering the single-return case.
    # - New _tuple_df_return_positions/_all_tuple_df_return_positions:
    #   the tuple-return counterpart, reading `-> tuple[..., pd.
    #   DataFrame, ...]` to find which positions are DataFrame-typed.
    # - _emit_local_function's own translator instance never had
    #   local_df_return_info threaded into it at all (only used
    #   separately for declaring the CURRENT function's own return
    #   type) -- prescan's `target = other_local_func(...)` recognition
    #   reads it off self.local_df_return_info, which stayed empty.
    # - That prescan branch was also missing its `continue`: once it
    #   registered the target as a DataFrame, execution fell through to
    #   the generic scalar-kind-inference fallback for the same
    #   statement anyway, which doesn't know to skip an already-
    #   recognized DataFrame target -- producing a conflicting
    #   duplicate declaration.
    # - Several independent, separately-duplicated copies of "mark each
    #   tuple-unpack target's kind from the callee's out_kinds" (one in
    #   the callee's own dummy-arg declaration loop, one in prescan, one
    #   in a hint-scanning pass over tr_seed, one in codegen's rebind-
    #   block detection) all needed the same tuple_df_return_positions
    #   check added, since out_kinds itself has no DataFrame case and
    #   each independently defaulted the target to real.
    # - Several scan-only translator instances (_local_return_maps's own
    #   tr, tr_local_scan, _tr_local_scan, tr_seed) needed both
    #   local_df_return_info and tuple_df_return_positions seeded too,
    #   the same recurring pattern as the parameter-passing fixes.
    # - The (correctly declared, once reachable) DataFrame-typed
    #   tuple-output dummy argument also needed excluding from the
    #   generic "local pandas_df_vars not already a dummy arg" decl
    #   loop, which didn't know about tuple-output names and re-
    #   declared it as a conflicting duplicate local.
    #
    # Exercises both a single DataFrame return and a tuple return with
    # two DataFrames at non-adjacent positions in one script.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_return_prop.py",
        [
            "import pandas as pd",
            "",
            "",
            "def make_df(n: int) -> pd.DataFrame:",
            "    vals = []",
            "    for i in range(n):",
            "        vals.append(float(i) * 2.0)",
            "    z = pd.DataFrame({'a': vals})",
            "    return z",
            "",
            "",
            "def make_stuff(n: int) -> tuple[pd.DataFrame, float, pd.DataFrame, int]:",
            "    vals = []",
            "    for i in range(n):",
            "        vals.append(float(i) * 2.0)",
            "    z = pd.DataFrame({'a': vals})",
            "    w = pd.DataFrame({'b': vals})",
            "    return z, 5.0, w, 7",
            "",
            "",
            "def main():",
            "    single = make_df(3)",
            "    single_col = single['a']",
            "    print(single_col[0], single_col[1], single_col[2])",
            "    z, k, w, m = make_stuff(3)",
            "    zc = z['a']",
            "    wc = w['b']",
            "    print(zc[0], zc[1], zc[2], k, wc[0], m)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pd_series_dropna_and_to_numpy_passthrough(tmp_path: Path) -> None:
    # Regression test: Series.dropna() -- drops NaN entries, shrinking
    # the result -- on a runtime-dynamic single column (df[symbol],
    # symbol a str function parameter), chained into .to_numpy(dtype=
    # float). New _plain_series_expr_text "dropna" branch lowers it to
    # Fortran's pack() intrinsic in one expression: pack(x, .not.
    # ieee_is_nan(x)) compacts x down to just the non-NaN elements, no
    # dedicated python.f90 helper needed (unlike rank_min_real/
    # shift_1d) since pack() already does exactly this.
    #
    # Also needed .to_numpy() extended with a general "X is already a
    # plain real array" passthrough case (checked via
    # _plain_series_expr_text, covering both a bare variable and a
    # chained .dropna()/.shift()/.rank() result) -- the existing to_numpy
    # branches only covered a DataFrame-subscript base (df["col"]/
    # df[name]) or a whole-DataFrame reference, neither of which matches
    # a plain local variable assigned from dropna()'s result.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_dropna.py",
        [
            "import pandas as pd",
            "import numpy as np",
            "",
            "",
            "def get_clean(returns: pd.DataFrame, symbol: str) -> float:",
            "    series = returns[symbol].dropna()",
            "    eps = series.to_numpy(dtype=float) - 1.0",
            "    return float(eps[0]) + float(eps[1]) + float(eps[2])",
            "",
            "",
            "def main():",
            "    d = pd.DataFrame({'a': [1.0, np.nan, 2.0, np.nan, 3.0]})",
            "    print(get_clean(d, 'a'))",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pd_chained_single_column_subscript(tmp_path: Path) -> None:
    # Regression test: df["col"][i] / df[col][i] (col a runtime
    # character-scalar expression too) -- a further single-element
    # subscript chained directly onto a single-column selection, in one
    # expression. df["col"] alone resolves to an array-SECTION
    # expression (df%values(:, df%col_pos("col"))), and Fortran doesn't
    # allow directly subscripting an array-section expression a second
    # time (`d%values(:, ...)(1)` is a syntax error) -- reproduced
    # (and worked around by splitting into two statements) repeatedly
    # earlier in this session without ever being fixed.
    #
    # Two separate bugs, both in expr()'s Subscript dispatch:
    # 1. _scalar_subscript_expr (the established "lower a chained
    #    subscript into one valid Fortran expression instead of
    #    emitting expr(i)" mechanism, already used for e.g. x[a:b][i])
    #    had no case at all for a df[col] base -- added one that
    #    combines both subscripts into a single direct 2D element
    #    access, df%values(idx, df%col_pos(col)), instead of trying to
    #    subscript the array-section result a second time. Scoped to a
    #    non-negative/non-slice idx (the common case).
    # 2. Before even reaching that, a separate, earlier "flatten chained
    #    subscripts into multi-dim array access" optimization
    #    (_flatten_subscript_chain, meant for ordinary nested numeric
    #    indexing like matrix[i][j]) fired first and had no
    #    pandas_df_vars exception -- it treated the DataFrame itself as
    #    a plain 2D array, producing outright nonsense
    #    (`df(col + 1, i + 1)`, calling a derived-type value as if it
    #    were a function/array) that failed at build time with
    #    "Dummy procedure 'df' ... must also be PURE". Fixed by
    #    excluding any pandas_df_vars-tracked root base from that
    #    optimization entirely.
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_chain_subscript.py",
        [
            "import pandas as pd",
            "",
            "",
            "def get_val(df: pd.DataFrame, col: str, i: int) -> float:",
            "    return df[col][i] + 1.0",
            "",
            "",
            "def main():",
            "    d = pd.DataFrame({'a': [1.0, 2.0, 3.0], 'b': [4.0, 5.0, 6.0]})",
            "    print(get_val(d, 'a', 0), get_val(d, 'b', 2))",
            "    print(d['a'][1] * 2.0)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pandas_read_csv_then_set_index_collapsed(tmp_path: Path) -> None:
    # Regression test: `X = pd.read_csv(path, parse_dates=[col]); X =
    # X.set_index(col)` -- reading a CSV, then separately committing to
    # one already-date-parsed column as the row index -- as opposed to
    # passing index_col=col to pd.read_csv directly (already supported).
    # X.set_index(...) is not itself implemented as a general runtime
    # operation (Fortran can't change a variable's declared derived
    # type at runtime, and a str-indexed vs. date-indexed DataFrame are
    # different Fortran types here) -- instead, new
    # rewrite_pandas_read_csv_set_index runs as an AST-level
    # preprocessing pass (alongside rewrite_integer_quotient_seed_
    # divisions, before any translator/prescan code runs) that
    # recognizes this specific two-statement idiom and collapses it
    # into the equivalent, already-working single-step
    # pd.read_csv(path, index_col=col, parse_dates=[col]) form.
    #
    # col may be a literal string (df.set_index("Date")) or a local
    # variable assigned exactly once to a literal string before use
    # (date_label = "Date"; ...; df.set_index(date_label)) -- the same
    # "resolve a Name back through a single literal assignment"
    # technique _scan_local_df_return_info already uses for a
    # pd.read_csv path argument. Exercises both shapes.
    #
    # Deliberately narrow: only fires when set_index's column is one of
    # read_csv's own parse_dates=[...] entries and read_csv doesn't
    # already have its own index_col= -- a set_index(...) on some other
    # column (see test_xp2f_pandas_read_csv_set_index_on_non_date_
    # column_still_unsupported below) still correctly reports
    # unsupported rather than being silently mishandled.
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_read_csv_set_index.py",
        [
            "import pandas as pd",
            "",
            "",
            "def read_prices_literal(filename):",
            "    df = pd.read_csv(filename, parse_dates=['Date'])",
            "    df = df.set_index('Date')",
            "    return df",
            "",
            "",
            "def read_prices_via_variable(filename):",
            "    date_label = 'Date'",
            "    df = pd.read_csv(filename, parse_dates=[date_label])",
            "    df = df.set_index(date_label)",
            "    return df",
            "",
            "",
            "def main():",
            "    d1 = read_prices_literal('prices.csv')",
            "    d2 = read_prices_via_variable('prices.csv')",
            "    print(d1.shape[0], d1.shape[1])",
            "    print(d2.shape[0], d2.shape[1])",
            "    print(d1['SPY'].to_numpy()[0], d2['EFA'].to_numpy()[2])",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_pandas_df_index_attribute(tmp_path: Path) -> None:
    # Regression test: `df.index` as a general-purpose expression (not
    # just as a construction kwarg or inside the narrow pd.to_datetime(
    # df[label]) alias pattern) was entirely unsupported -- even a bare
    # `idx = df.index` raised "unsupported attribute expr: df.index".
    #
    # Fixed with three additions: (1) expr()'s Attribute dispatch grew a
    # `df.index` -> `{df_expr}%index` case (mirroring the pre-existing
    # `df.columns` one); (2) _expr_kind/_rank_expr recognize the same
    # shape, but only claim a concrete char rank-1 kind for
    # DataFrame_str_index -- the date/datetime-index kinds are left
    # kind=None/rank=0 (like a bare pd.to_datetime(...) call) so the
    # generic declaration fallback doesn't wrongly force a real() array
    # declaration onto a type(date)/type(datetime)-typed target; (3) a
    # new prescan/visit_Assign pair recognizes `t = df.index` on a
    # date/datetime-indexed frame and registers `t` as a
    # pandas_date_array_aliases entry (exactly like the pre-existing
    # `t = pd.to_datetime(df[label])` pattern), so `t` becomes a pure
    # compile-time alias to `df%index` with no separate Fortran
    # declaration or statement at all.
    #
    # Covers both the character-indexed (DataFrame_str_index, via a
    # RangeIndex-default frame) and date-indexed (DataFrame_index_date,
    # via read_csv+set_index) kinds, and both the bare `df.index` and
    # `df.index[i]` subscript shapes. (An earlier, now-fixed draft of
    # this change wrongly forced rank=1 for date-indexed frames too,
    # corrupting unrelated declarations in the same program -- confirmed
    # fixed by manually diffing df.head() output before/after, which
    # isn't included in this test's own --run-diff since a named
    # DatetimeIndex header row is a separate, pre-existing df.head()
    # formatting gap unrelated to df.index itself.)
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_index_attr.py",
        [
            "import pandas as pd",
            "",
            "df_ri = pd.DataFrame({'a': [1.0, 2.0, 3.0]})",
            "idx_ri = df_ri.index",
            "print(len(idx_ri))",
            "print(df_ri.index[0])",
            "",
            "df_dt = pd.read_csv('prices.csv', parse_dates=['Date'])",
            "df_dt = df_dt.set_index('Date')",
            "idx_dt = df_dt.index",
            "print(len(idx_dt))",
            "print(df_dt.index[0] < df_dt.index[1])",
            "print(df_dt.index[-1] == df_dt.index[-1])",
        ],
    )


def test_xp2f_pandas_df_index_assign_date_noop(tmp_path: Path) -> None:
    # Regression test: `df.index = df.index.date` -- real pandas strips
    # the time-of-day component off a DatetimeIndex, turning it into an
    # object-dtype index of plain datetime.date values. Our
    # DataFrame_index_date already stores a plain type(date) index with
    # no time component at all (that's exactly what
    # _detect_pandas_index_kind picked, since this CSV's dates carry no
    # time), so the statement is a pure no-op here -- new visit_Assign
    # branch recognizes the `X.index = X.index.date` shape (target and
    # source both referencing the same pandas_df_vars-tracked frame) and
    # emits nothing at all, rather than raising "unsupported assign".
    shutil.copy2(DATAFRAME_HELPER_PATH, tmp_path / "dataframe_index_date.f90")
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    _run_xp2f_compile_diff(
        tmp_path,
        "xdf_index_assign_date.py",
        [
            "import pandas as pd",
            "",
            "df = pd.read_csv('prices.csv', parse_dates=['Date'])",
            "df = df.set_index('Date')",
            "df.index = df.index.date",
            "print(len(df.index))",
            "print(df.index[0] < df.index[1])",
            "print(df['SPY'].to_numpy()[0])",
        ],
    )


def test_xp2f_pandas_df_index_assign_date_on_datetime_index_still_unsupported(tmp_path: Path) -> None:
    # Companion to the no-op test above: `df.index = df.index.date` must
    # NOT be silently accepted on a DataFrame_index_datetime frame (a
    # real time-of-day component present) -- truncating it would need
    # reconstructing the frame under a different static Fortran type,
    # which isn't attempted; this stays a clearly-reported unsupported
    # assign instead.
    (tmp_path / "prices_dt.csv").write_text(
        "\n".join(
            [
                "Date,SPY",
                "2020-01-01 09:30:00,300.0",
                "2020-01-02 09:30:00,301.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    src = tmp_path / "xdf_index_assign_date_neg.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.read_csv('prices_dt.csv', parse_dates=['Date'])",
                "df = df.set_index('Date')",
                "df.index = df.index.date",
                "print(df.head())",
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
    assert proc.returncode != 0
    assert "Transpile: FAIL" in proc.stdout, proc.stdout + proc.stderr
    assert "DataFrame_index_datetime" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_pandas_read_csv_set_index_on_non_date_column_still_unsupported(tmp_path: Path) -> None:
    # Companion to the collapse test above: rewrite_pandas_read_csv_
    # set_index must NOT fire when set_index's column isn't one of
    # read_csv's own parse_dates=[...] entries (here, parse_dates is
    # omitted entirely) -- this stays a genuinely unsupported call
    # rather than being silently, incorrectly collapsed.
    (tmp_path / "prices.csv").write_text("\n".join(_PANDAS_TEST_CSV_ROWS) + "\n", encoding="utf-8")
    src = tmp_path / "xdf_read_csv_set_index_neg.py"
    src.write_text(
        "\n".join(
            [
                "import pandas as pd",
                "",
                "df = pd.read_csv('prices.csv')",
                "df = df.set_index('SPY')",
                "print(df.shape)",
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
    assert proc.returncode != 0
    assert "unsupported call" in proc.stdout, proc.stdout + proc.stderr
    assert "set_index" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_class_struct_field_assignment(tmp_path: Path) -> None:
    # Regression test: obj.field = expr / self.field = expr (inside a
    # hoisted method) was previously completely unsupported ("unsupported
    # assign") -- reads of a struct field already worked, but there was no
    # matching write path at all. Covers both an external field assignment
    # and a method mutating its own field via self.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_field_assign.py",
        [
            "class Point:",
            "    def __init__(self, x: float, y: float):",
            "        self.x = x",
            "        self.y = y",
            "",
            "    def translate(self, a: float, b: float):",
            "        self.x = self.x + a",
            "        self.y = self.y + b",
            "",
            "",
            "def main():",
            "    p = Point(1.0, 2.0)",
            "    p.x = 5.0",
            "    p.translate(1.0, 2.0)",
            "    print(p.x, p.y)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_del_instance(tmp_path: Path) -> None:
    # Regression test: `del obj` on a class instance (or any scalar/
    # derived-type variable) crashed with "unsupported delete target";
    # now a no-op for scalars/derived types (Fortran's own scoping
    # already reclaims that storage).
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_del.py",
        [
            "class Point:",
            "    def __init__(self, x: float, y: float):",
            "        self.x = x",
            "        self.y = y",
            "",
            "    def __del__(self):",
            "        pass",
            "",
            "",
            "def main():",
            "    p = Point(1.0, 2.0)",
            "    print(p.x, p.y)",
            "    del p",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_arithmetic_fold_precedence_with_leading_multiply(tmp_path: Path) -> None:
    # Regression test: combine_parenthesized_integer_offset's `(A) op2
    # lit2 -> (A op2 lit2)` fold was applied even when the parenthesized
    # group was itself multiplied/divided by something outside it, or
    # subtracted as a unit -- so `2 * (x + 6) - 2` was silently
    # miscomputed as `2 * (x + 4)` (found via a class repro, but
    # reproduces with no class involved at all). Also covers the
    # symmetric preceded-by-minus case: `n - (x + 6) - 3`.
    _run_xp2f_compile_diff(
        tmp_path,
        "xparen_fold_precedence.py",
        [
            "def main():",
            "    x = 0.0",
            "    a = 2 * (x + 6) - 2",
            "    print(a)",
            "    y = 5.0",
            "    b = 10 - (y + 3) - 2",
            "    print(b)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_literal_default_field(tmp_path: Path) -> None:
    # Regression test: collect_dataclass_info's plain-class field scan
    # only accepted `self.field = param_name` (a bare passthrough of an
    # __init__ parameter); a field initialized from a literal instead
    # (`self._default = 0`, not derived from any parameter) silently
    # rejected the whole class as "not struct-shaped". Now such a field
    # becomes the derived type's own default initializer.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_literal_default_field.py",
        [
            "class ArrProperties:",
            "    def __init__(self, n: int):",
            "        self._n_pts = n",
            "        self._default = 0",
            "",
            "    def get_n_pts(self):",
            "        return self._n_pts",
            "",
            "    def get_default(self):",
            "        return self._default",
            "",
            "",
            "def main():",
            "    a = ArrProperties(4)",
            "    print(a.get_n_pts())",
            "    print(a.get_default())",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_typed_param_forward_ref_string_annotation(tmp_path: Path) -> None:
    # Regression test: a user-class annotation written as a forward-ref
    # string (`a: "ArrProperties"`) wasn't recognized as a struct type at
    # several sites -- only a bare unquoted annotation matched
    # ast.unparse(ann) directly. Covers a non-self, class-typed parameter
    # on an ordinary function.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_forward_ref_param.py",
        [
            "class Point:",
            "    def __init__(self, x: float, y: float):",
            "        self.x = x",
            "        self.y = y",
            "",
            "",
            "def get_x(p: \"Point\"):",
            "    return p.x",
            "",
            "",
            "def main():",
            "    pt = Point(3.0, 4.0)",
            "    print(get_x(pt))",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_return_type_inference_no_annotation(tmp_path: Path) -> None:
    # Regression test: a function with no explicit '-> T' return
    # annotation, whose every 'return EXPR' hands back a bare struct-typed
    # variable/parameter (all the same class), had its result variable
    # fall through to the generic int default -- so the body's own
    # struct-typed assignment into it failed to compile.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_return_inference.py",
        [
            "class A:",
            "    def __init__(self, a: int):",
            "        self._a = a",
            "",
            "    def get_a(self):",
            "        return self._a",
            "",
            "",
            "def choose_A(a1: \"A\", a2: \"A\", b: bool):",
            "    if b:",
            "        return a1",
            "    else:",
            "        return a2",
            "",
            "",
            "def main():",
            "    x = A(5)",
            "    y = A(9)",
            "    z = choose_A(x, y, True)",
            "    print(z.get_a())",
            "    z2 = choose_A(x, y, False)",
            "    print(z2.get_a())",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_case_colliding_fields(tmp_path: Path) -> None:
    # Regression test: Fortran identifiers are case-insensitive, so a
    # class with two fields differing only in case (self.x/self.X)
    # lowered to a derived type with two colliding components
    # ("Component x already declared"). Now the later field is renamed to
    # a fresh, case-insensitively-unique name and every access to it is
    # rewritten consistently.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_case_collision.py",
        [
            "class Point:",
            "    def __init__(self, x: float, y: float):",
            "        self.x = x",
            "        self.X = y",
            "",
            "    def set_coordinates(self, x: float, y: float):",
            "        self.x = x",
            "        self.X = y",
            "",
            "    def get_coordinates(self):",
            "        return self.x, self.X",
            "",
            "",
            "def main():",
            "    p = Point(1.0, 2.0)",
            "    p.set_coordinates(3.0, 4.0)",
            "    a, b = p.get_coordinates()",
            "    print(a, b)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_optional_none_struct_param(tmp_path: Path) -> None:
    # Regression test: Optional[A] = None struct-typed parameters tried
    # to route through optval(), which has no derived-type overload --
    # decl_kind == 'type(...)' was never excluded from that scalar/array-
    # default machinery, silently mismarking the field as a plain integer
    # default. Now such a parameter is left as a genuinely optional
    # Fortran dummy (type(A_t), optional), with 'a is not None' correctly
    # compiling to present(a).
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_optional_none_param.py",
        [
            "class A:",
            "    def __init__(self, x: int):",
            "        self.data = x",
            "",
            "",
            "def get_x_from_A(a: \"A\" = None):",
            "    if a is not None:",
            "        return a.data",
            "    else:",
            "        return 5",
            "",
            "",
            "def main():",
            "    a = A(4)",
            "    print(get_x_from_A(a))",
            "    print(get_x_from_A())",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_computed_array_field(tmp_path: Path) -> None:
    # Regression test: `self.field = np.ones(n)` in __init__ -- an array
    # field whose VALUE, not just its presence, is computed from a
    # constructor argument -- was previously impossible to represent
    # (neither a positional passthrough nor a static default initializer
    # can express it) and silently rejected the whole class.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_computed_array_field.py",
        [
            "import numpy as np",
            "",
            "",
            "class A:",
            "    def __init__(self, n: int):",
            "        self.x = np.ones(n)",
            "",
            "    def get_x(self):",
            "        return self.x",
            "",
            "",
            "def main():",
            "    a = A(4)",
            "    print(a.get_x())",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_allocate_then_fill_field(tmp_path: Path) -> None:
    # Regression test: a field built across TWO __init__ statements -- an
    # allocating call immediately followed by a whole-slice fill
    # (`self.z = np.empty(k); self.z[:] = 7.0`) -- collapsed into an
    # equivalent single `np.full(k, 7.0)` template, the same 'allocate +
    # fill' idiom merge_allocate_then_scalar_fill_to_source already
    # recognizes at the generated-Fortran-text level, caught here at the
    # Python-source level instead.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_alloc_then_fill_field.py",
        [
            "import numpy as np",
            "",
            "",
            "class C:",
            "    def __init__(self, k: int):",
            "        self.z = np.empty(k)",
            "        self.z[:] = 7.0",
            "",
            "    def get_z(self):",
            "        return self.z",
            "",
            "",
            "def main():",
            "    c = C(3)",
            "    print(c.get_z())",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_stateless_empty_init(tmp_path: Path) -> None:
    # Regression test: a class with an empty __init__ (just `pass`, no
    # fields at all -- e.g. a class whose only job is hosting other
    # methods) was rejected outright by a stray 'fields must be
    # non-empty' check meant only for the @dataclass/NamedTuple branch.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_stateless.py",
        [
            "class Point:",
            "    def __init__(self):",
            "        pass",
            "",
            "    def addition(self, a: float, b: float):",
            "        return a + b",
            "",
            "",
            "def main():",
            "    p = Point()",
            "    print(p.addition(1.0, 2.0))",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_nested_composition(tmp_path: Path) -> None:
    # Regression test: a class whose own field is ANOTHER user class was
    # entirely unsupported -- _field_kind() only recognized primitive/
    # array annotations, never a bare class name. Also covers reading a
    # nested chain more than one level deep (line.a.x) and a derived-type
    # emission-order fix (a struct type referencing another must be
    # emitted after it, not just alphabetically).
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_nested_composition.py",
        [
            "class Point:",
            "    def __init__(self, x: float, y: float):",
            "        self.x = x",
            "        self.y = y",
            "",
            "    def get_x(self):",
            "        return self.x",
            "",
            "",
            "class Line:",
            "    def __init__(self, a: \"Point\", b: \"Point\"):",
            "        self.a = a",
            "        self.b = b",
            "",
            "    def length_x(self):",
            "        return self.b.get_x() - self.a.get_x()",
            "",
            "",
            "def main():",
            "    p1 = Point(1.0, 2.0)",
            "    p2 = Point(4.0, 6.0)",
            "    line = Line(p1, p2)",
            "    print(line.length_x())",
            "    print(line.a.x)",
            "    print(line.b.y)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_nested_field_mutation_in_constructor(tmp_path: Path) -> None:
    # Regression test: a class whose __init__ does more than assign each
    # field exactly once -- mutating a NESTED field afterward
    # (`self.a = a; self.a.x = 99.0`) -- couldn't be built by the single-
    # expression-per-field template mechanism; __init__ is now hoisted
    # into a real constructor function for exactly this case.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_nested_field_mutation.py",
        [
            "class Point:",
            "    def __init__(self, x: float, y: float):",
            "        self.x = x",
            "        self.y = y",
            "",
            "",
            "class Line:",
            "    def __init__(self, a: \"Point\"):",
            "        self.a = a",
            "        self.a.x = 99.0",
            "",
            "",
            "def main():",
            "    p1 = Point(1.0, 2.0)",
            "    line = Line(p1)",
            "    print(line.a.x, line.a.y)",
            "",
            "",
            "main()",
        ],
    )


def test_xp2f_class_new_field_from_nested_method_call_still_declined(tmp_path: Path) -> None:
    # Companion to the nested-field-mutation test above: a class __init__
    # that tries to DEFINE a new field from a method call on a nested
    # field (`self._x = self.l.get_x()`) must stay a cleanly declined,
    # unsupported case rather than being silently mishandled -- its own
    # type can't be determined at this static, pre-codegen stage.
    src = tmp_path / "xclass_new_field_from_method_call.py"
    src.write_text(
        "\n".join(
            [
                "class Point:",
                "    def __init__(self, x: float):",
                "        self.x = x",
                "",
                "    def get_x(self):",
                "        return self.x",
                "",
                "",
                "class Line:",
                "    def __init__(self, a: \"Point\"):",
                "        self.a = a",
                "        self._x = self.a.get_x()",
                "",
                "    def get_x(self):",
                "        return self._x",
                "",
                "",
                "def main():",
                "    p = Point(1.0)",
                "    line = Line(p)",
                "    print(line.get_x())",
                "",
                "",
                "main()",
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
    assert proc.returncode != 0
    assert "unsupported" in proc.stdout, proc.stdout + proc.stderr


def test_xp2f_main_guard_with_preceding_module_level_code(tmp_path: Path) -> None:
    # Regression test: a module-level statement before an
    # `if __name__ == "__main__":` guard previously caused the guard's
    # ENTIRE body to be silently discarded during codegen -- Build and
    # Run both reported success on a program with zero print statements
    # executed, no error or warning at all. Root cause: the guard-
    # unwrapping logic only fired when there was NO other top-level
    # executable code; otherwise the raw guard node was left for the
    # per-statement emission loop to unconditionally skip.
    _run_xp2f_compile_diff(
        tmp_path,
        "xmain_guard_with_module_level_code.py",
        [
            "a1 = 2 / 2",
            "a2 = 2 + 3",
            "",
            "if __name__ == \"__main__\":",
            "    print(a1)",
            "    print(a2)",
            "    print(a1 + a2)",
        ],
    )


def test_xp2f_main_guard_calls_main_with_preceding_module_level_code(tmp_path: Path) -> None:
    # Companion to the test above, covering the OTHER guard shape this
    # same fix handles: module-level code before the guard, and the
    # guard itself only calling a separately-defined main().
    _run_xp2f_compile_diff(
        tmp_path,
        "xmain_guard_calls_main_with_module_level_code.py",
        [
            "SCALE = 3",
            "",
            "def main():",
            "    x = 2 * SCALE",
            "    print(x)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    main()",
        ],
    )


def test_xp2f_arith_paren_fold_nested_negative_literal(tmp_path: Path) -> None:
    # Regression test: simplify_narrow_redundant_arith_parens' rule 5
    # (drop parens wrapping an entire expression followed by a genuine
    # binary +/-) could select two NESTED (not disjoint) removal spans
    # in the same pass -- e.g. `1 - 2 + -2 - 4 - 5`, where the inner
    # `(-2)` also independently qualified for the same rule -- and the
    # single left-to-right stitching pass that applies all chosen
    # removals assumes they're disjoint, corrupting the text (an
    # unbalanced-parens compile failure) whenever they're nested.
    _run_xp2f_compile_diff(
        tmp_path,
        "xparen_fold_nested_negative.py",
        [
            "if __name__ == \"__main__\":",
            "    f8 = 1 - 2 + -2 - 4 - 5",
            "    print(f8)",
        ],
    )


def test_xp2f_true_division_of_int_literals_not_folded_as_integer(tmp_path: Path) -> None:
    # Regression test: find_parameters' const_int_expr_to_fortran
    # conflated Python's `/` (ALWAYS true division -- 100/10/10/2 is
    # 0.5, a float, even though every operand is a plain int literal)
    # with `//` (floor division) -- folding a chain of bare `/`
    # literals the same way silently declared the result an `integer,
    # parameter` and truncated it via Fortran's own integer division,
    # producing 0 instead of 0.5.
    _run_xp2f_compile_diff(
        tmp_path,
        "xtrue_division_int_literals.py",
        [
            "if __name__ == \"__main__\":",
            "    f1 = 100 / 10 / 10 / 2",
            "    print(f1)",
        ],
    )


def test_xp2f_np_full_complex_fill_no_dtype(tmp_path: Path) -> None:
    # Regression test: np.full(shape, fill) with a complex fill value
    # and no explicit dtype= was declared real, silently dropping the
    # imaginary part on assignment -- an overly broad "zeros/ones/empty/
    # full" grouping in _expr_kind's own dtype-only check shadowed a
    # separate, correct fill-value-kind check for `full` specifically.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_full_complex_fill.py",
        [
            "if __name__ == \"__main__\":",
            "    from numpy import full",
            "",
            "    x = full((5, 5), (1 + 2j))",
            "    r = x.sum()",
            "    print(r.real, r.imag)",
        ],
    )


def test_xp2f_np_int64_large_literal_cast(tmp_path: Path) -> None:
    # Regression test: np.int64(large_literal) (e.g. 2147483648) failed
    # to compile ("Integer too big for its kind") even though the
    # cast's own target kind was wide enough -- the literal's own token
    # is parsed at the default 32-bit kind unless explicitly suffixed,
    # regardless of the int(..., kind=...) wrapper around it.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_int64_large_literal.py",
        [
            "from numpy import int64",
            "",
            "if __name__ == \"__main__\":",
            "    print(int64(2147483648))",
            "    print(int64(9223372036854775807))",
        ],
    )


def test_xp2f_np_where_mixed_int_real_branches(tmp_path: Path) -> None:
    # Regression test: np.where(cond, a, b) lowers to Fortran's MERGE
    # intrinsic, which requires its tsource/fsource arguments to share the
    # exact same type AND kind -- unlike np.where itself, which happily
    # promotes mixed int/real branches. `arr / 2` (Python's `/` is always
    # true division, so this branch is always real) alongside `arr * 2`
    # (which stays integer) previously reached MERGE unreconciled, a
    # gfortran compile error ("'fsource' argument of 'merge' intrinsic...
    # must be the same type and kind as 'tsource'").
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_where_mixed_int_real.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    arr = np.array([1, 2, 3, 4, 5, 6])",
            "    arr1 = np.where(arr < 5, arr / 2, arr * 2)",
            "    print(arr1)",
        ],
    )


def test_xp2f_bool_is_and_is_not_against_bool_value(tmp_path: Path) -> None:
    # Regression test: `is`/`is not` against a bool value -- a literal
    # (`a is False`, `a is not True`) or another bool variable (`a is b`)
    # -- was rejected outright ("is/is not supported only with None"),
    # even though Python's bool is a singleton type, making `is`/`is not`
    # against a bool value equivalent to `==`/`!=` (already correctly
    # lowered to Fortran's .eqv./.neqv. for logical operands).
    _run_xp2f_compile_diff(
        tmp_path,
        "xbool_is_not_bool_value.py",
        [
            "def is_false(a: \"bool\"):",
            "    c = False",
            "    if a is False:",
            "        c = True",
            "    return c",
            "",
            "",
            "def compare_is(a: \"bool\", b: \"bool\"):",
            "    c = False",
            "    if a is b:",
            "        c = True",
            "    return c",
            "",
            "",
            "def not_true(a: \"bool\"):",
            "    c = False",
            "    if a is not True:",
            "        c = True",
            "    return c",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(is_false(False))",
            "    print(compare_is(True, False))",
            "    print(not_true(True))",
        ],
    )


def test_xp2f_np_zeros_shape_from_niladic_function_call(tmp_path: Path) -> None:
    # Regression test: np.zeros(g()) where g() is a zero-argument
    # function whose entire body is `return (2, 3)` was rejected
    # outright ("unsupported call: g()") -- the array-constructor shape
    # argument's own resolution only recognized a literal Tuple/List (or
    # a Name bound to one), not a call to a niladic literal-tuple-
    # returning accessor.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_zeros_shape_niladic_call.py",
        [
            "import numpy as np",
            "",
            "",
            "def g():",
            "    return (2, 3)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    a = np.zeros(g())",
            "    print(a.shape[0], a.shape[1])",
        ],
    )


def test_xp2f_np_zeros_shape_from_tuple_literal_name(tmp_path: Path) -> None:
    # Regression test: np.zeros(shape) where `shape` is a plain Name
    # bound (exactly once) to a Tuple literal of int constants (e.g.
    # `c_shape = (1, 2)`) previously reached the array constructor's
    # shape-argument codegen unresolved, generating an invalid
    # `allocate(c(c_shape), source=0.0_dp)` -- using the whole array name
    # as a single bogus dimension spec instead of unpacking its elements
    # -- a gfortran "Bad array specification in ALLOCATE statement".
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_zeros_shape_tuple_literal_name.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    c_shape = (1, 2)",
            "    c = np.zeros(c_shape)",
            "    print(c.shape[0], c.shape[1])",
        ],
    )


def test_xp2f_math_nan_bare_name_from_import(tmp_path: Path) -> None:
    # Regression test: `from math import nan` then using the bare name
    # `nan` directly (pyccel's own tests/pyccel/scripts/print_nan.py) was
    # rejected ("Symbol 'nan' has no IMPLICIT type") -- `math.nan` as an
    # Attribute is already fully supported, but a bare Name left over
    # from a `from ... import ...` wasn't recognized as anything.
    _run_xp2f_compile_diff(
        tmp_path,
        "xmath_nan_bare_name.py",
        [
            "from math import nan",
            "",
            "if __name__ == \"__main__\":",
            "    print(nan)",
        ],
    )


def test_xp2f_print_string_with_form_feed_char(tmp_path: Path) -> None:
    # Regression test: a raw control character embedded in a Python
    # string literal (e.g. `print(\"\\f\")`, pyccel's own tests/pyccel/
    # scripts/print_strings.py) got silently corrupted by an internal
    # post-processing pass that split the whole generated Fortran source
    # text via `str.splitlines()` -- which treats \\x0b/\\x0c/\\x1c-\\x1e/
    # \\x85/\\u2028/\\u2029 as line boundaries too, not just '\\n' -- so
    # the character was dropped and a bogus newline inserted in its
    # place, landing mid string-literal ("Unterminated character
    # constant").
    _run_xp2f_compile_diff(
        tmp_path,
        "xprint_form_feed.py",
        [
            "if __name__ == \"__main__\":",
            "    print(\"\\f\")",
            "    print(\"before\\fafter\")",
        ],
    )


def test_xp2f_print_end_with_nonempty_custom_text(tmp_path: Path) -> None:
    # Regression test: print(..., end=". ") (a non-empty, non-default
    # `end=`) silently dropped the end text entirely and fell back to a
    # plain newline-terminated write -- pyccel's own tests/pyccel/
    # scripts/print_sp_and_end.py chains several prints with a custom
    # `end=` expecting them to share one physical line.
    # _emit_print_call only ever used `end=` to decide whether to
    # suppress Fortran's own automatic newline (true only for the exact
    # empty-string case) -- the custom text itself was never emitted by
    # any of the function's many content-type branches.
    _run_xp2f_compile_diff(
        tmp_path,
        "xprint_end_custom_text.py",
        [
            "if __name__ == \"__main__\":",
            "    print(\"The first sentence\", end=\". \")",
            "    print(\"The second sentence\", end=\". \")",
            "    print(\"Mercury\", \"Venus\", \"Earth\", sep=\", \", end=\", \")",
            "    print(\"Jupiter\", \"Saturn\", sep=\", \")",
        ],
    )


def test_xp2f_numpy_from_import_with_asname(tmp_path: Path) -> None:
    # Regression test: `from numpy import sum as np_sum` then calling
    # `np_sum(arr)` (pyccel's own tests/pyccel/scripts/hope_benchmarks/
    # point_spread_func.py) was rewritten to the bogus `np.np_sum(arr)`
    # -- rewrite_bare_numpy_imports_to_attribute_calls mapped the LOCAL
    # (aliased) name back onto itself as the synthetic `np.` attribute,
    # instead of the ORIGINAL numpy name, so none of this file's own
    # `node.func.attr == "sum"`-gated dispatch sites ever recognized it
    # ("unsupported call: np.np_sum(...)").
    _run_xp2f_compile_diff(
        tmp_path,
        "xnumpy_from_import_asname.py",
        [
            "from numpy import sum as np_sum",
            "from numpy import zeros",
            "",
            "if __name__ == \"__main__\":",
            "    arr = zeros(3)",
            "    arr[0] = 1.0",
            "    arr[1] = 2.0",
            "    arr[2] = 3.0",
            "    print(np_sum(arr))",
        ],
    )


def test_xp2f_function_named_fortran_keyword(tmp_path: Path) -> None:
    # Regression test: a Python function literally named `do` (a
    # genuine Fortran keyword -- pyccel's own tests/pyccel/scripts/
    # GENERATED_NAME_COLLISION.py) had its CALL SITES renamed to `xdo()`
    # by the translator's own reserved-keyword alias mechanism, but the
    # function's own definition header and its module `use ..., only:`
    # listing were built by a SEPARATE, independent alias mechanism
    # (fn_alias_map) that only knew about collisions with other already
    # -used symbols, not Fortran keywords -- leaving the definition and
    # `use` list with the literal, un-renamed `do`, so the renamed call
    # site (`xdo()`) referenced a symbol that was never actually
    # imported or defined ("has no IMPLICIT type").
    _run_xp2f_compile_diff(
        tmp_path,
        "xfn_named_do.py",
        [
            "def f():",
            "    do_0001 = 5",
            "    return g() + do() + do_0001",
            "",
            "",
            "def g():",
            "    return 2",
            "",
            "",
            "def do():",
            "    return 4",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    a = f()",
            "    print(a)",
        ],
    )


def test_xp2f_list_returning_function_subscripted_not_unpacked(tmp_path: Path) -> None:
    # Regression test: rewrite_tuple_call_subscript_to_temp's own
    # tuple_return_arity collection treated a function whose every
    # return is a List literal (as well as a Tuple literal) of fixed
    # arity as a multi-output-subroutine candidate -- but a List literal
    # return is genuinely ambiguous (Python uses it both for multi-value
    # tuple-unpack returns AND as a single sequence/array result), and
    # generate_flat's own canonical tuple_return_funcs collector already
    # resolves that ambiguity by only treating an all-list-literal
    # function as multi-output when some call site actually UNPACKS it
    # at matching arity -- not when every call site only ever subscripts
    # it. Without the same disambiguation here, `stats(x)[0]` (never
    # unpacked anywhere) got hijacked into a bogus tuple-unpack
    # assignment (`_tuple_tmp_1_0, _tuple_tmp_1_1 = stats(x)`) instead of
    # being left alone for the correct array-valued-function codegen --
    # "unsupported assign" once that bogus unpack reached codegen with
    # no matching subroutine to call.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlist_return_subscript_only.py",
        [
            "import numpy as np",
            "",
            "def stats(x):",
            "    return [np.mean(x), np.std(x)]",
            "",
            "if __name__ == \"__main__\":",
            "    x = np.array([1.0, 2.0, 3.0, 4.0])",
            "    print(stats(x)[0])",
        ],
    )


def test_xp2f_assert_false_aborts_with_nonzero_exit_code(tmp_path: Path) -> None:
    # Regression test: translator subclasses ast.NodeVisitor, so a
    # statement type with no visit_X method (ast.Assert had none at all)
    # is silently no-op'd by generic_visit instead of erroring -- `assert
    # False` (pyccel's own tests/pyccel/scripts/asserts/invalid_assert1.py)
    # previously transpiled to a program that built and ran successfully,
    # silently skipping the check entirely (exit code 0, matching neither
    # Python's own AssertionError nor any warning at transpile time).
    # `--run-diff` can't exercise this directly (it bails out as soon as
    # the reference Python run itself fails), so drive the compiled
    # binary directly and check its own exit code instead.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xassert_false.py"
    src.write_text(
        "\n".join(
            [
                "if __name__ == \"__main__\":",
                "    a = 0",
                "    b = 1",
                "    assert a == b, \"a must equal b\"",
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
    exe_path = tmp_path / "xassert_false_p.exe"
    assert exe_path.exists()
    run_proc = subprocess.run(
        [str(exe_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_proc.returncode != 0, run_proc.stdout + run_proc.stderr


def test_xp2f_assert_true_matches_python(tmp_path: Path) -> None:
    # Companion to the failing-assert test above: a passing assert must
    # not change program behavior/output at all.
    _run_xp2f_compile_diff(
        tmp_path,
        "xassert_true.py",
        [
            "if __name__ == \"__main__\":",
            "    a = 0",
            "    b = a",
            "    assert a == b",
            "    b = 1",
            "    assert a != b",
            "    assert a <= b",
            "    assert b >= a",
            "    print(a, b)",
        ],
    )


def test_xp2f_assert_inside_function_aborts_with_nonzero_exit_code(tmp_path: Path) -> None:
    # Companion to test_xp2f_assert_false_aborts_with_nonzero_exit_code:
    # an assert inside a FUNCTION body (not just top-level exec code)
    # must also actually be checked at runtime, not silently dropped.
    shutil.copy2(PYTHON_HELPER_PATH, tmp_path / "python.f90")
    src = tmp_path / "xassert_in_function.py"
    src.write_text(
        "\n".join(
            [
                "def check(x):",
                "    assert x > 0, \"x must be positive\"",
                "    return x * 2",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    print(check(-5))",
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
    exe_path = tmp_path / "xassert_in_function_p.exe"
    assert exe_path.exists()
    run_proc = subprocess.run(
        [str(exe_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_proc.returncode != 0, run_proc.stdout + run_proc.stderr


def test_xp2f_np_sign_int_argument_not_promoted_to_real(tmp_path: Path) -> None:
    # Regression test: np.sign(int_value) reused a real-valued
    # `sign(1.0_dp, a0)` template while explicitly excluding "sign" from
    # the int->real promotion just above it, pairing a real 1.0_dp with
    # an unpromoted integer argument -- a gfortran "'b' argument of
    # 'sign' intrinsic must be the same type and kind as 'a'" (pyccel's
    # own tests/pyccel/scripts/numpy/numpy_sign.py). np.sign also
    # preserves an int argument's own int-ness (numpy's sign(int) is an
    # int, not a float).
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_sign_int.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    print(np.sign(0))",
            "    print(np.sign(42))",
            "    print(np.sign(-42))",
            "    print(np.sign(np.int8(0)))",
            "    print(np.sign(np.int8(42)))",
            "    print(np.sign(np.int8(-42)))",
            "    print(np.sign(np.int64(0)))",
            "    print(np.sign(np.int64(-42)))",
        ],
    )


def test_xp2f_np_sign_zero_value_matches_numpy(tmp_path: Path) -> None:
    # Regression test: even with matching real types, Fortran's SIGN(A,
    # B) treats a zero B as positive-signed, so np.sign(0.0)/np.sign(
    # -0.0) came out 1.0/-1.0 instead of numpy's own 0.0/0.0.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnp_sign_zero.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    print(np.sign(0.0))",
            "    print(np.sign(-0.0))",
            "    print(np.sign(4.2))",
            "    print(np.sign(-4.2))",
        ],
    )


def test_xp2f_class_annotated_self_attribute_assignment_field(tmp_path: Path) -> None:
    # Regression test: `self.z: float = 10.0` (an annotated attribute
    # assignment inside __init__, alongside a plain `self.x = 3`) --
    # pyccel's own tests/pyccel/scripts/classes/class_variables.py --
    # only matched an ast.Assign-shaped field-defining statement, never
    # ast.AnnAssign, so `z` never became a declared struct field at all;
    # the constructor still tried to execute the assignment against the
    # already-built struct -- gfortran: "'z' is not a member of the
    # ... structure".
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_annassign_field.py",
        [
            "class A:",
            "    x: int",
            "",
            "    def __init__(self: \"A\"):",
            "        self.x = 3",
            "        self.z: float = 10.0",
            "",
            "    def get_4(self: \"A\"):",
            "        return 4",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    myA = A()",
            "    print(myA.x)",
            "    print(myA.z)",
        ],
    )


def test_xp2f_class_instance_aliasing_shares_mutations(tmp_path: Path) -> None:
    # Regression test: `my_a_ptr = my_a` (pyccel's own tests/pyccel/
    # scripts/classes/class_pointer.py) previously compiled to a plain
    # Fortran derived-type value-copy assignment -- mutating through
    # `my_a_ptr` afterward left `my_a` untouched, unlike Python, where
    # both names refer to the SAME object. `my_a_ptr` is now declared a
    # POINTER (assigned via `=>`) to the already-declared `target`
    # `my_a`, so a mutation through either name is visible through both.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_pointer_alias.py",
        [
            "class A:",
            "    def __init__(self, a: int):",
            "        self._a = a",
            "",
            "    def get_a(self):",
            "        return self._a",
            "",
            "    def set_a(self, a: int):",
            "        self._a = a",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    my_a = A(3)",
            "    my_a_ptr = my_a",
            "    print(my_a.get_a())",
            "    print(my_a_ptr.get_a())",
            "    my_a_ptr.set_a(4)",
            "    print(my_a.get_a())",
            "    print(my_a_ptr.get_a())",
        ],
    )


def test_xp2f_negative_variable_index_read_and_write(tmp_path: Path) -> None:
    # Regression test: a[-1] (a literal negative index) was already
    # special-cased at the AST level, but a[v] where v is a VARIABLE
    # that happens to be negative at runtime (v = -1) fell through to
    # the generic `(v + 1)` 0-based-to-1-based mapping -- (-1 + 1) = 0,
    # an out-of-bounds Fortran subscript -- a hard runtime crash, not a
    # decline. Confirmed both for reading (print(a[v])) and writing
    # (a[v] = ...). Surfaced by pyccel's own tests/pyccel/scripts/
    # arrays_view.py's array_view_negative_var (once its own pyccel-only
    # @allow_negative_index decorator is stripped).
    _run_xp2f_compile_diff(
        tmp_path,
        "xnegative_variable_index.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    a = np.array([1, 2, 3, 4, 5])",
            "    v = -1",
            "    print(a[v])",
            "    a[v] = 99",
            "    print(a)",
        ],
    )


def test_xp2f_negative_variable_index_2d_tuple_subscript(tmp_path: Path) -> None:
    # Companion to test_xp2f_negative_variable_index_read_and_write,
    # covering the 2D scalar+slice tuple-subscript shape (a[v, 1:])
    # pyccel's own array_view_negative_var actually uses -- a separate
    # nested _idx1_expr helper had the exact same un-wraparound-safe
    # `(v + 1)` fallback.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnegative_variable_index_2d.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    a = np.array([[1, 2, 3], [4, 5, 6], [7, 9, 5]])",
            "    v = -1",
            "    x = a[v, 1:]",
            "    print(x[0])",
            "    print(x[1])",
        ],
    )


def test_xp2f_type_print_numpy_scalar_and_array_dtypes(tmp_path: Path) -> None:
    # Regression test: print(type(x)) had no branch at all for complex
    # (fell through to a generic "unknown"), couldn't distinguish
    # np.int8/16/32/64 from a plain int (all printed "<class 'int'>"),
    # couldn't distinguish np.float64 from a plain float, and ignored
    # array-ness entirely (type(np.ones(3)) printed "<class 'float'>"
    # instead of "<class 'numpy.ndarray'>") -- pyccel's own tests/
    # pyccel/scripts/runtest_type_print.py and
    # runtest_array_type_print.py.
    _run_xp2f_compile_diff(
        tmp_path,
        "xtype_print_numpy_dtypes.py",
        [
            "import numpy as np",
            "",
            "if __name__ == \"__main__\":",
            "    print(type(int(3)))",
            "    print(type(np.int16(3)))",
            "    print(type(np.int32(3)))",
            "    print(type(np.int64(3)))",
            "    print(type(float(3)))",
            "    print(type(np.float32(3)))",
            "    print(type(np.float64(3)))",
            "    print(type(complex(3)))",
            "    print(type(np.complex64(3)))",
            "    print(type(np.complex128(3)))",
            "    a = np.ones(3)",
            "    print(type(a))",
        ],
    )


def test_xp2f_class_field_constructed_inline_from_another_class(tmp_path: Path) -> None:
    # Regression test: `self.param = A(5)` inside another class's
    # __init__ (constructing an already-known user class inline as a
    # field's OWN value, as opposed to receiving one as a constructor
    # parameter) wasn't recognized as a field-defining shape at all --
    # collect_dataclass_info's per-class scan had no branch for "field
    # value is a call to another known user class" -- so the whole
    # outer class was never registered, and its own constructor call
    # failed as "unsupported call: B()".
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_field_from_nested_ctor.py",
        [
            "class A:",
            "    def __init__(self, x: int):",
            "        self.x = x",
            "",
            "",
            "class B:",
            "    def __init__(self):",
            "        self.param = A(5)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    p = B()",
            "    print(p.param.x)",
        ],
    )


def test_xp2f_attribute_and_method_access_chained_off_call_result(tmp_path: Path) -> None:
    # Regression test: `get_A().x` / `get_A().f()` (attribute or method
    # access chained DIRECTLY off a call to a function that constructs
    # and returns a user class instance, with no intermediate variable)
    # -- pyccel's own tests/pyccel/scripts/classes/classes_5.py -- has
    # no single-expression Fortran equivalent: a derived-type function's
    # result cannot be the leftmost part of a component/type-bound-
    # procedure reference at all (gfortran: "The leftmost part-ref in a
    # data-ref cannot be a function reference"). Now hoisted into a
    # temporary variable first (rewrite_call_attribute_access_to_temp),
    # then accessed on that -- the same shape `a = get_A(); a.x` already
    # worked for.
    _run_xp2f_compile_diff(
        tmp_path,
        "xcall_result_attribute_access.py",
        [
            "class A:",
            "    def __init__(self, x: int):",
            "        self.x = x",
            "",
            "    def f(self):",
            "        return self.x + 2",
            "",
            "",
            "def get_A():",
            "    a_cls = A(3)",
            "    return a_cls",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    b = get_A().x",
            "    c = get_A().f() + 3",
            "    print(b)",
            "    print(c)",
        ],
    )


def test_xp2f_function_returns_class_constructor_call_directly(tmp_path: Path) -> None:
    # Regression test: `def get_A(): return A(4)` -- no explicit `-> T`
    # annotation, and the class instance is constructed directly in the
    # `return` (no intermediate Name) -- misdeclared its own result
    # variable as plain integer once called as an argument to another
    # function (`get_x_from_A(get_A())`, pyccel's own tests/pyccel/
    # scripts/classes/classes_7.py): _all_returns_same_struct_type only
    # recognized a bare-Name return already known via dict_typed_vars,
    # and get_A's own (fresh, per-function) prescan has no Assign
    # statement left to register such a Name from at all in this exact
    # shape -- a declared-vs-assigned type mismatch ("Cannot convert
    # TYPE(a_t) to INTEGER").
    _run_xp2f_compile_diff(
        tmp_path,
        "xfn_returns_ctor_call_directly.py",
        [
            "class A:",
            "    def __init__(self, x: int):",
            "        self.x = x",
            "",
            "",
            "def get_A():",
            "    return A(4)",
            "",
            "",
            "def get_x_from_A(a: \"A\"):",
            "    return a.x",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(get_x_from_A(get_A()))",
        ],
    )


def test_xp2f_class_computed_array_field_with_dtype_kwarg(tmp_path: Path) -> None:
    # Regression test: `self.field = np.ones(n, dtype=int)` inside
    # __init__ (a computed array field whose dtype= overrides the
    # default "real") was rejected outright by
    # _computed_array_field_template, which required NO keyword
    # arguments at all -- so the WHOLE CLASS silently failed to
    # register (not just this one field), breaking every OTHER method
    # on it too (pyccel's own tests/pyccel/scripts/classes/
    # classes_9.py's MyClass: even `self.param1` in an unrelated method
    # failed as "unsupported attribute expr").
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_computed_array_field_dtype.py",
        [
            "import numpy as np",
            "",
            "",
            "class MyClass:",
            "    def __init__(self, param1: \"int\", n: \"int\"):",
            "        self.param1 = param1",
            "        self.param2 = np.ones(n, dtype=int)",
            "",
            "    def get_param(self):",
            "        print(self.param1, self.param2)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    m = MyClass(2, 4)",
            "    m.get_param()",
        ],
    )


def test_xp2f_bare_math_import_used_only_inside_local_function(tmp_path: Path) -> None:
    # Regression test: `from math import gcd` (a supported bare-name
    # math import, MATH_DIRECT_IMPORT_SUPPORTED) used only inside a
    # local function (pyccel's own tests/pyccel/scripts/
    # pyccel_generated_compilation_dependency.py) previously went
    # completely undetected by the runtime-helper-needed scan: that
    # scan re-derives its own math/scipy/statistics/time/sys alias
    # dicts from whatever (sub-)tree it's handed, but the specific tree
    # views generate_flat builds for it (assembled from exec statements
    # + local function defs) have already had their own top-level
    # Import/ImportFrom nodes excluded -- so gcd_int_scalar never made
    # it into the module's own `use python_mod, only: ...` list at all,
    # a gfortran "has no IMPLICIT type" for a symbol the generated code
    # otherwise correctly tried to call.
    _run_xp2f_compile_diff(
        tmp_path,
        "xbare_math_import_in_local_func.py",
        [
            "from math import gcd",
            "",
            "",
            "def f(a: int, b: int):",
            "    s = gcd(a, b)",
            "    return s + 1",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(f(12, 18))",
            "    print(f(17, 5))",
        ],
    )


def test_xp2f_class_computed_property_getter(tmp_path: Path) -> None:
    # Regression test: a @property-decorated method whose body is a
    # COMPUTED expression (not the exact single-statement `return
    # self.FIELD` passthrough shape) was silently dropped by
    # rewrite_class_methods_to_toplevel -- its own docstring says this
    # should "surface as a clean unsupported call/undefined-name
    # failure", but the property's own read site (`obj.my_val`) was
    # left as a plain attribute access with nothing rewriting it,
    # producing a confusing Fortran build error instead ("'my_val' is
    # not a member of the ... structure"). Now hoisted into a real
    # function (ClassName_propname(self)), with every bare read of the
    # property (including from another method, via `self.prop`)
    # rewritten into a call to it.
    _run_xp2f_compile_diff(
        tmp_path,
        "xclass_computed_property.py",
        [
            "class A:",
            "    def __init__(self, n: int):",
            "        self._n = n",
            "",
            "    @property",
            "    def my_val(self):",
            "        return self._n * 10",
            "",
            "    def describe(self):",
            "        return self.my_val + 1",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    b = A(3)",
            "    print(b.my_val)",
            "    print(b.describe())",
        ],
    )


def test_xp2f_underscore_discard_scalar_and_array(tmp_path: Path) -> None:
    # Regression test: `_ = expr` (Python's conventional "discard this
    # value" idiom, e.g. pyccel's own test_create_arr: `_ =
    # np.ones(i); return True`) -- every _mark_*/_mark_alloc_* method
    # special-cased "_" as "never declared", but the actual statement-
    # emission code doesn't share that convention: it still emitted a
    # real allocate/assignment statement referencing _'s aliased
    # Fortran name (v_name) regardless, producing "has no IMPLICIT
    # type"/"neither a data pointer nor an allocatable variable" for
    # both a scalar and an array discard.
    _run_xp2f_compile_diff(
        tmp_path,
        "xunderscore_discard.py",
        [
            "import numpy as np",
            "",
            "",
            "def f_scalar(i: int):",
            "    _ = i * 2",
            "    return True",
            "",
            "",
            "def f_array(i: int):",
            "    _ = np.ones(i)",
            "    return True",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(f_scalar(7))",
            "    print(f_array(7))",
        ],
    )


def test_xp2f_return_none_in_otherwise_void_function(tmp_path: Path) -> None:
    # Regression test: `return None` as an early-exit guard clause
    # inside a function with NO other value-returning return anywhere
    # (pyccel's own test_return.py: `def divide_by(a, b): if abs(b) <
    # 0.1: return None; ...`) was misclassified as a genuine value-
    # returning function -- two duplicate "does this function return a
    # value" checks both tested `st.value is not None`, true even for
    # an explicit None constant -- so it was declared as a `function`
    # with a bogus result variable instead of a `subroutine`, then
    # (once that classification was fixed) left a leftover "-1"
    # Optional-int-sentinel assignment referencing a now-undeclared
    # result variable. A genuinely mixed Optional[int]-style function
    # (some branches return None, others return a real value) still
    # gets the sentinel assignment correctly -- only a WHOLLY void
    # function's own `return None` is now a bare `return`.
    _run_xp2f_compile_diff(
        tmp_path,
        "xreturn_none_void_function.py",
        [
            "import numpy as np",
            "",
            "",
            "def divide_by(a: \"float[:]\", b: \"float\"):",
            "    if abs(b) < 0.1:",
            "        return None",
            "    for i, ai in enumerate(a):",
            "        a[i] = ai / b",
            "",
            "",
            "def find_index(x: \"int\"):",
            "    if x < 0:",
            "        return None",
            "    return x * 2",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    x = np.ones(5)",
            "    b = 0.01",
            "    divide_by(x, b)",
            "    print(x)",
            "    b = 4.0",
            "    divide_by(x, b)",
            "    print(x)",
            "",
            "    a = find_index(5)",
            "    print(a)",
            "    c = find_index(-3)",
            "    print(c is None)",
        ],
    )


def test_xp2f_return_none_as_final_statement_of_void_function(tmp_path: Path) -> None:
    # Regression test for a SECOND, separate copy of the same bug fixed
    # by test_xp2f_return_none_in_otherwise_void_function above: pyccel's
    # own Burkardt-style helpers commonly end with `return None` as the
    # LAST statement of an otherwise-void function (e.g.
    # examples/xasa183_inferred.py's `timestamp()`: `t = time.time();
    # print(time.ctime(t)); return None`, no other return anywhere).
    # This exact shape is handled by a DIFFERENT code path than an early-
    # exit `return None` buried inside an if/for -- _emit_local_function
    # has its own inline, duplicate `isinstance(s, ast.Return)` handling
    # for a function's statement loop (to suppress a redundant `return`
    # when it's the final statement), entirely separate from
    # translator.visit_Return, and it was never updated with the
    # `void_return`/is_none(...) guard that visit_Return already has --
    # so `s.value is not None` was still True for a `Constant(value=None)`
    # node, falling through to `{result} = -1`, a bogus assignment to a
    # result variable never declared for a void function ("has no
    # IMPLICIT type").
    _run_xp2f_compile_diff(
        tmp_path,
        "xreturn_none_final_statement.py",
        [
            "def log_value(n: int) -> None:",
            "    x = n * 2",
            "    print(x)",
            "    return None",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    log_value(21)",
        ],
    )


def test_xp2f_iso_fortran_env_kind_use_in_proc_module_program(tmp_path: Path) -> None:
    # Regression test: the PROGRAM unit never got its own `use, intrinsic
    # :: iso_fortran_env` line when use_proc_module is True (a local
    # function exists, so the program relies on `use {proc_mod}, only:
    # dp, ...`) -- but a literal kind-suffixed integer (from an
    # np.int32(...)-style cast) can still appear directly in the
    # program's own exec-level code, with no `int32` symbol in scope
    # ("Missing kind-parameter"). Now always emitted (matching the
    # module's own unconditional line), relying on the already-correct
    # per-unit remove_unused_use_only_imports pass to prune it back down.
    _run_xp2f_compile_diff(
        tmp_path,
        "xiso_fortran_env_program.py",
        [
            "import numpy as np",
            "",
            "",
            "def f(a: \"int32\", b: \"int32\"):",
            "    return a + b",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(f(np.int32(3), np.int32(4)))",
        ],
    )


@pytest.mark.parametrize("operation", ["np.conj", "np.conjugate", "conjugate_alias"])
def test_xp2f_numpy_conjugation_preserves_kind_and_rank(tmp_path: Path, operation: str) -> None:
    _run_xp2f_compile_diff(
        tmp_path,
        "xnumpy_conjugate.py",
        [
            "import numpy as np",
            "from numpy import conjugate as conjugate_alias",
            "def real_matrix(a: 'float[:,:]'):",
            f"    return {operation}(np.transpose(a))",
            "def complex_matrix(a: 'complex[:,:]'):",
            f"    return {operation}(np.transpose(a))",
            f"print({operation}(2.5))",
            f"print({operation}(3))",
            f"print({operation}(1.0 + 2.0j))",
            f"print({operation}(True))",
            "r = np.array([1.5, -2.5, 3.0])",
            "i = np.array([1, -2, 3])",
            "z = np.array([1.0 + 2.0j, 3.0 - 4.0j])",
            f"print({operation}(r))",
            f"print({operation}(i))",
            f"zout = {operation}(z)",
            "print(zout.real)",
            "print(zout.imag)",
            f"b = {operation}(np.array([True, False]))",
            "print(b)",
            "print(b + 2)",
            "a = np.array([[1.5, 2.0, 3.0], [4.0, 5.0, 6.0]])",
            "print(real_matrix(a))",
            f"print({operation}(np.array([[1, 2, 3], [4, 5, 6]])))",
            "c = np.array([[1.0 + 2.0j, 3.0 - 4.0j], [5.0 + 6.0j, 7.0 - 8.0j]])",
            "cout = complex_matrix(c)",
            "for row in range(2):",
            "    for col in range(2):",
            "        print(cout[row, col].real, cout[row, col].imag)",
        ],
    )


def test_xp2f_conj_alias_and_non_complex_conjugate_imag(tmp_path: Path) -> None:
    # Regression test: `.conj()` wasn't recognized as `.conjugate()`'s
    # alias (2 sites: _expr_kind's Call-kind-inference and expr()'s
    # Call-codegen); separately, Fortran's CONJG/AIMAG intrinsics
    # strictly require COMPLEX operands, but the existing
    # .conjugate()/.imag codegen unconditionally emitted conjg()/aimag()
    # regardless of the operand's kind -- crashing for logical/int/real
    # operands (never actually reachable/tested before the .conj() fix
    # unblocked the rest of this file's own functions). bool.conjugate()
    # returns an int in Python (bool subclasses int); int/float
    # .conjugate() is a no-op passthrough; int/bool .imag is 0 (an int);
    # real .imag is 0.0.
    _run_xp2f_compile_diff(
        tmp_path,
        "xconj_imag_non_complex.py",
        [
            "import numpy as np",
            "",
            "",
            "def complex64_conj(a: \"complex64\", b: \"complex64\"):",
            "    return (a + b).conj()",
            "",
            "",
            "def float_conjugate(a: \"float\", b: \"float\"):",
            "    return (a + b).conjugate()",
            "",
            "",
            "def int_conjugate(a: \"int\", b: \"int\"):",
            "    return (a + b).conjugate()",
            "",
            "",
            "def bool_conjugate(a: \"bool\", b: \"bool\"):",
            "    return (a or b).conjugate()",
            "",
            "",
            "def imag_direct():",
            "    a = 1 + 2j",
            "    return a.imag",
            "",
            "",
            "def real_direct():",
            "    a = 1.5",
            "    return a.imag",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(complex64_conj(np.complex64(3 + 4j), np.complex64(1 + 2j)))",
            "    print(float_conjugate(3.5, 1.2))",
            "    print(int_conjugate(3, 4))",
            "    print(bool_conjugate(True, False))",
            "    print(imag_direct())",
            "    print(real_direct())",
        ],
    )


def test_xp2f_complex_builtin_single_and_two_arg_complex_operands(tmp_path: Path) -> None:
    # Regression test: Python's complex(z) with a SINGLE argument that's
    # already complex must return z unchanged (both real and imaginary
    # parts) -- the codegen unconditionally did `cmplx(real(z, kind=dp),
    # 0.0_dp, kind=dp)`, silently discarding the imaginary part.
    # Separately, complex(re, im) with either argument itself complex
    # computes `re + im*1j` using full COMPLEX arithmetic (a rotation by
    # 1j for the imag argument, not just taking its real part) -- e.g.
    # complex(1, -2j) == (3-0j), complex(2.8-7j, 1) == (2.8-6j).
    _run_xp2f_compile_diff(
        tmp_path,
        "xcomplex_builtin_complex_operands.py",
        [
            "def cast_complex_literal():",
            "    a = complex(2.8 + 7j)",
            "    return a",
            "",
            "",
            "def create_complex_literal_int_complex():",
            "    a = complex(1, -2j)",
            "    return a",
            "",
            "",
            "def create_complex_literal_complex_int():",
            "    a = complex(2.8 - 7j, 1)",
            "    return a",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(cast_complex_literal())",
            "    print(create_complex_literal_int_complex())",
            "    print(create_complex_literal_complex_int())",
        ],
    )


def test_xp2f_chained_comparison_expressions(tmp_path: Path) -> None:
    # Regression test: a Python chained comparison (`a <= b < c`) was
    # rejected outright ("chained compares not supported") -- now
    # decomposed into the conjunction of each adjacent pair, reusing the
    # existing single-op Compare codegen for each.
    _run_xp2f_compile_diff(
        tmp_path,
        "xchained_comparison.py",
        [
            "def in_range(a: float, b: float, c: float):",
            "    return a <= b < c",
            "",
            "",
            "def triple(a: int, b: int, c: int, d: int):",
            "    return a < b < c < d",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(in_range(0.0, 1.0, 2.0))",
            "    print(in_range(0.0, 10.0, 2.0))",
            "    print(triple(1, 2, 3, 4))",
            "    print(triple(1, 2, 2, 4))",
        ],
    )


def test_xp2f_round_variable_ndigits(tmp_path: Path) -> None:
    # Regression test: round(x, ndigits) required ndigits to be a
    # compile-time constant ("round() currently supports a constant-
    # integer ndigits argument"), even though py_round_ndigits's own
    # `ndigits` dummy is a plain runtime integer, not a constant --
    # pyccel's own test_builtins.py: `def round_ndigits(x, i): return
    # round(x, i)`. Also fixed a SEPARATE bug this exposed: _expr_kind
    # had no case for the bare `round` builtin at all, so a function
    # whose only return expression was `round(x, i)` (a real x) fell
    # through to a generic default and was misclassified -- silently
    # producing an integer-typed result instead of the correct real one
    # (and round(x) with no ndigits always returns an int, checked too).
    _run_xp2f_compile_diff(
        tmp_path,
        "xround_variable_ndigits.py",
        [
            "def round_int(x: float):",
            "    return round(x)",
            "",
            "",
            "def round_ndigits(x: float, i: int):",
            "    return round(x, i)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(round_int(3.345))",
            "    print(round_int(6.5))",
            "    print(round_ndigits(3.343, 2))",
            "    print(round_ndigits(3323.0, -2))",
        ],
    )


def test_xp2f_listcomp_zip_and_enumerate_tuple_targets(tmp_path: Path) -> None:
    # Regression test: a list-comprehension generator whose target is a
    # Tuple of Names iterating over zip(...)/enumerate(...) was rejected
    # outright ("ListComp currently supports only single-generator
    # form") -- pyccel's own functionals.py: `[i + j + k for i, j, k in
    # zip(a, b, c)]`, `[i * j for i, j in enumerate(a)]`. Now desugared
    # into a single-Name-target generator over range(), which the
    # existing lowering already handles. zip()'s own arguments are
    # iterated to the length of the SHORTEST one (Python's own zip()
    # truncates, never raises) -- using only the first argument's own
    # length previously crashed with an out-of-bounds Fortran index the
    # moment two zip() arguments had different lengths.
    _run_xp2f_compile_diff(
        tmp_path,
        "xlistcomp_zip_enumerate_targets.py",
        [
            "def functional_with_zip():",
            "    a = [x**2 for x in range(8)]",
            "    b = [0, 1, 2]",
            "    c = [k - y for k, y in zip(a, b)]",
            "    return len(c), c[0], c[1], c[2]",
            "",
            "",
            "def functional_with_enumerate():",
            "    a = [x + 1 for x in range(10)]",
            "    b = [i * j for i, j in enumerate(a)]",
            "    return len(b), b[0], b[1], b[2]",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    n1, c0, c1, c2 = functional_with_zip()",
            "    print(n1)",
            "    print(c0)",
            "    print(c1)",
            "    print(c2)",
            "    n2, b0, b1, b2 = functional_with_enumerate()",
            "    print(n2)",
            "    print(b0)",
            "    print(b1)",
            "    print(b2)",
        ],
    )


def test_xp2f_tuple_assign_subscript_target_swap(tmp_path: Path) -> None:
    # Regression test: `T1, T2, ... = V1, V2, ...` required every target
    # to be a plain Name ("tuple assignment targets must be names"),
    # rejecting the common element-swap idiom `l[i], l[j] = l[j], l[i]`
    # -- pyccel's own test_epyccel_expressions.py: swap by fixed AND
    # variable index. Now desugared into temp-variable assignments
    # (preserving Python's own tuple-assignment evaluation order: every
    # RHS value computed once, before any target is written to)
    # whenever at least one target is a Subscript/Attribute.
    _run_xp2f_compile_diff(
        tmp_path,
        "xtuple_assign_subscript_swap.py",
        [
            "def swp_index1(a: int, b: int, c: int):",
            "    l = [a, b, c]",
            "    l[0], l[1] = l[1], l[0]",
            "    return l[0], l[1], l[2]",
            "",
            "",
            "def swp_index2(i: int, j: int):",
            "    l = [1, 2, 3]",
            "    l[i], l[j] = l[j], l[i]",
            "    return l[0], l[1], l[2]",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    v0, v1, v2 = swp_index1(2, 4, 8)",
            "    print(v0)",
            "    print(v1)",
            "    print(v2)",
            "    w0, w1, w2 = swp_index2(0, 2)",
            "    print(w0)",
            "    print(w1)",
            "    print(w2)",
        ],
    )


@pytest.mark.parametrize("body", [
    "value = lo + ((value - lo) % (hi - lo + 1))\nreturn value",
    "before = value\nvalue = value + lo\nvalue = value * hi\nreturn before + value",
    "value = lo\nlo = hi\nhi = value\nreturn value + lo + hi",
])
def test_inline_reassigned_parameter_preserves_call_semantics(body: str) -> None:
    # Execute the transformed AST as Python to isolate the inliner from
    # subsequent type inference and Fortran postprocessing.
    source = "def helper(value, lo, hi):\n" + "\n".join(
        "    " + line for line in body.splitlines()
    ) + "\nresult = helper(actual(-1), actual(0), actual(5))\n"

    def execute(module):
        seen = []

        def actual(value):
            seen.append(value)
            return value

        namespace = {"actual": actual}
        exec(compile(ast.fix_missing_locations(module), "<inline-test>", "exec"), namespace)
        return namespace["result"], seen

    expected = execute(ast.parse(source))
    tree = ast.parse(source)
    functions = [tree.body[0]]
    statements = tree.body[1:]
    xp2f.inline_simple_value_returning_local_functions(statements, functions)
    assert not any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "helper"
        for statement in statements for node in ast.walk(statement)
    )
    assert execute(ast.Module(body=functions + statements, type_ignores=[])) == expected
    assert expected[1] == [-1, 0, 5]


@pytest.mark.parametrize("inferred, comment, expected", [
    ("real", "int", "real"),
    ("alloc_real", "int", "alloc_real"),
    ("complex", "int", "complex"),
    ("alloc_complex", "real", "alloc_complex"),
    ("int", "int", "int"),
    ("int", "real", "real"),
    (None, "int", "int"),
])
def test_numeric_comment_kind_does_not_narrow(inferred, comment, expected) -> None:
    assert xp2f._numeric_comment_kind(inferred, comment) == expected


@pytest.mark.parametrize("sentinel", ["np.inf", "-np.inf", "np.nan", "float('inf')", "2.5"])
def test_xp2f_tuple_return_preserves_real_sentinel(tmp_path: Path, sentinel: str) -> None:
    # Burkardt matrix_chain_brute documents the final cost as integer,
    # but its local cost also holds infinity. Comments cannot narrow the
    # storage required by executable assignments, including fractional values.
    _run_xp2f_compile_diff(
        tmp_path,
        "xreal_sentinel.py",
        [
            "import numpy as np",
            "def integer_cost(n):",
            "    total = 0",
            "    for i in range(n):",
            "        total = total + i",
            "    return total",
            "def search(n):",
            "    # Output:",
            "    # integer cost: the minimal cost.",
            "    if n == 0:",
            "        cost = 0",
            "        return cost, n",
            "    cost = " + sentinel,
            "    for i in range(n):",
            "        candidate = integer_cost(i)",
            "        if i > 0:",
            "            cost = candidate",
            "    return cost, n",
            "for n in range(3):",
            "    cost, count = search(n)",
            "    print(float(cost), count)",
        ],
    )


@pytest.mark.parametrize("list_name", ["index", "sum", "items"])
@pytest.mark.parametrize("tuple_result", [True, False])
def test_xp2f_return_appended_list_with_reserved_name(
    tmp_path: Path, list_name: str, tuple_result: bool
) -> None:
    returned = f"i, {list_name}" if tuple_result else list_name
    _run_xp2f_compile_diff(
        tmp_path,
        "xreserved_append.py",
        [
            "def collect(n):",
            f"    {list_name} = []",
            "    i = 0",
            "    if n == 0:",
            f"        return {returned}",
            "    while i < n:",
            f"        {list_name}.append(i + 1)",
            "        i = i + 1",
            f"    return {returned}",
            "for n in [0, 1, 3, 33]:",
            "    count, values = collect(n)" if tuple_result else "    values = collect(n)",
            "    print(len(values))",
            "    for value in values:",
            "        print(value)",
        ],
    )


@pytest.mark.parametrize("parameter", ["rank", "sum", "value"])
@pytest.mark.parametrize("initial", ["4", "4.5"])
def test_xp2f_rebound_reserved_parameter_uses_declared_dummy(
    tmp_path: Path, parameter: str, initial: str
) -> None:
    zero = "0.0" if "." in initial else "0"
    negative = "-1.0" if "." in initial else "-1"
    _run_xp2f_compile_diff(
        tmp_path,
        "xrebound_dummy.py",
        [
            f"def advance({parameter}, n):",
            f"    if {parameter} < 0:",
            f"        {parameter} = {zero}",
            f"        return {parameter}, n",
            "    for i in range(n):",
            f"        {parameter} = {parameter} + 1",
            f"    return {parameter}, n",
            "original = " + initial,
            "updated, count = advance(original, 3)",
            "print(original, updated, count)",
            f"updated, count = advance({negative}, 3)",
            "print(updated, count)",
        ],
    )


def test_xp2f_inline_reassigned_parameter_wrap_compile_diff(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(
        tmp_path,
        "xinline_reassigned_wrap.py",
        [
            "def wrap(value, lo, hi):",
            "    value = lo + ((value - lo) % (hi - lo + 1))",
            "    return value",
            "",
            "def exercise(n):",
            "    total = 0",
            "    for i in range(n):",
            "        left = wrap(i - 1, 0, n - 1)",
            "        right = wrap(i + 1, 0, n - 1)",
            "        total = total + left + right",
            "        print(left, right)",
            "    return total",
            "",
            "original = -1",
            "wrapped = wrap(original, 0, 5)",
            "print(original, wrapped)",
            "answer = exercise(6)",
            "print(answer)",
        ],
    )


def test_xp2f_toplevel_array_wrongly_promoted_to_parameter(tmp_path: Path) -> None:
    # Regression test: a top-level array assigned from a literal
    # np.array([...]) and never plain-reassigned/element-assigned gets
    # promoted to a Fortran PARAMETER (compile-time constant) as an
    # optimization -- but the "is this array ever mutated" safety check
    # (_name_used_as_call_arg) only recognized a `call SUBROUTINE(...)`
    # STATEMENT, never a locally-defined FUNCTION call embedded in an
    # ordinary expression (`print *, bump(arr)`) -- and xp2f.py emits
    # any Python function that both mutates a parameter and returns a
    # value as a Fortran `function`, not a `subroutine`. So `arr` got
    # wrongly promoted to a PARAMETER even though `bump` mutates it in
    # place, and gfortran refused to bind a PARAMETER to bump's own
    # intent(inout) dummy ("Named constant ... in variable definition
    # context").
    _run_xp2f_compile_diff(
        tmp_path,
        "xarray_wrongly_promoted_parameter.py",
        [
            "import numpy as np",
            "",
            "",
            "def bump(a: \"int[:]\"):",
            "    a[0] = a[0] + 1",
            "    return a",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    arr = np.array([10, 20, 30, 40])",
            "    print(bump(arr))",
        ],
    )


def test_xp2f_callback_parameter_default_value_bugs(tmp_path: Path) -> None:
    # Regression test for three interacting bugs found together via
    # pyccel's own highorder_functions.py `high_valuedarg_1(a, function:
    # "(int)(int)" = f1)`:
    # 1. A callback parameter's own DEFAULT value wasn't considered when
    #    inferring the callback's actual return kind -- defaulted to
    #    `real`, causing a Fortran interface type-mismatch build error
    #    once the default got materialized into an explicit call-site
    #    argument (f1 returns int, not real).
    # 2. prune_unreachable_local_functions's reachability walk never
    #    scanned a function's own args.defaults/kw_defaults -- a
    #    function referenced ONLY as another's callback default (never
    #    called directly) was wrongly pruned as unreachable.
    # 3. inline_simple_value_returning_local_functions's own separate
    #    "fully inlined away, drop it" cleanup had the identical blind
    #    spot, and was actually the one silently deleting `f1` in
    #    practice before the pruning pass ever ran.
    _run_xp2f_compile_diff(
        tmp_path,
        "xcallback_default_value.py",
        [
            "def f1(a: int):",
            "    return a",
            "",
            "",
            "def high_valuedarg_1(a: int, fn_cb: \"(int)(int)\" = f1):",
            "    x = fn_cb(a)",
            "    return x",
            "",
            "",
            "def test_valuedarg_1():",
            "    x = high_valuedarg_1(2)",
            "    return x",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(test_valuedarg_1())",
        ],
    )


def test_xp2f_numpy_self_assignment_triangles(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xself_triangles.py", [
        "import numpy as np",
        "for k in range(-3,4):",
        "    a = np.array([[1.,2.,3.], [4.,5.,6.]])",
        "    a = np.tril(a, k)",
        "    print(a)",
        "    b = np.array([[1,2], [3,4], [5,6]])",
        "    b = np.triu(b, k=k)",
        "    print(b)",
        "a = np.array([[1.,2.,3.], [4.,5.,6.]])",
        "a = np.tril(a)",
        "a = a + a.T.T",
        "print(a)",
    ])


def test_xp2f_numpy_self_assignment_constructors(tmp_path: Path) -> None:
    lines = ["import numpy as np"]
    for expr in ["np.zeros_like(a)", "np.ones_like(a)", "np.copy(a)",
                 "np.zeros(a.shape)", "np.ones(a.shape)",
                 "np.full(a.shape, a[0,0] + a[-1,-1])"]:
        lines += ["a = np.array([[1.,2.,3.], [4.,5.,6.]])", f"a = {expr}", "print(a)"]
    # Only the shape of an empty allocation is defined, not its contents.
    for expr in ["np.empty_like(a)", "np.empty(a.shape)"]:
        lines += ["a = np.array([[1.,2.,3.], [4.,5.,6.]])", f"a = {expr}",
                  "print(a.shape[0], a.shape[1])", "a[:,:] = 7.0", "print(a)"]
    lines += ["v = np.array([3.,1.,2.])", "v = np.zeros_like(v)", "print(v)",
              "v = np.ones_like(v)", "print(v)", "v = np.copy(v)", "print(v)"]
    _run_xp2f_compile_diff(tmp_path, "xself_constructors.py", lines)


def test_xp2f_numpy_self_assignment_repeat_sort(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xself_repeat_sort.py", [
        "import numpy as np",
        "a = np.array([[2.,3.,1.], [6.,4.,5.]])",
        "a = np.repeat(a, 2, axis=0)",
        "print(a)",
        "a = np.repeat(a, int(a[0,0]), axis=1)",
        "print(a)",
        "a = np.sort(a, axis=0)",
        "print(a)",
        "a = np.sort(a, axis=1)",
        "print(a)",
        "v = np.array([3.,1.,4.,2.])",
        "v = np.sort(v[::-1])",
        "print(v)",
        "p = np.array([3,1,4,2])",
        "p = np.argsort(p)",
        "print(p)",
    ])


def test_normalize_unused_callable_arguments_keeps_evaluated_and_used_arguments() -> None:
    tree = ast.parse('''
def callback(x):
    return x * x
def ignore(x, exact):
    return x + 1
def use(x, exact):
    return exact(x)
def shadow(callback):
    return ignore(1, callback)
ignore(1, callback)
ignore(x=2, exact=callback)
ignore(1, callback(2))
use(1, callback)
''')
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    body = [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
    xp2f.normalize_unused_callable_arguments(body, functions)
    assert isinstance(body[0].value.args[1], ast.Constant)
    assert isinstance(body[1].value.keywords[1].value, ast.Constant)
    assert isinstance(body[2].value.args[1], ast.Call)
    assert isinstance(body[3].value.args[1], ast.Name)
    assert isinstance(functions[-1].body[0].value.args[1], ast.Name)


def test_xp2f_unused_callback_arguments(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xunused_callbacks.py", [
        "import numpy as np",
        "def exact1(x):",
        "    return x*(1.0-x)/2.0",
        "def exact2(x):",
        "    return x*(x-1.0)*np.exp(x)",
        "def solve(n, exact):",
        "    x = np.linspace(0.0, 1.0, n+1)",
        "    return x, n",
        "def evaluated():",
        "    print(123)",
        "    return 0",
        "u, n = solve(4, exact1)",
        "v, m = solve(exact=exact2, n=4)",
        "w, k = solve(4, evaluated())",
        "print(u)",
        "print(v)",
        "print(w)",
        "print(n, m, k)",
        "print(round(exact1(0.5), 8), round(exact2(0.5), 8))",
    ])


def test_specialize_named_slice_callbacks_reuses_clones_and_preserves_defaults() -> None:
    tree = ast.parse('''
def constant(x):
    return 1.0
def vector(x):
    return x * 2.0
def solve(x, f=constant, scale=2.0):
    return f(x[1:]) * scale
solve(data, constant)
solve(data, f=vector, scale=3.0)
solve(data, constant)
solve(data)
''')
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    body = [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
    xp2f.specialize_named_slice_callbacks(body, functions)
    clones = [f for f in functions if f.name.startswith("solve_cb_")]
    assert len(clones) == 2
    assert any(f.name == "solve" for f in functions)  # Default call still needs it.
    assert body[0].value.func.id == body[2].value.func.id
    assert body[1].value.func.id != body[0].value.func.id
    for clone in clones:
        assert [a.arg for a in clone.args.args] == ["x", "scale"]
        assert len(clone.args.defaults) == 1
        assert clone.args.defaults[0].value == 2.0


@pytest.mark.parametrize("extra", ["f = constant", "saved = f", "vector = 3.0"])
def test_specialize_named_slice_callbacks_preserves_unsafe_bindings(extra: str) -> None:
    tree = ast.parse(
        "def constant(x):\n    return 1.0\n"
        "def vector(x):\n    return x * 2.0\n"
        f"def solve(x, f):\n    {extra}\n    return f(x[1:])\n"
        "solve(data, constant)\nsolve(data, vector)\n"
    )
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    body = [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
    before = ast.dump(tree)
    xp2f.specialize_named_slice_callbacks(body, functions)
    assert len(functions) == 3
    assert ast.dump(tree) == before


def test_xp2f_tuple_array_results_into_overlapping_sections(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xtuple_sections.py", [
        "import numpy as np",
        "def transfer(nf, uf, rf, nc):",
        "    uc = np.zeros(nc)",
        "    rc = np.zeros(nc)",
        "    rc[1:nc-1] = 4.0*(rf[2:2*nc-3:2] + uf[1:2*nc-4:2] - 2.0*uf[2:2*nc-3:2] + uf[3:2*nc-2:2])",
        "    return uc, rc",
        "u = np.arange(12, dtype=float)**2",
        "r = np.arange(12, dtype=float)",
        "u[1:6], r[2:7] = transfer(9, u[0:9], r[0:9], 5)",
        "print(u)",
        "print(r)",
        "u[0:10:2], r[1:11:2] = transfer(nf=9, uf=u[0:9], rf=r[0:9], nc=5)",
        "print(u)",
        "print(r)",
    ])


def test_xp2f_tuple_sections_preserve_result_types_and_positions(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xtuple_section_types.py", [
        "import numpy as np",
        "def results(n):",
        "    a = np.arange(n)",
        "    b = np.ones((2,n))*2.5",
        "    return a, 7.25, b",
        "a = np.zeros(6)",
        "b = np.zeros((2,6))",
        "a[1:4], value, b[:,2:5] = results(3)",
        "print(a)",
        "print(value)",
        "print(b)",
        "def scalars():",
        "    return 3, 4.5",
        "a[0], a[5] = scalars()",
        "print(a)",
        "def new_index_last():",
        "    return 9.5, 3",
        "def new_index_first():",
        "    return 0, 8.5",
        "index = 1",
        "a[index], index = new_index_last()",
        "print(a, index)",
        "index, a[index] = new_index_first()",
        "print(a, index)",
    ])


def test_xp2f_mixed_result_slice_callbacks(tmp_path: Path) -> None:
    # The forcing callbacks in Burkardt's Poisson solvers differ in result
    # rank: a constant broadcasts, while an elementwise formula is a vector.
    _run_xp2f_compile_diff(tmp_path, "xmixed_slice_callbacks.py", [
        "import numpy as np",
        "def constant(x):",
        "    return 1.0",
        "def vector(x):",
        "    return -x*(x+3.0)*np.exp(x)",
        "def solve(n, f, scale=1.0):",
        "    x = np.linspace(0.0, 1.0, n+1)",
        "    r = np.zeros(n+1)",
        "    r[1:n] = f(x[1:n])*scale/n/n",
        "    u = np.zeros(n+1)",
        "    it = 0",
        "    while it < 10000:",
        "        it += 1",
        "        change = 0.0",
        "        for i in range(1,n):",
        "            old = u[i]",
        "            u[i] = 0.5*(u[i-1]+u[i+1]+r[i])",
        "            change += abs(u[i]-old)",
        "        if change < 0.0001:",
        "            break",
        "    return u, it",
        "u, it = solve(16, constant)",
        "v, jt = solve(n=16, f=vector, scale=1.0)",
        "w, kt = solve(16, constant, scale=2.0)",
        "print(it, jt, kt)",
        "for i in range(17):",
        "    print(round(u[i], 9), round(v[i], 9), round(w[i], 9))",
    ])


def test_xp2f_compass_search_callback_argument_ranks(tmp_path: Path) -> None:
    # Reduced from Burkardt's MIT-licensed compass_search.py: the second
    # callback argument is a vector, while the first is an integer scalar.
    _run_xp2f_compile_diff(tmp_path, "xcompass_callbacks.py", [
        "import numpy as np",
        "def search(f, m, x, delta, tol, limit):",
        "    k = 0",
        "    fx = f(m, x)",
        "    while k < limit:",
        "        k += 1",
        "        decrease = False",
        "        s = 1.0",
        "        i = 0",
        "        for ii in range(2*m):",
        "            xd = x.copy()",
        "            xd[i] = xd[i] + s*delta",
        "            fxd = f(m, xd)",
        "            if fxd < fx:",
        "                x = xd.copy()",
        "                fx = fxd",
        "                decrease = True",
        "                break",
        "            s = -s",
        "            if s == 1.0:",
        "                i += 1",
        "        if not decrease:",
        "            delta /= 2.0",
        "            if delta < tol:",
        "                break",
        "    return x, fx, k",
        "def objective(m, x):",
        "    value = 0.0",
        "    for i in range(m-1):",
        "        value += (1.0-x[i])**2 + 100.0*(x[i+1]-x[i]**2)**2",
        "    return value",
        "x0 = np.zeros(2)",
        "x0[0] = -1.2",
        "x0[1] = 1.0",
        "x, fx, k = search(objective, 2, x0, 0.3, 1e-5, 20000)",
        "print(round(x[0], 8), round(x[1], 8), round(fx, 8), k)",
    ])


@pytest.mark.parametrize("integer_position", [None, "vector", "matrix"])
@pytest.mark.parametrize("keyword_call", [False, True])
def test_xp2f_callback_later_matrix_and_vector_arguments(
    tmp_path: Path, integer_position: str | None, keyword_call: bool
) -> None:
    _run_xp2f_compile_diff(tmp_path, "xcallback_later_arrays.py", [
        "import numpy as np",
        "def evaluate(f, n, x, a):",
        "    return f(n, x, a)",
        "def objective(n, x, a):",
        "    value = 0.0",
        "    for i in range(n):",
        "        value += x[i]*a[i,0]",
        "    return value",
        "x = np.array([2,3])" if integer_position == "vector" else "x = np.array([2.,3.])",
        "a = np.array([[1,4],[5,6]])" if integer_position == "matrix" else "a = np.array([[1.,4.],[5.,6.]])",
        "print(evaluate(f=objective, n=2, x=x, a=a))" if keyword_call else "print(evaluate(objective, 2, x, a))",
    ])


def test_xp2f_chebyshev_vector_callback_ranks(tmp_path: Path) -> None:
    # Adapted from Burkardt's MIT-licensed chebyshev.py. The callbacks
    # are elementwise but must have array interfaces when passed to coeff.
    _run_xp2f_compile_diff(tmp_path, "xchebyshev_callbacks.py", [
        "import numpy as np",
        "def coeff(a, b, n, f):",
        "    angle = np.linspace(1.0, 2.0*n-1, n)",
        "    angle = angle*np.pi/(2.0*n)",
        "    x = np.cos(angle)",
        "    x = 0.5*(a+b) + x*0.5*(b-a)",
        "    fx = f(x)",
        "    c = np.zeros(n)",
        "    for j in range(n):",
        "        for k in range(n):",
        "            c[j] = c[j] + fx[k]*np.cos(np.pi*j*(2*k+1)/2.0/n)",
        "    c = 2.0*c/n",
        "    return c",
        "def interpolant(a, b, n, c, m, x):",
        "    dip1 = np.zeros(m)",
        "    di = np.zeros(m)",
        "    y = (2.0*x-a-b)/(b-a)",
        "    for i in range(n-1, 0, -1):",
        "        dip2 = dip1",
        "        dip1 = di",
        "        di = 2.0*y*dip1-dip2+c[i]",
        "    value = y*di-dip1+0.5*c[0]",
        "    return value",
        "def polynomial(x):",
        "    # Input:",
        "    # real X(), evaluation points.",
        "    # Output:",
        "    # real VALUE(), function values.",
        "    value = (x-3.0)*(x-1.0)*(x+2.0)",
        "    return value",
        "def exponential(x):",
        "    # Input:",
        "    # real X(), evaluation points.",
        "    # Output:",
        "    # real VALUE(), function values.",
        "    value = np.exp(x)",
        "    return value",
        "def driver():",
        "    c = coeff(-1.0, 1.0, 12, polynomial)",
        "    d = coeff(-1.0, 1.0, 12, f=exponential)",
        "    x = np.linspace(-1.0, 1.0, 17)",
        "    y = interpolant(-1.0, 1.0, 12, c, 17, x)",
        "    z = interpolant(-1.0, 1.0, 12, d, 17, x)",
        "    print(np.max(np.abs(y-polynomial(x))) < 1e-10)",
        "    print(np.max(np.abs(z-exponential(x))) < 1e-10)",
        "    for i in range(12):",
        "        print(round(c[i], 8), round(d[i], 8))",
        "    for i in range(17):",
        # The dyadic cubic values are exact at nine decimal places; eight
        # puts some on a rounding tie that roundoff can tip either way.
        "        print(round(y[i], 9), round(z[i], 8))",
        "driver()",
    ])


def test_xp2f_gram_schmidt_rank_rebinding(tmp_path: Path) -> None:
    # Burkardt's MIT-licensed gram_schmidt_tolerance: v is a vector
    # during projection, then a matrix when appended to the basis.
    _run_xp2f_compile_diff(tmp_path, "xgram_schmidt_rebind.py", [
        "import numpy as np",
        "def orthogonalize(A, tol):",
        "    m, na = A.shape",
        "    nu = 0",
        "    U = np.zeros([m, nu])",
        "    for j in range(na):",
        "        v = A[:,j]",
        "        for j2 in range(nu):",
        "            vu = np.dot(v, U[:,j2])",
        "            v = v - vu * U[:,j2]",
        "        v_norm = np.linalg.norm(v)",
        "        if tol < v_norm:",
        "            v = v.reshape(m, 1) / v_norm",
        "            nu = nu + 1",
        "            U = np.hstack((U, v))",
        "    return U",
        "def check(A):",
        "    U = orthogonalize(A, 1e-10)",
        "    print(U.shape[0], U.shape[1])",
        "    print(np.linalg.norm(U.T @ U - np.eye(U.shape[1])) < 1e-10)",
        "    print(np.linalg.norm(A - U @ (U.T @ A)) < 1e-10)",
        "    for i in range(U.shape[0]):",
        "        for j in range(U.shape[1]):",
        "            print(round(U[i,j], 8))",
        "check(np.array([[1.,2.], [4.,5.], [7.,8.]]))",
        "check(np.array([[1.,2.,3.], [4.,5.,6.], [7.,8.,9.]]))",
        "check(np.array([[0.,1.,2.,0.], [0.,0.,0.,1.], [0.,0.,0.,0.]]))",
        "check(np.zeros((3,2)))",
    ])


def test_xp2f_self_reshape_rank_rebinding(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xreshape_rebind.py", [
        "import numpy as np",
        "a = np.array([1.,2.,3.,4.,5.,6.])",
        "a = a.reshape(2,3)",
        "print(a.shape[0], a.shape[1])",
        "print(a)",
        "a = a.reshape(6)",
        "print(a)",
        "a = a.reshape(2,1,3)",
        "a = a.reshape(6)",
        "print(a)",
        "a = a.reshape(2,3)",
        "a = a.reshape(6, order='F')",
        "print(a)",
        "for k in range(3):",
        "    v = np.array([1.,2.,3.]) + k",
        "    print(np.dot(v, v))",
        "    if k != 1:",
        "        v = v.reshape(3,1) / 2.0",
        "        print(v.shape[0], v.shape[1])",
        "        print(v[:,0])",
    ])


def test_xp2f_mesh_vtoe_loadtxt_integer_rebind(tmp_path: Path) -> None:
    # Core of Burkardt's MIT-licensed mesh_vtoe. Keep the original
    # load/transpose/self-cast path, using a tiny zero-based mesh.
    (tmp_path / "elements.txt").write_text("0 1 2\n2 1 3\n2 3 4\n4 3 5\n", encoding="utf-8")
    _run_xp2f_compile_diff(tmp_path, "xmesh_vtoe_fixture.py", [
        "import numpy as np",
        "def sortrows(x):",
        "    x = x[np.lexsort(x.T[::-1])]",
        "    return x",
        "def mesh_vtoe(e_order, e_num, etov, v_num):",
        "    # Input:",
        "    # integer E_ORDER, the order of the elements.",
        "    # integer E_NUM, the number of elements.",
        "    # integer ETOV(E_ORDER,E_NUM), the vertices of each element.",
        "    # integer V_NUM, the number of vertices.",
        "    ve = np.zeros([e_order*e_num, 2], dtype=int)",
        "    k = 0",
        "    for e in range(e_num):",
        "        for o in range(e_order):",
        "            ve[k,0] = etov[o,e]",
        "            ve[k,1] = e",
        "            k = k + 1",
        "    ve = sortrows(ve)",
        "    vtoe_pointer = np.zeros(v_num+1, dtype=int)",
        "    old = 0",
        "    for k in range(e_order*e_num):",
        "        new = ve[k,0]",
        "        if new != old:",
        "            for v in range(old+1, new+1):",
        "                vtoe_pointer[v] = k",
        "            old = new",
        "    vtoe_pointer[v_num] = e_order*e_num",
        "    vtoe = np.zeros(e_order*e_num)",
        "    vtoe[0:e_order*e_num] = ve[0:e_order*e_num,1]",
        "    return vtoe_pointer, vtoe",
        "def fixture():",
        "    etov = np.loadtxt('elements.txt')",
        "    etov = etov.T",
        "    etov = etov.astype(int)",
        "    element_order = etov.shape[0]",
        "    element_num = etov.shape[1]",
        "    v_base = np.min(etov)",
        "    v_num = np.max(etov)",
        "    if v_base == 0:",
        "        v_num = v_num + 1",
        "    pointers, elements = mesh_vtoe(element_order, element_num, etov, v_num)",
        "    print(pointers)",
        "    for i in range(element_order*element_num):",
        "        print(elements[i])",
        "fixture()",
    ])


def test_xp2f_self_astype_preserves_values_and_rank(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xself_astype.py", [
        "import numpy as np",
        "a = np.array([[-2.75, 0.0, 3.5], [4.25, -5.5, 6.75]])",
        "original = a.copy()",
        "a = a.astype(int)",
        "print(a.shape[0], a.shape[1])",
        "print(a)",
        "print(original)",
        "a = a.astype(float)",
        "a = a + 0.5",
        "print(a)",
        "a = a.astype(int)",
        "print(a)",
        "a = a.astype(bool)",
        "a = a.astype(int)",
        "print(a)",
        "b = np.array([-1.75, 0.0, 2.5])",
        "b = b.astype(int)",
        "print(b)",
    ])


def test_xp2f_mesh_etoe_lexsort_fixture(tmp_path: Path) -> None:
    # Core of Burkardt's MIT-licensed mesh_etoe, with an in-memory fixture
    # instead of the missing boxy_elements.txt/pool_elements.txt files.
    _run_xp2f_compile_diff(tmp_path, "xmesh_etoe_fixture.py", [
        "import numpy as np",
        "def mesh_etoe(etov):",
        "    e_num, e_order = etov.shape",
        "    r = np.zeros((e_order*e_num, 4), dtype=int)",
        "    row = 0",
        "    for e in range(e_num):",
        "        v2 = etov[e,e_order-1]",
        "        for o in range(e_order):",
        "            v1 = v2",
        "            v2 = etov[e,o]",
        "            r[row,0] = min(v1,v2)",
        "            r[row,1] = max(v1,v2)",
        "            r[row,2] = o",
        "            r[row,3] = e",
        "            row = row + 1",
        "    r = r[np.lexsort(r.T[::-1])]",
        "    etoe = -np.ones((e_num,e_order))",
        "    row = 0",
        "    while True:",
        "        if e_num*e_order <= row+1:",
        "            break",
        "        if r[row,0] != r[row+1,0] or r[row,1] != r[row+1,1]:",
        "            row = row+1",
        "        else:",
        "            s1 = r[row,2]",
        "            e1 = r[row,3]",
        "            s2 = r[row+1,2]",
        "            e2 = r[row+1,3]",
        "            etoe[e1,s1] = e2",
        "            etoe[e2,s2] = e1",
        "            row = row+2",
        "    return etoe",
        "etov = np.array([[0, 1, 2], [2, 1, 3], [2, 3, 4]])",
        "neighbors = mesh_etoe(etov)",
        "for i in range(3):",
        "    for j in range(3):",
        "        print(neighbors[i,j])",
    ])


def test_xp2f_lexsort_rejects_bad_key_shapes(tmp_path: Path) -> None:
    for keys, message in [
        ("(np.array([1,2]), np.array([3]))", "key size mismatch"),
        ("np.zeros((0,3))", "need at least one key"),
    ]:
        src = tmp_path / "xbad_lexsort.py"
        src.write_text(f"import numpy as np\np = np.lexsort({keys})\nprint(p)\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(XP2F_PATH), str(src), "--compile"],
                              cwd=tmp_path, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        exe = tmp_path / ("xbad_lexsort_p.exe" if sys.platform == "win32" else "xbad_lexsort_p")
        run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True,
                             check=False, timeout=30)
        assert run.returncode != 0, run.stdout + run.stderr
        assert message in run.stdout + run.stderr


def test_xp2f_lexsort_multiple_keys_stable_row_selection(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xlexsort_rows.py", [
        "import numpy as np",
        "def ordered(a):",
        "    b = a[np.lexsort(a.T[::-1])]",
        "    return b",
        "a = np.array([[1, 2, 4, 0], [1, 1, 9, 0], [0, 9, 9, 1], [1, 2, 3, 2], [1, 2, 3, 1], [1, 2, 3, 1]])",
        "p = np.lexsort(a.T[::-1])",
        "print(p)",
        "b = ordered(a)",
        "for i in range(6):",
        "    for j in range(4):",
        "        print(b[i,j])",
        "a = a[np.lexsort(a.T[::-1])]",
        "print(a[:,0])",
        "print(np.lexsort((a[:,3], a[:,2], a[:,1], a[:,0])))",
        "print(np.lexsort((a[:,0],)))",
        "r = np.array([[2.0, 1.0, 2.0, 1.0, 2.0], [3.0, 1.0, 3.0, 1.0, 2.0], [0.0, 0.0, 0.0, 0.0, 0.0]])",
        "print(np.lexsort(r))",
        "print(np.lexsort(r, axis=0))",
        "print(np.lexsort(r[::-1], axis=-1))",
        "print(np.lexsort((np.array([1, 0, 1, 0]), np.array([0.5, 0.5, -1.0, 0.5]))))",
        "nan_keys = np.array([[2.0, 1.0, 0.0, 1.0], [np.nan, 1.0, np.nan, 1.0]])",
        "print(np.lexsort(nan_keys))",
        "print(np.lexsort(np.zeros((3,0))))",
        "print(np.lexsort(np.zeros((1,4))))",
    ])


def test_xp2f_matrix_exponential_test9(tmp_path: Path) -> None:
    # Burkardt's r8mat_expm3 deliberately uses real parts of the eigenpairs.
    # The NAG test matrix has a conjugate pair, so both the eig output types
    # and the real-part conversions must survive translation.
    _run_xp2f_compile_diff(tmp_path, "xmatrix_exponential_test9.py", [
        "import numpy as np",
        "def exp_via_eig(a):",
        "    cevals, cevecs = np.linalg.eig(a)",
        "    evals = cevals.real",
        "    evecs = cevecs.real",
        "    exp_evals = np.exp(evals)",
        "    d2 = np.diag(exp_evals)",
        "    b = np.dot(evecs, d2)",
        "    bt = b.transpose()",
        "    at = evecs.transpose()",
        "    et, residuals, rank, s = np.linalg.lstsq(at, bt, rcond=None)",
        "    e = et.transpose()",
        "    return e",
        "a = np.array([[1.0, 3.0, 3.0, 3.0], [2.0, 1.0, 2.0, 3.0], [2.0, 1.0, 1.0, 3.0], [2.0, 2.0, 2.0, 1.0]])",
        "e = exp_via_eig(a)",
        "for i in range(4):",
        "    for j in range(4):",
        "        print(e[i,j])",
    ])


def test_xp2f_eig_real_matrix_with_complex_eigenpairs(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xcomplex_eigenpairs.py", [
        "import numpy as np",
        "def check(a):",
        "    w, v = np.linalg.eig(a)",
        "    for j in range(len(w)):",
        "        print(w[j].real, w[j].imag)",
        "        err = np.dot(a, v[:,j]) - w[j]*v[:,j]",
        "        print(np.max(np.abs(err)))",
        "        print(np.sum(np.abs(v[:,j])**2))",
        "    print(np.sum(a))",
        "check(np.array([[0.0, -1.0], [1.0, 0.0]]))",
        "check(np.array([[2.0, 0.0, 0.0], [0.0, 0.0, -3.0], [0.0, 3.0, 0.0]]))",
        "check(np.array([[2.0, 1.0], [0.0, 3.0]]))",
        "a = np.array([[0, -1], [1, 0]])",
        "w, _ = np.linalg.eig(a)",
        "print(w[0].imag, w[1].imag)",
        "_, v = np.linalg.eig(a)",
        "print(np.sum(np.abs(v)**2))",
        "w, v = np.linalg.eig(np.zeros((0,0)))",
        "print(len(w), v.shape[0], v.shape[1])",
    ])


def test_xp2f_lstsq_svd_rank_deficient_and_diagnostics(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xlstsq_svd.py", [
        "import numpy as np",
        "def report(a, b, cut):",
        "    x, residuals, rank, s = np.linalg.lstsq(a, b, rcond=cut)",
        "    print(rank, len(residuals), len(s), x.shape[0], x.shape[1])",
        "    for i in range(x.shape[0]):",
        "        for j in range(x.shape[1]):",
        "            print(x[i,j])",
        "    for i in range(len(residuals)):",
        "        print(residuals[i])",
        "    for i in range(len(s)):",
        "        print(s[i])",
        "a = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])",
        "b = np.array([[1.0, 0.0], [2.0, 1.0], [4.0, 2.0]])",
        "report(a, b, -1.0)",
        "report(np.array([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]]), np.array([[2.0], [3.0]]), -1.0)",
        "report(np.array([[1.0, 0.0], [0.0, 2.0], [1.0, 1.0]]), b, -1.0)",
        "report(np.zeros((3,2)), b, -1.0)",
        "report(np.zeros((0,2)), np.zeros((0,1)), -1.0)",
        "report(np.zeros((3,0)), b, -1.0)",
        "report(a, np.zeros((3,0)), -1.0)",
        "d = np.array([[1.0, 0.0], [0.0, 0.0001]])",
        "rhs = np.array([[1.0], [1.0]])",
        "report(d, rhs, 0.001)",
        "report(d, rhs, 0.0)",
        "v = np.array([1.0, 2.0, 4.0])",
        "x, residuals, rank, s = np.linalg.lstsq(a, v, rcond=None)",
        "print(x[0], x[1], rank, len(residuals))",
        "z = np.linalg.lstsq(a, v)[0]",
        "print(z[0], z[1])",
        "z2 = np.linalg.lstsq(d, np.array([1, 1]), 0.001)[0]",
        "print(z2[0], z2[1])",
        "full = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])",
        "x, residuals, rank, s = np.linalg.lstsq(full, v, rcond=None)",
        "print(x[0], x[1], rank, residuals[0])",
        "ai = np.array([[1, 2], [2, 4]])",
        "xi = np.linalg.lstsq(ai, np.array([1, 2]), rcond=None)[0]",
        "print(xi[0], xi[1])",
    ])


@pytest.mark.parametrize("loop", ["do k = 1, n", "outer: do K = 1, n", "do 100 k = 1, n"])
def test_scalar_constant_promotion_keeps_do_variables(loop: str) -> None:
    lines = ["subroutine f(n)", "integer, intent(in) :: n", "integer :: k",
             "integer :: fixed", "k = 0", "fixed = 7", "block", loop,
             "print *, k, fixed", "end do", "end block", "end subroutine f"]
    result = "\n".join(xp2f.promote_immediate_scalar_constants(lines))
    assert "parameter :: k" not in result
    assert "k = 0" in result
    assert "parameter :: fixed = 7" in result


def test_xp2f_initialized_loop_variable_in_branch(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xinitialized_loop.py", [
        "import numpy as np",
        "def matrix(n, which):",
        "    a = np.zeros((n, n))",
        "    if which == 13:",
        "        k = 0",
        "        for i in range(n):",
        "            a[i, i] = 1.0",
        "        value = 1.0",
        "        for k in range(1, n):",
        "            value = value / float(k)",
        "            for i in range(n-k):",
        "                a[i, i+k] = value",
        "        value = 1.0 / 10.0**n",
        "        for k in range(1, n):",
        "            value = value / float(k)",
        "            for j in range(k):",
        "                a[n+j-k, j] = value",
        "    return a",
        "for n in range(1, 5):",
        "    a = matrix(n, 13)",
        "    for i in range(n):",
        "        for j in range(n):",
        "            print(a[i,j])",
    ])


def test_xp2f_lstsq_matrix_rhs_preserves_rank(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xlstsq_matrix_rhs.py", [
        "import numpy as np",
        "from numpy import linalg as la",
        "def fit(a, b):",
        "    x, residuals, rank, s = np.linalg.lstsq(a, b, rcond=None)",
        "    result = x.transpose()",
        "    return result",
        "a = np.array([[1.0, 0.0], [0.0, 2.0], [1.0, 1.0]])",
        "b = np.array([[2.0, 3.0, 1.0], [4.0, -2.0, 5.0], [3.0, 1.0, 2.0]])",
        "x = fit(a, b)",
        "print(x.shape[0], x.shape[1])",
        "for i in range(3):",
        "    for j in range(2):",
        "        print(x[i,j])",
        "v, _, _, _ = np.linalg.lstsq(a, b[:,0], rcond=None)",
        "print(v[0], v[1])",
        "out = np.zeros((4, 5))",
        "out[1:3, 1:4], residuals, rank, s = la.lstsq(a, b, rcond=None)",
        "for i in range(4):",
        "    for j in range(5):",
        "        print(out[i,j])",
    ])


def test_xp2f_complex_solve_errors(tmp_path: Path) -> None:
    for a, b, message in [
        ("[[1j, 2j], [2j, 4j]]", "[1j, 2j]", "singular matrix"),
        ("[[1j, 2j]]", "[1j]", "matrix must be square"),
        ("[[1j, 0j], [0j, 1j]]", "[1j]", "rhs row mismatch"),
    ]:
        src = tmp_path / "xbad_complex_solve.py"
        src.write_text("import numpy as np\n"
                       f"a = np.array({a})\nb = np.array({b})\n"
                       "x = np.linalg.solve(a, b)\nprint(x)\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(XP2F_PATH), str(src), "--compile"],
                              cwd=tmp_path, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        exe = tmp_path / ("xbad_complex_solve_p.exe" if sys.platform == "win32" else "xbad_complex_solve_p")
        run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True,
                             check=False, timeout=30)
        assert run.returncode != 0, run.stdout + run.stderr
        assert message in run.stdout + run.stderr


def test_xp2f_complex_matrix_exponential(tmp_path: Path) -> None:
    # Reduced from John Burkardt's MIT-licensed c8mat_expm1.
    _run_xp2f_compile_diff(tmp_path, "xcomplex_expm.py", [
        "import numpy as np",
        "def c8mat_expm1(n, a):",
        "    q = 6",
        "    a2 = a.copy()",
        "    a_norm = np.linalg.norm(a2, np.inf)",
        "    ee = int(np.log2(a_norm)) + 1",
        "    s = max(0, ee + 1)",
        "    a2 = a2 / (2.0 ** s)",
        "    x = a2.copy()",
        "    c = 0.5",
        "    e = np.eye(n, dtype=np.complex64) + c * a2",
        "    d = np.eye(n, dtype=np.complex64) - c * a2",
        "    p = True",
        "    for k in range(2, q + 1):",
        "        c = c * float(q-k+1) / float(k*(2*q-k+1))",
        "        x = np.dot(a2, x)",
        "        e = e + c*x",
        "        if p:",
        "            d = d + c*x",
        "        else:",
        "            d = d - c*x",
        "        p = not p",
        "    e = np.linalg.solve(d, e)",
        "    for k in range(s):",
        "        e = np.dot(e, e)",
        "    return e",
        "for k in range(4):",
        "    if k == 0:",
        "        a = np.array([[1+0j, 0j], [0j, 2+0j]])",
        "    elif k == 1:",
        "        a = np.array([[3j, 0j], [0j, -4j]])",
        "    elif k == 2:",
        "        a = np.array([[5+6j, 0j], [0j, 7-8j]])",
        "    else:",
        "        a = np.array([[1+2j, 2-1j], [-3j, -1+1j]])",
        "    e = c8mat_expm1(2, a)",
        "    for i in range(2):",
        "        for j in range(2):",
        "            print(e[i,j].real, e[i,j].imag)",
    ])


def test_xp2f_complex_solve_vector_matrix_and_mixed_inputs(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xcomplex_solve.py", [
        "import numpy as np",
        "def solve_vector(a, b):",
        "    return np.linalg.solve(a, b)",
        "def solve_matrix(a, b):",
        "    return np.linalg.solve(a, b)",
        "a = np.array([[0j, 2+1j], [3-2j, 1j]])",
        "b = np.array([1+4j, 2-3j])",
        "original_a = a.copy()",
        "original_b = b.copy()",
        "x = solve_vector(a, b)",
        "print(x[0].real, x[0].imag, x[1].real, x[1].imag)",
        "print(np.max(np.abs(a - original_a)), np.max(np.abs(b - original_b)))",
        "c = np.array([[1+4j, 2j], [2-3j, 5+1j]])",
        "original_c = c.copy()",
        "y = solve_matrix(a, c)",
        "for i in range(2):",
        "    for j in range(2):",
        "        print(y[i,j].real, y[i,j].imag)",
        "print(np.max(np.abs(c - original_c)))",
        "r = np.array([[2.0, 1.0], [1.0, 3.0]])",
        "iv = np.array([1, 2])",
        "im = np.array([[1, 2], [3, 4]])",
        "x1 = np.linalg.solve(r, b)",
        "x2 = np.linalg.solve(a, iv)",
        "y1 = np.linalg.solve(r, c)",
        "y2 = np.linalg.solve(a, im)",
        "for i in range(2):",
        "    print(x1[i].real, x1[i].imag, x2[i].real, x2[i].imag)",
        "    for j in range(2):",
        "        print(y1[i,j].real, y1[i,j].imag, y2[i,j].real, y2[i,j].imag)",
        "rx = np.linalg.solve(r, iv)",
        "print(rx[0], rx[1])",
        "empty = np.linalg.solve(np.zeros((0,0), dtype=complex), np.zeros(0, dtype=complex))",
        "print(len(empty))",
    ])


def test_xp2f_complex_eigvals_matches_numpy(tmp_path: Path) -> None:
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(1729)
    burkardt = np.array([[4+7j, -10-3j, 1+6j],
                         [-7+1j, 4+6j, -2+3j],
                         [-5+2j, 4+11j, -3-6j]])
    cases = [np.array([[2-3j]]), np.zeros((3, 3), complex),
             np.diag([2+3j, 2+3j, -1j]),
             np.array([[1+2j, 1j], [0j, 1+2j]]),
             burkardt, 0.5 * (burkardt + burkardt.conj().T),
             burkardt * 1e200, burkardt * 1e-200]
    for n in (2, 3, 5, 8):
        cases.append(rng.normal(size=(n, n)) + 1j*rng.normal(size=(n, n)))
    lines = ["import numpy as np", "def show(a):",
             "    w = np.linalg.eigvals(a)",
             "    for i in range(len(w)):",
             "        print(w[i].real, w[i].imag)",
             "    for i in range(a.shape[0]):",
             "        for j in range(a.shape[1]):",
             "            print(a[i, j].real, a[i, j].imag)"]
    for a in cases:
        lines.append(f"show(np.array({a.tolist()!r}))")
    lines.append("show(np.zeros((0, 0), dtype=complex))")
    src = tmp_path / "xcomplex_eigvals.py"
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(XP2F_PATH), str(src), "--compile"],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    exe = tmp_path / ("xcomplex_eigvals_p.exe" if sys.platform == "win32" else "xcomplex_eigvals_p")
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True,
                         check=False, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    numbers = iter(float(s.replace("D", "E")) for s in run.stdout.split())
    for a in cases:
        n = len(a)
        actual = np.array([complex(next(numbers), next(numbers)) for _ in range(n)])
        # Eigenvalue ordering is unspecified. Match as a multiset, not by index,
        # and normalize before comparison so tiny/huge matrices are meaningful.
        scale = np.max(np.abs(a)) or 1.0
        expected = list(np.linalg.eigvals(a / scale))
        for value in actual / scale:
            index = int(np.argmin(np.abs(np.asarray(expected) - value)))
            np.testing.assert_allclose(value, expected.pop(index), rtol=1e-10, atol=1e-12)
        unchanged = np.array([complex(next(numbers), next(numbers)) for _ in range(n*n)])
        np.testing.assert_allclose(unchanged.reshape(a.shape), a, rtol=1e-14, atol=0)
    assert list(numbers) == []


def test_xp2f_complex_eigvals_rejects_invalid_input(tmp_path: Path) -> None:
    for values, message in [
        ("[[1j, 2j]]", "matrix must be square"),
        ("[[complex(np.nan, 0.0)]]", "matrix must contain only finite values"),
        ("[[complex(0.0, np.inf)]]", "matrix must contain only finite values"),
    ]:
        src = tmp_path / "xbad_eigvals.py"
        src.write_text("import numpy as np\n"
                       f"a = np.array({values})\n"
                       "w = np.linalg.eigvals(a)\nprint(w)\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(XP2F_PATH), str(src), "--compile"],
                              cwd=tmp_path, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        exe = tmp_path / ("xbad_eigvals_p.exe" if sys.platform == "win32" else "xbad_eigvals_p")
        run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True,
                             check=False, timeout=30)
        assert run.returncode != 0, run.stdout + run.stderr
        assert message in run.stdout + run.stderr


def test_xp2f_complex_log_norm_and_real_eigvals(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xcomplex_log_norm.py", [
        "import numpy as np",
        "def log_norm(a):",
        "    b = 0.5 * (a + np.conjugate(np.transpose(a)))",
        "    c = np.linalg.eigvals(b)",
        "    return np.max(np.real(c))",
        "a = np.array([[4+7j, -10-3j, 1+6j], [-7+1j, 4+6j, -2+3j], [-5+2j, 4+11j, -3-6j]])",
        "print(log_norm(a))",
        "r = np.array([[0.0, -1.0], [1.0, 0.0]])",
        "w = np.linalg.eigvals(r)",
        "print(np.max(w.imag), np.min(w.imag), np.sum(w.real))",
    ])


def test_xp2f_matrix_norms_and_complex_branch_returns(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xmatrix_norms.py", [
        "import numpy as np",
        "def matrix(k):",
        "    if k == 0:",
        "        a = np.array([[3.0, 1.0, 0.0], [0.0, 4.0, 2.0]])",
        "    else:",
        "        a = np.array([[3.0 + 2.0j, 1.0j, 0.0j], [0.0j, 4.0 - 1.0j, 2.0j]])",
        "    return a",
        "def check(a):",
        "    # Input:",
        "    # real/complex A(M,N), the matrix.",
        "    print(np.linalg.norm(a, 1))",
        "    print(np.linalg.norm(a, 2))",
        "    print(np.linalg.norm(a, np.inf))",
        "    print(np.linalg.norm(a, -np.inf))",
        "    print(np.linalg.norm(a))",
        "    print(np.linalg.norm(a, 'fro'))",
        "for k in range(2):",
        "    a = matrix(k)",
        "    print(a[0, 0].real, a[0, 0].imag)",
        "    d = np.diag(a)",
        "    print(d.real)",
        "    print(d.imag)",
        "    restored = np.diag(d)",
        "    print(restored[0, 0].real, restored[0, 0].imag)",
        "    check(a)",
        "r = np.array([[3.0, 1.0, 0.0], [0.0, 4.0, 2.0]])",
        "print(np.linalg.norm(r, 2))",
        "kept = np.linalg.norm(r, 1, keepdims=True)",
        "print(kept.shape[0], kept.shape[1], kept[0, 0])",
        "rows = np.linalg.norm(r, 2, axis=1)",
        "print(rows[0], rows[1])",
        "print(np.linalg.norm(np.array([3.0, 4.0]), 2))",
        "print(np.linalg.norm(np.array([[3, 1], [0, 4]]), 2))",
    ])


def test_xp2f_numpy_sum_positional_axis(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(tmp_path, "xsum_positional_axis.py", [
        "import numpy as np",
        "from numpy import sum as np_sum",
        "def column_totals(a: 'float[:,:]'):",
        "    return np.sum(a, 0)",
        "a = np.array([[1.5, 2.0, 3.0], [4.0, 5.0, 6.0]])",
        "print(column_totals(a))",
        "print(np.sum(a, 1))",
        "print(np.sum(a, axis=0))",
        "print(np.sum(a, axis=1))",
        "print(np.sum(a, 0, keepdims=True))",
        "print(np.sum(a, 1, keepdims=True))",
        "print(np_sum(a, 0))",
        "print(np.sum(np.sum(a, 0)))",
        "print(np.sum(np.sum(a, 1)))",
        "print(np.sum(np.sum(a)))",
        "print(np.sum(a > 2.0, 0))",
        "print(np.sum(a > 2.0, 1))",
        "i = np.array([[1, 2, 3], [4, 5, 6]])",
        "print(np.sum(i, 0))",
        "print(np.sum(i, 1))",
        "cube = np.array([[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]])",
        "print(np.sum(cube, 1))",
    ])


def test_xp2f_builtin_sum_reduces_only_first_axis(tmp_path: Path) -> None:
    _run_xp2f_compile_diff(
        tmp_path,
        "xbuiltin_matrix_sum.py",
        [
            "import numpy as np",
            "from numpy import sum as np_sum",
            "def columns(a: 'float[:,:]'):",
            "    return sum(a)",
            "def frobenius(a: 'float[:,:]'):",
            "    return np.sqrt(sum(sum(a ** 2)))",
            "a = np.array([[1.5, 2.0, 3.0], [4.0, 5.0, 6.0]])",
            "print(columns(a))",
            "print(frobenius(a))",
            "print(sum(a, 0.5))",
            "print(sum(a, start=0.5))",
            "print(np.sum(a))",
            "print(np_sum(a))",
            "print(a.sum())",
            "print(sum(np.array([1, 2, 3])))",
            "print(sum(np.array([[1, 2, 3], [4, 5, 6]])))",
            "print(sum(a > 2.0))",
            "cube = np.array([[[1, 2, 3], [4, 5, 6]], [[7, 8, 9], [10, 11, 12]]])",
            "print(sum(cube))",
            "print(sum(sum(sum(cube))))",
        ],
    )


def test_xp2f_generator_chained_flatten_sum(tmp_path: Path) -> None:
    # Regression test: a list-comprehension/generator chaining 2+
    # dependent, unfiltered `for` clauses purely to flatten a multi-rank
    # array before summing every element -- pyccel's own
    # test_epyccel_generators.py: `sum(aii for ai in a for aii in ai)`
    # -- hit the same "single-generator form" restriction as the zip/
    # enumerate case. Rather than lowering element-by-element, this
    # exact shape (chained generators, elt is exactly the innermost
    # bound name) is now recognized directly as Fortran's own SUM
    # intrinsic with no `dim=` argument (which already reduces over
    # every element regardless of rank) -- verified for both 2D and 3D.
    _run_xp2f_compile_diff(
        tmp_path,
        "xgenerator_flatten_sum.py",
        [
            "import numpy as np",
            "",
            "",
            "def sum_var2(a: \"int[:,:]\"):",
            "    return sum(aii for ai in a for aii in ai)",
            "",
            "",
            "def sum_var2_3d(a: \"int[:,:,:]\"):",
            "    return sum(aiii for ai in a for aii in ai for aiii in aii)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    x2d = np.array([[1, 2, 3], [4, 5, 6]], dtype=int)",
            "    print(sum_var2(x2d))",
            "    x3d = np.array([[[1, 2], [3, 4]], [[5, 6], [7, 8]]], dtype=int)",
            "    print(sum_var2_3d(x3d))",
        ],
    )


def test_xp2f_list_pop_expr_context_index_and_clear_reverse(tmp_path: Path) -> None:
    # Regression test for a cluster of list-method gaps found together
    # via pyccel's own lists.py:
    # 1. list.pop() used in a return/expression context (not just plain
    #    assignment or a bare statement) -- `return a.pop()`, `return
    #    a.pop() + 3`, `return a.pop(a.pop(0))` -- now hoisted into a
    #    preceding temp assignment via a new AST rewrite, innermost pop
    #    first (matching Python's own inner-before-outer call evaluation
    #    order for the nested-pop-as-index case).
    # 2. list.pop(index) with an explicit index (positive or negative)
    #    was unconditionally rejected everywhere ("pop with index is not
    #    yet supported") -- now supported with Python-style negative-
    #    index wraparound, via a new shared _emit_indexed_pop helper.
    # 3. list.clear() -- completely unimplemented before this (no code
    #    path at all).
    # 4. list.reverse() -- completely unimplemented before this (no code
    #    path at all).
    _run_xp2f_compile_diff(
        tmp_path,
        "xlist_pop_clear_reverse.py",
        [
            "def pop_last_element():",
            "    a = [1, 3, 45]",
            "    return a.pop()",
            "",
            "",
            "def pop_expression():",
            "    a = [1, 3, 45]",
            "    return a.pop() + 3",
            "",
            "",
            "def pop_as_arg():",
            "    a = [1, 3, 45]",
            "    return a.pop(a.pop(0))",
            "",
            "",
            "def pop_negative_index():",
            "    a = [1, 3, 45]",
            "    return a.pop(-1)",
            "",
            "",
            "def clear_1():",
            "    a = [1, 2, 3]",
            "    a.clear()",
            "    return a",
            "",
            "",
            "def list_reverse():",
            "    a_int = [1, 2, 3]",
            "    a_int.reverse()",
            "    return a_int[0], a_int[-1]",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(pop_last_element())",
            "    print(pop_expression())",
            "    print(pop_as_arg())",
            "    print(pop_negative_index())",
            "    print(clear_1())",
            "    r0, r1 = list_reverse()",
            "    print(r0)",
            "    print(r1)",
        ],
    )


def test_xp2f_tuple_return_of_in_expressions_rank(tmp_path: Path) -> None:
    # Regression test: `_rank_expr`'s generic ast.Compare handling
    # assumed elementwise-broadcast semantics (correct for `<`/`>`/`==`
    # between arrays, where the result shares the operands' own rank),
    # and wrongly applied the same "max of operand ranks" formula to
    # `in`/`not in` -- which in Python always yields a single scalar
    # bool, regardless of the right-hand side's own rank. Pyccel's own
    # lists.py: `return (1 in a), (5 in a), (3 in a)` with `a` a rank-1
    # list -- each tuple element was wrongly declared a rank-1
    # allocatable result instead of a scalar logical, crashing at
    # runtime ("Assignment of scalar to unallocated array") the moment
    # the actual scalar `any(...)` codegen was assigned into it.
    _run_xp2f_compile_diff(
        tmp_path,
        "xtuple_return_in_expr_rank.py",
        [
            "def list_contains():",
            "    a = [1, 3, 4, 7, 10, 3]",
            "    return (1 in a), (5 in a), (3 in a)",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    r0, r1, r2 = list_contains()",
            "    print(r0)",
            "    print(r1)",
            "    print(r2)",
        ],
    )


def test_xp2f_nested_single_return_function_with_leading_import(tmp_path: Path) -> None:
    # Regression test: a trivial nested `def` with exactly one statement
    # (`return EXPR`) is converted to a lambda substitution
    # (_simple_function_as_lambda) so a bare call to it anywhere else in
    # the enclosing function is resolved -- but a leading `import X` /
    # `from X import Y` statement before that single return (e.g.
    # pyccel's own test_epyccel_return_arrays.py: `def single_return():
    # from numpy import array; return array([1, 2, 3, 4])`) made
    # len(body) != 1, disqualifying the conversion even though the
    # import has no runtime effect on the return value -- so `b =
    # single_return() + 1` fell through to "unsupported call:
    # single_return()". Now stripped first, exactly like the
    # already-handled leading-docstring case.
    _run_xp2f_compile_diff(
        tmp_path,
        "xnested_single_return_leading_import.py",
        [
            "def return_arrays_in_expression():",
            "    def single_return():",
            "        from numpy import array",
            "        return array([1, 2, 3, 4])",
            "",
            "    b = single_return() + 1",
            "    return b",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    r = return_arrays_in_expression()",
            "    print(r[0])",
            "    print(r[1])",
            "    print(r[2])",
            "    print(r[3])",
        ],
    )


def test_xp2f_optional_complex_default_arg(tmp_path: Path) -> None:
    # Regression test: a complex-typed Optional argument
    # (`x: "complex" = None`) lowers its "value if present, else
    # default" pattern to the `optval` generic (python.f90) -- but the
    # generic interface only had int/real/logical/char specific
    # procedures, no complex one at all ("There is no specific function
    # for the generic 'optval'"). Added optval_complex alongside the
    # existing optval_real, matching the same present(x)-then-default
    # shape -- pyccel's own test_epyccel_default_args.py: `def f5(x:
    # "complex" = 1j): y = x - 1; return y`.
    _run_xp2f_compile_diff(
        tmp_path,
        "xoptional_complex_default.py",
        [
            "def f5c(x: \"complex\" = 1j):",
            "    y = x - 1",
            "    return y",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(f5c(2.9 + 3j))",
            "    print(f5c())",
        ],
    )


def test_xp2f_floor_division_real_annotated_arg_not_forced_int(tmp_path: Path) -> None:
    # Regression test: `_semantic_int_context` (used to decide whether a
    # local function parameter should be forced to "int") matched a
    # parameter used as EITHER operand of `//`/`%` unconditionally --
    # but Python's `//`/`%` stay real-valued when either operand is a
    # float (17 // 2.5 == 6.0, a float, not truncated to an int).
    # Without checking the parameter's own EXPLICIT annotation first,
    # this silently overrode an authoritative `float`-annotated
    # parameter's kind back to "int" -- pyccel's own
    # test_epyccel_division.py: `def fdiv_i_r(x: int, y: "float"):
    # return x // y`. The wrong INTEGER dummy-argument declaration then
    # also made the FloorDiv codegen itself dispatch to floor_div_int
    # instead of floor_div_real, silently truncating the divisor to an
    # integer before dividing (17 // 2.5 computed as 17 // 2 == 8,
    # instead of the correct floor(17 / 2.5) == 6.0).
    _run_xp2f_compile_diff(
        tmp_path,
        "xfloordiv_real_annotated_arg.py",
        [
            "def fdiv_i_r(x: int, y: \"float\"):",
            "    return x // y",
            "",
            "",
            "def fdiv_r_r(x: \"float\", y: \"float\"):",
            "    return x // y",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(fdiv_i_r(17, 2.5))",
            "    print(fdiv_i_r(-17, 2.5))",
            "    print(fdiv_r_r(19.5, 2.5))",
            "    print(fdiv_r_r(-19.5, -2.5))",
        ],
    )


def test_xp2f_for_loop_enumerate_bare_target_subscripted(tmp_path: Path) -> None:
    # Regression test: `for v in enumerate(z): ... v[0] ... v[1] ...`
    # (a bare-Name loop target, subscripted inside the body instead of
    # unpacked at the `for` itself) was rejected outright ("enumerate
    # target must be a 2-item tuple/list") -- pyccel's own loops.py:
    # `enumerate_on_1d_array_with_tuple`. This project's existing
    # enumerate()-in-a-for-loop lowering only ever recognized an
    # already-unpacked 2-tuple target (`for i, x in enumerate(z)`), even
    # though `v[0]`/`v[1]` access the exact same two values. New AST
    # rewrite desugars into fresh index/value names, substituting every
    # `v[0]`/`v[1]` subscript in the loop body.
    _run_xp2f_compile_diff(
        tmp_path,
        "xfor_enumerate_bare_target.py",
        [
            "import numpy as np",
            "",
            "",
            "def enumerate_on_1d_array_with_tuple(z: \"int[:]\"):",
            "    res = 0",
            "    for v in enumerate(z):",
            "        res += v[0] * v[1]",
            "",
            "    return res",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    z = np.arange(7)",
            "    print(enumerate_on_1d_array_with_tuple(z))",
        ],
    )


def test_xp2f_transpose_rank3_and_negative_index(tmp_path: Path) -> None:
    # Regression test for two bugs found together via pyccel's own
    # test_epyccel_transpose.py:
    # 1. Fortran's TRANSPOSE intrinsic strictly requires a rank-2
    #    matrix, but np.transpose(x)/x.T (no explicit axes -- reverses
    #    ALL axes) unconditionally emitted `transpose(x)` regardless of
    #    rank, crashing to build for a rank-3 array. Fixed at every
    #    codegen site (`.T` property, `.transpose()` method already had
    #    it, `np.transpose(x)` direct call, and the `t = np.transpose;
    #    t(x)` callable-alias form) via RESHAPE's own `order=` argument
    #    (verified: reshape(x, [size(x,3), size(x,2), size(x,1)],
    #    order=[3,2,1]) gives y(k,j,i) = x(i,j,k), exactly numpy's own
    #    default-axes transpose semantics).
    # 2. A 3D tuple subscript with ALL THREE indices scalar (no slice)
    #    used a naive `(expr + 1)` conversion per index, unconditionally
    #    -- for a literal negative index (`y[0, -1, 0]`) this computed
    #    `(-1 + 1) == 0`, an out-of-bounds Fortran index, instead of the
    #    correct `size(y, 2)` (Python's own last-element tail indexing).
    #    Fixed by teaching the shared _scalar_idx1_expr helper to
    #    resolve a literal negative constant directly, matching the
    #    sibling 2D-tuple-subscript codegen's own local `_idx1_expr`
    #    closure, which already got this right.
    _run_xp2f_compile_diff(
        tmp_path,
        "xtranspose_rank3_negindex.py",
        [
            "import numpy as np",
            "",
            "",
            "def f2_shape(x: \"int[:,:,:]\"):",
            "    from numpy import transpose",
            "",
            "    y = transpose(x)",
            "    n, m, p = y.shape",
            "    return n, m, p, y[0, -1, 0], y[0, 0, -1], y[-1, -1, 0]",
            "",
            "",
            "def f2_prop(x: \"int[:,:,:]\"):",
            "    y = x.T",
            "    n, m, p = y.shape",
            "    return n, m, p, y[0, -1, 0], y[0, 0, -1], y[-1, -1, 0]",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    x2 = np.array(",
            "        [[[0, 1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12, 13], [14, 15, 16, 17, 18, 19, 20]],",
            "         [[21, 22, 23, 24, 25, 26, 27], [28, 29, 30, 31, 32, 33, 34], [35, 36, 37, 38, 39, 40, 41]]],",
            "        dtype=int,",
            "    )",
            "    a2, b2, c2, d2, e2, f2v = f2_shape(x2)",
            "    print(a2); print(b2); print(c2); print(d2); print(e2); print(f2v)",
            "    a4, b4, c4, d4, e4, f4v = f2_prop(x2)",
            "    print(a4); print(b4); print(c4); print(d4); print(e4); print(f4v)",
        ],
    )


def test_xp2f_reshape_row_major_order_and_int_kind(tmp_path: Path) -> None:
    # Regression test for two bugs found together while investigating
    # the transpose fix above:
    # 1. NumPy's own reshape() defaults to row-major ('C') fill order
    #    (the LAST axis varies fastest), but Fortran's RESHAPE with no
    #    `order=` argument fills its own native column-major way (FIRST
    #    axis fastest) instead -- silently producing a completely
    #    different (same-shaped) array with no error at all. Fixed for
    #    both `x.reshape(shape)` (method call, previously never handled
    #    order at all) and `np.reshape(x, shape)` (function call,
    #    previously only correct for the rank-2 case) via RESHAPE's own
    #    reversed `order=[N, N-1, ..., 1]` argument (verified
    #    empirically for both rank 2 and rank 3), for any rank -- an
    #    explicit `order='F'` is still honored unchanged.
    # 2. np.reshape(x, shape)'s own element kind was derived from
    #    `node.func.value` (the `np`/`numpy` module name itself, always
    #    unknown) instead of `node.args[0]` (the array actually being
    #    reshaped) -- np.reshape(np.arange(10, dtype=int), (2, 5))
    #    silently declared its result `real` instead of `integer`.
    _run_xp2f_compile_diff(
        tmp_path,
        "xreshape_row_major_order.py",
        [
            "import numpy as np",
            "",
            "",
            "def method_2d():",
            "    x = np.arange(10, dtype=int).reshape(2, 5)",
            "    return x",
            "",
            "",
            "def func_2d():",
            "    x = np.reshape(np.arange(10, dtype=int), (2, 5))",
            "    return x",
            "",
            "",
            "def method_forder():",
            "    x = np.arange(10, dtype=int).reshape(2, 5, order='F')",
            "    return x",
            "",
            "",
            "if __name__ == \"__main__\":",
            "    print(method_2d())",
            "    print(func_2d())",
            "    print(method_forder())",
        ],
    )

def _run_both_output_blocks(proc_stdout: str) -> tuple[str, str]:
    """Split ``--run-both`` combined stdout into (python_block, fortran_block).

    The python block is everything printed by the script's own run, between
    the "Run (python): PASS" marker and the "wrote ..." marker; the fortran
    block is everything printed after the "Run: PASS" marker to the end of
    output. Both are returned with a trailing newline stripped so exact-text
    comparisons aren't thrown off by a final blank line.
    """
    py_start = proc_stdout.index("Run (python): PASS") + len("Run (python): PASS")
    py_end = proc_stdout.index("\nwrote ")
    python_block = proc_stdout[py_start:py_end].strip("\n")
    f_start = proc_stdout.index("Run: PASS") + len("Run: PASS")
    fortran_block = proc_stdout[f_start:].strip("\n")
    return python_block, fortran_block


def test_xp2f_prints_3d_int_array_numpy_style(tmp_path: Path) -> None:
    src = tmp_path / "x3d_print_int.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def make():",
                "    return np.array([[[1, -222], [3, 4]], [[5, 6], [-7, 8]]], dtype=int)",
                "",
                "x = make()",
                "print(x)",
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
    python_block, fortran_block = _run_both_output_blocks(proc.stdout)
    # numpy's own rank-3 print format: bracket nesting keyed on
    # (outer-slice-index, row-index), one GLOBAL width across the whole
    # array (not per-column/per-slice), and a blank line between
    # consecutive outer slices. Assert the Fortran output matches
    # Python/numpy's own output byte-for-byte.
    assert fortran_block == python_block
    assert python_block == (
        "[[[   1 -222]\n"
        "  [   3    4]]\n"
        "\n"
        " [[   5    6]\n"
        "  [  -7    8]]]"
    )


def test_xp2f_prints_3d_int_array_asymmetric_shapes(tmp_path: Path) -> None:
    src = tmp_path / "x3d_print_asym.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def make_row1():",
                "    return np.arange(6).reshape(3, 1, 2)",
                "",
                "def make_col1():",
                "    return np.arange(6).reshape(3, 2, 1)",
                "",
                "def make_single():",
                "    return np.arange(1).reshape(1, 1, 1)",
                "",
                "print(make_row1())",
                "print(make_col1())",
                "print(make_single())",
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
    python_block, fortran_block = _run_both_output_blocks(proc.stdout)
    assert fortran_block == python_block
    assert python_block == (
        "[[[0 1]]\n"
        "\n"
        " [[2 3]]\n"
        "\n"
        " [[4 5]]]\n"
        "[[[0]\n"
        "  [1]]\n"
        "\n"
        " [[2]\n"
        "  [3]]\n"
        "\n"
        " [[4]\n"
        "  [5]]]\n"
        "[[[0]]]"
    )


def test_xp2f_prints_2d_int_array_uses_global_width(tmp_path: Path) -> None:
    src = tmp_path / "x2d_print_width.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def make():",
                "    return np.array([[1, -222], [3, 4]])",
                "",
                "print(make())",
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
    python_block, fortran_block = _run_both_output_blocks(proc.stdout)
    # numpy pads every column to ONE global width across the whole 2D
    # matrix (here, width 4 from "-222"), not a per-column width.
    assert fortran_block == python_block
    assert python_block == "[[   1 -222]\n [   3    4]]"

def test_xp2f_bare_numpy_shape_tuple_unpack_declares_locals(tmp_path: Path) -> None:
    # Real bug found mining pyccel's own test suite
    # (tests/pyccel/scripts/import_syntax/import_mod.py): the local-function
    # declaration prescan's special case for `a, b = np.shape(x)`-style
    # tuple-unpacking only recognized the RHS when the numpy module alias
    # was spelled exactly "np" (a hardcoded `_m.value.func.value.id ==
    # "np"` check), unlike the actual codegen for this same pattern (in
    # visit_Assign), which correctly used the general is_numpy_name_node()
    # helper (accepting both "np" and a bare "numpy" import). A script
    # using `import numpy` (no "as np" alias) and calling
    # `numpy.shape(x)` inside a local function got its unpacked targets
    # silently skipped by the prescan, so no `integer ::` declaration was
    # emitted for them -- and if the function happened to live in the same
    # module as an unrelated module-level constant of the same name (e.g.
    # a top-level `n = 3` promoted to a Fortran PARAMETER), the identifier
    # resolved via host association to that immutable PARAMETER instead,
    # crashing the build with "Named constant ... in variable definition
    # context". Also failed (independently of any name collision) with a
    # plain "has no IMPLICIT type" error whenever no such collision existed
    # (confirmed via a variant using unique names n1/m1/n2/m2).
    src = tmp_path / "xbare_numpy_shape_unpack.py"
    src.write_text(
        "\n".join(
            [
                "import numpy",
                "",
                "",
                "def matmat(a: \"float[:,:]\", b: \"float[:,:]\", c: \"float[:,:]\"):",
                "    n, m = numpy.shape(a)",
                "    m, p = numpy.shape(b)",
                "    for i in range(0, n):",
                "        for j in range(0, p):",
                "            for k in range(0, m):",
                "                c[i, j] = c[i, j] + a[i, k] * b[k, j]",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    n = 3",
                "    m = 4",
                "    p = 3",
                "    a = numpy.zeros((n, m), \"double\")",
                "    b = numpy.zeros((m, p), \"double\")",
                "    c = numpy.zeros((n, p), \"double\")",
                "    a[0, 0] = 1.0",
                "    a[0, 1] = 2.0",
                "    b[0, 0] = 1.0",
                "    b[1, 0] = 1.0",
                "    matmat(a, b, c)",
                "    print(c[0, 0])",
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
    out_text = (tmp_path / "xbare_numpy_shape_unpack_p.f90").read_text(encoding="utf-8")
    assert "integer :: " in out_text
    # `n`/`m`/`p` (function-local, from numpy.shape() unpacking) must be
    # declared as ordinary local integers inside matmat's own subroutine,
    # not left to fall through to the unrelated module-level PARAMETER of
    # the same name.
    assert re.search(r"subroutine matmat\(.*?end subroutine matmat", out_text, re.S)
    matmat_body = re.search(r"subroutine matmat\(.*?end subroutine matmat", out_text, re.S).group(0)
    assert re.search(r"integer\s*::.*\bn\b", matmat_body)
    assert re.search(r"integer\s*::.*\bm\b", matmat_body)
    assert re.search(r"integer\s*::.*\bp\b", matmat_body)

def test_xp2f_np_power_array_args_not_misdetected_as_rng_distribution(tmp_path: Path) -> None:
    # Regression test: _rank_expr's `_is_rng_rank_source` helper treated
    # ANY bare Name receiver as an RNG-instance source (e.g. `rng.power(a,
    # size)` where `rng = np.random.default_rng()`), with no check that
    # the name was actually a tracked RNG variable -- so plain
    # `np.power(a, b)` (an ordinary elementwise ufunc, receiver is just
    # the module alias Name('np')) was misidentified as
    # `np.random.power(a, size)`, and its second array argument got
    # misinterpreted as a `size=` tuple, producing a bogus rank (the
    # array literal's own length) instead of the real broadcast rank.
    # This silently produced a wrong array rank for any code path
    # consulting _rank_expr, and crashed outright once print()'s
    # rank-3 dispatch (print_array_3d) started trusting it (found via
    # examples/xnp_math_funcs.py: print(np.power([2,3,4],[3,2,1]))).
    src = tmp_path / "xnp_power_rank.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "print(np.power([2.0, 3.0, 4.0], [3.0, 2.0, 1.0]))",
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
    out_text = (tmp_path / "xnp_power_rank_p.f90").read_text(encoding="utf-8")
    assert "call print_array_3d" not in out_text

def test_xp2f_for_loop_reversed_range(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # linear_algebra/gaussian_elimination.py: `for row in
    # reversed(range(rows)):` fell straight to "only for .. in range(..)
    # or for .. in sorted(..) supported". Fixed by reusing the same
    # start/stop/step parsing the forward-range case already has, just
    # swapping the bounds with a negated step.
    src = tmp_path / "xreversed_range.py"
    src.write_text(
        "\n".join(
            [
                "if __name__ == \"__main__\":",
                "    for i in reversed(range(5)):",
                "        print(i)",
                "    for i in reversed(range(2, 9, 3)):",
                "        print(i)",
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


def test_xp2f_return_empty_array_literal_matches_other_rank2_return(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # linear_algebra/gaussian_elimination.py: `return np.array((),
    # dtype=float)` (an "invalid input" sentinel) alongside a normal-path
    # `return x` where x is rank-2 crashed the build ("Incompatible
    # ranks 2 and 1 in assignment") since a Fortran array constructor
    # is always rank 1. Fixed by reshaping the empty-array return to
    # match the function's actual declared rank.
    src = tmp_path / "xempty_array_return.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "",
                "def maybe_identity(n, m):",
                "    if n != m:",
                "        return np.array((), dtype=float)",
                "    return np.zeros((n, m), dtype=float) + 1.0",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    a = maybe_identity(2, 3)",
                "    print(a.size)",
                "    b = maybe_identity(2, 2)",
                "    print(b[0, 0], b[1, 1])",
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


def test_xp2f_parameter_named_like_fortran_keyword_function(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # maths/numerical_analysis/bisection.py: a callback parameter
    # literally named `function` was declared under its raw name but
    # every body reference to it was independently renamed to
    # "xfunction" by the general Fortran-reserved-word aliasing
    # mechanism -- with nothing syncing the two, the build failed with
    # "Function 'xfunction' has no IMPLICIT type". Fixed by resolving
    # (and syncing) the alias for every parameter, not just DataFrame
    # ones (which already had this fix).
    src = tmp_path / "xreserved_word_param.py"
    src.write_text(
        "\n".join(
            [
                "def apply_twice(function, x):",
                "    return function(function(x))",
                "",
                "",
                "def square(x):",
                "    return x * x",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    print(apply_twice(square, 2.0))",
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


def test_xp2f_int_pow_negative_literal_exponent_is_real(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # maths/numerical_analysis/bisection.py: `10**-7` (used as a
    # convergence threshold: `abs(start - mid) > 10**-7`) compiled but
    # silently evaluated to Fortran INTEGER 0 -- `int ** int` with a
    # negative exponent computes 1 divided by a large integer via
    # INTEGER division -- since Python's int**negative_int is always a
    # float (1e-07) but xp2f emitted bare integer operands. This turned
    # the loop's guard into `> 0`, hanging the compiled program in a
    # genuine infinite loop (confirmed directly: the built .exe never
    # terminated). Also affected a separate module-level
    # constant-folding pass (the same class of bug already fixed once
    # for `/` vs `//`, but not extended to `**`).
    src = tmp_path / "xpow_negative_exponent.py"
    src.write_text(
        "\n".join(
            [
                "if __name__ == \"__main__\":",
                "    x = 10**-7",
                "    print(x)",
                "    y = 1.0",
                "    print(y > 10**-7)",
                "    start = 0.0",
                "    mid = 0.0",
                "    print(abs(start - mid) > 10**-7)",
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
        timeout=60,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout
    assert "Run: PASS" in proc.stdout

def test_xp2f_tolist_return_kind_matches_base_array(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # linear_algebra/matrix_inversion.py: `return inv_matrix.tolist()`
    # silently truncated every element of a REAL matrix to integer 0.
    # _rank_expr already passed a .tolist() call's rank through to its
    # base array, but _expr_kind had no matching case, so an untyped
    # .tolist() return defaulted the function's own result kind to int.
    src = tmp_path / "xtolist_return_kind.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "",
                "def halve(matrix):",
                "    m = np.array(matrix) / 2.0",
                "    return m.tolist()",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    print(halve([[1.0, 3.0], [5.0, 7.0]]))",
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


def test_xp2f_tuple_return_matching_param_name_gets_correct_rank_and_kind(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # linear_algebra/gauss_jordan.py: a local function returning a
    # tuple of two rank-2 arrays (`return coefficients, vertices`,
    # where BOTH names are also the function's own rebound parameters)
    # crashed the caller-side tuple-unpack declaration with "Rank
    # mismatch" -- a refinement pass overwrote the correct
    # alloc_real+rank tag with a bare "real" (losing the array-ness)
    # whenever the tuple-return source name matched a parameter name.
    src = tmp_path / "xtuple_return_param_name_rank.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "",
                "def halve_both(a, b):",
                "    a = a.astype(float).copy()",
                "    b = b.astype(float).copy()",
                "    a[0] /= 2.0",
                "    b[0] /= 2.0",
                "    return a, b",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    x = np.array([[4.0, 6.0], [8.0, 10.0]])",
                "    y = np.array([[20.0], [40.0]])",
                "    out_x, out_y = halve_both(x, y)",
                "    print(out_x)",
                "    print(out_y)",
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


def test_xp2f_np_isclose_two_scalars_not_indexed_as_array_result(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # linear_algebra/gauss_jordan.py: `not np.isclose(scalar, 0)`
    # lowered to `isclose_real([a], [b], ...)(1)` -- indexing a plain
    # (non-pointer) array-valued function's result at the call site,
    # which is a syntax error in standard Fortran (confirmed directly
    # with gfortran), not just non-idiomatic. A separate paren-
    # simplification pass then further mangled the already-invalid
    # text into a different-looking syntax error, masking the real
    # problem. Fixed by dispatching to a genuine scalar-returning
    # isclose_scalar_real helper for the all-scalar case instead.
    src = tmp_path / "xisclose_two_scalars.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "",
                "def check(x, y):",
                "    return not np.isclose(x, y)",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    print(check(1.0, 1.0 + 1e-12))",
                "    print(check(1.0, 2.0))",
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


def test_xp2f_none_sentinel_local_reset_every_loop_iteration(tmp_path: Path) -> None:
    # Real, serious bug found mining TheAlgorithms/Python's own
    # linear_algebra/gauss_jordan.py: `pivot_row = None` at the top of
    # an outer loop body (a manual "not found yet" scalar sentinel,
    # later checked via `pivot_row is None`) was silently dropped from
    # the generated Fortran entirely -- the codegen's "`x = None` is a
    # no-op, present() already represents absence" rule (correct for a
    # genuine Optional dummy argument) was applied unconditionally to
    # every plain-Name `= None`. Without the reset, a later outer
    # iteration that found no match reused the PREVIOUS iteration's
    # stale value instead of correctly skipping -- confirmed directly
    # to crash the real algorithm with a divide-by-zero SIGFPE.
    src = tmp_path / "xnone_sentinel_reset.py"
    src.write_text(
        "\n".join(
            [
                "def find_it(vals):",
                "    for col in range(2):",
                "        pivot_row = None",
                "        for row in range(len(vals)):",
                "            if col == 0 and vals[row] == 2:",
                "                pivot_row = row",
                "                break",
                "        if pivot_row is None:",
                "            print(col, -1)",
                "            continue",
                "        print(col, pivot_row)",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    find_it([1, 2, 3])",
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


def test_xp2f_np_eye_dtype_bool_is_logical(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # linear_algebra/jacobi_iteration_method.py: `~np.eye(n,
    # dtype=bool)` crashed with "unsupported unary op", since
    # _expr_kind's np.eye/np.identity handling ignored dtype=bool
    # entirely (a previously-documented gap: "Left as a documented gap
    # rather than fixed", since the codegen call site also needed
    # updating). Fixed by wrapping the (always-real) eye() helper call
    # in an explicit `(eye(...) /= 0)` whenever dtype=bool/logical is
    # requested.
    src = tmp_path / "xeye_dtype_bool.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "if __name__ == \"__main__\":",
                "    print(np.eye(3, dtype=bool))",
                "    print(~np.eye(3, dtype=bool))",
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


def test_xp2f_tuple_return_element_from_callback_call_defaults_to_real(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # maths/numerical_analysis/newton_raphson.py: a local function
    # returning a tuple whose ONLY evidence for one element's kind came
    # from a callback call (`error = abs(f(a))`, then `return a,
    # error`) left that element with no determined kind at all -- none
    # of the kind-inference helpers used for a tuple-return element
    # have any visibility into which of the function's own parameters
    # are callbacks. The caller's own unpacked variable (`err` in
    # `root, err = newton_raphson(...)`) was then never declared at
    # all, "has no IMPLICIT type". Fixed by defaulting to real when an
    # unresolved right-hand side calls one of the function's own
    # parameters, matching the convention every untyped scalar
    # callback interface this codebase emits already uses.
    src = tmp_path / "xtuple_return_from_callback.py"
    src.write_text(
        "\n".join(
            [
                "def root_and_residual(f, x0):",
                "    x = x0",
                "    for _ in range(50):",
                "        residual = abs(f(x))",
                "        if residual < 1e-9:",
                "            return x, residual",
                "        x = x - f(x) / 2.0",
                "    return x, residual",
                "",
                "",
                "def g(x):",
                "    return x - 3.0",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    root, err = root_and_residual(g, 0.0)",
                "    print(root, err)",
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

def test_xp2f_large_int_pow_inside_local_function_does_not_overflow_int32(tmp_path: Path) -> None:
    # Real bug found mining TheAlgorithms/Python's own
    # physics/relativistic_velocity_summation.py: a module-level integer
    # constant (c = 299792458, the speed of light) squared via c**2
    # inside a local function's own expression exceeds Fortran's default
    # 4-byte INTEGER range (~2.1e9) even though it fits comfortably in
    # int64, and even though Python's own arbitrary-precision int handles
    # it trivially -- a hard gfortran compile-time error ("Result of
    # exponentiation ... exceeds the range of INTEGER(4)"). Fixed by
    # detecting a provably-overflowing INT**INT at codegen time and
    # widening the base via int(base, kind=8); a companion fix lets a
    # local function's own scope-isolated translator (which deliberately
    # has an empty params dict) still recognize a module-level integer
    # constant's own value for this overflow check.
    src = tmp_path / "xlarge_int_pow.py"
    src.write_text(
        "\n".join(
            [
                "c = 299792458",
                "",
                "",
                "def relativistic_velocity_summation(object_velocity, frame_velocity):",
                "    numerator = object_velocity + frame_velocity",
                "    denominator = 1 + object_velocity * frame_velocity / c**2",
                "    return numerator / denominator",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    print(relativistic_velocity_summation(200000000.0, 200000000.0))",
                "    print(relativistic_velocity_summation(299792458.0, 100000000.0))",
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


def test_xp2f_toplevel_int_const_pow_overflow_used_inline_in_real_expr(tmp_path: Path) -> None:
    # Companion bug to the local-function case above: a module-level
    # integer constant squared directly inside a top-level real-valued
    # expression (1.0 / c**2) hit the same int32 overflow at Fortran
    # compile time. Also exercises const_int_expr_to_fortran's own
    # overflow check, which now declines to constant-fold c**2 into a
    # Fortran `integer, parameter ::` initializer (which would itself
    # fail to compile), falling through to the fixed runtime codegen
    # path instead.
    src = tmp_path / "xtoplevel_const_pow_overflow.py"
    src.write_text(
        "\n".join(
            [
                "c = 299792458",
                "",
                "if __name__ == \"__main__\":",
                "    print(1.0 / c**2)",
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
