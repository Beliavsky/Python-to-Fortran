program probe
use numpy_fortran, only: np_delete_real_1d, random_gamma, random_binomial, linalg_cholesky, arange_int
use, intrinsic :: iso_fortran_env, only: dp => real64
implicit none
character(32) :: mode
real(dp), allocatable :: a(:), l(:,:)
real(dp) :: g
integer :: n
call get_command_argument(1, mode)
select case (trim(mode))
case ('delete')
    a = np_delete_real_1d([1.0_dp,2.0_dp], 2)
case ('gamma')
    g = random_gamma(-1.0_dp)
case ('binomial')
    n = random_binomial(3, 1.5_dp)
case ('cholesky_shape')
    l = linalg_cholesky(reshape([1.0_dp,2.0_dp], [1,2]))
case ('cholesky_definite')
    l = linalg_cholesky(reshape([-1.0_dp], [1,1]))
case ('valid')
    call pure_check()
case default
    error stop 'unknown test mode'
end select
print *, 'REACHED END'
contains
pure subroutine pure_check()
    real(dp), allocatable :: result(:)
    result = np_delete_real_1d([1.0_dp,2.0_dp,3.0_dp], -1)
    if (size(result) /= 2) error stop 'size'
    if (any(result /= [1.0_dp,2.0_dp])) error stop 'values'
    if (any(arange_int(1,4,1) /= [1,2,3])) error stop 'stop dummy changed'
end subroutine pure_check
end program probe
