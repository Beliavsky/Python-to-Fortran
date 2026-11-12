"""Compact, topic-grouped access declarations in the extracted library."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from xextract_fortran_lib import (grouped_public_declarations, omit_inherited_implicit_none,
                                 promote_library_elementals)


def test_public_names_grouped_and_alphabetized():
    lines = grouped_public_declarations({
        'sorting': ['argsort_vec', 'argsort', 'argsort_2d'],
        'arrays': ['zeros', 'allclose'],
    })
    assert lines == [
        '', '! Array creation and manipulation', 'public :: allclose, zeros',
        '', '! Sorting and searching', 'public :: argsort, argsort_2d, argsort_vec', '',
    ]


def test_public_lines_wrap_without_losing_names():
    names = ['routine_' + str(i).zfill(3) for i in range(40)]
    lines = grouped_public_declarations({'math': names[::-1]})
    declarations = [line for line in lines if line.startswith('public :: ')]
    assert 1 < len(declarations) < len(names)
    assert all(len(line) <= 100 and not line.endswith(',') and '&' not in line
               for line in declarations)
    assert [name for line in declarations for name in line[len('public :: '):].split(', ')] == names


def test_exact_width_fits_on_one_line():
    assert grouped_public_declarations({'math': ['bb', 'a']}, width=15) == [
        '', '! Mathematical functions', 'public :: a, bb', '',
    ]
    assert grouped_public_declarations({'math': ['bb', 'a']}, width=14) == [
        '', '! Mathematical functions', 'public :: a', 'public :: bb', '',
    ]


def test_empty_and_custom_topics():
    assert grouped_public_declarations({}) == []
    assert grouped_public_declarations({'arrays': []}) == []
    assert grouped_public_declarations({'custom_topic': ['foo']}) == [
        '', '! Custom topic', 'public :: foo', '',
    ]


def test_implicit_none_inherited_by_procedures():
    source = '''subroutine outer()
  implicit none ! Explicit types required
  ! implicit none in a comment must stay
contains
  subroutine inner()
    IMPLICIT NONE
  end subroutine inner
end subroutine outer'''.splitlines()
    assert omit_inherited_implicit_none(source) == [
        'subroutine outer()', '  ! Explicit types required',
        '  ! implicit none in a comment must stay', 'contains',
        '  subroutine inner()', '  end subroutine inner', 'end subroutine outer',
    ]


def test_interface_implicit_none_is_preserved():
    source = '''subroutine outer()
implicit none
abstract interface
  function callback(x) result(y)
    implicit none
    real, intent(in) :: x
    real :: y
  end function callback
end interface
interface
  subroutine external_proc()
    implicit none
  end subroutine external_proc
end interface
end subroutine outer'''.splitlines()
    assert omit_inherited_implicit_none(source) == source[:1] + source[2:]


def test_internal_procedure_below_implicit_override_keeps_none():
    source = '''subroutine outer()
implicit real(a-z)
contains
subroutine inner()
implicit none
end subroutine inner
end subroutine outer'''.splitlines()
    assert omit_inherited_implicit_none(source) == source


def test_qualified_implicit_none_is_preserved():
    source = ['subroutine outer()', 'implicit none(type, external)', 'end subroutine outer']
    assert omit_inherited_implicit_none(source) == source


def test_library_elementals_preserve_callbacks_and_nonscalar_results():
    source = '''module m
implicit none
contains
pure real function scalar(x)
real, intent(in) :: x
scalar = x * 2
end function scalar
pure real function callback(x)
real, intent(in) :: x
callback = x + 1
end function callback
pure real function apply(f, x)
procedure(callback) :: f
real, intent(in) :: x
apply = f(x)
end function apply
pure real function caller(x)
real, intent(in) :: x
caller = apply(callback, x)
end function caller
pure function vector(x) result(y)
real, intent(in) :: x(:)
real :: y(size(x))
y = x
end function vector
pure function alloc_result(x) result(y)
real, intent(in) :: x
real, allocatable :: y
y = x
end function alloc_result
end module m'''.splitlines()
    result = '\n'.join(promote_library_elementals(source))
    assert 'pure elemental real function scalar(x)' in result
    assert 'pure real function callback(x)' in result
    assert 'pure real function apply(f, x)' in result
    assert 'pure function vector(x)' in result
    assert 'pure function alloc_result(x)' in result
    assert promote_library_elementals(result.splitlines()) == result.splitlines()
