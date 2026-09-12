! transpiled by xp2f.py from run_ode_euler.py on 2026-09-11 08:28:52
module run_ode_euler_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   integer, parameter :: n = 200 ! constant from python source
   public :: dp, euler, humps_deriv, humps_fun
contains

subroutine euler(dydt, tspan, y0, n, t, y)

   interface
      pure subroutine euler_dydt_cb_if(cb_a1, cb_a2, cb_a3)
         import dp
         real(kind=dp), intent(in) :: cb_a1
         real(kind=dp), intent(in) :: cb_a2(:)
         real(kind=dp), intent(inout) :: cb_a3(:)
      end subroutine euler_dydt_cb_if
   end interface
   procedure(euler_dydt_cb_if) :: dydt
   real(kind=dp), intent(in) :: tspan(:), y0(:), t(:)
   integer, intent(in) :: n
   real(kind=dp), intent(inout) :: y(:,:)
   real(kind=dp) :: dt, t0, t1
   integer :: i
   
   t0 = tspan(1)
   t1 = tspan(2)
   dt = (t1 - t0) / real(n, kind=dp)
   y(1, :) = y0
   do i = 1, n
      call dydt(t(i), y(i, :), y(i + 1, :))
      y(i + 1, :) = y(i, :) + (dt * y(i + 1, :))
   end do
end subroutine euler

pure subroutine humps_deriv(x, y, out_)
   real(kind=dp), intent(in) :: x
   real(kind=dp), intent(in) :: y(:)
   real(kind=dp), intent(inout) :: out_(:)
   out_(1) = (-2.0_dp * (x - 0.3_dp)) / (((x - 0.3_dp) ** 2 + 0.01_dp) ** 2) - &
      & ((2.0_dp * (x - 0.9_dp)) / (((x - 0.9_dp) ** 2 + 0.04_dp) ** 2))
end subroutine humps_deriv

pure function humps_fun(x) result(y)
   real(kind=dp), intent(in) :: x
   real(kind=dp) :: y
   
   y = 1.0_dp / ((x - 0.3_dp) ** 2 + 0.01_dp) + (1.0_dp / ((x - 0.9_dp) ** 2 + &
      & 0.04_dp)) - 6.0_dp
end function humps_fun

end module run_ode_euler_proc_mod

program run_ode_euler
   use run_ode_euler_proc_mod, only: dp, euler, humps_deriv, humps_fun
   use python_mod, only: linspace
   implicit none
   integer, parameter :: n = 200 ! constant from python source
   real(kind=dp) :: err
   real(kind=dp), parameter :: t0 = 0.0_dp, t1 = 2000.0_dp
   real(kind=dp), allocatable :: t(:), tspan(:), y(:,:), y0(:)
   
   tspan = [t0, t1]
   y0 = [humps_fun(t0)]
   t = linspace(t0, t1, n + 1)
   if (allocated(y)) deallocate(y)
   allocate(y(n + 1,1), source=0.0_dp)
   call euler(humps_deriv, tspan, y0, n, t, y)
   err = y(size(y,1), 1) - humps_fun(t1)
   write(*,"(es0.10)") err
end program run_ode_euler
