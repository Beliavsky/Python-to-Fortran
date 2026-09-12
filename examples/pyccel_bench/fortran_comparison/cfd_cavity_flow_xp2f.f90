! transpiled by xp2f.py from run_cfd_cavity_flow.py on 2026-09-11 08:33:20
module run_cfd_cavity_flow_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   integer, parameter :: nt = 5 ! constant from python source
   real(kind=dp), allocatable :: closure_cavity_flow_2d_p(:,:)
   public :: build_up_b, cavity_flow_2d, closure_cavity_flow_2d_p, dp, &
      & pressure_poisson
contains

pure subroutine build_up_b(b, rho, dt, u, v, dx, dy)
   real(kind=dp), intent(inout) :: b(:,:)
   real(kind=dp), intent(in) :: rho, dt, dx, dy
   real(kind=dp), intent(in) :: u(:,:), v(:,:)
   integer :: col, i, j, row
   
   row = size(closure_cavity_flow_2d_p,1)
   col = size(closure_cavity_flow_2d_p,2)
   do j = 2, row - 1
      do i = 2, col - 1
         b(j - 1 + 1, i - 1 + 1) = rho * ((real(1, &
            & kind=dp) / dt) * ((u(j - 1 + 1, i + 1) - u(j - 1 + 1, i - 2 + &
            & 1)) / (2 * dx) + ((v(j + 1, i - 1 + 1) - v(j - 2 + 1, i - 1 + &
            & 1)) / (2 * dy))) - (((u(j - 1 + 1, i + 1) - u(j - 1 + 1, i - 2 + &
            & 1)) / (2 * dx)) ** 2) - (2 * ((((u(j + 1, i - 1 + 1) - u(j - 2 + &
            & 1, i - 1 + 1)) / (2 * dy)) * (v(j - 1 + 1, i + 1) - v(j - 1 + 1, &
            & i - 2 + 1))) / (2 * dx))) - (((v(j + 1, i - 1 + 1) - v(j - 2 + &
            & 1, i - 1 + 1)) / (2 * dy)) ** 2))
      end do
   end do
end subroutine build_up_b

pure subroutine pressure_poisson(p, dx, dy, b)
   real(kind=dp), intent(inout) :: p(:,:)
   real(kind=dp), intent(in) :: dx, dy
   real(kind=dp), intent(in) :: b(:,:)
   integer :: col, i, j, q, row
   integer, parameter :: nit = 50
   real(kind=dp), allocatable :: pn(:,:)
   
   row = size(p,1)
   col = size(p,2)
   allocate(pn(row,col))
   pn = p
   do q = 0, nit - 1
      pn = p
      do j = 2, row - 1
         do i = 2, col - 1
            p(j - 1 + 1, i - 1 + 1) = ((pn(j - 1 + 1, i + 1) + pn(j - 1 + 1, i &
               & - 2 + 1)) * (dy ** 2) + ((pn(j + 1, i - 1 + 1) + pn(j - 2 + &
               & 1, i - 1 + 1)) * (dx ** 2))) / (2 * (dx ** 2 + dy ** 2)) - &
               & ((((dx ** 2) * (dy ** 2)) / (2 * (dx ** 2 + (dy ** 2)))) * &
               & b(j - 1 + 1, i - 1 + 1))
         end do
      end do
      p(:, size(p,2)) = p(:, size(p,2) - 1)
      p(1, :) = p(2, :)
      p(:, 1) = p(:, 2)
      p(size(p,1), :) = 0
   end do
end subroutine pressure_poisson

