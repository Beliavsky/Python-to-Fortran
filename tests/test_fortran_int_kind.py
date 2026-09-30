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
