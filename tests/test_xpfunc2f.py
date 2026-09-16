from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import xpfunc2f

XPFUNC2F_PATH = REPO_ROOT / "xpfunc2f.py"
XPRIME_FUNC_PATH = REPO_ROOT / "xprime_func.py"
XAR_ACF_PATH = REPO_ROOT / "examples" / "xar_acf.py"
XFILTER_BOUNDS_PATH = REPO_ROOT / "examples" / "xfilter_bounds.py"
XPARTITION_BOUNDS_PATH = REPO_ROOT / "examples" / "xpartition_bounds.py"
XBRENTQ_PATH = REPO_ROOT / "examples" / "xbrentq.py"
XCHOICE_TUPLE_REPRO_PATH = REPO_ROOT / "examples" / "xchoice_tuple_repro.py"
XFSOLVE_PATH = REPO_ROOT / "examples" / "xfsolve.py"
XFSOLVE_LIST_RETURN_PATH = REPO_ROOT / "examples" / "xfsolve_list_return.py"
XLEAST_SQUARES_PATH = REPO_ROOT / "examples" / "xleast_squares.py"
XASA183_INFERRED_PATH = REPO_ROOT / "examples" / "xasa183_inferred.py"
XBS_VEC_PATH = REPO_ROOT / "examples" / "xbs_vec.py"
XOPTIONS_PDE_PATH = REPO_ROOT / "examples" / "xoptions_pde.py"
XSIM_FIT_NAGARCH_T_PATH = REPO_ROOT / "examples" / "xsim_fit_nagarch_t.py"
XALIAS_REPRO_PATH = REPO_ROOT / "examples" / "xalias_repro.py"
XARMA_AIC_FIT_PATH = REPO_ROOT / "examples" / "xarma_aic_fit.py"
XMIX_PATH = REPO_ROOT / "examples" / "xmix.py"
XARMA_NAGARCH_FIT_PATH = REPO_ROOT / "examples" / "xarma_nagarch_fit.py"


