module linearconv_1d_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T

  implicit none

  public :: linearconv_1d

  private

  contains

  !........................................
  !__________________________________________________________________!
  !                                                                  !
  !    Compute an approximation of the solution u(t, x) to the 1D    !
  !    linear advection equation                                     !
  !                                                                  !
  !        du/dt + du/dx = 0                                         !
  !                                                                  !
  !    on the domain [0, 2], with discontinuous initial conditions   !
  !                                                                  !
  !        u(t=0, x) = 2   for 0.5 < x < 1,                          !
  !        u(t=0, x) = 1   otherwise.                                !
  !                                                                  !
  !    The numerical solution is computed on a uniform grid using    !
  !    the 1st-order Godunov method, i.e. explicit Euler time stepping!
  !    combined with upwind fluxes.                                  !
  !                                                                  !
  !    Parameters                                                    !
  !    ----------                                                    !
  !    nx : int                                                      !
  !        Number of grid points in the domain.                      !
  !                                                                  !
  !    dt : float                                                    !
  !        Time step size.                                           !
  !                                                                  !
  !    nt : int                                                      !
  !        Number of time steps to be taken.                         !
  !                                                                  !
  !    Returns                                                       !
  !    -------                                                       !
  !    x : numpy.ndarray of nx floats                                !
  !        Spatial grid where solution is computed.                  !
  !                                                                  !
  !    u : numpy.ndarray of nx floats                                !
  !        Numerical solution u at final time.                       !
  !                                                                  !
  !                                                                  !
  !__________________________________________________________________!

  subroutine linearconv_1d(x, u, nx, dt, nt) 

    implicit none

    real(f64), allocatable, intent(out) :: x(:)
    real(f64), allocatable, intent(out) :: u(:)
    integer(i64), value :: nx
    real(f64), value :: dt
    integer(i64), value :: nt
    real(f64) :: c
    real(f64) :: dx
    real(f64) :: cp
    real(f64), allocatable :: un(:)
    integer(i64) :: Dummy_0000
    integer(i64) :: Dummy_0001
    integer(i64) :: i
    integer(i64) :: linspace_index

    c = 1.0_f64
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    allocate(x(0:nx - 1_i64))
    x(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64) / &
          Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64,nx - &
          1_i64)]
    x(nx - 1_i64) = 2.0_f64

    allocate(u(0:nx - 1_i64))
    u(:) = 1.0_f64
    u(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64) &
          - 1_i64) = 2_i64
    cp = c * dt / dx
    allocate(un(0:nx - 1_i64))
    un(:) = 0.0_f64
    do Dummy_0000 = 0_i64, nt - 1_i64
      un(:) = u(:)
      do i = 1_i64, nx - 1_i64
        u(i) = un(i) - cp * (un(i) - un(i - 1_i64))
      end do
    end do
    if (allocated(un)) deallocate(un)
    return

  end subroutine linearconv_1d
  !........................................

end module linearconv_1d_mod
