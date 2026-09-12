! transpiled by xp2f.py from run_linearconv_1d.py on 2026-09-11 08:30:10
module run_linearconv_1d_proc_mod
   use python_mod, only: linspace
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dp, linearconv_1d
contains

pure subroutine linearconv_1d(nx, dt, nt, x, u)
   !
   !     Compute an approximation of the solution u(t, x) to the 1D
   !     linear advection equation
   !
   !         du/dt + du/dx = 0
   !
   !     on the domain [0, 2], with discontinuous initial conditions
   !
   !         u(t=0, x) = 2   for 0.5 < x < 1,
   !         u(t=0, x) = 1   otherwise.
   !
   !     The numerical solution is computed on a uniform grid using
   !     the 1st-order Godunov method, i.e. explicit Euler time stepping
   !     combined with upwind fluxes.
   !
   !     Parameters
   !     ----------
   !     nx : int
   !         Number of grid points in the domain.
   !
   !     dt : float
   !         Time step size.
   !
   !     nt : int
   !         Number of time steps to be taken.
   !
   !     Returns
   !     -------
   !     x : numpy.ndarray of nx floats
   !         Spatial grid where solution is computed.
   !
   !     u : numpy.ndarray of nx floats
   !         Numerical solution u at final time.
   !
   !
   integer, intent(in) :: nx, nt
   real(kind=dp), intent(in) :: dt
   real(kind=dp), allocatable, intent(out) :: x(:), u(:)
   real(kind=dp), parameter :: c = 1.0_dp
   real(kind=dp) :: cp, dx
   integer :: i, i_
   real(kind=dp), allocatable :: un(:)
   
   dx = real(2, kind=dp) / real(nx - 1, kind=dp)
   x = linspace(real(0, kind=dp), real(2, kind=dp), nx)
   allocate(u(nx), source=1.0_dp)
   u(int(0.5_dp / dx) + 1:int(real(1, kind=dp) / dx + 1)) = 2
   cp = (c * dt) / dx
   allocate(un(nx), source=0.0_dp)
   do i_ = 0, nt - 1
      un = u
      do i = 1, nx - 1
         u(i + 1) = un(i + 1) - (cp * (un(i + 1) - un(i)))
      end do
   end do
end subroutine linearconv_1d

end module run_linearconv_1d_proc_mod

program run_linearconv_1d
   use run_linearconv_1d_proc_mod, only: dp, linearconv_1d
   implicit none
   real(kind=dp), allocatable :: u(:), x(:)
   
   call linearconv_1d(201, 0.003_dp, 300, x, u)
   print *, anint(u * (10.0_dp**8)) / (10.0_dp**8)
end program run_linearconv_1d