def _run_xpfunc2f(args, cwd) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(XPFUNC2F_PATH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_xpfunc2f_inlines_complex_eigvals_helpers(tmp_path: Path) -> None:
    # A generic eigvals must bring in both overloads and the entire DCEIGV
    # dependency chain, including its intrinsic imports, without new files.
    source = """module eigen_test
use, intrinsic :: iso_fortran_env, only: real64
use python_mod, only: linalg_eigvals
implicit none
integer, parameter :: dp = real64
contains
function spectral_abscissa(a) result(r)
complex(dp), intent(in) :: a(:,:)
real(dp) :: r
r = maxval(real(linalg_eigvals(a), dp))
end function spectral_abscissa
end module eigen_test
"""
    inlined, unresolved = xpfunc2f.inline_python_mod_helpers(source)
    assert unresolved == []
    assert "use python_mod" not in inlined.lower()
    for name in ("linalg_eigvals_real", "linalg_eigvals_complex", "dceigv",
                 "dcbal", "dcorth", "dcmqr2", "dcbabk", "dcsqrt", "dcpabs"):
        assert name in inlined.lower()
    src = tmp_path / "eigen_test.f90"
    src.write_text(inlined, encoding="utf-8")
    proc = subprocess.run(["gfortran", "-fcheck=all", "-c", str(src)],
                          cwd=tmp_path, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_xpfunc2f_scalar_only_happy_path(tmp_path: Path) -> None:
    # The original, already-established scalar-only case: count_primes
    # (tuple return of two ints) + its one dependency is_prime -- must
    # keep working unaffected by the later array-support additions.
    proc = _run_xpfunc2f(
        [str(XPRIME_FUNC_PATH), "count_primes", "--out-dir", str(tmp_path), "--verify", "--verify-args", "(1000,)"],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Extract: PASS (count_primes + 1 dependency function(s): is_prime)" in proc.stdout
    assert "F2PY Build: PASS" in proc.stdout
    assert "Verify: MATCH (python=(168, 997) fortran=(168, 997))" in proc.stdout


def test_xpfunc2f_bridges_array_argument_and_array_result(tmp_path: Path) -> None:
    # User-reported real case: acf(x, nacf) from examples/xar_acf.py --
    # a rank-1 array argument (assumed-shape `x(:)`) AND a rank-1
    # allocatable array result (`np.array([... for k in range(1, nacf +
    # 1)])`, size = nacf, a simple function of the target's own
    # argument) -- previously rejected outright by check_f2py_compatible
    # ("has an array-shaped dummy argument or result"). Now bridged via
    # rewrite_target_for_f2py (assumed-shape -> explicit-shape with a
    # synthesized, f2py-auto-inferred size argument; allocatable function
    # result -> explicit-shape subroutine intent(out), size expression
    # symbolically simplified from xp2f.py's own arange_int-range-length
    # idiom), a generated `.f2py_f2cmap` file (the confirmed fix for
    # f2py's own wrapper otherwise silently mis-resolving this project's
    # `dp = real64` kind parameter to single precision for an array), and
    # inline_python_mod_helpers (acf calls python_mod's mean_1d --
    # inlined directly into the trimmed module rather than compiled/
    # linked as a separate object, since f2py's own Fortran cracker can't
    # parse either python.f90's full public surface or lapack_d.f90 at
    # all on this toolchain).
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0, 2.0]
    proc = _run_xpfunc2f(
        [
            str(XAR_ACF_PATH),
            "acf",
            "--out-dir",
            str(tmp_path),
            "--verify",
            "--verify-args",
            f"({x!r}, 4)",
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "has a rank-1 array argument/result" in proc.stdout
    assert "F2PY Build: PASS" in proc.stdout
    assert "Verify: MATCH" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "acf_f.f90").read_text(encoding="utf-8")
    assert "pure subroutine acf(" in out_f90, out_f90
    assert "allocatable :: lc_res_1" not in out_f90, out_f90
    assert "use python_mod" not in out_f90, out_f90
    assert "function mean_1d" in out_f90, out_f90


def test_xpfunc2f_run_both_matches_for_array_target(tmp_path: Path) -> None:
    # Companion end-to-end test: --run-both patches ONLY acf's own call
    # site into the real xar_acf.py script (its own dependency-closure
    # RNG-driven driver code stays ordinary Python on both sides), so the
    # comparison is a pure function-of-its-own-inputs check -- MATCH is
    # expected exactly (not just "close"), unlike a script whose own
    # output also depends on independent Python/Fortran RNG streams.
    proc = _run_xpfunc2f([str(XAR_ACF_PATH), "acf", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run (python): PASS" in proc.stdout
    assert "Run (fortran-backed): PASS" in proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout


def test_xpfunc2f_rejects_data_dependent_array_result_size(tmp_path: Path) -> None:
    # This particular result has length max(n, 0), but the generated
    # append accumulator uses dynamic allocation. Until that representation
    # is supported, reject it at extraction rather than treating its initial
    # zero-length allocation as the final result size.
    src = tmp_path / "xmakerange.py"
    src.write_text(
        "\n".join(
            [
                "def make_range(n):",
                "    out = []",
                "    for i in range(n):",
                "        out.append(i * 2)",
                "    return out",
                "",
                "r = make_range(5)",
                "print(r)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run_xpfunc2f([str(src), "make_range", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Extract: FAIL" in proc.stdout, proc.stdout + proc.stderr
    assert "dynamic allocation" in proc.stdout, proc.stdout + proc.stderr
    assert "F2PY Build:" not in proc.stdout, proc.stdout + proc.stderr


@pytest.mark.parametrize("body, message", [
    (["allocate(y(0))", "allocate(y(n))"], "multiple allocations"),
    (["allocate(y(0), work(n))", "allocate(y(n))"], "multiple allocations"),
    (["if (.not. ALLOCATED(Y)) then", "allocate(y(n))", "end if"],
     "dynamic allocation"),
])
def test_rewrite_target_for_f2py_rejects_dynamic_result_storage(body, message) -> None:
    lines = [
        "function f(n) result(y)",
        "integer, intent(in) :: n",
        "real(kind=dp), allocatable :: y(:)",
        "real(kind=dp), allocatable :: work(:)",
        *body,
        "end function f",
    ]
    original = lines.copy()
    with pytest.raises(xpfunc2f.UnsupportedFunction, match=message):
        xpfunc2f.rewrite_target_for_f2py(lines, 0, len(lines) - 1, "f")
    assert lines == original


def test_xpfunc2f_rejects_rank2_array_argument(tmp_path: Path) -> None:
    src = tmp_path / "xmatsum.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def row_sums(a):",
                "    return np.array([np.sum(a[i, :]) for i in range(a.shape[0])])",
                "",
                "m = np.array([[1.0, 2.0], [3.0, 4.0]])",
                "print(row_sums(m))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run_xpfunc2f([str(src), "row_sums", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Extract: FAIL" in proc.stdout, proc.stdout + proc.stderr


def test_rewrite_target_for_f2py_converts_scalar_function_to_subroutine() -> None:
    # A scalar-result function (no array argument/result at all: had_array
    # stays False) is STILL converted into a subroutine -- f2py generates
    # its own separate scalar-function wrapper file for any bridged
    # FUNCTION (never a subroutine), and that generated wrapper
    # references this project's `dp` kind parameter without importing it
    # whenever a real(kind=dp) argument or result is involved ("has no
    # IMPLICIT type") -- a real f2py bug confirmed with xbrentq.py's own
    # `f(x) = x ** 2 - 2.0`, no array anywhere. This test uses an
    # integer-only function precisely because it does NOT need the fix
    # (no `dp` involved) -- confirming the conversion happens
    # unconditionally, for any scalar result type, not just real/complex.
    lines = [
        "pure function double_it(x) result(y)",
        "   integer, intent(in) :: x",
        "   integer :: y",
        "   y = x * 2",
        "end function double_it",
    ]
    new_lines, had_array = xpfunc2f.rewrite_target_for_f2py(lines, 0, len(lines) - 1, "double_it")
    assert had_array is False
    assert new_lines == [
        "pure subroutine double_it(x, y)",
        "   integer, intent(in) :: x",
        "   integer, intent(out) :: y",
        "   y = x * 2",
        "end subroutine double_it",
    ]


def test_rewrite_target_for_f2py_handles_already_subroutine_array_output() -> None:
    # Regression test for a real bug (found via examples/xchoice_tuple_repro.py's
    # backbin_rc): a target that's ALREADY a subroutine (xp2f.py's own
    # tuple-return convention), needing only its array ARGUMENT rewritten
    # (assumed-shape -> explicit-shape), also has an allocatable rank-1
    # array among its own intent(out) dummies (`y = x`, a whole-array
    # copy straight from the now-explicit-shape argument, no `allocate()`
    # statement at all -- Fortran auto-allocates on assignment). Two bugs
    # this exercises together: (1) the array-argument loop used to treat
    # THAT allocatable intent(out) dummy as if it were an assumed-shape
    # INPUT needing a synthesized size too, corrupting it into an
    # ILLEGAL `allocatable ... y(n_2)` (allocatable arrays must stay
    # deferred-shape) -- confirmed via gfortran's own rejection ("must
    # have a deferred shape or assumed rank"); (2) separately, the
    # signature-rebuild step used to hardcode "function" whenever no
    # function-result conversion happened, producing a mismatched
    # `function bump(...)` paired with the untouched `end subroutine
    # bump` end line. Both must now come out right: `y` becomes a plain
    # explicit-shape `intent(out)` dummy (reusing `x`'s own synthesized
    # size, since it's a whole-array copy of `x`), and the signature
    # stays a subroutine throughout.
    lines = [
        "subroutine bump(n, x, y)",
        "   integer, intent(in) :: n",
        "   integer, intent(inout) :: x(:)",
        "   integer, allocatable, intent(out) :: y(:)",
        "   x(1) = x(1) + n",
        "   y = x",
        "end subroutine bump",
    ]
    new_lines, had_array = xpfunc2f.rewrite_target_for_f2py(lines, 0, len(lines) - 1, "bump")
    assert had_array is True
    assert new_lines == [
        "subroutine bump(n, x, y, n_1)",
        "   integer, intent(in) :: n",
        "   integer, intent(inout) :: x(n_1)",
        "   integer, intent(in) :: n_1",
        "   integer, intent(out) :: y(n_1)",
        "   x(1) = x(1) + n",
        "   y = x",
        "end subroutine bump",
    ]


def test_infer_rank1_size_elementwise_arithmetic_and_parameter_arrays() -> None:
    # Regression test for the array_result_no_allocate_recognized bucket
    # xpfunc2f_batch.py --compile surfaced: an array result with NO
    # `allocate(...)` at all, built purely from elementwise arithmetic
    # over the target's own array argument and two local PARAMETER
    # (compile-time-constant) arrays -- examples/xleast_squares.py's own
    # `resid(p) = p(1) * x + p(2) - y`, where `x`/`y` are each a 5-
    # element literal array constructor. Exercises: a numeric-literal
    # array-constructor part (`_SCALAR`, contributing exactly 1 each);
    # binary elementwise ops combining a known-size array with a scalar
    # subscript access (`p(1)`, `p(2)` -- single-element accesses of a
    # known array, provably scalar); and seeding a PARAMETER array's own
    # size from its own initializer.
    size_of = {"p": "n_1"}
    scalar_names: set[str] = set()
    assert (
        xpfunc2f._infer_rank1_size("[0.0_dp, 1.0_dp, 2.0_dp, 3.0_dp, 4.0_dp]", size_of, scalar_names)
        == "1 + 1 + 1 + 1 + 1"
    )
    size_of["x"] = "1 + 1 + 1 + 1 + 1"
    size_of["y"] = "1 + 1 + 1 + 1 + 1"
    assert xpfunc2f._infer_rank1_size("p(1) * x + p(2) - y", size_of, scalar_names) == size_of["x"]


def test_infer_rank1_size_array_constructor_of_compound_scalar_parts() -> None:
    # Regression test for examples/xfsolve_list_return.py's own
    # `equations(x) = [(x(1) ** 2 + x(2) ** 2 - 4.0_dp), (x(1) - x(2))]`
    # -- each part is a parenthesized COMPOUND scalar expression (not
    # just a bare literal or bare name), needing the `_SCALAR` sentinel
    # (vs. plain None for "unresolvable") to tell "definitely scalar,
    # contributes 1" apart from "might itself be an unresolvable array,
    # bail" without guessing.
    size_of = {"x": "n_1"}
    scalar_names: set[str] = set()
    assert (
        xpfunc2f._infer_rank1_size(
            "[(x(1) ** 2 + x(2) ** 2 - 4.0_dp), (x(1) - x(2))]", size_of, scalar_names
        )
        == "1 + 1"
    )


def test_infer_rank1_size_recognized_python_mod_helpers() -> None:
    # Regression test for examples/xarma_aic_fit.py's own
    # `simulate_arma`: `eps = rnorm(n + burnin)` (python.f90's rnorm1,
    # length = its own argument's value) feeding `xfull =
    # lfilter_real(ma_poly, ar_poly, eps)` (same length as its 3rd
    # argument) feeding a final slice `func_res = xfull(burnin + 1:
    # size(xfull))` -- the true length simplifies to plain `n`.
    size_of: dict[str, str] = {}
    scalar_names: set[str] = set()
    assert xpfunc2f._infer_rank1_size("rnorm(n + burnin)", size_of, scalar_names) == "n + burnin"
    size_of["eps"] = "n + burnin"
    assert xpfunc2f._infer_rank1_size("lfilter_real(ma_poly, ar_poly, eps)", size_of, scalar_names) == "n + burnin"
    size_of["xfull"] = "n + burnin"
    assert (
        xpfunc2f._infer_rank1_size("xfull(burnin + 1:size(xfull))", size_of, scalar_names)
        == "((n + burnin)) - (burnin + 1) + 1"
    )


def test_rewrite_target_for_f2py_handles_allocate_with_trailing_keyword_arg() -> None:
    # Regression test: `allocate(NAME(SIZE), source=...)` -- a trailing
    # keyword argument after the array's own size spec -- used to defeat
    # the single greedy regex that originally looked for `allocate(NAME
    # (SIZE))` with nothing else inside the parens at all (examples/
    # xequicorr_turnover.py's own `allocate(turnover(n), source=0.0_dp)`).
    lines = [
        "function f(n) result(y)",
        "   integer, intent(in) :: n",
        "   real(kind=dp), allocatable :: y(:)",
        "   allocate(y(n), source=0.0_dp)",
        "   y(1) = 1.0_dp",
        "end function f",
    ]
    new_lines, had_array = xpfunc2f.rewrite_target_for_f2py(lines, 0, len(lines) - 1, "f")
    assert had_array is True
    assert "   real(kind=dp), intent(out) :: y(n)" in new_lines
    assert not any("allocate(" in ln for ln in new_lines)


def test_xpfunc2f_bridges_array_result_via_elementwise_arithmetic(tmp_path: Path) -> None:
    # End-to-end companion to the unit tests above: examples/
    # xleast_squares.py's `resid(p)` has NO `allocate(...)` at all --
    # its array result comes purely from elementwise arithmetic over `p`
    # and two local PARAMETER arrays.
    proc = _run_xpfunc2f([str(XLEAST_SQUARES_PATH), "resid", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout


def test_xpfunc2f_bridges_array_constructor_of_compound_scalars(tmp_path: Path) -> None:
    # End-to-end companion: examples/xfsolve_list_return.py's
    # `equations(x) = [(x(1) ** 2 + x(2) ** 2 - 4.0_dp), (x(1) - x(2))]`
    # -- no allocate() at all, an array constructor of compound scalar
    # expressions.
    proc = _run_xpfunc2f(
        [str(XFSOLVE_LIST_RETURN_PATH), "equations", "--out-dir", str(tmp_path), "--run-both"], tmp_path
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout


def test_xpfunc2f_bridges_allocate_with_trailing_keyword_arg(tmp_path: Path) -> None:
    # End-to-end companion: examples/xfsolve.py's `equations(x)` has
    # `allocate(y(2), source=0.0_dp)` -- a trailing keyword argument
    # after the array's own literal size.
    proc = _run_xpfunc2f([str(XFSOLVE_PATH), "equations", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout


def test_build_trimmed_module_filters_multiline_public_statement() -> None:
    # Regression test for examples/xasa183_inferred.py's own `timestamp`
    # target (and 3 other Burkardt-derived files sharing this shape):
    # build_trimmed_module's own `public ::` filtering used to look at
    # each PHYSICAL header line in isolation, so a `public ::` statement
    # long enough to `&`-continue across several lines only had its
    # FIRST line's names filtered -- the continuation line's own names
    # (here, unneeded_helper) survived VERBATIM into the trimmed
    # module's own public list, which gfortran then rejects outright
    # ("has no IMPLICIT type", since `public` requires the entity to
    # actually exist).
    header = [
        "module m",
        "   use, intrinsic :: iso_fortran_env, only: real64",
        "   implicit none",
        "   private",
        "   integer, parameter :: dp = real64",
        "   public :: dp, keep_me, &",
        "      & unneeded_helper",
    ]
    lines = header + [
        "contains",
        "",
        "pure function keep_me(x) result(y)",
        "   real(kind=dp), intent(in) :: x",
        "   real(kind=dp) :: y",
        "   y = x",
        "end function keep_me",
        "",
        "pure function unneeded_helper(x) result(y)",
        "   real(kind=dp), intent(in) :: x",
        "   real(kind=dp) :: y",
        "   y = x",
        "end function unneeded_helper",
        "",
        "end module m",
    ]
    procedures = {"keep_me": (9, 13), "unneeded_helper": (15, 19)}
    new_text = xpfunc2f.build_trimmed_module("m", header, lines, procedures, {"keep_me"})
    assert "unneeded_helper" not in new_text
    assert "public :: dp, keep_me" in new_text


def test_inline_python_mod_helpers_resolves_generic_interface() -> None:
    # Regression test for examples/xbs.py's own `black_scholes` (and 3
    # other files sharing this shape): python.f90's own `optval` is a
    # GENERIC interface (`interface optval / module procedure
    # optval_int, optval_real, optval_logical, optval_char / end
    # interface`), never itself a concrete procedure -- so a plain
    # `"optval" in py_procs` lookup (parse_module deliberately skips
    # interface bodies, since an interface isn't a procedure) always
    # failed, leaving `optval` unresolved even though it's an ordinary,
    # simple, self-contained helper like mean_1d. Fixed by also
    # resolving a requested name through python.f90's own generic
    # interface table, inlining ALL its concrete overloads PLUS the
    # `interface optval ... end interface` block itself (into the
    # specification section, before `contains` -- never the executable
    # body, unlike an ordinary procedure) so the caller's own
    # `optval(...)` call site still has a generic name to resolve
    # through.
    text = xpfunc2f.PYTHON_MOD_PATH.read_text(encoding="utf-8", errors="ignore")
    _, header, _, procs = xpfunc2f.parse_module(text)
    assert "optval" not in procs
    interfaces = xpfunc2f._find_python_mod_interfaces(header)
    assert "optval" in interfaces
    assert set(interfaces["optval"][2]) == {
        "optval_int", "optval_real", "optval_logical", "optval_char", "optval_complex",
    }

    trimmed = "\n".join(
        [
            "module m",
            "   use python_mod, only: optval",
            "   implicit none",
            "contains",
            "   pure function f(x) result(y)",
            "      real(kind=8), intent(in), optional :: x",
            "      real(kind=8) :: y",
            "      y = optval(x, 0.0d0)",
            "   end function f",
            "end module m",
            "",
        ]
    )
    new_text, unresolved = xpfunc2f.inline_python_mod_helpers(trimmed)
    assert unresolved == []
    assert "use python_mod" not in new_text
    assert "interface optval" in new_text
    assert "end interface optval" in new_text
    assert "function optval_real" in new_text
    # The interface block belongs in the SPECIFICATION section (before
    # `contains`), never inside it, alongside the concrete overloads.
    assert new_text.index("interface optval") < new_text.index("contains")
    assert new_text.index("contains") < new_text.index("function optval_real")


def test_proc_start_re_matches_nested_paren_type_spec() -> None:
    # Regression test: python.f90's own `to_lower` is declared
    # `pure character(len=len(s)) function to_lower(s)` -- a dynamic-
    # length character function whose own type spec has a NESTED paren
    # (`len(s)` inside `(len=len(s))`). The original `_FUNC_TYPE_PREFIX_RE`
    # only allowed `[^()]*` inside the type spec's own parens (no nesting
    # at all), so PROC_START_RE failed to match this line entirely,
    # leaving `to_lower` invisible to parse_module's own procedure table.
    m = xpfunc2f.PROC_START_RE.match("pure character(len=len(s)) function to_lower(s)")
    assert m is not None
    assert m.group(2) == "to_lower"

    text = xpfunc2f.PYTHON_MOD_PATH.read_text(encoding="utf-8", errors="ignore")
    _, _, _, procs = xpfunc2f.parse_module(text)
    assert "to_lower" in procs


def test_generate_wrapper_lowercases_f2py_keyword_names() -> None:
    # Regression test: f2py always lowercases a Fortran dummy's own name
    # for its generated Python-facing keyword (Fortran identifiers are
    # case-insensitive, so f2py canonicalizes to lowercase regardless of
    # how the Fortran source spelled it) -- confirmed via examples/
    # xbs_vec.py's own `black_scholes(S, K, T, r, sigma, option)`: a
    # keyword call using the ORIGINAL case (`S=S`) raised "missing
    # required argument 's'". The wrapper's own Python-facing signature
    # must still use the ORIGINAL case (a drop-in replacement has to
    # accept calls the same way the original Python function did) --
    # only the f2py-side keyword needs lowercasing.
    src = xpfunc2f.generate_wrapper("m", "ext", "f", ["S", "K"])
    assert "def f(S, K):" in src
    assert "ext.m.f(s=S, k=K)" in src


def test_build_trimmed_module_keeps_dependencies_private() -> None:
    # Regression test for the array_in_dependency blocker (11 files):
    # a DEPENDENCY's own array-shaped (or derived-type) signature used
    # to be rejected outright, since f2py's own Fortran cracker crawls a
    # module's ENTIRE public interface and hits a real bug trying to
    # wrap one. Confirmed empirically (a minimal, hand-built repro) that
    # simply keeping a dependency PRIVATE sidesteps this completely --
    # f2py never even attempts to wrap it -- and an ordinary internal
    # Fortran-to-Fortran call to it (array argument, allocatable result,
    # even a derived type) needs no f2py-facing rewrite at all. This
    # also exercises unwrap_block_constructs now being applied to every
    # dependency's own body, not just the target's -- a dependency's own
    # `block` construct (xp2f.py's own loop-counter-scoping idiom) badly
    # confuses f2py's own parser, corrupting everything AFTER it in the
    # same file (confirmed via examples/xequicorr_bands.py's own
    # `equicorr_cov`).
    header = [
        "module m",
        "   use, intrinsic :: iso_fortran_env, only: real64",
        "   implicit none",
        "   private",
        "   integer, parameter :: dp = real64",
        "   public :: dp, target_proc",
    ]
    lines = header + [
        "contains",
        "",
        "pure function dep(x) result(y)",
        "   real(kind=dp), intent(in) :: x(:)",
        "   real(kind=dp), allocatable :: y(:,:)",
        "   allocate(y(size(x), 1))",
        "   block",
        "      integer :: i_scope",
        "      do i_scope = 1, size(x)",
        "         y(i_scope, 1) = x(i_scope)",
        "      end do",
        "   end block",
        "end function dep",
        "",
        "pure subroutine target_proc(n, s)",
        "   integer, intent(in) :: n",
        "   real(kind=dp), intent(out) :: s",
        "   s = n",
        "end subroutine target_proc",
        "",
        "end module m",
    ]
    procedures = {"dep": (8, 18), "target_proc": (20, 24)}
    new_text = xpfunc2f.build_trimmed_module("m", header, lines, procedures, {"dep", "target_proc"})
    assert "public :: dp, target_proc" in new_text
    assert "dep" not in new_text.split("public ::")[1].splitlines()[0]
    assert "block" not in new_text
    assert "integer :: i_scope" in new_text  # hoisted, not lost


def test_split_multi_name_decls() -> None:
    # Regression test for a real bug (examples/xsim_fit_nagarch.py's own
    # `simulate_nagarch`, whose `r`/`h` outputs share one `real(kind=dp),
    # allocatable, intent(out) :: r(:), h(:)` line): a per-name rewrite
    # (see _convert_array_result) that modifies a matched declaration
    # line AS A WHOLE is only safe when it declares exactly one name --
    # rewriting `r`'s own shape used to collaterally strip the SHARED
    # `allocatable` attribute off the whole line, silently leaving `h`
    # unresolved (worse, no longer even recognized as needing this
    # rewrite, since its own "is this allocatable?" check then failed
    # too).
    lines = [
        "subroutine f(n, r, h)",
        "   integer, intent(in) :: n",
        "   real(kind=dp), allocatable, intent(out) :: r(:), h(:)",
        "end subroutine f",
    ]
    new_lines = xpfunc2f._split_multi_name_decls(lines)
    assert new_lines == [
        "subroutine f(n, r, h)",
        "   integer, intent(in) :: n",
        "   real(kind=dp), allocatable, intent(out) :: r(:)",
        "   real(kind=dp), allocatable, intent(out) :: h(:)",
        "end subroutine f",
    ]
    # A single-name line is left completely untouched.
    assert xpfunc2f._split_multi_name_decls(["integer, intent(in) :: n"]) == ["integer, intent(in) :: n"]

    # Regression test for a second, separate bug this same normalization
    # introduced: an ordinary ASSIGNMENT statement whose RHS is a Fortran
    # array constructor with an explicit type-spec (`[real(kind=dp) ::
    # part1, part2]`) also CONTAINS a `::` token -- but nested inside the
    # brackets, not a genuine declaration separator at all. Naively
    # splitting at the first `::` anywhere treated this as a two-name
    # declaration and split it at the constructor's own top-level comma,
    # producing two broken, unbalanced lines (confirmed via examples/
    # xarma_aic_fit.py's own `simulate_arma`: "syntax error in array
    # constructor"). Must be left completely untouched.
    assign_line = "   ar_poly = [real(kind=dp) :: [1.0_dp], -ar]"
    assert xpfunc2f._split_multi_name_decls([assign_line]) == [assign_line]


def test_find_top_level_double_colon() -> None:
    assert xpfunc2f._find_top_level_double_colon("integer, intent(in) :: n") is not None
    assert xpfunc2f._find_top_level_double_colon("ar_poly = [real(kind=dp) :: [1.0_dp], -ar]") is None


def test_strip_unused_dataframe_use() -> None:
    # Regression test: xp2f.py emits a `use dataframe_str_index_mod,
    # only: ...` header line whenever the SCRIPT AS A WHOLE uses a
    # pandas DataFrame anywhere -- not just within the target's own
    # dependency closure -- so it can be left orphaned once trimmed down
    # to a target that doesn't touch pandas at all, needing a companion
    # module never compiled/linked into this standalone f2py build
    # (confirmed via examples/xmix.py's own `simulate_normal_mixture`:
    # gfortran "Cannot open module file 'dataframe_str_index_mod.mod'").
    unused = "\n".join(
        [
            "module m",
            "   use dataframe_str_index_mod, only: DataFrame_str_index, nrow, ncol, "
            "operator(+), operator(-), operator(*), operator(/), abs_str",
            "   implicit none",
            "contains",
            "   pure function f(x) result(y)",
            "      real(kind=8), intent(in) :: x",
            "      real(kind=8) :: y",
            "      y = x + 1.0d0",
            "   end function f",
            "end module m",
            "",
        ]
    )
    new_text = xpfunc2f.strip_unused_dataframe_use(unused)
    assert "use dataframe_str_index_mod" not in new_text
    assert "pure function f(x) result(y)" in new_text  # everything else untouched

    # A dependency that genuinely still uses one of the imported PLAIN
    # names (nrow) keeps its own `use` line intact.
    still_used = unused.replace("y = x + 1.0d0", "y = x + real(nrow(x), kind=8)")
    new_text2 = xpfunc2f.strip_unused_dataframe_use(still_used)
    assert "use dataframe_str_index_mod" in new_text2


def test_rewrite_target_for_f2py_handles_multiline_signature_and_shared_allocate() -> None:
    # Regression test combining two real bugs found together (examples/
    # xsim_fit_nagarch.py's own `simulate_nagarch`): (1) SIG_RE's own
    # match against target_lines[0] ALONE used to fail outright whenever
    # the signature itself `&`-continued across physical lines (silently
    # skipping the WHOLE rewrite, no error, so the target's own
    # unrewritten assumed-shape argument failed a LATER check instead,
    # with a confusing "not covered by rewrite_target_for_f2py's own
    # rewrites" message); (2) `r`/`h` are allocated TOGETHER in one
    # `allocate(r(n), h(n))` statement -- the array-result size finder
    # originally only recognized `name` as the FIRST thing allocated.
    lines = [
        "subroutine simulate_nagarch(n, mu, r, &",
        "   & h)",
        "   integer, intent(in) :: n",
        "   real(kind=dp), intent(in) :: mu",
        "   real(kind=dp), allocatable, intent(out) :: r(:), h(:)",
        "   allocate(r(n), h(n))",
        "   r(1) = mu",
        "   h(1) = mu",
        "end subroutine simulate_nagarch",
    ]
    new_lines, had_array = xpfunc2f.rewrite_target_for_f2py(lines, 0, len(lines) - 1, "simulate_nagarch")
    assert had_array is True
    assert "subroutine simulate_nagarch(n, mu, r, h)" in new_lines
    assert "   real(kind=dp), intent(out) :: r(n)" in new_lines
    assert "   real(kind=dp), intent(out) :: h(n)" in new_lines
    assert not any("allocatable" in ln.lower() for ln in new_lines)
    assert not any("allocate(" in ln for ln in new_lines)


def test_rewrite_target_for_f2py_resolves_size_through_local_dependency() -> None:
    # Regression test for the array_result_size_not_derivable blocker:
    # examples/xarma_nagarch_fit.py's own `simulate_arma_nagarch` derives
    # its own array result's size from `eps`, which comes from a call to
    # `simulate_nagarch_noise` -- a plain, LOCALLY-DEFINED function (not
    # a python.f90 builtin) with its own `allocate(eps(n))`, i.e. its
    # own length is simply its own first argument, `n`. Previously
    # rejected outright ("no ... known-helper expression"); now resolved
    # by passing `procedures` (parse_module's own name -> (start, end)
    # table) so a call to some OTHER locally-defined procedure can be
    # recursively derived too, then its own dummy names substituted for
    # the call site's own actual argument text (`n` -> `n + burnin`).
    lines = [
        "function simulate_nagarch_noise(n, omega) result(eps)",
        "   integer, intent(in) :: n",
        "   real(kind=dp), intent(in) :: omega",
        "   real(kind=dp), allocatable :: eps(:)",
        "   allocate(eps(n))",
        "   eps = omega",
        "end function simulate_nagarch_noise",
        "",
        "function simulate_arma_nagarch(n, burnin, omega) result(func_res)",
        "   integer, intent(in) :: n, burnin",
        "   real(kind=dp), intent(in) :: omega",
        "   real(kind=dp), allocatable :: func_res(:)",
        "   real(kind=dp), allocatable :: eps(:)",
        "   eps = simulate_nagarch_noise(n + burnin, omega)",
        "   func_res = eps",
        "end function simulate_arma_nagarch",
    ]
    procedures = {
        "simulate_nagarch_noise": (0, 6),
        "simulate_arma_nagarch": (8, 15),
    }
    start, end = procedures["simulate_arma_nagarch"]

    # Without `procedures`, still correctly rejected (previous, more
    # limited behavior -- unchanged for any existing caller that doesn't
    # pass it).
    with pytest.raises(xpfunc2f.UnsupportedFunction):
        xpfunc2f.rewrite_target_for_f2py(lines, start, end, "simulate_arma_nagarch")

    new_lines, had_array = xpfunc2f.rewrite_target_for_f2py(
        lines, start, end, "simulate_arma_nagarch", procedures
    )
    assert had_array is True
    assert "   real(kind=dp), intent(out) :: func_res((n + burnin))" in new_lines


def test_inline_python_mod_helpers_hoists_rng_replay_state() -> None:
    # Regression test: python.f90's own `rnorm` (a generic interface,
    # like `optval`) dispatches to `rnorm0`/`rnorm1`/etc., which read/
    # write private RNG-replay bookkeeping (`rng_replay_enabled`,
    # `rng_replay_bin_u`, ...) declared in python.f90's own
    # specification section, never as one of their own dummy arguments.
    # This function only ever copies a PROCEDURE's own body text, so
    # inlining `rnorm` without ALSO hoisting these state declarations
    # into the trimmed module's own specification section produced a
    # build failure ("has no IMPLICIT type") -- confirmed via examples/
    # xsim_fit_nagarch.py's own `simulate_nagarch`. Fixed by hoisting
    # every module-level state name any inlined helper's own transitive
    # closure touches, the same way a needed `interface` block already
    # is.
    #
    # `optval` exercises the OTHER side of this: it must NOT falsely
    # trigger hoisting the module-level `v` declaration (a real,
    # unrelated global) -- 3 of its 4 concrete overloads use `result(v)`
    # as their OWN local name, which shadows the module-level one.
    text = xpfunc2f.PYTHON_MOD_PATH.read_text(encoding="utf-8", errors="ignore")
    assert "rng_replay_enabled" in text

    trimmed = "\n".join(
        [
            "module m",
            "   use python_mod, only: rnorm, optval",
            "   implicit none",
            "contains",
            "   pure function f(x) result(y)",
            "      real(kind=8), intent(in), optional :: x",
            "      real(kind=8) :: y",
            "      y = optval(x, 0.0d0) + rnorm()",
            "   end function f",
            "end module m",
            "",
        ]
    )
    new_text, unresolved = xpfunc2f.inline_python_mod_helpers(trimmed)
    assert unresolved == []
    assert "use python_mod" not in new_text
    assert "interface optval" in new_text
    assert "interface rnorm" in new_text
    assert "rng_replay_enabled" in new_text
    assert "rng_replay_bin_u" in new_text
    # The module-level `v` declaration is NOT spuriously hoisted --
    # optval's own overloads' `result(v)` shadows it, so it's correctly
    # recognized as unrelated.
    assert not re.search(r"^\s*character\(len=:\), allocatable :: v\(:\)\s*$", new_text, re.MULTILINE)


def test_inline_python_mod_helpers_finds_type_prefixed_functions() -> None:
    # Regression test for the parse_module / PROC_START_RE widening this
    # feature needed: python.f90 (unlike xp2f.py's own generated code)
    # uses the `TYPE FUNCTION NAME(...)` style for at least one helper
    # (`pure real(kind=dp) function mean_1d(x)`) -- PROC_START_RE
    # originally only matched a bare `function NAME(...)`, so mean_1d
    # was silently absent from parse_module's own procedure table
    # (mean_1d not in procs), and inline_python_mod_helpers found nothing
    # to inline at all.
    text = xpfunc2f.PYTHON_MOD_PATH.read_text(encoding="utf-8", errors="ignore")
    _, _, _, procs = xpfunc2f.parse_module(text)
    assert "mean_1d" in procs
    assert "arange_int" in procs

    trimmed = "\n".join(
        [
            "module m",
            "   use python_mod, only: mean_1d",
            "   implicit none",
            "contains",
            "   pure function f(x) result(y)",
            "      real(kind=8), intent(in) :: x(:)",
            "      real(kind=8) :: y",
            "      y = mean_1d(x)",
            "   end function f",
            "end module m",
            "",
        ]
    )
    new_text, unresolved = xpfunc2f.inline_python_mod_helpers(trimmed)
    assert unresolved == []
    assert "use python_mod" not in new_text
    assert "function mean_1d" in new_text


def test_xpfunc2f_bridges_data_dependent_filter_result(tmp_path: Path) -> None:
    # User-requested case: values_within_bounds(x, lower, upper) filters
    # x down to the entries inside [lower, upper] -- xp2f.py's own
    # growable-accumulator idiom (capacity-doubling local array, sliced
    # `func_res = out_(1:n_out)` at the end), a genuinely data-dependent
    # result length, NOT a simple function of the arguments the way
    # acf's is. Bridged via try_build_bridge_for_target/
    # build_bridge_procedure: a NEW subroutine, kept alongside the
    # ORIGINAL (unmodified) function, over-allocates to len(x) (an
    # accumulator can never emit more elements than it read) and returns
    # the true count for the Python wrapper to trim by.
    #
    # Getting this to build surfaced two further, real bugs (beyond the
    # bridge-generation logic itself):
    # 1. f2py's own Fortran cracker badly mis-parses xp2f.py's `block
    #    ... end block` scoping construct (used for the accumulator
    #    loop's own counter variable), corrupting the symbol name it
    #    generates for a LATER, unrelated procedure in the same file --
    #    fixed by unwrap_block_constructs, hoisting the block's own
    #    local declaration out and deleting the block/end block lines,
    #    applied ONLY to the copy of the original kept alongside the
    #    bridge (never touching xp2f.py's own translation).
    # 2. Certain generated Fortran (ieee_arithmetic usage, from this
    #    project's own NaN-safe comparison codegen) needs gfortran's own
    #    win32-threads GTHR runtime stubs at link time, which f2py's
    #    meson/clang/lld pipeline doesn't pull in automatically the way
    #    gfortran's own native linker invocation does -- fixed by adding
    #    `-L<libgcc dir> -lgcc` to the f2py build whenever arrays are
    #    involved.
    proc = _run_xpfunc2f(
        [
            str(XFILTER_BOUNDS_PATH),
            "values_within_bounds",
            "--out-dir",
            str(tmp_path),
            "--verify",
            "--verify-args",
            "([-3.5, -1.0, 0.0, 0.5, 2.2, 4.9, 5.0, 7.1, 10.0], -1.0, 5.0)",
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "bridged via a generated 'values_within_bounds_bridge'" in proc.stdout
    assert "F2PY Build: PASS" in proc.stdout
    assert "Verify: MATCH" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "values_within_bounds_f.f90").read_text(encoding="utf-8")
    assert "pure subroutine values_within_bounds_bridge(" in out_f90, out_f90
    assert "block" not in out_f90.lower(), out_f90


def test_xpfunc2f_bridges_data_dependent_three_output_partition(tmp_path: Path) -> None:
    # Companion test for the multi-output case: partition_by_bounds
    # returns THREE independently data-dependent-length arrays (below/
    # within/above), each bounded by len(x) the same way -- xp2f.py's
    # own multi-value-return convention emits this as a SUBROUTINE with
    # three allocatable intent(out) array arguments (not a function with
    # one allocatable result), and its own signature/declaration lines
    # are long enough to wrap across several physical `&`-continued
    # lines -- a real bug surfaced here specifically: name/declaration
    # lookups that only checked one physical line at a time silently
    # missed the 2nd/3rd output names (no `::` on their own continuation
    # line), misclassifying them as scalar inputs instead of array
    # outputs. Fixed with _merge_continuations, applied before any of
    # try_build_bridge_for_target/build_bridge_procedure's own line-
    # based scanning.
    proc = _run_xpfunc2f(
        [
            str(XPARTITION_BOUNDS_PATH),
            "partition_by_bounds",
            "--out-dir",
            str(tmp_path),
            "--verify",
            "--verify-args",
            "([-3.5, -1.0, 0.0, 0.5, 2.2, 4.9, 5.0, 7.1, 10.0], -1.0, 5.0)",
        ],
        tmp_path,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "bridged via a generated 'partition_by_bounds_bridge'" in proc.stdout
    assert "F2PY Build: PASS" in proc.stdout
    assert "Verify: MATCH" in proc.stdout, proc.stdout


def test_unwrap_block_constructs_hoists_array_shaped_local() -> None:
    # Direct unit test for BLOCK_DECL_RE's own bug: a block-local
    # declared WITH a shape (`integer, allocatable :: tmp_out_2_50(:)`)
    # must be recognized and hoisted just like a bare scalar local
    # (`integer :: tmp_out_1_50`) -- the original regex only matched a
    # decl line ending immediately after the bare name, so the block-
    # decl-collecting loop stopped at the first (scalar) local and left
    # the array-shaped one stranded in the body once `block`/`end block`
    # were stripped.
    lines = [
        "subroutine other_call()",
        "   integer, parameter :: n = 3",
        "   integer :: n2",
        "   integer, allocatable :: choice(:)",
        "   n2 = -1",
        "   block",
        "      integer :: tmp_out_1_50",
        "      integer, allocatable :: tmp_out_2_50(:)",
        "      call backbin_rc(n, n2, choice, tmp_out_1_50, tmp_out_2_50)",
        "      n2 = tmp_out_1_50",
        "      choice = tmp_out_2_50",
        "   end block",
        "   print *, choice(1)",
        "end subroutine other_call",
    ]
    existing_names = {tok.lower() for ln in lines for tok in re.findall(r"[A-Za-z_]\w*", ln)}
    new_lines = xpfunc2f.unwrap_block_constructs(lines, existing_names)
    assert not any("block" in ln.lower() for ln in new_lines)
    # Both locals hoisted -- appearing in the DECLARATION section, before
    # the first executable statement (`n2 = -1`).
    exec_i = new_lines.index("   n2 = -1")
    decl_lines = new_lines[:exec_i]
    assert any("tmp_out_1_50" in ln for ln in decl_lines)
    assert any("allocatable" in ln and "tmp_out_2_50" in ln for ln in decl_lines)
    # Nothing resembling either temp's own declaration is left stranded
    # in the body (after the first executable statement).
    body_lines = new_lines[exec_i:]
    assert not any("::" in ln and "tmp_out_2_50" in ln for ln in body_lines)


def test_merge_continuations_joins_wrapped_declaration() -> None:
    # Direct unit test: a declaration listing several names, wrapped by
    # xp2f.py's own line-wrapping across 3 physical lines, becomes ONE
    # logical line -- so a per-line name/`::` search (this project's own
    # established style) can find EVERY name on it, not just the first.
    phys = [
        "   real(kind=dp), allocatable, intent(out) :: partition_by_bounds_out_1(:), &",
        "      & partition_by_bounds_out_2(:), &",
        "      & partition_by_bounds_out_3(:)",
    ]
    merged = xpfunc2f._merge_continuations(phys)
    assert len(merged) == 1
    assert merged[0].count("::") == 1
    for name in ("partition_by_bounds_out_1", "partition_by_bounds_out_2", "partition_by_bounds_out_3"):
        assert name in merged[0]


def test_xpfunc2f_run_both_prints_captured_stdout(tmp_path: Path) -> None:
    # User-reported real bug: --run-both/--time-both captured each run's
    # own stdout (xp2f.run_capture, tee=False) but never printed it --
    # only the "Run (...): PASS"/"Run-both: MATCH" status lines showed,
    # silently dropping the ORIGINAL script's own print() output (e.g.
    # xfilter_bounds.py's own "x: ...", "result: ...", "test passed"
    # lines). xp2f.py's own --run-both prints the captured text after
    # each "Run (...): PASS"; xpfunc2f.py's didn't. Fixed to match.
    proc = _run_xpfunc2f([str(XFILTER_BOUNDS_PATH), "values_within_bounds", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run-both: MATCH" in proc.stdout, proc.stdout
    # The script's own output must appear TWICE (once per run), not zero
    # times.
    assert proc.stdout.count("test passed") == 2, proc.stdout
    assert proc.stdout.count("result:") == 2, proc.stdout


def test_xpfunc2f_bridges_scalar_real_function_result(tmp_path: Path) -> None:
    # Found running xpfunc2f_batch.py --compile over examples/: a purely
    # scalar real(kind=dp)-returning function -- xbrentq.py's own
    # `def f(x): return x ** 2 - 2.0`, no array involved anywhere --
    # failed the f2py build with "Parameter 'dp' ... has not been
    # declared" and "Type mismatch ... passed REAL(4) to REAL(8)" inside
    # an f2py-AUTOGENERATED "<ext>-f2pywrappers2.f90" file. That file's
    # own `use xbrentq_proc_mod, only: f` imports ONLY the function name,
    # never `dp` -- a real f2py code-generation bug for ANY bridged
    # FUNCTION (never a subroutine) whose argument or result is
    # real(kind=dp), regardless of array involvement. xp2f.py's own
    # already-scalar-only cases (count_primes/is_prime) never hit this
    # because they're integer/logical-typed, not real. Fixed two ways:
    # (1) rewrite_target_for_f2py now converts ANY scalar function
    # result into a subroutine (f2py never generates that broken wrapper
    # for a subroutine), and (2) --f2cmap/-lgcc are now applied
    # unconditionally (previously gated behind had_array, which is False
    # here).
    proc = _run_xpfunc2f(
        [str(XBRENTQ_PATH), "f", "--out-dir", str(tmp_path), "--verify", "--verify-args", "(3.0,)"], tmp_path
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    assert "Verify: MATCH (python=7.0 fortran=7.0)" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "f_f.f90").read_text(encoding="utf-8")
    assert "pure subroutine f(x, func_res)" in out_f90, out_f90


def test_xpfunc2f_bridges_already_subroutine_with_array_output(tmp_path: Path) -> None:
    # Found running xpfunc2f_batch.py --compile over examples/:
    # xchoice_tuple_repro.py's backbin_rc is ALREADY a subroutine in
    # xp2f.py's own output (xp2f.py's own tuple-return convention for a
    # multi-value Python return), needing only its `choice(:)` array
    # ARGUMENT rewritten -- no function-result conversion happens at all
    # (made_subroutine stays False). The old signature-rebuild code
    # hardcoded "function" whenever made_subroutine was False, producing
    # a mismatched `function backbin_rc(...)` paired with the untouched
    # `end subroutine backbin_rc` line ("Expecting END FUNCTION
    # statement"). A second, independent bug surfaced fixing this one:
    # backbin_rc also has an allocatable rank-1 array among its OTHER
    # intent(out) dummies (`backbin_rc_out_2 = choice`, a whole-array
    # copy with no `allocate()` at all), which the array-argument loop
    # used to mistake for an assumed-shape INPUT needing its own
    # synthesized size, corrupting it into an illegal
    # `allocatable ... (n)` declaration (allocatable arrays must stay
    # deferred-shape). --run-both patches only backbin_rc's own call
    # sites in the real script (both main() and other_call() call it),
    # so a real 3-argument-in/2-argument-out, tuple-unpacked bridge is
    # exercised end-to-end.
    proc = _run_xpfunc2f(
        [str(XCHOICE_TUPLE_REPRO_PATH), "backbin_rc", "--out-dir", str(tmp_path), "--run-both"], tmp_path
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "backbin_rc_f.f90").read_text(encoding="utf-8")
    assert "subroutine backbin_rc(" in out_f90, out_f90
    assert "end subroutine backbin_rc" in out_f90, out_f90
    assert "function backbin_rc" not in out_f90.lower(), out_f90
    assert "allocatable" not in out_f90.lower(), out_f90


def test_xpfunc2f_bridges_wraparound_public_and_optval_helper(tmp_path: Path) -> None:
    # End-to-end companion for both the multiline-public-statement fix
    # and the optval generic-interface fix, together: examples/
    # xbs_vec.py's own `black_scholes` needs `optval`/`to_lower` inlined
    # (previously unresolvable), has a rank-1 array argument/result of
    # its own, AND its own trimmed module's `public ::` statement is
    # long enough to `&`-continue (this project's own generated header,
    # not python.f90's). Also exercises the f2py-keyword-case fix
    # (`black_scholes(S, K, T, r, sigma, option)` -- mixed-case args).
    proc = _run_xpfunc2f([str(XBS_VEC_PATH), "black_scholes", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "black_scholes_f.f90").read_text(encoding="utf-8")
    assert "interface optval" in out_f90, out_f90
    assert "function to_lower" in out_f90, out_f90


def test_xpfunc2f_bridges_burkardt_style_multiline_public(tmp_path: Path) -> None:
    # End-to-end companion for the multiline-public-statement fix:
    # examples/xasa183_inferred.py's `timestamp()` target has NO
    # dependencies of its own, but its own SOURCE module's `public ::`
    # statement lists many OTHER, unrelated Burkardt-test procedures
    # (r8_uni, r8_random_test01, ...) long enough to `&`-continue across
    # several lines -- none of which belong in `needed`, but the
    # continuation line's own names used to survive the filter
    # unfiltered. `timestamp()` returns the current wall-clock time, so
    # --run-both isn't meaningful here (it necessarily differs between
    # the two runs); this only checks the build itself.
    proc = _run_xpfunc2f([str(XASA183_INFERRED_PATH), "timestamp", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "timestamp_f.f90").read_text(encoding="utf-8")
    assert "r8_uni" not in out_f90, out_f90
    assert "r8_random" not in out_f90, out_f90


def test_xpfunc2f_bridges_target_with_multiple_private_dependencies(tmp_path: Path) -> None:
    # End-to-end companion for the array_in_dependency fix (11 files):
    # examples/xoptions_pde.py's `run_example` has 3 dependencies of its
    # own (finite_difference_option_price, print_example,
    # solve_tridiagonal), at least one with its own array-shaped
    # signature -- previously rejected outright. --run-both isn't
    # checked here: its own output has a real, but PRE-EXISTING and
    # unrelated, Fortran-vs-Python number-formatting quirk (a leading
    # zero/exponent style difference, not a value mismatch) this fix
    # doesn't touch; only the build itself is checked.
    proc = _run_xpfunc2f([str(XOPTIONS_PDE_PATH), "run_example", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Extract: PASS (run_example + 3 dependency function(s)" in proc.stdout, proc.stdout
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "run_example_f.f90").read_text(encoding="utf-8")
    assert "public :: dp, run_example" in out_f90, out_f90


def test_xpfunc2f_bridges_shared_allocate_and_multiline_signature(tmp_path: Path) -> None:
    # End-to-end companion for the multiline-signature and shared-
    # allocate-statement fixes together: examples/xsim_fit_nagarch_t.py's
    # own `simulate_nagarch_t` has a `&`-continued signature and shares
    # one `allocate(r(n), h(n))` statement between its two array
    # outputs. --run-both isn't checked here: the generated run-both
    # script imports a sibling module (`nagarch_t_model`) by a relative
    # import that only resolves from the ORIGINAL script's own
    # directory, a pre-existing --run-both infrastructure limitation
    # unrelated to this fix; only the build itself is checked.
    proc = _run_xpfunc2f(
        [str(XSIM_FIT_NAGARCH_T_PATH), "simulate_nagarch_t", "--out-dir", str(tmp_path)], tmp_path
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "simulate_nagarch_t_f.f90").read_text(encoding="utf-8")
    lines = out_f90.splitlines()
    sig_i = next(i for i, ln in enumerate(lines) if ln.startswith("subroutine simulate_nagarch_t("))
    end_i = next(i for i, ln in enumerate(lines) if ln.startswith("end subroutine simulate_nagarch_t"))
    target_lines = lines[sig_i : end_i + 1]
    # The TARGET's own r/h are no longer allocatable (a MODULE-level `r`
    # elsewhere in the file, an unrelated top-level global that happens
    # to share the name, is a separate matter and untouched by this fix).
    assert not any("allocatable" in ln.lower() for ln in target_lines)
    assert any("intent(out) :: r(n)" in ln for ln in target_lines)
    assert any("intent(out) :: h(n)" in ln for ln in target_lines)


def test_xpfunc2f_defaults_function_name_skipping_main(tmp_path: Path) -> None:
    # function_name is now optional: default to the first function the
    # script actually CALLS (not merely the first one defined), skipping
    # a call to "main" -- but transparently ENTERING main's own body,
    # since a `def main(): ...; main()` wrapper's body IS the script's
    # real top-level driver code for this purpose. A helper defined
    # BEFORE main but never actually called by anything (helper_unused)
    # must NOT be picked -- an earlier, narrower version of this
    # heuristic (stop at a literal call to "main" instead of entering
    # it) found nothing else at the true top level and silently fell
    # back to "first def", picking helper_unused: exactly the
    # dependency-before-entry-point bias this heuristic exists to avoid.
    src = tmp_path / "xmain_skip.py"
    src.write_text(
        "\n".join(
            [
                "def helper_unused(x):",
                "    return x + 1",
                "",
                "",
                "def main():",
                "    print(square(4))",
                "",
                "",
                "def square(x):",
                "    return x * x",
                "",
                "",
                "main()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run_xpfunc2f([str(src), "--out-dir", str(tmp_path), "--verify", "--verify-args", "(4,)"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Target: 'square' (defaulted" in proc.stdout, proc.stdout
    assert "Extract: PASS (square" in proc.stdout, proc.stdout
    assert "Verify: MATCH (python=16 fortran=16)" in proc.stdout, proc.stdout

    # Explicit function_name still overrides the default -- even to
    # "main" itself. Asserted only up through Extract (not a full,
    # successful build): bridging a no-argument, no-return-value target
    # like this main() hits a separate, pre-existing limitation
    # unrelated to defaulting itself, out of scope here.
    proc2 = _run_xpfunc2f([str(src), "main", "--out-dir", str(tmp_path)], tmp_path)
    assert "Target:" not in proc2.stdout, proc2.stdout
    assert "Extract: PASS (main + 1 dependency function(s): square)" in proc2.stdout, proc2.stdout


def test_xpfunc2f_defaulting_fails_cleanly_when_only_main_exists(tmp_path: Path) -> None:
    src = tmp_path / "xonly_main.py"
    src.write_text("def main():\n    print('hi')\n\nmain()\n", encoding="utf-8")
    proc = _run_xpfunc2f([str(src), "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Target: FAIL" in proc.stdout, proc.stdout


def test_xpfunc2f_defaults_to_called_function_not_first_defined(tmp_path: Path) -> None:
    # The real case that motivated switching from "first def" to "first
    # called": xprime_func.py defines is_prime (a pure dependency, never
    # itself called from the top level) before count_primes (the
    # function its own driver code actually calls). "First def" picks
    # is_prime; "first called" must pick count_primes.
    proc = _run_xpfunc2f([str(XPRIME_FUNC_PATH), "--out-dir", str(tmp_path), "--verify", "--verify-args", "(1000,)"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Target: 'count_primes' (defaulted" in proc.stdout, proc.stdout
    assert "Extract: PASS (count_primes + 1 dependency function(s): is_prime)" in proc.stdout, proc.stdout


def test_default_target_function_name_unit() -> None:
    # No call anywhere -> falls back to first def, skipping main.
    tree = ast.parse("def main():\n    pass\ndef square(x):\n    return x * x\n")
    assert xpfunc2f.default_target_function_name(tree) == "square"

    tree_no_main = ast.parse("def first():\n    pass\ndef second():\n    pass\n")
    assert xpfunc2f.default_target_function_name(tree_no_main) == "first"

    tree_only_main = ast.parse("def main():\n    pass\n")
    with pytest.raises(xpfunc2f.UnsupportedFunction):
        xpfunc2f.default_target_function_name(tree_only_main)

    # A real top-level call wins over an earlier, never-called def.
    tree_called = ast.parse("def dep(x):\n    return x\ndef entry(y):\n    return dep(y)\nentry(1)\n")
    assert xpfunc2f.default_target_function_name(tree_called) == "entry"

    # A call to main() is entered transparently -- the first OTHER call
    # inside main's own body is the answer, not a fallback to "first
    # def" (which would wrongly pick `unused`, defined earlier but never
    # called by anything).
    tree_main_wraps = ast.parse(
        "def unused(x):\n    return x\ndef main():\n    return real(2)\ndef real(y):\n    return y\nmain()\n"
    )
    assert xpfunc2f.default_target_function_name(tree_main_wraps) == "real"


def test_build_run_both_source_patches_several_functions_at_once() -> None:
    # Regression test for --all's own combined run-both: EVERY named
    # target's own def is replaced by an import of its own wrapper in
    # ONE pass (not just one, the classic single-target case) -- other
    # top-level code (a helper NOT itself a target, and the script's own
    # driver statements) is left completely untouched.
    src = "\n".join(
        [
            "def helper(x):",
            "    return x + 1",
            "def a(x):",
            "    return x * 2",
            "def b(y):",
            "    return y - 1",
            "print(a(1), b(2), helper(3))",
            "",
        ]
    )
    new_src = xpfunc2f.build_run_both_source(src, [("a", "a_f"), ("b", "b_f")])
    assert "from a_f import a" in new_src
    assert "from b_f import b" in new_src
    assert "def helper(x):" in new_src
    assert "def a(" not in new_src
    assert "def b(" not in new_src
    assert "print(a(1), b(2), helper(3))" in new_src


def test_build_run_both_source_rejects_missing_target() -> None:
    src = "def a(x):\n    return x\n"
    with pytest.raises(xpfunc2f.UnsupportedFunction):
        xpfunc2f.build_run_both_source(src, [("a", "a_f"), ("missing", "missing_f")])


def test_xpfunc2f_all_bridges_every_function(tmp_path: Path) -> None:
    # End-to-end: --all on xprime_func.py (is_prime + count_primes, no
    # main()) bridges BOTH functions independently, sharing one
    # transpile pass, and reports a per-function summary.
    proc = _run_xpfunc2f([str(XPRIME_FUNC_PATH), "--all", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("Transpile: PASS") == 1, proc.stdout  # shared, not once per function
    assert "[1/2] is_prime" in proc.stdout, proc.stdout
    assert "[2/2] count_primes" in proc.stdout, proc.stdout
    assert "All-functions summary: 2 of 2 bridged" in proc.stdout, proc.stdout
    assert "PASS  is_prime" in proc.stdout, proc.stdout
    assert "PASS  count_primes" in proc.stdout, proc.stdout
    assert (tmp_path / "is_prime_f.py").exists()
    assert (tmp_path / "count_primes_f.py").exists()


def test_xpfunc2f_all_run_both_when_every_function_bridges(tmp_path: Path) -> None:
    # End-to-end: --all --run-both patches BOTH functions in at once
    # (count_primes' own Fortran calls is_prime via its own PRIVATE
    # embedded copy internally, entirely bypassing is_prime's own
    # separately-bridged wrapper -- no cross-extension linking needed)
    # and runs the whole script once, matching the original exactly.
    proc = _run_xpfunc2f([str(XPRIME_FUNC_PATH), "--all", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "All-functions summary: 2 of 2 bridged" in proc.stdout, proc.stdout
    assert "Run-both: MATCH" in proc.stdout, proc.stdout
    run_both_src = (tmp_path / "xprime_func_all_run_both.py").read_text(encoding="utf-8")
    assert "from is_prime_f import is_prime" in run_both_src
    assert "from count_primes_f import count_primes" in run_both_src


def test_xpfunc2f_all_skips_run_both_on_partial_failure(tmp_path: Path) -> None:
    # End-to-end: one function bridges fine, the other has a rank-2
    # array argument -- genuinely out of scope ("only rank-1 arrays are
    # bridged for now"), so only 1 of 2 functions bridges. --run-both
    # must be SKIPPED rather than attempted with a partially-bridged
    # script, and the run must be reported as failed overall since the
    # explicitly-requested --run-both didn't happen.
    src = tmp_path / "xsynth_partial.py"
    src.write_text(
        "\n".join(
            [
                "import numpy as np",
                "",
                "def good_func(x):",
                "    return x + 1.0",
                "",
                "def bad_func(m):",
                "    return m[0, 0] + m[1, 1]",
                "",
                "a = np.array([[1.0, 2.0], [3.0, 4.0]])",
                "print(good_func(2.0))",
                "print(bad_func(a))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    proc = _run_xpfunc2f([str(src), "--all", "--out-dir", str(tmp_path), "--run-both"], tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "All-functions summary: 1 of 2 bridged" in proc.stdout, proc.stdout
    assert "PASS  good_func" in proc.stdout, proc.stdout
    assert "FAIL  bad_func" in proc.stdout, proc.stdout
    assert "Run-both: SKIPPED" in proc.stdout, proc.stdout


def test_xpfunc2f_all_bridges_tuple_unpack_temp_with_array_shape(tmp_path: Path) -> None:
    # Regression test for a real bug found running --all over examples/
    # xchoice_tuple_repro.py: `other_call`'s own body has a `block ...
    # end block` construct (xp2f.py's own scoping idiom for a tuple-
    # unpacking call site's temp holders) whose SECOND local is
    # array-shaped (`integer, allocatable :: tmp_out_2_50(:)`) --
    # BLOCK_DECL_RE originally required a block-local's own decl line to
    # end immediately after the bare name, so it never matched a shaped
    # local at all. The block-decl-collecting loop stops at the first
    # non-matching line, so it silently stopped after just the FIRST
    # (scalar) local, leaving the array-shaped one stranded in the body
    # once the `block`/`end block` wrapper was stripped -- a declaration
    # after an executable statement, illegal Fortran ("data declaration
    # statement ... cannot appear after executable statements").
    proc = _run_xpfunc2f([str(XCHOICE_TUPLE_REPRO_PATH), "other_call", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "other_call_f.f90").read_text(encoding="utf-8")
    assert "block" not in out_f90.lower()
    assert "allocatable :: tmp_out_2_50" in out_f90, out_f90


def test_xpfunc2f_all_rejects_function_name_and_verify(tmp_path: Path) -> None:
    # --all is mutually exclusive with an explicit function_name (which
    # function would it even apply to?) and with --verify (which needs
    # one function's own arguments, not a script-wide run).
    proc = _run_xpfunc2f([str(XPRIME_FUNC_PATH), "count_primes", "--all"], tmp_path)
    assert proc.returncode != 0
    assert "mutually exclusive" in (proc.stdout + proc.stderr)

    proc = _run_xpfunc2f([str(XPRIME_FUNC_PATH), "--all", "--verify"], tmp_path)
    assert proc.returncode != 0
    assert "mutually exclusive" in (proc.stdout + proc.stderr)


def test_xpfunc2f_reports_unparseable_module_cleanly(tmp_path: Path) -> None:
    # Regression test for a real bug the --all refactor introduced:
    # parse_module used to run INSIDE the per-target try/except (this
    # project's own established style for a clean "Extract: FAIL (...)"
    # report), but hoisting the transpile-once step out of the per-
    # target logic (so --all can share it across every function) moved
    # this call to run BEFORE any try/except existed at all -- a script
    # whose own transpiled output has no `module ... contains ... end
    # module` block (examples/xalias_repro.py's own, xp2f.py's own
    # --flat-style output here) crashed with an unhandled traceback
    # instead of the same clean message every other unsupported-shape
    # case gets.
    proc = _run_xpfunc2f([str(XALIAS_REPRO_PATH), "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "Traceback" not in proc.stderr, proc.stdout + proc.stderr
    assert "Extract: FAIL" in proc.stdout, proc.stdout


def test_xpfunc2f_bridges_rnorm_using_function(tmp_path: Path) -> None:
    # End-to-end: examples/xarma_aic_fit.py's own `simulate_arma` calls
    # `rnorm(n + burnin)` -- previously rejected outright ("needs
    # helper(s) 'rnorm'"), now successfully inlined (its own RNG-replay
    # state hoisted into the trimmed module's specification section).
    # Not checked with --run-both/--verify: rnorm draws genuine random
    # numbers here (no replay file set up), so Python's own and
    # Fortran's own draws are expected to differ -- only the build
    # itself, and that the resulting extension actually runs, matter.
    proc = _run_xpfunc2f([str(XARMA_AIC_FIT_PATH), "simulate_arma", "--out-dir", str(tmp_path)], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    sys.path.insert(0, str(tmp_path))
    wrapper_mod = __import__("simulate_arma_f")
    np = __import__("numpy")
    result = wrapper_mod.simulate_arma(50, np.array([0.5]), np.array([0.2]), 10)
    assert result.shape == (50,)
    assert np.isfinite(result).all()


def test_xpfunc2f_bridges_function_needing_optval_and_rnorm(tmp_path: Path) -> None:
    # End-to-end: examples/xmix.py's own `simulate_normal_mixture` needs
    # BOTH `rnorm` and `optval` inlined together, AND exercises
    # strip_unused_dataframe_use -- the script's own driver code builds
    # a pandas DataFrame elsewhere to report fit results (unrelated to
    # this target), so xp2f.py emits a module-wide `use
    # dataframe_str_index_mod, only: ...` header line that would
    # otherwise be left orphaned (needing a companion module never
    # linked into this standalone f2py build) once trimmed down to just
    # this target.
    proc = _run_xpfunc2f(
        [str(XMIX_PATH), "simulate_normal_mixture", "--out-dir", str(tmp_path)], tmp_path
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    out_f90 = (tmp_path / "simulate_normal_mixture_f.f90").read_text(encoding="utf-8")
    assert "dataframe_str_index_mod" not in out_f90, out_f90
    sys.path.insert(0, str(tmp_path))
    wrapper_mod = __import__("simulate_normal_mixture_f")
    np = __import__("numpy")
    x, component = wrapper_mod.simulate_normal_mixture(
        200, np.array([0.5, 0.5]), np.array([-1.0, 1.0]), np.array([0.5, 0.5]), 1
    )
    assert x.shape == (200,)
    assert component.shape == (200,)
    assert np.isfinite(x).all()
    assert set(component.tolist()) <= {0, 1}


def test_xpfunc2f_bridges_size_derived_through_local_dependency(tmp_path: Path) -> None:
    # End-to-end: examples/xarma_nagarch_fit.py's own
    # `simulate_arma_nagarch` derives its own array result's size
    # through a call to `simulate_nagarch_noise`, a plain, locally-
    # defined dependency function (previously rejected outright: "no
    # ... known-helper expression"). Not checked with --run-both/
    # --verify: rnorm draws genuine random numbers here (no replay file
    # set up), so Python's own and Fortran's own draws are expected to
    # differ -- only the build itself, and that the resulting extension
    # actually runs, matter.
    proc = _run_xpfunc2f(
        [str(XARMA_NAGARCH_FIT_PATH), "simulate_arma_nagarch", "--out-dir", str(tmp_path)], tmp_path
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Extract: PASS (simulate_arma_nagarch + 1 dependency function(s): simulate_nagarch_noise)" in proc.stdout, (
        proc.stdout
    )
    assert "F2PY Build: PASS" in proc.stdout, proc.stdout
    sys.path.insert(0, str(tmp_path))
    np = __import__("numpy")
    wrapper_mod = __import__("simulate_arma_nagarch_f")
    result = wrapper_mod.simulate_arma_nagarch(50, np.array([0.5]), np.array([0.2]), 10, 0.01, 0.05, 0.1, 0.85)
    assert result.shape == (50,)
    assert np.isfinite(result).all()
