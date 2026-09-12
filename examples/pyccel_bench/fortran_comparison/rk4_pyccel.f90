module rk4_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T

  implicit none

  public :: rk4
  public :: humps_fun
  public :: humps_deriv
  public :: rk4_humps_test

  private

  contains

  !........................................
  !__________________________________________________________!
  !                                                          !
  !    Function implementing a fourth order Runge-Kutta method!
  !                                                          !
  !__________________________________________________________!

  subroutine rk4(dydt, tspan, y0, n, t, y) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    real(f64), intent(inout) :: t(0_i64:)
    real(f64), intent(inout) :: y(0_i64:, 0_i64:)
    integer(i64) :: m
    real(f64), allocatable :: f1(:)
    real(f64), allocatable :: f2(:)
    real(f64), allocatable :: f3(:)
    real(f64), allocatable :: f4(:)
    real(f64) :: tfirst
    real(f64) :: tlast
    real(f64) :: dt
    integer(i64) :: i
    real(f64), allocatable :: Dummy_0000(:)
    real(f64), allocatable :: Dummy_0001(:)
    real(f64), allocatable :: Dummy_0002(:)

    interface
      subroutine dydt(Dummy_0000, Dummy_0001, Dummy_0002) 
        use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
              C_INT64_T

        real(f64), value :: Dummy_0000
        real(f64), intent(inout) :: Dummy_0001(0_i64:)
        real(f64), intent(inout) :: Dummy_0002(0_i64:)
      end subroutine dydt
    end interface

    m = size(y0, kind=i64)
    allocate(f1(0:m - 1_i64))
    f1(:) = 0.0_f64
    allocate(f2(0:m - 1_i64))
    f2(:) = 0.0_f64
    allocate(f3(0:m - 1_i64))
    f3(:) = 0.0_f64
    allocate(f4(0:m - 1_i64))
    f4(:) = 0.0_f64
    tfirst = tspan(0_i64)
    tlast = tspan(1_i64)
    dt = (tlast - tfirst) / n
    t(0_i64) = tspan(0_i64)
    y(:, 0_i64) = y0(:)
    do i = 0_i64, n - 1_i64
      call dydt(t(i), y(:, i), f1(:))
      if (allocated(Dummy_0000)) then
        if (any(size(Dummy_0000) /= [size(y, 1_i64, i64)])) then
          deallocate(Dummy_0000)
          allocate(Dummy_0000(0:size(y, 1_i64, i64) - 1_i64))
        end if
      else
        allocate(Dummy_0000(0:size(y, 1_i64, i64) - 1_i64))
      end if
      Dummy_0000(:) = y(:, i) + dt * f1(:) / 2.0_f64
      call dydt(t(i) + dt / 2.0_f64, Dummy_0000, f2(:))
      if (allocated(Dummy_0001)) then
        if (any(size(Dummy_0001) /= [size(y, 1_i64, i64)])) then
          deallocate(Dummy_0001)
          allocate(Dummy_0001(0:size(y, 1_i64, i64) - 1_i64))
        end if
      else
        allocate(Dummy_0001(0:size(y, 1_i64, i64) - 1_i64))
      end if
      Dummy_0001(:) = y(:, i) + dt * f2(:) / 2.0_f64
      call dydt(t(i) + dt / 2.0_f64, Dummy_0001, f3(:))
      if (allocated(Dummy_0002)) then
        if (any(size(Dummy_0002) /= [size(y, 1_i64, i64)])) then
          deallocate(Dummy_0002)
          allocate(Dummy_0002(0:size(y, 1_i64, i64) - 1_i64))
        end if
      else
        allocate(Dummy_0002(0:size(y, 1_i64, i64) - 1_i64))
      end if
      Dummy_0002(:) = y(:, i) + dt * f3(:)
      call dydt(t(i) + dt, Dummy_0002, f4(:))
      t(i + 1_i64) = t(i) + dt
      y(:, i + 1_i64) = y(:, i) + dt * (f1(:) + 2.0_f64 * f2(:) + &
            2.0_f64 * f3(:) + f4(:)) / 6.0_f64
    end do
    if (allocated(Dummy_0002)) deallocate(Dummy_0002)
    if (allocated(f1)) deallocate(f1)
    if (allocated(f2)) deallocate(f2)
    if (allocated(f3)) deallocate(f3)
    if (allocated(f4)) deallocate(f4)
    if (allocated(Dummy_0000)) deallocate(Dummy_0000)
    if (allocated(Dummy_0001)) deallocate(Dummy_0001)

  end subroutine rk4
  !........................................

  !........................................
  !____________________!
  !                    !
  !    Humps function  !
  !                    !
  !____________________!

  function humps_fun(x) result(y)

    implicit none

    real(f64) :: y
    real(f64), value :: x

    y = 1.0_f64 / ((x - 0.3_f64) ** 2_i64 + 0.01_f64) + 1.0_f64 / ((x - &
          0.9_f64) ** 2_i64 + 0.04_f64) - 6.0_f64
    return

  end function humps_fun
  !........................................

  !........................................
  !____________________________________!
  !                                    !
  !    Derivative of the humps function!
  !                                    !
  !____________________________________!

  subroutine humps_deriv(x, y, out) 

    implicit none

    real(f64), value :: x
    real(f64), intent(inout) :: y(0_i64:)
    real(f64), intent(inout) :: out(0_i64:)

    out(0_i64) = (-2.0_f64) * (x - 0.3_f64) / ((x - 0.3_f64) ** 2_i64 + &
          0.01_f64) ** 2_i64 - 2.0_f64 * (x - 0.9_f64) / ((x - 0.9_f64 &
          ) ** 2_i64 + 0.04_f64) ** 2_i64

  end subroutine humps_deriv
  !........................................

  !........................................
  !____________________________________________________________________!
  !                                                                    !
  !    Compute an approximate solution y_h(t) ~= y(t) of the initial   !
  !    value problem                                                   !
  !                                                                    !
  !      dy/dt = f(t)                                                  !
  !      y(t0) = y0                                                    !
  !                                                                    !
  !    over the interval [t0, t1].                                     !
  !                                                                    !
  !    For test purposes we use the method of manufactured solutions,  !
  !    i.e. we choose the humps function y(t) as the exact solution    !
  !    and we compute f(t) := dy/dt, which is then passed to the ODE   !
  !    integrator. Finally the numerical solution y_h(t) is compared to!
  !    the exact solution y(t) at the final time t1.                   !
  !                                                                    !
  !    Numerical integration is performed with n uniform steps of the  !
  !    classical 4th-order Runga Kutta method.                         !
  !                                                                    !
  !    Parameters                                                      !
  !    ----------                                                      !
  !    t0 : float                                                      !
  !        Initial time.                                               !
  !                                                                    !
  !    t1 : float                                                      !
  !        Final time.                                                 !
  !                                                                    !
  !    n : int                                                         !
  !        Number of uniform time steps.                               !
  !                                                                    !
  !    Returns                                                         !
  !    -------                                                         !
  !    err : float                                                     !
  !        Difference between numerical and exact solution at the      !
  !        final time t=t1.                                            !
  !                                                                    !
  !                                                                    !
  !____________________________________________________________________!

  function rk4_humps_test(t0, t1, n) result(err)

    implicit none

    real(f64) :: err
    real(f64), value :: t0
    real(f64), value :: t1
    integer(i64), value :: n
    real(f64), allocatable :: tspan(:)
    real(f64), allocatable :: y0(:)
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: yh(:, :)
    integer(i64) :: linspace_index

    !Time interval and initial conditions
    allocate(tspan(0:1_i64))
    tspan(:) = [t0, t1]
    allocate(y0(0:0_i64))
    y0(:) = [humps_fun(t0)]
    !Uniform time array where solution should be computed
    allocate(t(0:n))
    t(:) = [((t0 + linspace_index*(t1 - t0) / n), linspace_index = 0_i64 &
          ,n)]
    t(n) = t1

    !Empty array which will contain numerical solution
    allocate(yh(0:0_i64, 0:n))
    yh(:,:) = 0.0_f64
    !Time integration
    call rk4(humps_deriv, tspan, y0, n, t, yh)
    !Error at final time
    err = yh(0_i64, size(yh, 2_i64, i64) - 1_i64) - humps_fun(t1)
    if (allocated(tspan)) deallocate(tspan)
    if (allocated(yh)) deallocate(yh)
    if (allocated(y0)) deallocate(y0)
    if (allocated(t)) deallocate(t)
    return

  end function rk4_humps_test
  !........................................

end module rk4_mod
