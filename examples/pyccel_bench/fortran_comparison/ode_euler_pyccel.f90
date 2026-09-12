module ode_test

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T

  implicit none

  public :: euler
  public :: midpoint_explicit
  public :: midpoint_fixed
  public :: leapfrog
  public :: rk4
  public :: humps_fun
  public :: humps_deriv
  public :: predator_prey_deriv
  public :: shm_deriv
  public :: euler_humps_test
  public :: midpoint_explicit_humps_test
  public :: midpoint_explicit_predator_prey_test
  public :: midpoint_fixed_humps_test
  public :: midpoint_fixed_predator_prey_test
  public :: leapfrog_shm_test
  public :: rk4_humps_test
  public :: rk4_predator_prey_test

  private

  contains

  !........................................
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
        real(f64), intent(in) :: Dummy_0001(0_i64:)
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
  subroutine midpoint_explicit(dydt, tspan, y0, n, t, y) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    real(f64), intent(inout) :: t(0_i64:)
    real(f64), intent(inout) :: y(0_i64:, 0_i64:)
    integer(i64) :: m
    real(f64), allocatable :: ym(:)
    real(f64) :: dt
    integer(i64) :: i
    real(f64) :: tm

    interface
      subroutine dydt(Dummy_0000, Dummy_0001, Dummy_0002) 
        use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
              C_INT64_T

        real(f64), value :: Dummy_0000
        real(f64), intent(in) :: Dummy_0001(0_i64:)
        real(f64), intent(inout) :: Dummy_0002(0_i64:)
      end subroutine dydt
    end interface

    m = size(y0, kind=i64)
    allocate(ym(0:m - 1_i64))
    ym(:) = 0.0_f64
    dt = (tspan(1_i64) - tspan(0_i64)) / Real(n, kind = f64)
    t(0_i64) = tspan(0_i64)
    y(:, 0_i64) = y0(:)
    do i = 0_i64, n - 1_i64
      tm = t(i) + 0.5_f64 * dt
      call dydt(t(i), y(:, i), ym(:))
      ym(:) = y(:, i) + 0.5_f64 * dt * ym(:)
      t(i + 1_i64) = t(i) + dt
      call dydt(tm, ym(:), y(:, i + 1_i64))
      y(:, i + 1_i64) = y(:, i) + dt * y(:, i + 1_i64)
    end do
    if (allocated(ym)) deallocate(ym)

  end subroutine midpoint_explicit
  !........................................

  !........................................
  subroutine midpoint_fixed(dydt, tspan, y0, n, t, y) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    real(f64), intent(inout) :: t(0_i64:)
    real(f64), intent(inout) :: y(0_i64:, 0_i64:)
    integer(i64) :: m
    real(f64), allocatable :: y1m(:)
    real(f64), allocatable :: y2m(:)
    real(f64) :: dt
    integer(i64) :: it_max
    real(f64) :: theta
    integer(i64) :: i
    real(f64) :: xm
    integer(i64) :: j

    interface
      subroutine dydt(Dummy_0000, Dummy_0001, Dummy_0002) 
        use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
              C_INT64_T

        real(f64), value :: Dummy_0000
        real(f64), intent(in) :: Dummy_0001(0_i64:)
        real(f64), intent(inout) :: Dummy_0002(0_i64:)
      end subroutine dydt
    end interface

    m = size(y0, kind=i64)
    allocate(y1m(0:m - 1_i64))
    y1m(:) = 0.0_f64
    allocate(y2m(0:m - 1_i64))
    y2m(:) = 0.0_f64
    dt = (tspan(1_i64) - tspan(0_i64)) / Real(n, kind = f64)
    it_max = 10_i64
    theta = 0.5_f64
    t(0_i64) = tspan(0_i64)
    y(:, 0_i64) = y0
    do i = 0_i64, n - 1_i64
      xm = t(i) + theta * dt
      y1m(:) = y(:, i)
      do j = 0_i64, it_max - 1_i64
        call dydt(xm, y1m(:), y2m(:))
        y1m(:) = y(:, i) + theta * dt * y2m(:)
      end do
      t(i + 1_i64) = t(i) + dt
      y(:, i + 1_i64) = 1.0_f64 / theta * y1m(:) + (1.0_f64 - 1.0_f64 / &
            theta) * y(:, i)
    end do
    if (allocated(y1m)) deallocate(y1m)
    if (allocated(y2m)) deallocate(y2m)

  end subroutine midpoint_fixed
  !........................................

  !........................................
  subroutine leapfrog(dydt, tspan, y0, n, t, y) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    real(f64), intent(inout) :: t(0_i64:)
    real(f64), intent(inout) :: y(0_i64:, 0_i64:)
    integer(i64) :: m
    real(f64), allocatable, target :: anew(:)
    real(f64) :: t0
    real(f64) :: tstop
    real(f64) :: dt
    integer(i64) :: i
    real(f64), pointer :: aold(:)

    interface
      subroutine dydt(Dummy_0000, Dummy_0001, Dummy_0002) 
        use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
              C_INT64_T

        real(f64), value :: Dummy_0000
        real(f64), intent(in) :: Dummy_0001(0_i64:)
        real(f64), intent(inout) :: Dummy_0002(0_i64:)
      end subroutine dydt
    end interface

    !TODO len(y0) == 2
    m = size(y0, kind=i64)
    allocate(anew(0:m - 1_i64))
    anew(:) = 0.0_f64
    t0 = tspan(0_i64)
    tstop = tspan(1_i64)
    dt = (tstop - t0) / n
    do i = 0_i64, n
      if (i == 0_i64) then
        t(0_i64) = t0
        y(0_i64, 0_i64) = y0(0_i64)
        y(1_i64, 0_i64) = y0(1_i64)
        call dydt(t(i), y(:, i), anew)
      else
        t(i) = t(i - 1_i64) + dt
        aold(0:) => anew
        y(0_i64, i) = y(0_i64, i - 1_i64) + dt * (y(1_i64, i - 1_i64) + &
              0.5_f64 * dt * aold(1_i64))
        call dydt(t(i), y(:, i), anew)
        y(1_i64, i) = y(1_i64, i - 1_i64) + 0.5_f64 * dt * (aold(1_i64) &
              + anew(1_i64))
      end if
    end do
    if (allocated(anew)) deallocate(anew)

  end subroutine leapfrog
  !........................................

  !........................................
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
        real(f64), intent(in) :: Dummy_0001(0_i64:)
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
    if (allocated(f3)) deallocate(f3)
    if (allocated(f4)) deallocate(f4)
    if (allocated(Dummy_0002)) deallocate(Dummy_0002)
    if (allocated(Dummy_0001)) deallocate(Dummy_0001)
    if (allocated(Dummy_0000)) deallocate(Dummy_0000)
    if (allocated(f2)) deallocate(f2)
    if (allocated(f1)) deallocate(f1)

  end subroutine rk4
  !........................................

  !........................................
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
  subroutine predator_prey_deriv(t, rf, out) 

    implicit none

    real(f64), value :: t
    real(f64), intent(inout) :: rf(0_i64:)
    real(f64), intent(inout) :: out(0_i64:)
    real(f64) :: r
    real(f64) :: f
    real(f64) :: drdt
    real(f64) :: dfdt

    r = rf(0_i64)
    f = rf(1_i64)
    drdt = 2.0_f64 * r - 0.001_f64 * r * f
    dfdt = (-10.0_f64) * f + 0.002_f64 * r * f
    out(0_i64) = drdt
    out(1_i64) = dfdt

  end subroutine predator_prey_deriv
  !........................................

  !........................................
  subroutine shm_deriv(x, y, out) 

    implicit none

    real(f64), value :: x
    real(f64), intent(inout) :: y(0_i64:)
    real(f64), intent(inout) :: out(0_i64:)

    out(0_i64) = y(1_i64)
    out(1_i64) = -y(0_i64)

  end subroutine shm_deriv
  !........................................

  !........................................
  subroutine euler_humps_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64) :: t0
    real(f64) :: t1
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)
    integer(i64) :: linspace_index

    m = size(y0, kind=i64)
    t0 = tspan(0_i64)
    t1 = tspan(1_i64)
    allocate(t(0:n))
    t(:) = [((t0 + linspace_index*(t1 - t0) / n), linspace_index = 0_i64 &
          ,n)]
    t(n) = t1

    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call euler(humps_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine euler_humps_test
  !........................................

  !........................................
  subroutine midpoint_explicit_humps_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64) :: t0
    real(f64) :: t1
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)
    integer(i64) :: linspace_index

    m = size(y0, kind=i64)
    t0 = tspan(0_i64)
    t1 = tspan(1_i64)
    allocate(t(0:n))
    t(:) = [((t0 + linspace_index*(t1 - t0) / n), linspace_index = 0_i64 &
          ,n)]
    t(n) = t1

    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call midpoint_explicit(humps_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine midpoint_explicit_humps_test
  !........................................

  !........................................
  subroutine midpoint_explicit_predator_prey_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)

    m = size(y0, kind=i64)
    allocate(t(0:n))
    t(:) = 0.0_f64
    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call midpoint_explicit(predator_prey_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine midpoint_explicit_predator_prey_test
  !........................................

  !........................................
  subroutine midpoint_fixed_humps_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64) :: t0
    real(f64) :: t1
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)
    integer(i64) :: linspace_index

    m = size(y0, kind=i64)
    t0 = tspan(0_i64)
    t1 = tspan(1_i64)
    allocate(t(0:n))
    t(:) = [((t0 + linspace_index*(t1 - t0) / n), linspace_index = 0_i64 &
          ,n)]
    t(n) = t1

    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call midpoint_fixed(humps_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine midpoint_fixed_humps_test
  !........................................

  !........................................
  subroutine midpoint_fixed_predator_prey_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)

    m = size(y0, kind=i64)
    allocate(t(0:n))
    t(:) = 0.0_f64
    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call midpoint_fixed(predator_prey_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine midpoint_fixed_predator_prey_test
  !........................................

  !........................................
  subroutine leapfrog_shm_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)

    m = size(y0, kind=i64)
    allocate(t(0:n))
    t(:) = 0.0_f64
    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call leapfrog(shm_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine leapfrog_shm_test
  !........................................

  !........................................
  subroutine rk4_humps_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)

    m = size(y0, kind=i64)
    allocate(t(0:n))
    t(:) = 0.0_f64
    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call rk4(humps_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine rk4_humps_test
  !........................................

  !........................................
  subroutine rk4_predator_prey_test(tspan, y0, n) 

    implicit none

    real(f64), intent(inout) :: tspan(0_i64:)
    real(f64), intent(inout) :: y0(0_i64:)
    integer(i64), value :: n
    integer(i64) :: m
    real(f64), allocatable :: t(:)
    real(f64), allocatable :: y(:, :)

    m = size(y0, kind=i64)
    allocate(t(0:n))
    t(:) = 0.0_f64
    allocate(y(0:m - 1_i64, 0:n))
    y(:,:) = 0.0_f64
    call rk4(predator_prey_deriv, tspan, y0, n, t, y)
    if (allocated(y)) deallocate(y)
    if (allocated(t)) deallocate(t)

  end subroutine rk4_predator_prey_test
  !........................................

end module ode_test
