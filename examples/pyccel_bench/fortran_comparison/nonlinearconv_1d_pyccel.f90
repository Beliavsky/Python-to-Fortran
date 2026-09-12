module nonlinearconv_1d_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T

  implicit none

  public :: nonlinearconv_1d

  private

  contains

  !........................................
  !______________________________________________________________!
  !                                                              !
  !    Compute an approximation of the solution u(t, x) to the 1D!
  !    Burgers' equation                                         !
  !                                                              !
  !        du/dt + u du/dx = 0                                   !
  !                                                              !
  !    on the domain [0, 2], with initial conditions consisting of!
  !    a Gaussian perturbation over a uniform background:        !
  !                                                              !
  !        u(t=0, x) = 1 + 0.5 exp( -((x-0.5)^2 / 0.15^2) ).     !
  !                                                              !
  !    The numerical solution is computed on a uniform grid using!
  !    one-sided upwind finite-differences combined with explicit!
  !    Euler time stepping.                                      !
  !                                                              !
  !    Parameters                                                !
  !    ----------                                                !
  !    nx : int                                                  !
  !        Number of grid points in the domain.                  !
  !                                                              !
  !    dt : float                                                !
  !        Time step size.                                       !
  !                                                              !
  !    nt : int                                                  !
  !        Number of time steps to be taken.                     !
  !                                                              !
  !    Returns                                                   !
  !    -------                                                   !
  !    x : numpy.ndarray of nx floats                            !
  !        Spatial grid where solution is computed.              !
  !                                                              !
  !    u : numpy.ndarray of nx floats                            !
  !        Numerical solution u at final time.                   !
  !                                                              !
  !                                                              !
  !______________________________________________________________!

  subroutine nonlinearconv_1d(x, u, nx, dt, nt) 

    implicit none

    real(f64), allocatable, intent(out) :: x(:)
    real(f64), allocatable, intent(out) :: u(:)
    integer(i64), value :: nx
    real(f64), value :: dt
    integer(i64), value :: nt
    real(f64) :: dx
    real(f64) :: dt_dx
    real(f64), allocatable :: un(:)
    integer(i64) :: Dummy_0000
    integer(i64) :: Dummy_0001
    integer(i64) :: i
    integer(i64) :: linspace_index

    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    allocate(x(0:nx - 1_i64))
    x(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64) / &
          Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64,nx - &
          1_i64)]
    x(nx - 1_i64) = 2.0_f64

    allocate(u(0:size(x, kind=i64) - 1_i64))
    u(:) = 1.0_f64 + 0.5_f64 * exp(-((x - 0.5_f64) / 0.15_f64) ** 2_i64)
    dt_dx = dt / dx
    allocate(un(0:nx - 1_i64))
    un(:) = 0.0_f64
    do Dummy_0000 = 0_i64, nt - 1_i64
      un(:) = u(:)
      do i = 1_i64, nx - 1_i64
        u(i) = un(i) - un(i) * dt_dx * (un(i) - un(i - 1_i64))
      end do
    end do
    if (allocated(un)) deallocate(un)
    return

  end subroutine nonlinearconv_1d
  !........................................

end module nonlinearconv_1d_mod
