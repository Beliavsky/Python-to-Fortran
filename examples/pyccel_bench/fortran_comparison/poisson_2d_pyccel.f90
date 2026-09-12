module poisson_2d_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T
  use pyc_math_f90

  implicit none

  public :: poisson_2d

  private

  contains

  !........................................
  !__________________________________________________________________!
  !                                                                  !
  !    Solve the 2D poisson equation for phi(x, y) on the rectangular!
  !    domain [0, 2] * [0, 1] with 2 point sources (Dirac deltas) of !
  !    charge +1 and -1 respectively, at the positions               !
  !                                                                  !
  !        (x, y) = (0.5, 0.25) and                                  !
  !        (x, y) = (1.5, 0.75),                                     !
  !                                                                  !
  !    and subject to the boundary conditions                        !
  !                                                                  !
  !        phi = 0      at x = xmin,                                 !
  !        phi = y      at x = xmax,                                 !
  !        dphi/dy = 0  at y = ymin,                                 !
  !        dphi/dy = 0  at y = ymax.                                 !
  !                                                                  !
  !    The numerical solution is computed on a uniform grid using 2nd!
  !    order finite differences and the Jacobi method with a fixed   !
  !    number of iterations.                                         !
  !                                                                  !
  !    Parameters                                                    !
  !    ----------                                                    !
  !    nx : int                                                      !
  !        Number of grid points along x axis.                       !
  !                                                                  !
  !    ny : int                                                      !
  !        Number of grid points along y axis.                       !
  !                                                                  !
  !    nt : int                                                      !
  !        Number of Jacobi iterations.                              !
  !                                                                  !
  !    Returns                                                       !
  !    -------                                                       !
  !    x : numpy.ndarray[nx]                                         !
  !        Computational grid along x axis.                          !
  !                                                                  !
  !    y : numpy.ndarray[ny]                                         !
  !        Computational grid along y axis.                          !
  !                                                                  !
  !    phi : numpy.ndarray[ny, nx]                                   !
  !        Numerical solution on the computational grid.             !
  !                                                                  !
  !                                                                  !
  !__________________________________________________________________!

  subroutine poisson_2d(x, y, phi, nx, ny, nt) 

    implicit none

    real(f64), allocatable, intent(out) :: x(:)
    real(f64), allocatable, intent(out) :: y(:)
    real(f64), allocatable, intent(out) :: phi(:, :)
    integer(i64), value :: nx
    integer(i64), value :: ny
    integer(i64), value :: nt
    real(f64) :: xmin
    real(f64) :: xmax
    real(f64) :: ymin
    real(f64) :: ymax
    real(f64) :: dx
    real(f64) :: dy
    real(f64), allocatable :: b(:, :)
    real(f64), allocatable :: pn(:, :)
    integer(i64) :: Dummy_0000
    integer(i64) :: Dummy_0001
    integer(i64) :: j
    integer(i64) :: i
    integer(i64) :: linspace_index
    integer(i64) :: linspace_index_0001

    !Domain size
    xmin = 0.0_f64
    xmax = 2.0_f64
    ymin = 0.0_f64
    ymax = 1.0_f64
    !Computational grid
    dx = (xmax - xmin) / (nx - 1_i64)
    dy = (ymax - ymin) / (ny - 1_i64)
    allocate(x(0:nx - 1_i64))
    x(:) = [((xmin + linspace_index*(xmax - xmin) / (nx - 1_i64)), &
          linspace_index = 0_i64,nx - 1_i64)]
    x(nx - 1_i64) = xmax

    allocate(y(0:ny - 1_i64))
    y(:) = [((ymin + linspace_index_0001*(ymax - ymin) / (ny - 1_i64)), &
          linspace_index_0001 = 0_i64,ny - 1_i64)]
    y(ny - 1_i64) = ymax

    !Charge density with point sources
    allocate(b(0:nx - 1_i64, 0:ny - 1_i64))
    b(:,:) = 0.0_f64
    b(pyc_floor_div(nx, 4_i64), pyc_floor_div(ny, 4_i64)) = 1.0_f64 / ( &
          dx * dy)
    b(pyc_floor_div(3_i64 * nx, 4_i64), pyc_floor_div(3_i64 * ny, 4_i64 &
          )) = (-1.0_f64) / (dx * dy)
    !First guess
    allocate(phi(0:nx - 1_i64, 0:ny - 1_i64))
    phi(:,:) = 0.0_f64
    !Temporary array
    allocate(pn(0:nx - 1_i64, 0:ny - 1_i64))
    !Jacobi iteration
    do Dummy_0000 = 0_i64, nt - 1_i64
      pn(:, :) = phi(:, :)
      do j = 1_i64, ny - 2_i64
        do i = 1_i64, nx - 2_i64
          phi(i, j) = ((pn(i + 1_i64, j) + pn(i - 1_i64, j)) * (dy * dy &
                ) + (pn(i, j + 1_i64) + pn(i, j - 1_i64)) * (dx * dx) - &
                b(i, j) * (dx * dx) * (dy * dy)) / (2_i64 * (dx * dx + &
                dy * dy))
        end do
      end do
      phi(0_i64, :) = 0_i64
      phi(size(phi, 1_i64, i64) - 1_i64, :) = y
      phi(:, 0_i64) = phi(:, 1_i64)
      phi(:, size(phi, 2_i64, i64) - 1_i64) = phi(:, size(phi, 2_i64, &
            i64) - 2_i64)
    end do
    !Return axes' grid and solution
    if (allocated(pn)) deallocate(pn)
    if (allocated(b)) deallocate(b)
    return

  end subroutine poisson_2d
  !........................................

end module poisson_2d_mod
