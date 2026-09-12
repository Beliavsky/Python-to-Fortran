! transpiled by xp2f.py from run_laplace_2d.py on 2026-09-11 08:28:30
module run_laplace_2d_proc_mod
   use python_mod, only: linspace
   use, intrinsic :: ieee_arithmetic, only: ieee_is_nan
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dp, laplace_2d
contains

pure subroutine laplace_2d(nx, ny, rtol, maxiter, x, y, phi, niter)
   !
   !     Solve the 2D Laplace equation for phi(x, y) on the rectangular
   !     domain [0, 2] * [0, 1] with boundary conditions
   !
   !         phi = 0      at x = xmin,
   !         phi = y      at x = xmax,
   !         dphi/dy = 0  at y = ymin,
   !         dphi/dy = 0  at y = ymax.
   !
   !     The numerical solution is computed on a uniform grid using 2nd
   !     order finite differences and the Jacobi method with a prescribed
   !     relative tolerance.
   !
   !     Parameters
   !     ----------
   !     nx : int
   !         Number of grid points along x axis.
   !
   !     ny : int
   !         Number of grid points along y axis.
   !
   !     rtol : float
   !         Stopping condition for the Jacobi method: the relative L1 norm
   !         of the difference between successive solutions should be lower
   !         than the value provided.
   !
   !     maxiter : int
   !         Maximum number of Jacobi iterations allowed.
   !
   !     Returns
   !     -------
   !     x : numpy.ndarray[nx]
   !         Computational grid along x axis.
   !
   !     y : numpy.ndarray[ny]
   !         Computational grid along y axis.
   !
   !     phi : numpy.ndarray[ny, nx]
   !         Numerical solution on the computational grid.
   !
   !     niter : int
   !         Number of Jacobi iterations performed.
   !
   integer, intent(in) :: nx, ny, maxiter
   real(kind=dp), intent(in) :: rtol
   real(kind=dp), allocatable, intent(out) :: x(:), y(:), phi(:,:)
   integer, intent(out) :: niter
   real(kind=dp) :: dx, dy, l1norm
   real(kind=dp), parameter :: xmax = 2.0_dp, xmin = 0.0_dp, ymax = 1.0_dp, &
      & ymin = 0.0_dp
   real(kind=dp), allocatable :: a(:,:), diff(:,:), err(:,:), pn(:,:)
   
   dx = (xmax - xmin) / real(nx - 1, kind=dp)
   dy = (ymax - ymin) / real(ny - 1, kind=dp)
   x = linspace(xmin, xmax, nx)
   y = linspace(ymin, ymax, ny)
   allocate(phi(ny,nx), source=1.0_dp)
   l1norm = 2 * rtol
   niter = 0
   allocate(pn(ny,nx), diff(ny,nx), a(ny,nx), err(ny,nx))
   do while (merge(.false., merge(0.0_dp, l1norm, ieee_is_nan(l1norm)) > &
      & merge(0.0_dp, rtol, ieee_is_nan(rtol)), ieee_is_nan(l1norm) .or. &
      & ieee_is_nan(rtol)) .and. (niter < maxiter))
      pn = phi
      phi(2:size(phi,1) - 1, 2:size(phi,2) - 1) = ((dy ** 2) * (pn(2:size(pn, &
         & 1) - 1, 3:size(pn,2)) + pn(2:size(pn,1) - 1, 1:size(pn,2) - 2)) + &
         & ((dx ** 2) * (pn(3:size(pn,1), 2:size(pn,2) - 1) + pn(1:size(pn,1) &
         & - 2, 2:size(pn,2) - 1)))) / (2 * (dx ** 2 + dy ** 2))
      phi(:, 1) = 0
      phi(:, size(phi,2)) = y
      phi(1, :) = phi(2, :)
      phi(size(phi,1), :) = phi(size(phi,1) - 1, :)
      diff = phi - pn
      err = abs(diff)
      a = abs(pn)
      l1norm = sum(err) / sum(a)
      niter = niter + 1
   end do
end subroutine laplace_2d

end module run_laplace_2d_proc_mod

program run_laplace_2d
   use run_laplace_2d_proc_mod, only: dp, laplace_2d
   implicit none
   integer :: niter
   real(kind=dp) :: c, e, hi, lo, s
   real(kind=dp), allocatable :: phi(:,:), x(:), y(:)
   
   call laplace_2d(40, 40, 0.0001_dp, 3000, x, y, phi, niter)
   s = sum(phi)
   lo = minval(phi)
   hi = maxval(phi)
   c = phi(21, 21)
   e = phi(11, 31)
   print *, niter, s, lo, hi, c, e
end program run_laplace_2d
