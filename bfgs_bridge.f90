! Small adapter generated for xp2f.py's scipy.optimize.minimize (BFGS)
! support. Bridges a Python-style `def f(x): return scalar` objective
! callback (translated to a Fortran `function f(x) result(y)` with an
! assumed-shape real(dp) input and a scalar real(dp) result) to the callback
! shape bfgs_mod's bfgs_minimize_fd expects: `subroutine func_f(p, np, f)`.
! See bfgs.f90 (vendored alongside this file) for the actual solver.
module bfgs_bridge_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none

   abstract interface
      function bfgs_scalarfunc_iface(x) result(y)
         import :: dp
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: y
      end function bfgs_scalarfunc_iface
   end interface

   procedure(bfgs_scalarfunc_iface), pointer :: bfgs_user_fn => null()

contains

   subroutine bfgs_generic_wrapper(p, np, f)
      integer, intent(in) :: np
      real(kind=dp), intent(in) :: p(np)
      real(kind=dp), intent(out) :: f
      f = bfgs_user_fn(p)
   end subroutine bfgs_generic_wrapper

end module bfgs_bridge_mod
