! Small adapter generated for xp2f.py's scipy.optimize.brentq support.
! Bridges a Python-style `def f(x): return scalar` callback (translated to a
! Fortran `function f(x) result(y)` with a scalar real(dp) input and a
! scalar real(dp) result) to root.f90's root_scalar('brentq', ...) callback
! shape: `function fun(x) result(f)`.
! See root.f90 (vendored alongside this file, from jacobwilliams/roots-fortran)
! for the actual solver.
module brentq_bridge_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none

   abstract interface
      function brentq_scalarfunc_iface(x) result(y)
         import :: dp
         real(kind=dp), intent(in) :: x
         real(kind=dp) :: y
      end function brentq_scalarfunc_iface
   end interface

   procedure(brentq_scalarfunc_iface), pointer :: brentq_user_fn => null()

contains

   function brentq_generic_wrapper(x) result(y)
      real(kind=dp), intent(in) :: x
      real(kind=dp) :: y
      y = brentq_user_fn(x)
   end function brentq_generic_wrapper

end module brentq_bridge_mod
