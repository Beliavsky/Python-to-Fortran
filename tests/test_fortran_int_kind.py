"""Integer widening must preserve constructors and external call boundaries."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fortran_int_kind as fikind
import fortran_scan as fscan


@pytest.mark.parametrize("code, expected", [
    ("42", "42_ikind"),
    ("x = 1", "x = 1_ikind"),
    ("x = 4294967296", "x = 4294967296_ikind"),
    ("x = -9223372036854775807", "x = -9223372036854775807_ikind"),
    ("x = 1 + 2", "x = 1_ikind + 2_ikind"),
    ("x = 1e-3 + 2", "x = 1e-3 + 2_ikind"),
    ("x = 1e+3", "x = 1e+3"),
    ("x = .5d-2 + 3", "x = .5d-2 + 3_ikind"),
    ("x = 1.0E-10_dp + 3", "x = 1.0E-10_dp + 3_ikind"),
    ("x = 1.d+5", "x = 1.d+5"),
    ("x = 42_int64 + 3_8", "x = 42_int64 + 3_8"),
    ("real(8) :: x", "real(8) :: x"),
    ("real(kind=real64) :: x", "real(kind=real64) :: x"),
    ("print *, '42', \"1e-3\", 42", "print *, '42', \"1e-3\", 42_ikind"),
])
def test_integer_literal_token_boundaries(code, expected):
    assert fikind._suffix_bare_int_literals_in_code(code) == expected


@pytest.mark.parametrize("text,expected", [
    ("a(*) = [1, 2, 3], b = 4", ["a(*) = [1, 2, 3]", "b = 4"]),
    ("a = reshape([1,2,3,4], [2,2]), b", ["a = reshape([1,2,3,4], [2,2])", "b"]),
    ("a = [integer :: ], b = (/1,2/)", ["a = [integer :: ]", "b = (/1,2/)"]),
    ("a = ['[,'']', 'x,y'], b", ["a = ['[,'']', 'x,y']", "b"]),
    ('a = ["[,]", "x""y"], b', ['a = ["[,]", "x""y"]', 'b']),
])
def test_split_commas_preserves_array_constructors(text, expected):
    assert fscan._split_top_level_commas(text) == expected


def test_mixed_declaration_preserves_excluded_constructor():
    lines = fikind._rewrite_decl_line("integer, parameter :: a(*) = [1, 2, 3], b = 4\n", {"a"})
    assert lines == ["integer, parameter :: a(*) = [1, 2, 3]\n",
                     "integer(kind=ikind), parameter :: b = 4\n"]


@pytest.mark.parametrize("typed_function", [False, True])
def test_exclusions_follow_host_association_and_shadows(typed_function):
    text = """module demo
integer :: n
contains
subroutine parent()
integer :: r
call helper(n)
call helper(r)
contains
subroutine child()
integer :: r
r = 1
end subroutine child
end subroutine parent
subroutine sibling()
integer :: r
r = 2
end subroutine sibling
end module demo
"""
    if typed_function:
        text = text.replace("subroutine sibling()", "pure real function sibling()")
        text = text.replace("end subroutine sibling", "end function sibling")
    stmts = fscan.iter_fortran_statements(text.splitlines())
    exclusions = fikind._scoped_exclusions(stmts, frozenset({"helper"}))
    local_r = [exclusions[line] for line, stmt in stmts if stmt == "integer :: r"]
    assert ["r" in names for names in local_r] == [True, False, False]
    assert "n" in exclusions[2]
    assert all("n" in names for names in local_r)


@pytest.mark.parametrize("kind", ["int32", "int64"])
def test_compile_constructor_scope_and_allocation_boundaries(tmp_path, monkeypatch, kind):
    compiler = shutil.which("gfortran")
    if not compiler:
        pytest.skip("gfortran required")
    monkeypatch.setattr(fikind, "_boundary_calls_cache", frozenset({"helper"}))
    text = """module demo
implicit none
contains
subroutine boundary(n)
integer, intent(in) :: n
integer, parameter :: a(*) = [1, &
 & 2, 3], b = 4
