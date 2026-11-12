program main
use numpy_fortran
use, intrinsic :: iso_fortran_env, only: dp => real64
implicit none
call check_helpers()
contains
pure subroutine check_helpers()
integer, allocatable :: u(:), counts(:), pairs(:,:), h(:)
real(dp), allocatable :: nodes(:), weights(:), edges(:)
complex(dp), allocatable :: spectrum(:), restored(:), eigenvalues(:)
complex(dp), allocatable :: lower(:,:), vectors(:,:), covariance(:,:), correlation(:,:)
complex(dp) :: a(2,2)
real(dp) :: samples(4)
integer :: n

if (mode_int([2,1,2]) /= 2) error stop 'integer mode'
u = multimode_int([2,1,2,1,3])
if (any(u /= [1,2])) error stop 'integer multimode'
edges = np_delete_real_1d([1.0_dp,2.0_dp,3.0_dp], -1)
if (any(edges /= [1.0_dp,2.0_dp])) error stop 'delete'

call unique_int_counts([2,1,2], u, counts)
if (any(u /= [1,2]) .or. any(counts /= [1,2])) error stop 'counts'
pairs = where_pair_2d([1], [0,2])
if (any(pairs(1,:) /= [1,1]) .or. any(pairs(2,:) /= [0,2])) error stop 'paired indices'
u = bincount_int([0,2,2])
if (any(u /= [1,0,2])) error stop 'bincount'
u = repeat_int([1,2], 2)
if (any(u /= [1,1,2,2])) error stop 'repeat'
u = tile_int([1,2], 2)
if (any(u /= [1,2,1,2])) error stop 'tile'
u = lexsort_keys(reshape([2,1,1,1,0,2], [2,3]))
if (any(u /= [1,0,2])) error stop 'lexsort'
if (abs(quantile_linear([1.0_dp,3.0_dp,2.0_dp], 0.5_dp)-2.0_dp) > 1e-12_dp) error stop 'quantile'
call histogram_real_edges([0.0_dp,0.5_dp,1.0_dp], [0.0_dp,0.5_dp,1.0_dp], h, edges)
if (any(h /= [1,2])) error stop 'histogram'
call leggauss(3, nodes, weights)
if (abs(sum(weights*nodes**4)-0.4_dp) > 1e-12_dp) error stop 'quadrature'

samples = [1.0_dp,2.0_dp,3.0_dp,4.0_dp]
! Three points uses direct DFT; four uses the radix-2 worker.
do n = 3, 4
    spectrum = fft_fft(samples(:n))
    restored = fft_ifft(spectrum)
    if (maxval(abs(restored-cmplx(samples(:n),0.0_dp,dp))) > 1e-12_dp) error stop 'FFT'
end do
a = cmplx(0.0_dp,0.0_dp,dp)
a(1,1) = cmplx(1.0_dp,2.0_dp,dp)
a(2,2) = cmplx(3.0_dp,-1.0_dp,dp)
eigenvalues = linalg_eigvals(a)
if (minval(abs(eigenvalues-a(1,1))) > 1e-12_dp) error stop 'eigenvalue 1'
if (minval(abs(eigenvalues-a(2,2))) > 1e-12_dp) error stop 'eigenvalue 2'
call linalg_eig_complex(a, eigenvalues, vectors)
do n = 1, 2
    if (maxval(abs(matmul(a,vectors(:,n))-eigenvalues(n)*vectors(:,n))) > 1e-12_dp) &
        error stop 'complex eigenvectors'
end do
a = cmplx(0.0_dp,0.0_dp,dp)
a(1,1) = 4.0_dp
a(2,2) = 9.0_dp
lower = linalg_cholesky_complex(a)
if (maxval(abs(matmul(lower,conjg(transpose(lower)))-a)) > 1e-12_dp) error stop 'complex Cholesky'
a = reshape(cmplx([1.0_dp,3.0_dp,2.0_dp,6.0_dp],0.0_dp,dp), [2,2])
covariance = cov_matrix_rows_complex(a)
if (abs(covariance(1,2)-4.0_dp) > 1e-12_dp) error stop 'complex covariance'
correlation = corrcoef_matrix_rows_complex(a)
if (maxval(abs(correlation-1.0_dp)) > 1e-12_dp) error stop 'complex correlation'
end subroutine
end program
