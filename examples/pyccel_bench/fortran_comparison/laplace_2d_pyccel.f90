module laplace_2d_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T

  implicit none

  public :: laplace_2d

  private

  contains

  !........................................
  !______________________________________________________________________!
  !                                                                      !
  !    Solve the 2D Laplace equation for phi(x, y) on the rectangular    !
  !    domain [0, 2] * [0, 1] with boundary conditions                   !
  !                                                                      !
  !        phi = 0      at x = xmin,                                     !
  !        phi = y      at x = xmax,                                     !
  !        dphi/dy = 0  at y = ymin,                                     !
  !        dphi/dy = 0  at y = ymax.                                     !
  !                                                                      !
  !    The numerical solution is computed on a uniform grid using 2nd    !
  !    order finite differences and the Jacobi method with a prescribed  !
  !    relative tolerance.                                               !
  !                                                                      !
  !    Parameters                                                        !
  !    ----------                                                        !
  !    nx : int                                                          !
  !        Number of grid points along x axis.                           !
  !                                                                      !
  !    ny : int                                                          !
  !        Number of grid points along y axis.                           !
  !                                                                      !
  !    rtol : float                                                      !
  !        Stopping condition for the Jacobi method: the relative L1 norm!
  !        of the difference between successive solutions should be lower!
  !        than the value provided.                                      !
  !                                                                      !
  !    maxiter : int                                                     !
  !        Maximum number of Jacobi iterations allowed.                  !
  !                                                                      !
  !    Returns                                                           !
  !    -------                                                           !
  !    x : numpy.ndarray[nx]                                             !
  !        Computational grid along x axis.                              !
  !                                                                      !
  !    y : numpy.ndarray[ny]                                             !
  !        Computational grid along y axis.                              !
  !                                                                      !
  !    phi : numpy.ndarray[ny, nx]                                       !
  !        Numerical solution on the computational grid.                 !
  !                                                                      !
  !    niter : int                                                       !
  !        Number of Jacobi iterations performed.                        !
  !                                                                      !
  !______________________________________________________________________!

  subroutine laplace_2d(x, y, phi, niter, nx, ny, rtol, maxiter) 

    implicit none

    real(f64), allocatable, intent(out) :: x(:)
    real(f64), allocatable, intent(out) :: y(:)
    real(f64), allocatable, intent(out) :: phi(:, :)
    integer(i64), intent(out) :: niter
    integer(i64), value :: nx
    integer(i64), value :: ny
    real(f64), value :: rtol
    integer(i64), value :: maxiter
    real(f64) :: xmin
    real(f64) :: xmax
    real(f64) :: ymin
    real(f64) :: ymax
    real(f64) :: dx
    real(f64) :: dy
    real(f64) :: l1norm
    real(f64), allocatable :: pn(:, :)
    real(f64), allocatable :: diff(:, :)
    real(f64), allocatable :: a(:, :)
    real(f64), allocatable :: err(:, :)
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

    !Initial values
    allocate(phi(0:nx - 1_i64, 0:ny - 1_i64))
    phi(:,:) = 1.0_f64
    l1norm = 2_i64 * rtol
    niter = 0_i64
    !Temporary arrays
    allocate(pn(0:nx - 1_i64, 0:ny - 1_i64))
    allocate(diff(0:nx - 1_i64, 0:ny - 1_i64))
    allocate(a(0:nx - 1_i64, 0:ny - 1_i64))
    allocate(err(0:nx - 1_i64, 0:ny - 1_i64))
    !Jacobi iteration
    do while (l1norm > rtol .and. niter < maxiter)
      pn(:, :) = phi(:, :)
      phi(1_i64:size(phi, 1_i64, i64) - 2_i64, 1_i64:size(phi, 2_i64, &
            i64) - 2_i64) = (dy * dy * (pn(2_i64:, 1_i64:size(pn, 2_i64 &
            , i64) - 2_i64) + pn(0_i64:size(pn, 1_i64, i64) - 3_i64, &
            1_i64:size(pn, 2_i64, i64) - 2_i64)) + dx * dx * (pn(1_i64: &
            size(pn, 1_i64, i64) - 2_i64, 2_i64:) + pn(1_i64:size(pn, &
            1_i64, i64) - 2_i64, 0_i64:size(pn, 2_i64, i64) - 3_i64))) &
            / (2_i64 * (dx * dx + dy * dy))
      phi(0_i64, :) = 0_i64
      phi(size(phi, 1_i64, i64) - 1_i64, :) = y
      phi(:, 0_i64) = phi(:, 1_i64)
      phi(:, size(phi, 2_i64, i64) - 1_i64) = phi(:, size(phi, 2_i64, &
            i64) - 2_i64)
      diff(:, :) = phi(:, :) - pn(:, :)
      err(:, :) = abs(diff(:, :))
      a(:, :) = abs(pn(:, :))
      l1norm = sum(err) / sum(a)
      niter = niter + 1_i64
    end do
    !Return axes' grid, solution, and number of iterations
    if (allocated(a)) deallocate(a)
    if (allocated(err)) deallocate(err)
    if (allocated(pn)) deallocate(pn)
    if (allocated(diff)) deallocate(diff)
    return

  end subroutine laplace_2d
  !........................................

end module laplace_2d_mod
