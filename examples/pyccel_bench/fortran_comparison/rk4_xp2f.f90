! transpiled by xp2f.py from run_rk4.py on 2026-09-11 08:31:47
module run_rk4_proc_mod
   use python_mod, only: linspace
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dp, humps_deriv, humps_fun, rk4, rk4_humps_test
contains

function rk4_humps_test(t0, t1, n) result(err)
   !
   !     Compute an approximate solution y_h(t) ~= y(t) of the initial
   !     value problem
   !
   !       dy/dt = f(t)
   !       y(t0) = y0
   !
   !     over the interval [t0, t1].
   !
   !     For test purposes we use the method of manufactured solutions,
   !     i.e. we choose the humps function y(t) as the exact solution
   !     and we compute f(t) := dy/dt, which is then passed to the ODE
   !     integrator. Finally the numerical solution y_h(t) is compared to
   !     the exact solution y(t) at the final time t1.
   !
   !     Numerical integration is performed with n uniform steps of the
   !     classical 4th-order Runga Kutta method.
   !
   !     Parameters
   !     ----------
   !     t0 : float
   !         Initial time.
   !
   !     t1 : float
   !         Final time.
   !
   !     n : int
   !         Number of uniform time steps.
   !
   !     Returns
   !     -------
   !     err : float
   !         Difference between numerical and exact solution at the
   !         final time t=t1.
   !
   !
   real(kind=dp), intent(in) :: t0, t1
   integer, intent(in) :: n
   real(kind=dp) :: err
   real(kind=dp), allocatable :: t(:), tspan(:), y0(:), yh(:,:)
   
   tspan = [t0, t1]
   y0 = [humps_fun(t0)]
   t = linspace(t0, t1, n + 1)
   allocate(yh(n + 1,1), source=0.0_dp)
   call rk4(humps_deriv, tspan, y0, n, t, yh)
   err = yh(size(yh,1), 1) - humps_fun(t1)
end function rk4_humps_test

pure function humps_fun(x) result(y)
   !
   !     Humps function
   !
   real(kind=dp), intent(in) :: x
   real(kind=dp) :: y
   
   y = 1.0_dp / ((x - 0.3_dp) ** 2 + 0.01_dp) + (1.0_dp / ((x - 0.9_dp) ** 2 + &
      & 0.04_dp)) - 6.0_dp
end function humps_fun

pure subroutine humps_deriv(x, y, out_)
   !
   !     Derivative of the humps function
   !
   real(kind=dp), intent(in) :: x
   real(kind=dp), intent(in) :: y(:)
   real(kind=dp), intent(inout) :: out_(:)
   out_(1) = (-2.0_dp * (x - 0.3_dp)) / (((x - 0.3_dp) ** 2 + 0.01_dp) ** 2) - &
      & ((2.0_dp * (x - 0.9_dp)) / (((x - 0.9_dp) ** 2 + 0.04_dp) ** 2))
end subroutine humps_deriv

subroutine rk4(dydt, tspan, y0, n, t, y)
   !
   !     Function implementing a fourth order Runge-Kutta method
   !

   interface
      pure subroutine rk4_dydt_cb_if(cb_a1, cb_a2, cb_a3)
         import dp
         real(kind=dp), intent(in) :: cb_a1
         real(kind=dp), intent(in) :: cb_a2(:)
         real(kind=dp), intent(inout) :: cb_a3(:)
      end subroutine rk4_dydt_cb_if
   end interface
   procedure(rk4_dydt_cb_if) :: dydt
   real(kind=dp), intent(in) :: tspan(:), y0(:)
   integer, intent(in) :: n
   real(kind=dp), intent(inout) :: t(:), y(:,:)
   real(kind=dp) :: dt, tfirst, tlast
   integer :: i, m
   real(kind=dp), allocatable :: f1(:), f2(:), f3(:), f4(:)
   
   m = size(y0)
   allocate(f1(m), source=0.0_dp)
   allocate(f2(m), source=0.0_dp)
   allocate(f3(m), source=0.0_dp)
   allocate(f4(m), source=0.0_dp)
   tfirst = tspan(1)
   tlast = tspan(2)
   dt = (tlast - tfirst) / real(n, kind=dp)
   t(1) = tspan(1)
   y(1, :) = y0
   do i = 1, n
      call dydt(t(i), y(i, :), f1)
      call dydt(t(i) + dt / 2.0_dp, y(i, :) + (dt * f1) / 2.0_dp, f2)
      call dydt(t(i) + dt / 2.0_dp, y(i, :) + (dt * f2) / 2.0_dp, f3)
      call dydt(t(i) + dt, y(i, :) + dt * f3, f4)
      t(i + 1) = t(i) + dt
      y(i + 1, :) = y(i, :) + ((dt * (f1 + 2.0_dp * f2 + 2.0_dp * f3 + f4)) / &
         & 6.0_dp)
   end do
end subroutine rk4

end module run_rk4_proc_mod

program run_rk4
   use run_rk4_proc_mod, only: dp, rk4_humps_test
   implicit none
   real(kind=dp) :: err
   
   err = rk4_humps_test(0.0_dp, 2000.0_dp, 2000)
   write(*,"(es0.10)") err
end program run_rk4
