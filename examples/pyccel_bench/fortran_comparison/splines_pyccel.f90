module splines

  use, intrinsic :: ISO_C_Binding, only : b1 => C_BOOL , f64 => C_DOUBLE &
        , i64 => C_INT64_T
  use pyc_math_f90

  implicit none

  public :: Spline

  private

  type :: Spline
    integer(i64) :: private_degree
    real(f64), pointer :: private_knots(:)
    real(f64), pointer :: private_coeffs(:)
    logical(b1), private :: is_freed

    contains
    procedure :: init => spline_init
    procedure :: degree => spline_degree
    procedure :: private_basis_funcs => spline_private_basis_funcs
    procedure :: private_find_span => spline_private_find_span
    procedure :: eval => spline_eval
    procedure :: free => spline_free
  end type Spline

  contains


  !........................................

  subroutine spline_init(self, degree, knots, coeffs) 

    implicit none

    class(Spline), intent(inout) :: self
    integer(i64), value :: degree
    real(f64), target, intent(inout) :: knots(0_i64:)
    real(f64), target, intent(inout) :: coeffs(0_i64:)

    self%is_freed = .False._b1
    self%private_degree = degree
    self%private_knots(0:) => knots
    self%private_coeffs(0:) => coeffs

  end subroutine spline_init

  !........................................


  !........................................

  function spline_degree(self) result(result_0001)

    implicit none

    integer(i64) :: result_0001
    class(Spline), intent(inout) :: self

    result_0001 = self%private_degree
    return

  end function spline_degree

  !........................................


  !........................................

  !______________________________________________________________!
  ! Compute non-zero basis functions at x following Algorithm A2.2!
  !        from the NURBS book [1].                              !
  !______________________________________________________________!

  subroutine spline_private_basis_funcs(self, x, span, values) 

    implicit none

    class(Spline), intent(inout) :: self
    real(f64), value :: x
    integer(i64), value :: span
    real(f64), intent(inout) :: values(0_i64:)
    real(f64), allocatable :: left(:)
    real(f64), allocatable :: right(:)
    integer(i64) :: j
    real(f64) :: saved
    integer(i64) :: r
    real(f64) :: temp

    allocate(left(0:self%private_degree - 1_i64))
    allocate(right(0:self%private_degree - 1_i64))
    values(0_i64) = 1.0_f64
    do j = 0_i64, self%private_degree - 1_i64
      left(j) = x - self%private_knots(span - j)
      right(j) = self%private_knots(span + 1_i64 + j) - x
      saved = 0.0_f64
      do r = 0_i64, j
        temp = values(r) / (right(r) + left(j - r))
        values(r) = saved + right(r) * temp
        saved = left(j - r) * temp
      end do
      values(j + 1_i64) = saved
    end do
    if (allocated(right)) deallocate(right)
    if (allocated(left)) deallocate(left)

  end subroutine spline_private_basis_funcs

  !........................................


  !........................................

  function spline_private_find_span(self, x) result(returnVal)

    implicit none

    integer(i64) :: returnVal
    class(Spline), intent(inout) :: self
    real(f64), value :: x
    integer(i64) :: low
    integer(i64) :: high
    integer(i64) :: span

    !Knot index at left/right boundary
    low = self%private_degree
    high = size(self%private_knots, kind=i64) - 1_i64 - self% &
          private_degree
    !Check if point is exactly on left/right boundary, or outside domain
    if (x <= self%private_knots(low)) then
      returnVal = low
    else if (x >= self%private_knots(high)) then
      returnVal = high - 1_i64
    else
      !Perform binary search
      span = pyc_floor_div((low + high), 2_i64)
      do while (x < self%private_knots(span) .or. x >= self% &
            private_knots(span + 1_i64))
        if (x < self%private_knots(span)) then
          high = span
        else
          low = span
        end if
        span = pyc_floor_div((low + high), 2_i64)
      end do
      returnVal = span
    end if
    return

  end function spline_private_find_span

  !........................................


  !........................................

  !________________________________________________________________!
  ! Evaluate spline at non-zero basis elements: sum_i N_i(x) * c_i.!
  !                                                                !
  !________________________________________________________________!

  subroutine spline_eval(self, x, y) 

    implicit none

    class(Spline), intent(inout) :: self
    real(f64), intent(in) :: x(0_i64:)
    real(f64), intent(inout) :: y(0_i64:)
    real(f64), allocatable :: basis(:)
    integer(i64) :: i
    real(f64) :: xi
    integer(i64) :: span
    integer(i64) :: j

    allocate(basis(0:self%private_degree))
    do i = 0_i64, size(x, kind=i64) - 1_i64
      xi = x(i)
      span = self % private_find_span(xi)
      call self % private_basis_funcs(xi, span, basis)
      !Evaluate the spline at xi
      y(i) = 0.0_f64
      do j = 0_i64, self%private_degree
        y(i) = y(i) + self%private_coeffs(span - self%private_degree + j &
              ) * basis(j)
      end do
    end do
    if (allocated(basis)) deallocate(basis)

  end subroutine spline_eval

  !........................................


  !........................................

  subroutine spline_free(self) 

    implicit none

    class(Spline), intent(inout) :: self

    if (.not. self%is_freed) then
      ! pass
      self%is_freed = .True._b1
    end if

  end subroutine spline_free

  !........................................


end module splines
