! Small adapter generated for xp2f.py's scipy.optimize.minimize(method=
! 'L-BFGS-B') support. lbfgsb_module's setulb() is a reverse-communication
! routine: the caller must invoke it repeatedly, evaluating f and its
! gradient whenever task=='FG' and stopping on 'CONV'/'ABNO'/'ERROR'. This
! module hides that loop behind a single lbfgsb_minimize() call, bridging a
! Python-style `def f(x): return scalar` objective (translated to a Fortran
! `function f(x) result(y)` with an assumed-shape real(dp) input and a
! scalar real(dp) result) the same way the other bridge modules do.
!
! Since xp2f-translated objectives don't carry an analytic-gradient
! counterpart, the gradient is estimated via central finite differences at
! each 'FG' request -- the same approach bfgs_bridge.f90 uses for
! unconstrained minimize().
! See lbfgsb.f90 (vendored alongside this file) for the actual solver.
module lbfgsb_bridge_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   use lbfgsb_module, only: setulb
   implicit none

   abstract interface
      function lbfgsb_scalarfunc_iface(x) result(y)
         import :: dp
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: y
      end function lbfgsb_scalarfunc_iface
   end interface

   procedure(lbfgsb_scalarfunc_iface), pointer :: lbfgsb_user_fn => null()

contains

   subroutine lbfgsb_minimize(x, l, u, nbd, f_opt)
      real(kind=dp), intent(inout) :: x(:)
      real(kind=dp), intent(in) :: l(:), u(:)
      integer, intent(in) :: nbd(:)
      real(kind=dp), intent(out) :: f_opt

      integer, parameter :: mem = 10
      real(kind=dp), parameter :: factr = 1.0e7_dp
      real(kind=dp), parameter :: pgtol = 1.0e-5_dp
      real(kind=dp), parameter :: h = 1.0e-8_dp
      integer, parameter :: max_setulb_calls = 20000
      integer :: n, i, calls
      real(kind=dp) :: f, f_plus
      real(kind=dp), allocatable :: g(:), wa(:), p_pert(:)
      integer, allocatable :: iwa(:)
      character(len=60) :: task, csave
      logical :: lsave(4)
      integer :: isave(44)
      real(kind=dp) :: dsave(29)

      n = size(x)
      allocate (g(n), p_pert(n))
      allocate (wa(2*mem*n + 5*n + 11*mem*mem + 8*mem))
      allocate (iwa(3*n))

      task = 'START'
      do calls = 1, max_setulb_calls
         call setulb(n, mem, x, l, u, nbd, f, g, factr, pgtol, wa, iwa, task, &
                     -1, csave, lsave, isave, dsave)
         if (task(1:2) == 'FG') then
            ! Forward differences (2-point), matching scipy's default
            ! numerical-differentiation scheme for L-BFGS-B when no
            ! analytic jac is supplied (method='2-point', eps=1e-8).
            f = lbfgsb_user_fn(x)
            do i = 1, n
               p_pert = x
               p_pert(i) = x(i) + h
               f_plus = lbfgsb_user_fn(p_pert)
               g(i) = (f_plus - f)/h
            end do
         else if (task(1:5) == 'NEW_X') then
            cycle
         else
            exit
         end if
      end do
      f_opt = f
   end subroutine lbfgsb_minimize

end module lbfgsb_bridge_mod
