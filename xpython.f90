! Standalone, source-level tests of python_mod; no transpiler is needed.
! Build in a separate directory to keep its .mod/.o files out of runtime caches:
! gfortran -O0 -g -ffree-line-length-none -fcheck=all -fbacktrace &
!   ../python.f90 ../lapack_d.f90 ../xpython.f90 -o xpython.exe
! Change the named problem sizes below, then recompile. Small literal fixtures
! in scalar/string tests deliberately stay fixed because they test exact values.
program xpython
   use python_mod, only: isqrt_int, factorial_int, comb_int, perm_int, mod_pow_int, &
      arange_int, linspace, logspace, geomspace, mean, weighted_mean_1d, var_1d, std, &
      quantile_linear, cov2_real, corrcoef2_real, cumsum, cumprod, gradient_1d, interp_1d, &
      sorted_vec, reversed_vec, argsort_idx, unique, unique_int_inv_counts, bincount_int, &
      repeat, tile, eye, searchsorted_left_int_scalar, searchsorted_right_int_scalar, &
      py_str_int, str_format_real_fixed, to_lower, to_upper, str_strip, str_lstrip, &
      str_rstrip, str_replace, str_find, str_rfind, str_count, str_reverse, str_zfill, &
      str_split, str_join, grow_and_set_char, insert_char, seed_rng, runif, rnorm, &
      random_choice_norep, random_binomial, random_poisson, random_geometric, &
      leggauss, histogram_real_edges, convolve_real, lfilter_real, fft_fft, fft_ifft, &
      fft_rfft, fft_irfft, fft_fftfreq, fft_rfftfreq, linalg_solve, linalg_solve_safe, &
      linalg_cholesky, linalg_det, linalg_inv, linalg_cond, linalg_eig, linalg_eigvals, &
      linalg_eigh, linalg_eigvalsh, linalg_qr_reduced, linalg_svd, linalg_svd_econ, &
      linalg_lstsq, linalg_pinv, matrix_norm2
   use, intrinsic :: iso_fortran_env, only: dp => real64, int64
   use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
   implicit none

   ! ---------------- User-adjustable problem sizes ----------------
   integer, parameter :: n_stats = 12       ! >= 2: statistics sample length
   integer, parameter :: n_array = 16       ! >= 1: sorting/indexing sample length
   integer, parameter :: n_random = 256     ! >= 1: RNG sample/population length
   integer, parameter :: n_fft = 16         ! >= 1: even, odd, or non-power-of-two
   integer, parameter :: n_matrix = 5       ! >= 1: square linear algebra order
   integer, parameter :: n_lstsq_rows = 9    ! >= n_lstsq_cols
   integer, parameter :: n_lstsq_cols = 3    ! >= 1: rectangular matrix width
   integer, parameter :: n_grid = 17        ! >= 2: interpolation/grid length
   integer, parameter :: n_quadrature = 6   ! >= 1: Gauss-Legendre order
   ! ----------------------------------------------------------------
   real(dp), parameter :: tolerance = 1.0e-10_dp
   real(dp), parameter :: pi = acos(-1.0_dp)
   integer, parameter :: rng_seed = 12345
   integer :: tests_run = 0, failures = 0

   if (n_stats < 2 .or. n_array < 1 .or. n_random < 1 .or. n_fft < 1 .or. &
       n_matrix < 1 .or. n_lstsq_cols < 1 .or. n_lstsq_rows < n_lstsq_cols .or. &
       n_grid < 2 .or. n_quadrature < 1) then
      print '(a)', 'Invalid problem sizes: see the requirements beside each parameter.'
      error stop 2
   end if
   print '(a)', 'Testing python_mod with the bundled external LAPACK'
   print '(a,i0,a,i0,a,i0)', 'stats=', n_stats, ' arrays=', n_array, ' random=', n_random
   print '(a,i0,a,i0,a,i0,a,i0)', 'fft=', n_fft, ' matrix=', n_matrix, &
      ' least-squares rows=', n_lstsq_rows, ' cols=', n_lstsq_cols
   print '(a,i0,a,i0)', 'grid=', n_grid, ' quadrature=', n_quadrature
   call test_scalars()
   call test_statistics()
   call test_arrays()
   call test_strings()
   call test_random()
   call test_numerical_helpers()
   call test_fft()
   call test_linear_algebra()
   print '(a,i0,a,i0)', 'Checks: ', tests_run, '; failures: ', failures
   if (failures /= 0) error stop 1
   print '(a)', 'PASS python_mod standalone tests'