integer, allocatable :: r(:)
allocate(r(3), source=0)
if (n /= 3) stop 2
r = a
call helper(r * a)
end subroutine boundary
subroutine independent()
integer :: r, i
r = 1
do i = 1, 10
r = r * 10
end do
print *, r
end subroutine independent
end module demo
program test
use demo, only: boundary, independent
implicit none
call boundary(3)
call independent()
end program test
"""
    if kind == "int32":
        text = text.replace("do i = 1, 10", "do i = 1, 9")
    rewritten = "".join(fikind.add_integer_kind(text.splitlines(keepends=True), kind))
    assert "integer :: r, i" not in rewritten
    assert "source=0_ikind" not in rewritten
    assert "integer(kind=ikind), parameter :: b" in rewritten
    src = tmp_path / "test.f90"
    src.write_text(rewritten, encoding="utf-8")
    helper = tmp_path / "helper.f90"
    helper.write_text("subroutine helper(x)\ninteger :: x(3)\nif (any(x /= [1,4,9])) stop 1\nend subroutine\n", encoding="utf-8")
    exe = tmp_path / "test.exe"
    build = subprocess.run([compiler, "-fcheck=all", str(src), str(helper), "-o", str(exe)],
                           cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.strip() == ("10000000000" if kind == "int64" else "1000000000")



@pytest.mark.parametrize("lines, expected", [
    # Inside a string the text resumes right after the second `&`.
    (['   write(*,"(a)") "trade nee&', '      &ded)"'], 'write(*,"(a)") "trade needed)"'),
    (['   x = "ab  &', '      &  cd" ! note'], 'x = "ab    cd"'),
    (["   s = 'it''s &", "   &a ! not a comment'"], "s = 'it''s a ! not a comment'"),
    # Between tokens: one space; comment lines may sit between continuations.
    (['   call f(1, &', '   ! comment', '', '      & 2)'], 'call f(1, 2)'),
])
def test_join_continued_lines_inside_strings(lines, expected):
    assert fscan.join_continued_lines(lines)[0][1] == expected


def test_helper_arguments_are_converted_per_call():
    text = """module demo
implicit none
contains
subroutine run(n, k)
integer, intent(in) :: n
integer, intent(in), optional :: k
integer :: z(3), m
character(len=:), allocatable :: s
logical :: active(3)
s = py_format_int(n + 1, 5, '', 'd')
m = optval(k, 7)
call seed_rng(12345 + n)
call random_choice_prob([0.5d0, 0.5d0], 3, z)
active(2) = .true.
end subroutine run
end module demo
"""
    out = "".join(fikind.add_integer_kind(text.splitlines(keepends=True), "int64"))
    # py_format_int has an int64 specific: no conversion. A helper with a
    # default-integer intent(in) dummy gets a checked narrow_int.
    assert "py_format_int(n + 1_ikind, 5, '', 'd')" in out, out
    assert "use python_mod, only: narrow_int" in out, out
    # An optional dummy: a plain name stays default kind, an expression is converted.
    assert "optval(k, 7)" in out and "integer, intent(in), optional :: k" in out, out
    assert "seed_rng(narrow_int(12345_ikind + n))" in out, out
    # An intent(out) actual stays default kind; others are widened.
    assert "integer :: z(3_ikind)" in out and "integer(kind=ikind) :: m" in out, out
    # `active` is this file's array, not lbfgsb.f90's routine.
    assert "active(2_ikind) = .true." in out, out



def test_interface_bodies_import_ikind():
    text = """module demo
implicit none
contains
function apply(f, n) result(r)
interface
function f_cb(x) result(y)
import dp
integer :: x
real :: y
end function f_cb
function g_cb(x) result(y)
integer :: x
integer :: y
end function g_cb
end interface
procedure(f_cb) :: f
integer :: n
real :: r
r = f(n)
end function apply
end module demo
"""
    out = "".join(fikind.add_integer_kind(text.splitlines(keepends=True), "int64"))
    assert "import dp, ikind" in out, out
    assert out.count("import :: ikind") == 1, out


@pytest.mark.parametrize("value, ok", [("2147483647_int64", True), ("3000000000_int64", False)])
def test_narrow_int_stops_outside_default_range(tmp_path, value, ok):
    compiler = shutil.which("gfortran")
    if not compiler:
        pytest.skip("gfortran required")
    prog = tmp_path / "narrow.f90"
    prog.write_text(
        "program p\n"
        "use, intrinsic :: iso_fortran_env, only: int64\n"
        "use python_mod, only: narrow_int\n"
        "implicit none\n"
        f"print *, narrow_int({value})\n"
        "end program p\n", encoding="utf-8")
    exe = tmp_path / "narrow.exe"
    build = subprocess.run([compiler, str(ROOT / "python.f90"), str(ROOT / "lapack_d.f90"), str(prog), "-o", str(exe)],
                           cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True)
    assert (run.returncode == 0) is ok, run.stdout + run.stderr
    if not ok:
        assert "out of the default integer range" in run.stdout + run.stderr


def test_narrow_int_use_is_added_per_unit_without_losing_lines():
    text = ("program p\nimplicit none\ninteger :: n\nn = 3\ncall seed_rng(n + 1)\nend program p\n"
            "module m\nimplicit none\ncontains\nsubroutine s(k)\ninteger, intent(in) :: k\n"
            "call seed_rng(k + 2)\nend subroutine s\nend module m\n")
    out = "".join(fikind.add_integer_kind(text.splitlines(keepends=True), "int64"))
    assert out.count("use python_mod, only: narrow_int") == 2, out
    assert "end program p" in out and "end module m" in out, out
