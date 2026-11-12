program main
use numpy_fortran
use, intrinsic :: iso_fortran_env, only: dp => real64, int64
implicit none
call checks()
print *, 'PASS elemental arrays'
contains
pure subroutine checks()

integer :: squares(2,2)
squares = reshape([0,1,4,9], [2,2])
if (any(isqrt_int(squares) /= reshape([0,1,2,3], [2,2]))) error stop 'rank-2 square roots'
if (isqrt_int(15) /= 3) error stop 'scalar square root'
if (any(mod_pow_int([2,3,4], 3, 5) /= [3,2,4])) error stop 'modular power'
if (any(factorial_int([0,3,5]) /= [1,6,120])) error stop 'factorials'
if (any(factorial_int_i64([0_int64,20_int64]) /= [1_int64,2432902008176640000_int64])) &
    error stop 'int64 factorials'
if (any(comb_int([5,6], 2) /= [10,15])) error stop 'combinations'
if (any(comb_int_i64([5_int64,6_int64], 2_int64) /= [10_int64,15_int64])) error stop 'int64 combinations'
if (any(perm_int([5,6], 2) /= [20,30])) error stop 'permutations'
if (any(perm_int([3,4]) /= [6,24])) error stop 'permutation optional argument'
if (any(perm_int_i64([3_int64,4_int64]) /= [6_int64,24_int64])) error stop 'int64 permutations'
if (.not. all(isclose_scalar_real([1.0_dp,2.0_dp], [1.0_dp,2.0_dp], 1e-5_dp, 1e-8_dp, .false.))) &
    error stop 'isclose'
if (any(abs(np_maximum([1.0_dp,3.0_dp], 2.0_dp)-[2.0_dp,3.0_dp]) > 1e-12_dp)) error stop 'maximum'
if (any(abs(np_minimum([1.0_dp,3.0_dp], 2.0_dp)-[1.0_dp,2.0_dp]) > 1e-12_dp)) error stop 'minimum'
if (any(abs(np_floor([1.9_dp,-1.1_dp])-[1.0_dp,-2.0_dp]) > 1e-12_dp)) error stop 'floor'

end subroutine checks
end program main