contains
   subroutine check(condition, label)
      logical, intent(in) :: condition
      character(*), intent(in) :: label
      tests_run = tests_run + 1
      if (.not. condition) then
         failures = failures + 1
         print '(a)', 'FAIL '//label
      end if
   end subroutine check

   subroutine close(actual, expected, label)
      real(dp), intent(in) :: actual, expected
      character(*), intent(in) :: label
      logical :: agrees
      agrees = .false.
      if (ieee_is_finite(actual) .and. ieee_is_finite(expected)) &
         agrees = abs(actual-expected) <= tolerance*max(1.0_dp, abs(expected))
      call check(agrees, label)
      if (.not. agrees) print '(a,es24.15,a,es24.15)', '  actual=', actual, ' expected=', expected
   end subroutine close

   subroutine ints(actual, expected, label)
      integer, intent(in) :: actual(:), expected(:)
      character(*), intent(in) :: label
      if (size(actual) /= size(expected)) then
         call check(.false., label//' (size)')
      else
         call check(all(actual == expected), label)
      end if
   end subroutine ints

   subroutine reals(actual, expected, label)
      real(dp), intent(in) :: actual(:), expected(:)
      character(*), intent(in) :: label
      if (size(actual) /= size(expected)) then
         call check(.false., label//' (size)')
      else if (.not. all(ieee_is_finite(actual))) then
         call check(.false., label//' (nonfinite)')
      else
         call check(all(abs(actual-expected) <= tolerance*max(1.0_dp,abs(expected))), label)
      end if
   end subroutine reals

   subroutine test_scalars()
      call check(isqrt_int(0) == 0, 'isqrt zero')
      call check(isqrt_int(24) == 4 .and. isqrt_int(25) == 5, 'isqrt boundary')
      call check(factorial_int(0) == 1 .and. factorial_int(6) == 720, 'factorial')
      call check(comb_int(8,3) == 56, 'combinations')
      call check(perm_int(8,3) == 336, 'permutations')
      call check(mod_pow_int(3,5,7) == 5, 'modular exponentiation')
      print '(a)', '  scalar helpers checked'
   end subroutine test_scalars

   subroutine test_statistics()
      real(dp) :: x(n_stats), weights(n_stats), n, variance, covariance(2,2), corr(2,2)
      real(dp), allocatable :: sums(:), products(:), gradient(:)
      integer :: i
      x = [(real(i,dp), i=1,n_stats)]
      weights = 1.0_dp
      n = real(n_stats,dp)
      variance = (n*n-1.0_dp)/12.0_dp
      call close(mean(x), (n+1.0_dp)/2.0_dp, 'mean')
      call close(weighted_mean_1d(x,weights), mean(x), 'weighted mean')
      call close(var_1d(x), variance, 'population variance')
      call close(var_1d(x,1), n*(n+1.0_dp)/12.0_dp, 'sample variance')
      call close(std(x), sqrt(variance), 'population std')
      call close(std(x,1), sqrt(n*(n+1.0_dp)/12.0_dp), 'sample std')
      call close(quantile_linear(x,0.0_dp), 1.0_dp, 'minimum quantile')
      call close(quantile_linear(x,0.5_dp), (n+1.0_dp)/2.0_dp, 'median quantile')
      call close(quantile_linear(x,1.0_dp), n, 'maximum quantile')
      covariance = cov2_real(x,2.0_dp*x+1.0_dp,ddof=1)
      call close(covariance(1,2), n*(n+1.0_dp)/6.0_dp, 'covariance')
      corr = corrcoef2_real(x,2.0_dp*x+1.0_dp)
      call close(corr(1,2), 1.0_dp, 'correlation')
      sums = cumsum(x)
      call reals(sums, x*(x+1.0_dp)/2.0_dp, 'cumulative sums')
      products = cumprod(1.0_dp+0.0_dp*x)
      call reals(products, 1.0_dp+0.0_dp*x, 'cumulative products')
      gradient = gradient_1d(x)
      call reals(gradient, 1.0_dp+0.0_dp*x, 'gradient of linear sequence')
      print '(a)', '  statistics checked'
   end subroutine test_statistics

   subroutine test_arrays()
      integer :: original(n_array), ascending(n_array), i
      integer, allocatable :: sorted(:), indices(:), u(:), inv(:), counts(:), doubled(:), bins(:)
      real(dp), allocatable :: real_sorted(:), empty(:)
      ascending = [(i-1, i=1,n_array)]
      original = ascending(n_array:1:-1)
      sorted = sorted_vec(original)
      call ints(sorted, ascending, 'integer sorted copy')
      call ints(original, ascending(n_array:1:-1), 'sort preserves input')
      call ints(reversed_vec(original), ascending, 'reverse')
      indices = argsort_idx(original)
      call ints(indices, ascending(n_array:1:-1), 'zero-based argsort')
      real_sorted = sorted_vec(real(original,dp)+0.25_dp)
      call reals(real_sorted, real(ascending,dp)+0.25_dp, 'real sort preserves fractions')
      doubled = tile(original,2)
      call unique_int_inv_counts(doubled,u,inv,counts)
      call ints(u, ascending, 'unique values')
      call ints(counts, [(2, i=1,n_array)], 'unique counts')
      call ints(u(inv+1), doubled, 'unique inverse reconstructs input')
      bins = bincount_int(doubled)
      call ints(bins, [(2, i=1,n_array)], 'bincount')
      call check(searchsorted_left_int_scalar(sorted,0) == 0, 'searchsorted left')
      call check(searchsorted_right_int_scalar(sorted,n_array-1) == n_array, 'searchsorted right')
      call ints(arange_int(0,n_array,1), ascending, 'arange positive step')
      call ints(arange_int(n_array-1,-1,-1), original, 'arange negative step')
      call ints(repeat(original,0), [integer ::], 'zero repeat')
      call ints(tile(original,0), [integer ::], 'zero tile')
      allocate(empty(0))
      call reals(sorted_vec(empty), empty, 'sort empty vector')
      call reals(unique(empty), empty, 'unique empty vector')
      print '(a)', '  arrays and indices checked'
   end subroutine test_arrays

   subroutine test_strings()
      character(:), allocatable :: strings(:), text
      call check(py_str_int(42) == '42', 'integer formatting')
      call check(py_str_int(3000000000_int64) == '3000000000', 'int64 formatting')
      call check(str_format_real_fixed(1.25_dp,2) == '1.25', 'fixed real formatting')
      call check(to_lower('Ab C!?') == 'ab c!?', 'lowercase')
      call check(to_upper('Ab c!?') == 'AB C!?', 'uppercase')
      call check(len(to_lower('Ab  ')) == 4, 'case conversion preserves trailing blanks')
      call check(len(to_upper('')) == 0, 'case conversion empty string')
      call check(str_strip('  abc  ') == 'abc', 'strip')
      call check(str_lstrip('  abc  ') == 'abc  ', 'left strip')
      call check(str_rstrip('  abc  ') == '  abc', 'right strip')
      call check(str_replace('ab ab','ab','xyz') == 'xyz xyz', 'replace')
      call check(str_find('abcabc','bc') == 1, 'zero-based find')
      call check(str_rfind('abcabc','bc') == 4, 'zero-based reverse find')
      call check(str_count('ababab','ab') == 3, 'substring count')
      call check(str_reverse('abcd') == 'dcba', 'string reverse')
      call check(str_zfill('-42',5) == '-0042', 'zero fill sign')
      text = str_join('|',str_split('alpha,beta,gamma',','))
      call check(text == 'alpha|beta|gamma', 'split and join')
      call grow_and_set_char(strings,1,'a')
      call insert_char(strings,0,'long')
      call check(size(strings) == 2 .and. len(strings) == 4, 'string array grows length')
      call check(strings(1) == 'long' .and. strings(2) == 'a', 'string insertion')
      print '(a)', '  strings checked'
   end subroutine test_strings

   subroutine test_random()
      real(dp), allocatable :: uniform(:), uniform_again(:), normal(:), normal_again(:), empty(:)
      integer :: selected(n_random), i
      ! Test invariants and within-compiler reproducibility, not particular
      ! draws or approximate moments: intrinsic RNGs differ between compilers.
      call seed_rng(rng_seed)
      uniform = runif(n_random)
      normal = rnorm(n_random)
      call seed_rng(rng_seed)
      uniform_again = runif(n_random)
      normal_again = rnorm(n_random)
      call check(size(uniform) == n_random, 'uniform shape')
      call check(all(uniform >= 0.0_dp .and. uniform < 1.0_dp), 'uniform range')
      call check(all(ieee_is_finite(normal)), 'normal draws finite')
      call reals(uniform_again, uniform, 'seed reproducibility uniform')
      call reals(normal_again, normal, 'seed reproducibility normal')
      call random_choice_norep(n_random,n_random,selected)
      call ints(sorted_vec(selected), [(i-1, i=1,n_random)], 'sampling without replacement')
      call check(random_binomial(0,0.5_dp) == 0, 'zero binomial trials')
      call check(random_binomial(n_random,0.0_dp) == 0, 'binomial probability zero')
      call check(random_binomial(n_random,1.0_dp) == n_random, 'binomial probability one')
      call check(random_poisson(0.0_dp) == 0, 'Poisson mean zero')
      call check(random_geometric(1.0_dp) == 1, 'geometric probability one')
      empty = runif(0)
      call check(size(empty) == 0, 'empty uniform draws')
      empty = rnorm(0)
      call check(size(empty) == 0, 'empty normal draws')
      print '(a)', '  random helper invariants checked'
   end subroutine test_random

   subroutine test_numerical_helpers()
      real(dp), allocatable :: grid(:), y(:), nodes(:), weights(:), edges(:), actual_edges(:)
      integer, allocatable :: h(:)
      integer :: degree
      grid = linspace(0.0_dp,1.0_dp,n_grid)
      call close(grid(1), 0.0_dp, 'linspace first endpoint')
      call close(grid(n_grid), 1.0_dp, 'linspace last endpoint')
      call close(sum(grid), real(n_grid,dp)/2.0_dp, 'linspace sum')
      y = interp_1d(grid, [0.0_dp,1.0_dp], [1.0_dp,3.0_dp])
      call reals(y, 1.0_dp+2.0_dp*grid, 'linear interpolation')
      y = logspace(0.0_dp,2.0_dp,n_grid)
      call close(y(1), 1.0_dp, 'logspace first endpoint')
      call close(y(n_grid), 100.0_dp, 'logspace last endpoint')
      y = geomspace(1.0_dp,100.0_dp,n_grid)
      call reals(y, logspace(0.0_dp,2.0_dp,n_grid), 'geomspace versus logspace')
      edges = [0.0_dp,0.5_dp,1.0_dp]
      call histogram_real_edges(grid,edges,h,actual_edges)
      call check(sum(h) == n_grid, 'histogram includes right endpoint')
      call reals(actual_edges, edges, 'histogram edges')
      call reals(convolve_real(grid,[1.0_dp],'full'), grid, 'convolution identity')
      call reals(lfilter_real([1.0_dp],[1.0_dp],grid), grid, 'filter identity')
      call leggauss(n_quadrature,nodes,weights)
      call close(sum(weights), 2.0_dp, 'quadrature constant')
      call check(all(weights > 0.0_dp), 'quadrature positive weights')
      degree = min(4,2*n_quadrature-2)
      call close(sum(weights*nodes**degree), 2.0_dp/real(degree+1,dp), 'quadrature polynomial')
      print '(a)', '  grids, histograms, filtering and quadrature checked'
   end subroutine test_numerical_helpers

   subroutine test_fft()
      real(dp) :: signal(n_fft)
      real(dp), allocatable :: restored_real(:), frequencies(:)
      complex(dp), allocatable :: spectrum(:), restored(:)
      integer :: i
      ! The ramp excites all Fourier bins, unlike a single sinusoid.
      signal = [(sin(2.0_dp*pi*real(i-1,dp)/real(n_fft,dp))+0.25_dp+ &
         real(i-1,dp)/real(n_fft,dp), i=1,n_fft)]
      spectrum = fft_fft(signal)
      restored = fft_ifft(spectrum)
      call reals(real(restored,dp), signal, 'FFT inverse real part')
      call close(maxval(abs(aimag(restored))), 0.0_dp, 'FFT inverse imaginary part')
      call close(real(spectrum(1),dp), sum(signal), 'FFT DC coefficient')
      call close(sum(abs(spectrum)**2)/real(n_fft,dp), sum(signal**2), 'FFT Parseval identity')
      spectrum = fft_rfft(signal)
      call check(size(spectrum) == n_fft/2+1, 'real FFT shape')
      ! Explicit length makes the round trip valid for odd lengths too.
      restored_real = fft_irfft(spectrum,n_fft)
      call reals(restored_real, signal, 'real FFT round trip')
      frequencies = fft_fftfreq(n_fft)
      call check(size(frequencies) == n_fft, 'FFT frequency shape')
      call close(frequencies(1), 0.0_dp, 'FFT zero frequency')
      frequencies = fft_rfftfreq(n_fft)
      call check(size(frequencies) == n_fft/2+1, 'real FFT frequency shape')
      print '(a)', '  FFT checked'
   end subroutine test_fft

   subroutine test_linear_algebra()
      real(dp) :: a(n_matrix,n_matrix), identity(n_matrix,n_matrix), b(n_matrix), rhs(n_matrix,2)
      real(dp) :: diagonal(n_matrix,n_matrix), tall(n_lstsq_rows,n_lstsq_cols), coefficients(n_lstsq_cols)
      real(dp), allocatable :: x(:), xm(:,:), inverse(:,:), l(:,:), w(:), v(:,:), q(:,:), r(:,:)
      real(dp), allocatable :: u(:,:), s(:), vt(:,:), sigma(:,:), residuals(:), pinv(:,:), column_identity(:,:)
      complex(dp), allocatable :: cw(:), cv(:,:), cx(:)
      complex(dp) :: ca(n_matrix,n_matrix), cb(n_matrix)
      real(dp) :: expected_det, angle, largest, smallest
      integer :: i, j, rank
      logical :: ok
      a = 0.0_dp
      identity = eye(n_matrix)
      diagonal = 0.0_dp
      expected_det = 1.0_dp
      do i = 1, n_matrix
         a(i,i) = 4.0_dp
         if (i < n_matrix) then
            a(i,i+1) = 1.0_dp
            a(i+1,i) = 1.0_dp
         end if
         diagonal(i,i) = 1.0_dp+real(i,dp)/(real(n_matrix,dp)**2)
         expected_det = expected_det*diagonal(i,i)
      end do
      b = [(real(i,dp)/real(n_matrix,dp), i=1,n_matrix)]
      x = linalg_solve(a,b)
      call reals(matmul(a,x), b, 'vector linear solve')
      rhs(:,1) = b
      rhs(:,2) = -b
      xm = linalg_solve(a,rhs)
      call close(maxval(abs(matmul(a,xm)-rhs)), 0.0_dp, 'multiple RHS solve')
      call linalg_solve_safe(a,b,x,ok)
      call check(ok, 'safe solve status')
      call reals(matmul(a,x), b, 'safe solve result')
      call linalg_solve_safe(0.0_dp*a,b,x,ok)
      call check(.not. ok, 'singular safe solve status')
      ca = cmplx(a,0.0_dp,dp)
      ca(1,1) = ca(1,1)+cmplx(0.0_dp,0.5_dp,dp)
      cb = cmplx(b,-b,dp)
      cx = linalg_solve(ca,cb)
      call close(maxval(abs(matmul(ca,cx)-cb)), 0.0_dp, 'complex solve')
      l = linalg_cholesky(a)
      call close(maxval(abs(matmul(l,transpose(l))-a)), 0.0_dp, 'Cholesky reconstruction')
      call close(linalg_det(diagonal), expected_det, 'diagonal determinant')
      diagonal(1,1) = -diagonal(1,1)
      call close(linalg_det(diagonal), -expected_det, 'negative determinant')
      inverse = linalg_inv(a)
      call close(maxval(abs(matmul(a,inverse)-identity)), 0.0_dp, 'matrix inverse')
      call linalg_eigh(a,w,v)
      call close(maxval(abs(matmul(transpose(v),v)-identity)), 0.0_dp, 'eigenvector orthogonality')
      do i = 1, n_matrix
         call reals(matmul(a,v(:,i)), w(i)*v(:,i), 'symmetric eigenpair')
      end do
      call reals(linalg_eigvalsh(a), w, 'symmetric eigenvalues')
      angle = pi/real(n_matrix+1,dp)
      largest = 4.0_dp+2.0_dp*cos(angle)
      smallest = 4.0_dp-2.0_dp*cos(angle)
      call close(maxval(w), largest, 'analytic largest eigenvalue')
      call close(minval(w), smallest, 'analytic smallest eigenvalue')
      call close(linalg_cond(a), largest/smallest, 'condition number')
      call close(matrix_norm2(a), largest, 'spectral norm')
      call linalg_eig(a,cw,cv)
      do i = 1, n_matrix
         call close(maxval(abs(matmul(cmplx(a,0.0_dp,dp),cv(:,i))-cw(i)*cv(:,i))), &
            0.0_dp, 'general eigenpair')
      end do
      cw = linalg_eigvals(a)
      call close(real(sum(cw),dp), 4.0_dp*real(n_matrix,dp), 'eigenvalue trace')
      do j = 1, n_lstsq_cols
         coefficients(j) = real((-1)**j,dp)/real(j,dp)
         do i = 1, n_lstsq_rows
            tall(i,j) = cos(pi*(real(i,dp)-0.5_dp)*real(j-1,dp)/real(n_lstsq_rows,dp))
         end do
      end do
      column_identity = eye(n_lstsq_cols)
      call linalg_qr_reduced(tall,q,r)
      call close(maxval(abs(matmul(q,r)-tall)), 0.0_dp, 'tall QR reconstruction')
      call close(maxval(abs(matmul(transpose(q),q)-column_identity)), 0.0_dp, 'QR orthogonality')
      call linalg_qr_reduced(transpose(tall),q,r)
      call close(maxval(abs(matmul(q,r)-transpose(tall))), 0.0_dp, 'wide QR reconstruction')
      call linalg_svd(tall,u,s,vt)
      allocate(sigma(size(u,2),size(vt,1)), source=0.0_dp)
      do i = 1, size(s)
         sigma(i,i) = s(i)
      end do
      call close(maxval(abs(matmul(matmul(u,sigma),vt)-tall)), 0.0_dp, 'full SVD reconstruction')
      deallocate(sigma)
      call linalg_svd_econ(tall,u,s,vt)
      allocate(sigma(size(s),size(s)), source=0.0_dp)
      do i = 1, size(s)
         sigma(i,i) = s(i)
      end do
      call close(maxval(abs(matmul(matmul(u,sigma),vt)-tall)), 0.0_dp, 'economy SVD reconstruction')
      call linalg_lstsq(tall,matmul(tall,coefficients),x,residuals,rank,s)
      call check(rank == n_lstsq_cols, 'least-squares rank')
      call reals(x, coefficients, 'least-squares coefficients')
      pinv = linalg_pinv(tall)
      call close(maxval(abs(matmul(pinv,tall)-column_identity)), 0.0_dp, 'pseudoinverse')
      print '(a)', '  LAPACK-backed linear algebra checked'
   end subroutine test_linear_algebra
end program xpython
