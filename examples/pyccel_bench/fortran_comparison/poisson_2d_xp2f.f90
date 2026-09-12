! transpiled by xp2f.py from run_poisson_2d.py on 2026-09-11 08:34:03
module run_poisson_2d_proc_mod
   use python_mod, only: linspace
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dp, poisson_2d
contains

pure subroutine poisson_2d(nx, ny, nt, x, y, phi)
   !
   !     Solve the 2D poisson equation for phi(x, y) on the rectangular
   !     domain [0, 2] * [0, 1] with 2 point sources (Dirac deltas) of
   !     charge +1 and -1 respectively, at the positions
   !
   !         (x, y) = (0.5, 0.25) and
   !         (x, y) = (1.5, 0.75),
   !
   !     and subject to the boundary conditions
   !
   !         phi = 0      at x = xmin,
   !         phi = y      at x = xmax,
   !         dphi/dy = 0  at y = ymin,
   !         dphi/dy = 0  at y = ymax.
   !
   !     The numerical solution is computed on a uniform grid using 2nd
   !     order finite differences and the Jacobi method with a fixed
   !     number of iterations.
   !
   !     Parameters
   !     ----------
   !     nx : int
   !         Number of grid points along x axis.
   !
   !     ny : int
   !         Number of grid points along y axis.
   !
   !     nt : int
   !         Number of Jacobi iterations.
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
   !
   integer, intent(in) :: nx, ny, nt
   real(kind=dp), allocatable, intent(out) :: x(:), y(:), phi(:,:)
   real(kind=dp) :: dx, dy
   real(kind=dp), parameter :: xmax = 2.0_dp, xmin = 0.0_dp, ymax = 1.0_dp, &
      & ymin = 0.0_dp
   integer :: i, i_, j
   real(kind=dp), allocatable :: b(:,:), pn(:,:)
   
   dx = (xmax - xmin) / real(nx - 1, kind=dp)
   dy = (ymax - ymin) / real(ny - 1, kind=dp)
   x = linspace(xmin, xmax, nx)
   y = linspace(ymin, ymax, ny)
   allocate(b(ny,nx), source=0.0_dp)
   b(ny / 4 + 1, nx / 4 + 1) = 1.0_dp / (dx * dy)
   b((3 * ny) / 4 + 1, (3 * nx) / 4 + 1) = -1.0_dp / (dx * dy)
   allocate(phi(ny,nx), source=0.0_dp)
   allocate(pn(ny,nx))
   do i_ = 0, nt - 1
      pn = phi
      do j = 1, ny - 1 - 1
         do i = 1, nx - 1 - 1
            phi(j + 1, i + 1) = ((pn(j + 1, i + 1 + 1) + pn(j + 1, i - 1 + 1)) &
               & * (dy ** 2) + (pn(j + 1 + 1, i + 1) + pn(j - 1 + 1, i + 1)) * &
               & (dx ** 2) - ((b(j + 1, i + 1) * (dx ** 2)) * (dy ** 2))) / (2 &
               & * (dx ** 2 + dy ** 2))
         end do
      end do
      phi(:, 1) = 0
      phi(:, size(phi,2)) = y
      phi(1, :) = phi(2, :)
      phi(size(phi,1), :) = phi(size(phi,1) - 1, :)
   end do
end subroutine poisson_2d

end module run_poisson_2d_proc_mod

program run_poisson_2d
   use run_poisson_2d_proc_mod, only: dp, poisson_2d
   implicit none
   real(kind=dp), allocatable :: phi(:,:), x(:), y(:)
   
   call poisson_2d(40, 40, 50, x, y, phi)
   write(*,"(f0.8, 4(1x, f0.8))") sum(phi), minval(phi), maxval(phi), phi(21, &
      & 21), phi(11, 31)
end program run_poisson_2d
