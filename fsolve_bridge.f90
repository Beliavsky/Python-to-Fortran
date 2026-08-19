! Small adapter generated for xp2f.py's scipy.optimize.fsolve support.
! Bridges a Python-style `def f(x): ... return y` callback (translated to a
! Fortran `function f(x) result(y)` with an assumed-shape real(dp) input and
! an allocatable real(dp) result of the same size) to the callback shape
! MINPACK's hybrd/hybrd1 expect: `subroutine fcn(n, x, fvec, iflag)`.
! See minpack.f90 (vendored alongside this file) for the actual solver.
module fsolve_bridge_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none

   abstract interface
      function fsolve_vecfunc_iface(x) result(y)
         import :: dp
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp), allocatable :: y(:)
      end function fsolve_vecfunc_iface
   end interface

   procedure(fsolve_vecfunc_iface), pointer :: fsolve_user_fn => null()

contains

   subroutine fsolve_generic_wrapper(n, x, fvec, iflag)
      integer, intent(in) :: n
      real(kind=dp), intent(in) :: x(n)
      real(kind=dp), intent(out) :: fvec(n)
      integer, intent(inout) :: iflag
      fvec = fsolve_user_fn(x)
   end subroutine fsolve_generic_wrapper

end module fsolve_bridge_mod
