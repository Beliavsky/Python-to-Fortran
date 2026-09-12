! transpiled by xp2f.py from run_nonlinearconv_1d.py on 2026-09-11 08:31:22
module run_nonlinearconv_1d_proc_mod
   use python_mod, only: linspace
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dp, nonlinearconv_1d
contains

pure subroutine nonlinearconv_1d(nx, dt, nt, x, u)
   !
   !     Compute an approximation of the solution u(t, x) to the 1D
   !     Burgers' equation
   !
   !         du/dt + u du/dx = 0
   !
   !     on the domain [0, 2], with initial conditions consisting of
   !     a Gaussian perturbation over a uniform background:
   !
   !         u(t=0, x) = 1 + 0.5 exp( -((x-0.5)^2 / 0.15^2) ).
   !
   !     The numerical solution is computed on a uniform grid using
   !     one-sided upwind finite-differences combined with explicit
   !     Euler time stepping.
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
   real(kind=dp) :: dt_dx, dx
   integer :: i, i_
   real(kind=dp), allocatable :: un(:)
   
   dx = real(2, kind=dp) / real(nx - 1, kind=dp)
   x = linspace(real(0, kind=dp), real(2, kind=dp), nx)
   u = 1.0_dp + (0.5_dp * exp(-(((x - 0.5_dp) / 0.15_dp) ** 2)))
   dt_dx = dt / dx
   allocate(un(nx), source=0.0_dp)
   do i_ = 0, nt - 1
      un = u
      do i = 1, nx - 1
         u(i + 1) = un(i + 1) - ((un(i + 1) * dt_dx) * (un(i + 1) - un(i)))
      end do
   end do
end subroutine nonlinearconv_1d

end module run_nonlinearconv_1d_proc_mod

program run_nonlinearconv_1d
   use run_nonlinearconv_1d_proc_mod, only: dp, nonlinearconv_1d
   implicit none
   real(kind=dp), allocatable :: u(:), x(:)
   
   call nonlinearconv_1d(201, 0.0035_dp, 300, x, u)
   print *, anint(u * (10.0_dp**8)) / (10.0_dp**8)
end program run_nonlinearconv_1d