subroutine cavity_flow_2d(u, v, p, nt, dt, dx, dy, rho, nu)
   real(kind=dp), intent(inout) :: u(:,:), v(:,:), p(:,:)
   integer, intent(in) :: nt
   real(kind=dp), intent(in) :: dt, dx, dy, rho, nu
   integer :: col, i, j, n, row
   real(kind=dp), allocatable :: b(:,:), un(:,:), vn(:,:)
   
   row = size(p,1)
   col = size(p,2)
   allocate(un(row,col), vn(row,col))
   allocate(b(row,col), source=0.0_dp)
   do n = 0, nt - 1
      un = u
      vn = v
      closure_cavity_flow_2d_p = p
      call build_up_b(b, rho, dt, u, v, dx, dy)
      call pressure_poisson(p, dx, dy, b)
      do j = 2, row - 1
         do i = 2, col - 1
            u(j - 1 + 1, i - 1 + 1) = un(j - 1 + 1, i - 1 + 1) - (((un(j - 1 + &
               & 1, i - 1 + 1) * dt) / dx) * (un(j - 1 + 1, i - 1 + 1) - un(j &
               & - 1 + 1, i - 2 + 1))) - (((vn(j - 1 + 1, i - 1 + 1) * dt) / &
               & dy) * (un(j - 1 + 1, i - 1 + 1) - un(j - 2 + 1, i - 1 + 1))) &
               & - ((dt / ((2 * rho) * dx)) * (p(j - 1 + 1, i + 1) - p(j - 1 + &
               & 1, i - 2 + 1))) + (nu * ((dt / (dx ** 2)) * (un(j - 1 + 1, i &
               & + 1) - (2 * un(j - 1 + 1, i - 1 + 1)) + un(j - 1 + 1, i - 2 + &
               & 1)) + ((dt / (dy ** 2)) * (un(j + 1, i - 1 + 1) - (2 * un(j - &
               & 1 + 1, i - 1 + 1)) + un(j - 2 + 1, i - 1 + 1)))))
            v(j - 1 + 1, i - 1 + 1) = vn(j - 1 + 1, i - 1 + 1) - (((un(j - 1 + &
               & 1, i - 1 + 1) * dt) / dx) * (vn(j - 1 + 1, i - 1 + 1) - vn(j &
               & - 1 + 1, i - 2 + 1))) - (((vn(j - 1 + 1, i - 1 + 1) * dt) / &
               & dy) * (vn(j - 1 + 1, i - 1 + 1) - vn(j - 2 + 1, i - 1 + 1))) &
               & - ((dt / ((2 * rho) * dy)) * (p(j + 1, i - 1 + 1) - p(j - 2 + &
               & 1, i - 1 + 1))) + (nu * ((dt / (dx ** 2)) * (vn(j - 1 + 1, i &
               & + 1) - (2 * vn(j - 1 + 1, i - 1 + 1)) + vn(j - 1 + 1, i - 2 + &
               & 1)) + ((dt / (dy ** 2)) * (vn(j + 1, i - 1 + 1) - (2 * vn(j - &
               & 1 + 1, i - 1 + 1)) + vn(j - 2 + 1, i - 1 + 1)))))
         end do
      end do
      u(1, :) = 0
      u(:, 1) = 0
      u(:, size(u,2)) = 0
      u(size(u,1), :) = 1
      v(1, :) = 0
      v(size(v,1), :) = 0
      v(:, 1) = 0
      v(:, size(v,2)) = 0
   end do
end subroutine cavity_flow_2d

end module run_cfd_cavity_flow_proc_mod

program run_cfd_cavity_flow
   use run_cfd_cavity_flow_proc_mod, only: cavity_flow_2d, dp
   implicit none
   integer, parameter :: nx = 8 ! constant from python source
   integer, parameter :: ny = 8 ! constant from python source
   integer, parameter :: nt = 5 ! constant from python source
   real(kind=dp), parameter :: dt = 0.001_dp, nu = 0.1_dp, rho = 1.0_dp
   real(kind=dp) :: dx, dy
   real(kind=dp), allocatable :: p(:,:), u(:,:), v(:,:)
   
   dx = 2.0_dp / real(nx - 1, kind=dp)
   dy = 2.0_dp / real(ny - 1, kind=dp)
   if (allocated(u)) deallocate(u)
   allocate(u(ny,nx), source=0.0_dp)
   if (allocated(v)) deallocate(v)
   allocate(v(ny,nx), source=0.0_dp)
   if (allocated(p)) deallocate(p)
   allocate(p(ny,nx), source=0.0_dp)
   call cavity_flow_2d(u, v, p, nt, dt, dx, dy, rho, nu)
   write(*,"(f0.8, 8(1x, f0.8))") sum(u), minval(u), maxval(u), sum(v), &
      & minval(v), maxval(v), sum(p), minval(p), maxval(p)
end program run_cfd_cavity_flow
