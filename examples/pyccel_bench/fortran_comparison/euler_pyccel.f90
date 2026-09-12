module euler_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T

  implicit none

  public :: euler
  public :: humps_fun
  public :: humps_deriv
  public :: euler_humps_test

  private

  contains

  !........................................
  !________________________________________!
  !                                        !
  !    Function implementing Euler's method!
  !                                        !
  !________________________________________!

  subroutine euler(dydt, tspan, y0, n, t, y) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    real(f64), intent(inout) :: t(0_i64:)
    real(f64), intent(inout) :: y(0_i64:, 0_i64:)
    real(f64) :: t0
    real(f64) :: t1
    real(f64) :: dt
    integer(i64) :: i

    interface
      subroutine dydt(Dummy_0000, Dummy_0001, Dummy_0002) 
        use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
              C_INT64_T

        real(f64), value :: Dummy_0000
        real(f64), intent(inout) :: Dummy_0001(0_i64:)
        real(f64), intent(inout) :: Dummy_0002(0_i64:)
      end subroutine dydt
    end interface

    t0 = tspan(0_i64)
    t1 = tspan(1_i64)
    dt = (t1 - t0) / Real(n, kind = f64)
    y(:, 0_i64) = y0(:)
    do i = 0_i64, n - 1_i64
      call dydt(t(i), y(:, i), y(:, i + 1_i64))
      y(:, i + 1_i64) = y(:, i) + dt * y(:, i + 1_i64)
    end do

  end subroutine euler
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
  !    explicit Euler method.                                          !
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

  function euler_humps_test(t0, t1, n) result(err)

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
    call euler(humps_deriv, tspan, y0, n, t, yh)
    !Error at final time
    err = yh(0_i64, size(yh, 2_i64, i64) - 1_i64) - humps_fun(t1)
    if (allocated(y0)) deallocate(y0)
    if (allocated(t)) deallocate(t)
    if (allocated(yh)) deallocate(yh)
    if (allocated(tspan)) deallocate(tspan)
    return

  end function euler_humps_test
  !........................................

end module euler_mod
