! transpiled by xp2f.py from run_splines.py on 2026-09-11 08:30:33
module run_splines_proc_mod
   use, intrinsic :: ieee_arithmetic, only: ieee_is_nan
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   type :: Spline_t
      integer :: v_degree
      real(kind=dp), allocatable :: v_knots(:), v_coeffs(:)
   end type Spline_t
   public :: Spline__basis_funcs, Spline__find_span, Spline_eval, Spline_t, dp
contains

pure subroutine Spline__basis_funcs(self, x, span, values)
   !  Compute non-zero basis functions at x following Algorithm A2.2
   !         from the NURBS book [1].
   type(Spline_t), intent(in) :: self
   real(kind=dp), intent(in) :: x
   integer, intent(in) :: span
   real(kind=dp), intent(inout) :: values(:)
   real(kind=dp) :: saved, temp
   integer :: j, r
   real(kind=dp), allocatable :: left(:), right(:)
   
   allocate(left(self%v_degree), right(self%v_degree))
   values(1) = 1.0_dp
   do j = 0, self%v_degree - 1
      left(j + 1) = x - self%v_knots(span - j + 1)
      right(j + 1) = self%v_knots(span + 1 + j + 1) - x
      saved = 0.0_dp
      do r = 0, j
         temp = values(r + 1) / (right(r + 1) + left(j - r + 1))
         values(r + 1) = saved + (right(r + 1) * temp)
         saved = left(j - r + 1) * temp
      end do
      values(j + 1 + 1) = saved
   end do
end subroutine Spline__basis_funcs

pure subroutine Spline_eval(self, x, y)
   !  Evaluate spline at non-zero basis elements: sum_i N_i(x) * c_i.
   !
   type(Spline_t), intent(in) :: self
   real(kind=dp), intent(in) :: x(:)
   real(kind=dp), intent(inout) :: y(:)
   real(kind=dp) :: span, xi
   integer :: i, j
   real(kind=dp), allocatable :: basis(:)
   allocate(basis(self%v_degree + 1))
   block
      integer :: i_1
      do i_1 = 1, size(x)
         i = i_1 - 1
         xi = x(i_1)
         span = Spline__find_span(self, xi)
         call Spline__basis_funcs(self, xi, int(span), basis)
         y(i + 1) = 0.0_dp
         do j = 0, self%v_degree
            y(i + 1) = y(i + 1) + (self%v_coeffs(span - self%v_degree + j + 1) &
               & * basis(j + 1))
         end do
      end do
   end block
end subroutine Spline_eval

pure function Spline__find_span(self, x) result(returnVal)
   type(Spline_t), intent(in) :: self
   real(kind=dp), intent(in) :: x
   integer :: returnVal
   integer :: high, low, span
   
   low = self%v_degree
   high = size(self%v_knots) - 1 - self%v_degree
   if (merge(.false., merge(0.0_dp, x, ieee_is_nan(x)) <= self%v_knots(low + &
      & 1), ieee_is_nan(x))) then
      returnVal = low
   else
      if (merge(.false., merge(0.0_dp, x, ieee_is_nan(x)) >= self%v_knots(high &
         & + 1), ieee_is_nan(x))) then
         returnVal = high - 1
      else
         span = (low + high) / 2
         do while (merge(.false., merge(0.0_dp, x, ieee_is_nan(x)) < &
            & self%v_knots(span + 1), ieee_is_nan(x)) .or. merge(.false., &
            & merge(0.0_dp, x, ieee_is_nan(x)) >= self%v_knots(span + 1 + 1), &
            & ieee_is_nan(x)))
            if (merge(.false., merge(0.0_dp, x, ieee_is_nan(x)) < &
               & self%v_knots(span + 1), ieee_is_nan(x))) then
               high = span
            else
               low = span
            end if
            span = (low + high) / 2
         end do
         returnVal = span
      end if
   end if
end function Spline__find_span

end module run_splines_proc_mod

program run_splines
   use run_splines_proc_mod, only: Spline_eval, Spline_t, dp
   use python_mod, only: linspace
   implicit none
   type(Spline_t) :: s
   real(kind=dp), parameter :: x(*) = [0.05_dp, 0.2_dp, 0.35_dp, 0.5_dp, &
      & 0.65_dp, 0.8_dp, 0.95_dp]
   real(kind=dp), allocatable :: y(:)
   
   s = Spline_t(v_degree=3, v_knots=linspace(0.0_dp, 1.0_dp, 20), &
      & v_coeffs=linspace(1.0_dp, 2.0_dp, 16))
   allocate(y(size(x)))
   call Spline_eval(s, x, y)
   print *, y
end program run_splines
