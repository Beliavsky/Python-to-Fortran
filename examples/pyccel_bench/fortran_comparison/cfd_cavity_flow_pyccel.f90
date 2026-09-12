module cfd_python_test

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T
  use pyc_math_f90

  implicit none

  public :: linearconv_1d
  public :: lineardiff_1d
  public :: nonlinearconv_1d
  public :: burgers_1d
  public :: linearconv_2d
  public :: lineardiff_2d
  public :: poisson_2d
  public :: nonlinearconv_2d
  public :: laplace_2d
  public :: burgers_2d
  public :: cavity_flow_2d
  public :: test_linearconv_1d
  public :: test_lineardiff_1d
  public :: test_nonlinearconv_1d
  public :: test_linearconv_2d
  public :: test_lineardiff_2d
  public :: test_poisson_2d
  public :: test_laplace_2d

  private

  contains

  !........................................
  subroutine linearconv_1d(u, un, nt, nx, dt, dx, c) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:)
    real(f64), intent(inout) :: un(0_i64:)
    integer(i64), value :: nt
    integer(i64), value :: nx
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: c
    integer(i64) :: n
    integer(i64) :: i

    do n = 0_i64, nt - 1_i64
      un(:nx - 1_i64) = u(:nx - 1_i64)
      do i = 1_i64, nx - 1_i64
        u(i) = un(i) - c * dt / dx * (un(i) - un(i - 1_i64))
      end do
    end do

  end subroutine linearconv_1d
  !........................................

  !........................................
  subroutine lineardiff_1d(u, un, nt, nx, dt, dx, nu) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:)
    real(f64), intent(inout) :: un(0_i64:)
    integer(i64), value :: nt
    integer(i64), value :: nx
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: nu
    integer(i64) :: n
    integer(i64) :: i

    do n = 0_i64, nt - 1_i64
      un(:) = u(:)
      do i = 1_i64, nx - 2_i64
        u(i) = un(i) + nu * dt / (dx * dx) * (un(i + 1_i64) - 2_i64 * un &
              (i) + un(i - 1_i64))
      end do
    end do

  end subroutine lineardiff_1d
  !........................................

  !........................................
  subroutine nonlinearconv_1d(u, un, nt, nx, dt, dx) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:)
    real(f64), intent(inout) :: un(0_i64:)
    integer(i64), value :: nt
    integer(i64), value :: nx
    real(f64), value :: dt
    real(f64), value :: dx
    integer(i64) :: n
    integer(i64) :: i

    do n = 0_i64, nt - 1_i64
      un(:) = u(:)
      do i = 1_i64, nx - 1_i64
        u(i) = un(i) - un(i) * dt / dx * (un(i) - un(i - 1_i64))
      end do
    end do

  end subroutine nonlinearconv_1d
  !........................................

  !........................................
  subroutine burgers_1d(u, un, nt, nx, dt, dx, nu) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:)
    real(f64), intent(inout) :: un(0_i64:)
    integer(i64), value :: nt
    integer(i64), value :: nx
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: nu
    integer(i64) :: n
    integer(i64) :: i

    do n = 0_i64, nt - 1_i64
      un(:) = u(:)
      do i = 1_i64, nx - 2_i64
        u(i) = un(i) - un(i) * dt / dx * (un(i) - un(i - 1_i64)) + nu * &
              dt / (dx * dx) * (un(i + 1_i64) - 2_i64 * un(i) + un(i - &
              1_i64))
      end do
      u(0_i64) = un(0_i64) - un(0_i64) * dt / dx * (un(0_i64) - un(size( &
            un, kind=i64) - 2_i64)) + nu * dt / (dx * dx) * (un(1_i64) &
            - 2_i64 * un(0_i64) + un(size(un, kind=i64) - 2_i64))
      u(size(u, kind=i64) - 1_i64) = u(0_i64)
    end do

  end subroutine burgers_1d
  !........................................

  !........................................
  subroutine linearconv_2d(u, un, nt, dt, dx, dy, c) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:, 0_i64:)
    real(f64), intent(inout) :: un(0_i64:, 0_i64:)
    integer(i64), value :: nt
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: dy
    real(f64), value :: c
    integer(i64) :: row
    integer(i64) :: col
    integer(i64) :: n
    integer(i64) :: j
    integer(i64) :: i

    row = size(u, 2_i64, i64)
    col = size(u, 1_i64, i64)
    do n = 0_i64, nt
      un(:, :) = u(:, :)
      do j = 1_i64, row - 1_i64
        do i = 1_i64, col - 1_i64
          u(i, j) = un(i, j) - c * dt / dx * (un(i, j) - un(i - 1_i64, j &
                )) - c * dt / dy * (un(i, j) - un(i, j - 1_i64))
          u(:, 0_i64) = 1_i64
          u(:, size(u, 2_i64, i64) - 1_i64) = 1_i64
          u(0_i64, :) = 1_i64
          u(size(u, 1_i64, i64) - 1_i64, :) = 1_i64
        end do
      end do
    end do

  end subroutine linearconv_2d
  !........................................

  !........................................
  subroutine lineardiff_2d(u, un, nt, dt, dx, dy, nu) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:, 0_i64:)
    real(f64), intent(inout) :: un(0_i64:, 0_i64:)
    integer(i64), value :: nt
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: dy
    real(f64), value :: nu
    integer(i64) :: row
    integer(i64) :: col
    integer(i64) :: n
    integer(i64) :: j
    integer(i64) :: i

    row = size(u, 2_i64, i64)
    col = size(u, 1_i64, i64)
    !#Assign initial conditions
    !set hat function I.C. : u(.5<=x<=1 && .5<=y<=1 ) is 2
    u(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64) &
          - 1_i64, Int(0.5_f64 / dy, kind = i64):Int(1_i64 / dy + 1_i64 &
          , kind = i64) - 1_i64) = 2_i64
    do n = 0_i64, nt
      un(:, :) = u(:, :)
      do j = 2_i64, row - 1_i64
        do i = 2_i64, col - 1_i64
          u(i - 1_i64, j - 1_i64) = un(i - 1_i64, j - 1_i64) + nu * dt / &
                (dx * dx) * (un(i, j - 1_i64) - 2_i64 * un(i - 1_i64, j &
                - 1_i64) + un(i - 2_i64, j - 1_i64)) + nu * dt / (dy * &
                dy) * (un(i - 1_i64, j) - 2_i64 * un(i - 1_i64, j - &
                1_i64) + un(i - 1_i64, j - 2_i64))
        end do
      end do
      u(:, 0_i64) = 1_i64
      u(:, size(u, 2_i64, i64) - 1_i64) = 1_i64
      u(0_i64, :) = 1_i64
      u(size(u, 1_i64, i64) - 1_i64, :) = 1_i64
    end do

  end subroutine lineardiff_2d
  !........................................

  !........................................
  subroutine poisson_2d(p, pd, b, nx, ny, nt, dx, dy) 

    implicit none

    real(f64), intent(inout) :: p(0_i64:, 0_i64:)
    real(f64), intent(inout) :: pd(0_i64:, 0_i64:)
    real(f64), intent(inout) :: b(0_i64:, 0_i64:)
    integer(i64), value :: nx
    integer(i64), value :: ny
    integer(i64), value :: nt
    real(f64), value :: dx
    real(f64), value :: dy
    integer(i64) :: row
    integer(i64) :: col
    integer(i64) :: it
    integer(i64) :: j
    integer(i64) :: i

    row = size(p, 2_i64, i64)
    col = size(p, 1_i64, i64)
    !Source
    b(pyc_floor_div(nx, 4_i64), pyc_floor_div(ny, 4_i64)) = 100_i64
    b(pyc_floor_div(3_i64 * nx, 4_i64), pyc_floor_div(3_i64 * ny, 4_i64 &
          )) = -100_i64
    do it = 0_i64, nt - 1_i64
      pd(:, :) = p(:, :)
      do j = 2_i64, row - 1_i64
        do i = 2_i64, col - 1_i64
          p(i - 1_i64, j - 1_i64) = ((pd(i, j - 1_i64) + pd(i - 2_i64, j &
                - 1_i64)) * (dy * dy) + (pd(i - 1_i64, j) + pd(i - &
                1_i64, j - 2_i64)) * (dx * dx) - b(i - 1_i64, j - 1_i64 &
                ) * (dx * dx) * (dy * dy)) / (2_i64 * (dx * dx + dy * &
                dy))
        end do
      end do
      p(:, 0_i64) = 0_i64
      p(:, ny - 1_i64) = 0_i64
      p(0_i64, :) = 0_i64
      p(nx - 1_i64, :) = 0_i64
    end do

  end subroutine poisson_2d
  !........................................

  !........................................
  subroutine nonlinearconv_2d(u, un, v, vn, nt, dt, dx, dy, c) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:, 0_i64:)
    real(f64), intent(inout) :: un(0_i64:, 0_i64:)
    real(f64), intent(inout) :: v(0_i64:, 0_i64:)
    real(f64), intent(inout) :: vn(0_i64:, 0_i64:)
    integer(i64), value :: nt
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: dy
    real(f64), value :: c
    integer(i64) :: row
    integer(i64) :: col
    integer(i64) :: n
    integer(i64) :: j
    integer(i64) :: i

    !##Assign initial conditions
    !#set hat function I.C. : u(.5<=x<=1 && .5<=y<=1 ) is 2
    u(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64) &
          - 1_i64, Int(0.5_f64 / dy, kind = i64):Int(1_i64 / dy + 1_i64 &
          , kind = i64) - 1_i64) = 2_i64
    !#set hat function I.C. : v(.5<=x<=1 && .5<=y<=1 ) is 2
    v(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64) &
          - 1_i64, Int(0.5_f64 / dy, kind = i64):Int(1_i64 / dy + 1_i64 &
          , kind = i64) - 1_i64) = 2_i64
    row = size(u, 2_i64, i64)
    col = size(u, 1_i64, i64)
    do n = 0_i64, nt
      un(:, :) = u(:, :)
      vn(:, :) = v(:, :)
      do j = 1_i64, row - 1_i64
        do i = 1_i64, col - 1_i64
          u(i, j) = un(i, j) - un(i, j) * c * dt / dx * (un(i, j) - un(i &
                - 1_i64, j)) - vn(i, j) * c * dt / dy * (un(i, j) - un( &
                i, j - 1_i64))
          v(i, j) = vn(i, j) - un(i, j) * c * dt / dx * (vn(i, j) - vn(i &
                - 1_i64, j)) - vn(i, j) * c * dt / dy * (vn(i, j) - vn( &
                i, j - 1_i64))
        end do
      end do
      u(:, 0_i64) = 1_i64
      u(:, size(u, 2_i64, i64) - 1_i64) = 1_i64
      u(0_i64, :) = 1_i64
      u(size(u, 1_i64, i64) - 1_i64, :) = 1_i64
      v(:, 0_i64) = 1_i64
      v(:, size(v, 2_i64, i64) - 1_i64) = 1_i64
      v(0_i64, :) = 1_i64
      v(size(v, 1_i64, i64) - 1_i64, :) = 1_i64
    end do

  end subroutine nonlinearconv_2d
  !........................................

  !........................................
  subroutine laplace_2d(p, y, dx, dy, l1norm_target) 

    implicit none

    real(f64), intent(inout) :: p(0_i64:, 0_i64:)
    real(f64), intent(inout) :: y(0_i64:)
    real(f64), value :: dx
    real(f64), value :: dy
    real(f64), value :: l1norm_target
    integer(i64) :: row
    integer(i64) :: col
    real(f64), allocatable :: pn(:, :)
    real(f64) :: l1norm
    real(f64), allocatable :: Dummy_0000(:, :)
    real(f64), allocatable :: Dummy_0001(:, :)

    row = size(p, 2_i64, i64)
    col = size(p, 1_i64, i64)
    allocate(pn(0:col - 1_i64, 0:row - 1_i64))
    l1norm = 1.0_f64
    do while (l1norm > l1norm_target)
      pn(:, :) = p(:, :)
      p(1_i64:size(p, 1_i64, i64) - 2_i64, 1_i64:size(p, 2_i64, i64) - &
            2_i64) = (dy * dy * (pn(2_i64:, 1_i64:size(pn, 2_i64, i64) &
            - 2_i64) + pn(0_i64:size(pn, 1_i64, i64) - 3_i64, 1_i64: &
            size(pn, 2_i64, i64) - 2_i64)) + dx * dx * (pn(1_i64:size( &
            pn, 1_i64, i64) - 2_i64, 2_i64:) + pn(1_i64:size(pn, 1_i64, &
            i64) - 2_i64, 0_i64:size(pn, 2_i64, i64) - 3_i64))) / ( &
            2_i64 * (dx * dx + dy * dy))
      p(0_i64, :) = 0_i64
      p(size(p, 1_i64, i64) - 1_i64, :) = y
      p(:, 0_i64) = p(:, 1_i64)
      p(:, size(p, 2_i64, i64) - 1_i64) = p(:, size(p, 2_i64, i64) - &
            2_i64)
      if (allocated(Dummy_0000)) then
        if (any(size(Dummy_0000) /= [size(p, 1_i64, i64), size(p, 2_i64, &
              i64)])) then
          deallocate(Dummy_0000)
          allocate(Dummy_0000(0:size(p, 1_i64, i64) - 1_i64, 0:size(p, &
                2_i64, i64) - 1_i64))
        end if
      else
        allocate(Dummy_0000(0:size(p, 1_i64, i64) - 1_i64, 0:size(p, &
              2_i64, i64) - 1_i64))
      end if
      Dummy_0000(:,:) = abs(p(:, :)) - abs(pn(:, :))
      if (allocated(Dummy_0001)) then
        if (any(size(Dummy_0001) /= [size(pn, 1_i64, i64), size(pn, &
              2_i64, i64)])) then
          deallocate(Dummy_0001)
          allocate(Dummy_0001(0:size(pn, 1_i64, i64) - 1_i64, 0:size(pn, &
                2_i64, i64) - 1_i64))
        end if
      else
        allocate(Dummy_0001(0:size(pn, 1_i64, i64) - 1_i64, 0:size(pn, &
              2_i64, i64) - 1_i64))
      end if
      Dummy_0001(:,:) = abs(pn(:, :))
      l1norm = sum(Dummy_0000) / sum(Dummy_0001)
    end do
    if (allocated(pn)) deallocate(pn)
    if (allocated(Dummy_0000)) deallocate(Dummy_0000)
    if (allocated(Dummy_0001)) deallocate(Dummy_0001)

  end subroutine laplace_2d
  !........................................

  !........................................
  subroutine burgers_2d(u, un, v, vn, nt, dt, dx, dy, nu) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:, 0_i64:)
    real(f64), intent(inout) :: un(0_i64:, 0_i64:)
    real(f64), intent(inout) :: v(0_i64:, 0_i64:)
    real(f64), intent(inout) :: vn(0_i64:, 0_i64:)
    integer(i64), value :: nt
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: dy
    real(f64), value :: nu
    integer(i64) :: row
    integer(i64) :: col
    integer(i64) :: n
    integer(i64) :: j
    integer(i64) :: i

    !##Assign initial conditions
    !#set hat function I.C. : u(.5<=x<=1 && .5<=y<=1 ) is 2
    u(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64) &
          - 1_i64, Int(0.5_f64 / dy, kind = i64):Int(1_i64 / dy + 1_i64 &
          , kind = i64) - 1_i64) = 2_i64
    !#set hat function I.C. : u(.5<=x<=1 && .5<=y<=1 ) is 2
    v(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64) &
          - 1_i64, Int(0.5_f64 / dy, kind = i64):Int(1_i64 / dy + 1_i64 &
          , kind = i64) - 1_i64) = 2_i64
    row = size(u, 2_i64, i64)
    col = size(u, 1_i64, i64)
    do n = 0_i64, nt
      un(:, :) = u(:, :)
      vn(:, :) = v(:, :)
      do j = 2_i64, row - 1_i64
        do i = 2_i64, col - 1_i64
          u(i - 1_i64, j - 1_i64) = un(j - 1_i64, i - 1_i64) - dt / dx * &
                un(i - 1_i64, j - 1_i64) * (un(i - 1_i64, j - 1_i64) - &
                un(i - 2_i64, j - 1_i64)) - dt / dy * vn(i - 1_i64, j - &
                1_i64) * (un(i - 1_i64, j - 1_i64) - un(i - 1_i64, j - &
                2_i64)) + nu * dt / (dx * dx) * (un(i, j - 1_i64) - &
                2_i64 * un(i - 1_i64, j - 1_i64) + un(i - 2_i64, j - &
                1_i64)) + nu * dt / (dy * dy) * (un(i - 1_i64, j) - &
                2_i64 * un(i - 1_i64, j - 1_i64) + un(i - 1_i64, j - &
                2_i64))
          v(i - 1_i64, j - 1_i64) = vn(i - 1_i64, j - 1_i64) - dt / dx * &
                un(i - 1_i64, j - 1_i64) * (vn(i - 1_i64, j - 1_i64) - &
                vn(i - 2_i64, j - 1_i64)) - dt / dy * vn(i - 1_i64, j - &
                1_i64) * (vn(i - 1_i64, j - 1_i64) - vn(i - 1_i64, j - &
                2_i64)) + nu * dt / (dx * dx) * (vn(i, j - 1_i64) - &
                2_i64 * vn(i - 1_i64, j - 1_i64) + vn(i - 2_i64, j - &
                1_i64)) + nu * dt / (dy * dy) * (vn(i - 1_i64, j) - &
                2_i64 * vn(i - 1_i64, j - 1_i64) + vn(i - 1_i64, j - &
                2_i64))
        end do
      end do
      u(:, 0_i64) = 1_i64
      u(:, size(u, 2_i64, i64) - 1_i64) = 1_i64
      u(0_i64, :) = 1_i64
      u(size(u, 1_i64, i64) - 1_i64, :) = 1_i64
      v(:, 0_i64) = 1_i64
      v(:, size(v, 2_i64, i64) - 1_i64) = 1_i64
      v(0_i64, :) = 1_i64
      v(size(v, 1_i64, i64) - 1_i64, :) = 1_i64
    end do

  end subroutine burgers_2d
  !........................................

  !........................................
  subroutine cavity_flow_2d(u, v, p, nt, dt, dx, dy, rho, nu) 

    implicit none

    real(f64), intent(inout) :: u(0_i64:, 0_i64:)
    real(f64), intent(inout) :: v(0_i64:, 0_i64:)
    real(f64), intent(inout) :: p(0_i64:, 0_i64:)
    integer(i64), value :: nt
    real(f64), value :: dt
    real(f64), value :: dx
    real(f64), value :: dy
    real(f64), value :: rho
    real(f64), value :: nu
    integer(i64) :: row
    integer(i64) :: col
    real(f64), allocatable :: un(:, :)
    real(f64), allocatable :: vn(:, :)
    real(f64), allocatable :: b(:, :)
    integer(i64) :: n
    integer(i64) :: j
    integer(i64) :: i

    !...
    !...
    !...
    !...
    row = size(p, 2_i64, i64)
    col = size(p, 1_i64, i64)
    allocate(un(0:col - 1_i64, 0:row - 1_i64))
    allocate(vn(0:col - 1_i64, 0:row - 1_i64))
    allocate(b(0:col - 1_i64, 0:row - 1_i64))
    b(:,:) = 0.0_f64
    do n = 0_i64, nt - 1_i64
      !... copy u and v to un and vn
      un(:, :) = u(:, :)
      vn(:, :) = v(:, :)
      !...
      call build_up_b(b, rho, dt, u, v, dx, dy)
      call pressure_poisson(p, dx, dy, b)
      do j = 2_i64, row - 1_i64
        do i = 2_i64, col - 1_i64
          u(i - 1_i64, j - 1_i64) = un(i - 1_i64, j - 1_i64) - un(i - &
                1_i64, j - 1_i64) * dt / dx * (un(i - 1_i64, j - 1_i64 &
                ) - un(i - 2_i64, j - 1_i64)) - vn(i - 1_i64, j - 1_i64 &
                ) * dt / dy * (un(i - 1_i64, j - 1_i64) - un(i - 1_i64, &
                j - 2_i64)) - dt / (2_i64 * rho * dx) * (p(i, j - 1_i64 &
                ) - p(i - 2_i64, j - 1_i64)) + nu * (dt / (dx * dx) * ( &
                un(i, j - 1_i64) - 2_i64 * un(i - 1_i64, j - 1_i64) + &
                un(i - 2_i64, j - 1_i64)) + dt / (dy * dy) * (un(i - &
                1_i64, j) - 2_i64 * un(i - 1_i64, j - 1_i64) + un(i - &
                1_i64, j - 2_i64)))
          v(i - 1_i64, j - 1_i64) = vn(i - 1_i64, j - 1_i64) - un(i - &
                1_i64, j - 1_i64) * dt / dx * (vn(i - 1_i64, j - 1_i64 &
                ) - vn(i - 2_i64, j - 1_i64)) - vn(i - 1_i64, j - 1_i64 &
                ) * dt / dy * (vn(i - 1_i64, j - 1_i64) - vn(i - 1_i64, &
                j - 2_i64)) - dt / (2_i64 * rho * dy) * (p(i - 1_i64, j &
                ) - p(i - 1_i64, j - 2_i64)) + nu * (dt / (dx * dx) * ( &
                vn(i, j - 1_i64) - 2_i64 * vn(i - 1_i64, j - 1_i64) + &
                vn(i - 2_i64, j - 1_i64)) + dt / (dy * dy) * (vn(i - &
                1_i64, j) - 2_i64 * vn(i - 1_i64, j - 1_i64) + vn(i - &
                1_i64, j - 2_i64)))
        end do
      end do
      u(:, 0_i64) = 0_i64
      u(0_i64, :) = 0_i64
      u(size(u, 1_i64, i64) - 1_i64, :) = 0_i64
      u(:, size(u, 2_i64, i64) - 1_i64) = 1_i64
      v(:, 0_i64) = 0_i64
      v(:, size(v, 2_i64, i64) - 1_i64) = 0_i64
      v(0_i64, :) = 0_i64
      v(size(v, 1_i64, i64) - 1_i64, :) = 0_i64
    end do
    if (allocated(b)) deallocate(b)
    if (allocated(un)) deallocate(un)
    if (allocated(vn)) deallocate(vn)

    contains
    subroutine build_up_b(b, rho_0001, dt_0001, u_0001, v_0001, dx_0001, &
          dy_0001)

      implicit none

      real(f64), intent(inout) :: b(0_i64:, 0_i64:)
      real(f64), value :: rho_0001
      real(f64), value :: dt_0001
      real(f64), intent(inout) :: u_0001(0_i64:, 0_i64:)
      real(f64), intent(inout) :: v_0001(0_i64:, 0_i64:)
      real(f64), value :: dx_0001
      real(f64), value :: dy_0001
      integer(i64) :: j
      integer(i64) :: i

      row = size(p, 2_i64, i64)
      col = size(p, 1_i64, i64)
      do j = 2_i64, row - 1_i64
        do i = 2_i64, col - 1_i64
          b(i - 1_i64, j - 1_i64) = rho_0001 * (1_i64 / dt_0001 * (( &
                u_0001(i, j - 1_i64) - u_0001(i - 2_i64, j - 1_i64)) / &
                (2_i64 * dx_0001) + (v_0001(i - 1_i64, j) - v_0001(i - &
                1_i64, j - 2_i64)) / (2_i64 * dy_0001)) - ((u_0001(i, j &
                - 1_i64) - u_0001(i - 2_i64, j - 1_i64)) / (2_i64 * &
                dx_0001)) ** 2_i64 - 2_i64 * ((u_0001(i - 1_i64, j) - &
                u_0001(i - 1_i64, j - 2_i64)) / (2_i64 * dy_0001) * ( &
                v_0001(i, j - 1_i64) - v_0001(i - 2_i64, j - 1_i64)) / &
                (2_i64 * dx_0001)) - ((v_0001(i - 1_i64, j) - v_0001(i &
                - 1_i64, j - 2_i64)) / (2_i64 * dy_0001)) ** 2_i64)
        end do
      end do

    end subroutine build_up_b

    subroutine pressure_poisson(p_0001, dx_0001, dy_0001, b) 

      implicit none

      real(f64), intent(inout) :: p_0001(0_i64:, 0_i64:)
      real(f64), value :: dx_0001
      real(f64), value :: dy_0001
      real(f64), intent(inout) :: b(0_i64:, 0_i64:)
      real(f64), allocatable :: pn(:, :)
      integer(i64) :: nit
      integer(i64) :: q
      integer(i64) :: j
      integer(i64) :: i

      row = size(p_0001, 2_i64, i64)
      col = size(p_0001, 1_i64, i64)
      allocate(pn(0:col - 1_i64, 0:row - 1_i64))
      !... copy p to pn
      pn(:, :) = p_0001(:, :)
      !...
      nit = 50_i64
      do q = 0_i64, nit - 1_i64
        !... copy p to pn
        pn(:, :) = p_0001(:, :)
        !...
        do j = 2_i64, row - 1_i64
          do i = 2_i64, col - 1_i64
            p_0001(i - 1_i64, j - 1_i64) = ((pn(i, j - 1_i64) + pn(i - &
                  2_i64, j - 1_i64)) * (dy_0001 * dy_0001) + (pn(i - &
                  1_i64, j) + pn(i - 1_i64, j - 2_i64)) * (dx_0001 * &
                  dx_0001)) / (2_i64 * (dx_0001 * dx_0001 + dy_0001 * &
                  dy_0001)) - dx_0001 * dx_0001 * (dy_0001 * dy_0001) / &
                  (2_i64 * (dx_0001 * dx_0001 + dy_0001 * dy_0001)) * b &
                  (i - 1_i64, j - 1_i64)
          end do
        end do
        p_0001(size(p_0001, 1_i64, i64) - 1_i64, :) = p_0001(size(p_0001 &
              , 1_i64, i64) - 2_i64, :)
        p_0001(:, 0_i64) = p_0001(:, 1_i64)
        p_0001(0_i64, :) = p_0001(1_i64, :)
        p_0001(:, size(p_0001, 2_i64, i64) - 1_i64) = 0_i64
      end do
      if (allocated(pn)) deallocate(pn)

    end subroutine pressure_poisson

  end subroutine cavity_flow_2d
  !........................................

  !........................................
  subroutine test_linearconv_1d(nx, nt, c, dt) 

    implicit none

    integer(i64), value :: nx
    integer(i64), value :: nt
    real(f64), value :: c
    real(f64), value :: dt
    real(f64) :: dx
    real(f64), allocatable :: grid(:)
    real(f64), allocatable :: u0(:)
    real(f64), allocatable :: u(:)
    real(f64), allocatable :: un(:)
    integer(i64) :: linspace_index

    !...
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    allocate(grid(0:nx - 1_i64))
    grid(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64 &
          ) / Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64, &
          nx - 1_i64)]
    grid(nx - 1_i64) = 2.0_f64

    allocate(u0(0:nx - 1_i64))
    u0(:) = 1.0_f64
    u0(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64 &
          ) - 1_i64) = 2_i64
    allocate(u(0:nx - 1_i64))
    u(:) = u0
    allocate(un(0:nx - 1_i64))
    un(:) = 1.0_f64
    !...
    !...
    call linearconv_1d(u, un, nt, nx, dt, dx, c)
    !...
    if (allocated(u)) deallocate(u)
    if (allocated(u0)) deallocate(u0)
    if (allocated(un)) deallocate(un)
    if (allocated(grid)) deallocate(grid)

  end subroutine test_linearconv_1d
  !........................................

  !........................................
  subroutine test_lineardiff_1d(nx, nt, nu) 

    implicit none

    integer(i64), value :: nx
    integer(i64), value :: nt
    real(f64), value :: nu
    real(f64) :: dx
    real(f64) :: CFL
    real(f64) :: dt
    real(f64), allocatable :: grid(:)
    real(f64), allocatable :: u0(:)
    real(f64), allocatable :: u(:)
    real(f64), allocatable :: un(:)
    integer(i64) :: linspace_index

    !...
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    CFL = 0.5_f64
    dt = CFL * (dx * dx) / nu
    allocate(grid(0:nx - 1_i64))
    grid(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64 &
          ) / Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64, &
          nx - 1_i64)]
    grid(nx - 1_i64) = 2.0_f64

    allocate(u0(0:nx - 1_i64))
    u0(:) = 1.0_f64
    u0(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64 &
          ) - 1_i64) = 2_i64
    allocate(u(0:nx - 1_i64))
    u(:) = u0
    allocate(un(0:nx - 1_i64))
    un(:) = 1.0_f64
    !...
    !...
    call lineardiff_1d(u, un, nt, nx, dt, dx, nu)
    !...
    if (allocated(u)) deallocate(u)
    if (allocated(u0)) deallocate(u0)
    if (allocated(un)) deallocate(un)
    if (allocated(grid)) deallocate(grid)

  end subroutine test_lineardiff_1d
  !........................................

  !........................................
  subroutine test_nonlinearconv_1d(nx, nt, c, dt) 

    implicit none

    integer(i64), value :: nx
    integer(i64), value :: nt
    real(f64), value :: c
    real(f64), value :: dt
    real(f64) :: dx
    real(f64), allocatable :: grid(:)
    real(f64), allocatable :: u0(:)
    real(f64), allocatable :: u(:)
    real(f64), allocatable :: un(:)
    integer(i64) :: linspace_index

    !...
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    allocate(grid(0:nx - 1_i64))
    grid(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64 &
          ) / Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64, &
          nx - 1_i64)]
    grid(nx - 1_i64) = 2.0_f64

    allocate(u0(0:nx - 1_i64))
    u0(:) = 1.0_f64
    u0(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64 &
          ) - 1_i64) = 2_i64
    allocate(u(0:nx - 1_i64))
    u(:) = u0
    allocate(un(0:nx - 1_i64))
    un(:) = 1.0_f64
    !...
    !...
    call nonlinearconv_1d(u, un, nt, nx, dt, dx)
    !...
    if (allocated(u)) deallocate(u)
    if (allocated(u0)) deallocate(u0)
    if (allocated(un)) deallocate(un)
    if (allocated(grid)) deallocate(grid)

  end subroutine test_nonlinearconv_1d
  !........................................

  !........................................
  subroutine test_linearconv_2d(nx, ny, nt, c) 

    implicit none

    integer(i64), value :: nx
    integer(i64), value :: ny
    integer(i64), value :: nt
    real(f64), value :: c
    real(f64) :: dx
    real(f64) :: dy
    real(f64) :: sigma
    real(f64) :: dt
    real(f64), allocatable :: x(:)
    real(f64), allocatable :: y(:)
    real(f64), allocatable :: u0(:, :)
    real(f64), allocatable :: u(:, :)
    real(f64), allocatable :: un(:, :)
    integer(i64) :: linspace_index
    integer(i64) :: linspace_index_0001

    !...
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    dy = 2.0_f64 / Real((ny - 1_i64), kind = f64)
    sigma = 0.2_f64
    dt = sigma * dx
    allocate(x(0:nx - 1_i64))
    x(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64) / &
          Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64,nx - &
          1_i64)]
    x(nx - 1_i64) = 2.0_f64

    allocate(y(0:ny - 1_i64))
    y(:) = [((0_i64 + linspace_index_0001*Real((2_i64 - 0_i64), kind = &
          f64) / Real((ny - 1_i64), kind = f64)), linspace_index_0001 = &
          0_i64,ny - 1_i64)]
    y(ny - 1_i64) = 2.0_f64

    allocate(u0(0:nx - 1_i64, 0:ny - 1_i64))
    u0(:,:) = 1.0_f64
    u0(Int(0.5_f64 / dx, kind = i64):Int(1_i64 / dx + 1_i64, kind = i64 &
          ) - 1_i64, Int(0.5_f64 / dy, kind = i64):Int(1_i64 / dy + &
          1_i64, kind = i64) - 1_i64) = 2_i64
    allocate(u(0:nx - 1_i64, 0:ny - 1_i64))
    u(:, :) = u0
    allocate(un(0:nx - 1_i64, 0:ny - 1_i64))
    un(:,:) = 1.0_f64
    !...
    !...
    call linearconv_2d(u, un, nt, dt, dx, dy, c)
    !...
    if (allocated(x)) deallocate(x)
    if (allocated(un)) deallocate(un)
    if (allocated(u)) deallocate(u)
    if (allocated(y)) deallocate(y)
    if (allocated(u0)) deallocate(u0)

  end subroutine test_linearconv_2d
  !........................................

  !........................................
  subroutine test_lineardiff_2d(nt, nx, ny, nu) 

    implicit none

    integer(i64), value :: nt
    integer(i64), value :: nx
    integer(i64), value :: ny
    real(f64), value :: nu
    real(f64) :: dx
    real(f64) :: dy
    real(f64) :: sigma
    real(f64) :: dt
    real(f64), allocatable :: x(:)
    real(f64), allocatable :: y(:)
    real(f64), allocatable :: u(:, :)
    real(f64), allocatable :: un(:, :)
    integer(i64) :: linspace_index
    integer(i64) :: linspace_index_0001

    !...
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    dy = 2.0_f64 / Real((ny - 1_i64), kind = f64)
    sigma = 0.25_f64
    dt = sigma * dx * dy / nu
    allocate(x(0:nx - 1_i64))
    x(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64) / &
          Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64,nx - &
          1_i64)]
    x(nx - 1_i64) = 2.0_f64

    allocate(y(0:ny - 1_i64))
    y(:) = [((0_i64 + linspace_index_0001*Real((2_i64 - 0_i64), kind = &
          f64) / Real((ny - 1_i64), kind = f64)), linspace_index_0001 = &
          0_i64,ny - 1_i64)]
    y(ny - 1_i64) = 2.0_f64

    allocate(u(0:nx - 1_i64, 0:ny - 1_i64))
    u(:,:) = 1.0_f64
    allocate(un(0:nx - 1_i64, 0:ny - 1_i64))
    un(:,:) = 1.0_f64
    !...
    !...
    call lineardiff_2d(u, un, nt, dt, dx, dy, nu)
    !...
    if (allocated(x)) deallocate(x)
    if (allocated(u)) deallocate(u)
    if (allocated(un)) deallocate(un)
    if (allocated(y)) deallocate(y)

  end subroutine test_lineardiff_2d
  !........................................

  !........................................
  subroutine test_poisson_2d(nx, ny, nt) 

    implicit none

    integer(i64), value :: nx
    integer(i64), value :: ny
    integer(i64), value :: nt
    integer(i64) :: xmin
    integer(i64) :: xmax
    integer(i64) :: ymin
    integer(i64) :: ymax
    real(f64) :: dx
    real(f64) :: dy
    real(f64), allocatable :: p(:, :)
    real(f64), allocatable :: pd(:, :)
    real(f64), allocatable :: b(:, :)
    real(f64), allocatable :: x(:)
    real(f64), allocatable :: y(:)
    integer(i64) :: linspace_index
    integer(i64) :: linspace_index_0001

    !...
    xmin = 0_i64
    xmax = 2_i64
    ymin = 0_i64
    ymax = 1_i64
    dx = Real((xmax - xmin), kind = f64) / Real((nx - 1_i64), kind = f64 &
          )
    dy = Real((ymax - ymin), kind = f64) / Real((ny - 1_i64), kind = f64 &
          )
    !Initialization
    allocate(p(0:nx - 1_i64, 0:ny - 1_i64))
    p(:,:) = 0.0_f64
    allocate(pd(0:nx - 1_i64, 0:ny - 1_i64))
    pd(:,:) = 0.0_f64
    allocate(b(0:nx - 1_i64, 0:ny - 1_i64))
    b(:,:) = 0.0_f64
    allocate(x(0:nx - 1_i64))
    x(:) = [((xmin + linspace_index*Real((xmax - xmin), kind = f64) / &
          Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64,nx - &
          1_i64)]
    x(nx - 1_i64) = Real(xmax, kind = f64)

    allocate(y(0:ny - 1_i64))
    y(:) = [((xmin + linspace_index_0001*Real((xmax - xmin), kind = f64 &
          ) / Real((ny - 1_i64), kind = f64)), linspace_index_0001 = &
          0_i64,ny - 1_i64)]
    y(ny - 1_i64) = Real(xmax, kind = f64)

    !...
    !...
    call poisson_2d(p, pd, b, nx, ny, nt, dx, dy)
    !...
    if (allocated(p)) deallocate(p)
    if (allocated(pd)) deallocate(pd)
    if (allocated(b)) deallocate(b)
    if (allocated(x)) deallocate(x)
    if (allocated(y)) deallocate(y)

  end subroutine test_poisson_2d
  !........................................

  !........................................
  subroutine test_laplace_2d(nx, ny, c, l1norm_target) 

    implicit none

    integer(i64), value :: nx
    integer(i64), value :: ny
    real(f64), value :: c
    real(f64), value :: l1norm_target
    real(f64) :: dx
    real(f64) :: dy
    real(f64), allocatable :: p(:, :)
    real(f64), allocatable :: x(:)
    real(f64), allocatable :: y(:)
    integer(i64) :: linspace_index
    integer(i64) :: linspace_index_0001

    !...
    dx = 2.0_f64 / Real((nx - 1_i64), kind = f64)
    dy = 2.0_f64 / Real((ny - 1_i64), kind = f64)
    allocate(p(0:nx - 1_i64, 0:ny - 1_i64))
    p(:,:) = 0.0_f64
    allocate(x(0:nx - 1_i64))
    x(:) = [((0_i64 + linspace_index*Real((2_i64 - 0_i64), kind = f64) / &
          Real((nx - 1_i64), kind = f64)), linspace_index = 0_i64,nx - &
          1_i64)]
    x(nx - 1_i64) = 2.0_f64

    allocate(y(0:ny - 1_i64))
    y(:) = [((0_i64 + linspace_index_0001*Real((1_i64 - 0_i64), kind = &
          f64) / Real((ny - 1_i64), kind = f64)), linspace_index_0001 = &
          0_i64,ny - 1_i64)]
    y(ny - 1_i64) = 1.0_f64

    p(0_i64, :) = 0_i64
    p(size(p, 1_i64, i64) - 1_i64, :) = y
    p(:, 0_i64) = p(:, 1_i64)
    p(:, size(p, 2_i64, i64) - 1_i64) = p(:, size(p, 2_i64, i64) - 2_i64 &
          )
    !...
    !...
    call laplace_2d(p, y, dx, dy, l1norm_target)
    !...
    if (allocated(x)) deallocate(x)
    if (allocated(p)) deallocate(p)
    if (allocated(y)) deallocate(y)

  end subroutine test_laplace_2d
  !........................................

end module cfd_python_test
