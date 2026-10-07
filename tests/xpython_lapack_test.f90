! Standalone checks for python_mod's LAPACK-backed helpers.
! Works with either lapack_d.f90 or an adapted runtime using lapack_mod.f90.
program xpython_lapack_test
   use python_mod, only: linalg_solve, linalg_solve_safe, linalg_cholesky, &
      linalg_det, linalg_inv, linalg_cond, linalg_eig, linalg_eigvals, &
      linalg_eigh, linalg_eigvalsh, linalg_qr_reduced, linalg_svd, &
      linalg_svd_econ, linalg_lstsq, linalg_pinv, matrix_norm2
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none
   real(dp), parameter :: tol = 1.0e-10_dp
   real(dp) :: a(3,3), identity(3,3), b(3), rhs(3,2), tall(4,2)
   real(dp), allocatable :: x(:), xm(:,:), inv(:,:), l(:,:), w(:), v(:,:)
   real(dp), allocatable :: q(:,:), r(:,:), u(:,:), s(:), vt(:,:), sigma(:,:)
   real(dp), allocatable :: residuals(:), pinv(:,:)
   complex(dp), allocatable :: cw(:), cv(:,:), cx(:)
   complex(dp) :: ca(3,3), cb(3)
   integer :: i, rank
   logical :: ok

   a = reshape([4.0_dp, 1.0_dp, 0.0_dp, 1.0_dp, 3.0_dp, 1.0_dp, &
                0.0_dp, 1.0_dp, 2.0_dp], [3,3])
   identity = 0.0_dp
   do i = 1, 3
      identity(i,i) = 1.0_dp
   end do
   b = [1.0_dp, 2.0_dp, 3.0_dp]
   x = linalg_solve(a, b)
   call check(maxval(abs(matmul(a,x)-b)) < tol, 'vector solve')
   rhs(:,1) = b
   rhs(:,2) = 2.0_dp*b
   xm = linalg_solve(a, rhs)
   call check(maxval(abs(matmul(a,xm)-rhs)) < tol, 'matrix solve')
   call linalg_solve_safe(a, b, x, ok)
   call check(ok, 'safe solve status')
   call check(maxval(abs(matmul(a,x)-b)) < tol, 'safe solve')
   call linalg_solve_safe(0.0_dp*a, b, x, ok)
   call check(.not. ok, 'singular safe solve')
   ca = cmplx(a, 0.0_dp, dp)
   ca(1,1) = ca(1,1) + cmplx(0.0_dp, 0.5_dp, dp)
   cb = cmplx(b, -b, dp)
   cx = linalg_solve(ca, cb)
   call check(maxval(abs(matmul(ca,cx)-cb)) < tol, 'complex solve')

   l = linalg_cholesky(a)
   call check(maxval(abs(matmul(l,transpose(l))-a)) < tol, 'Cholesky')
   call check(abs(linalg_det(a)-18.0_dp) < tol, 'determinant')
   inv = linalg_inv(a)
   call check(maxval(abs(matmul(a,inv)-identity)) < tol, 'inverse')
   call linalg_eigh(a, w, v)
   call check(maxval(abs(matmul(transpose(v),v)-identity)) < tol, 'orthogonal eigenvectors')
   do i = 1, 3
      call check(maxval(abs(matmul(a,v(:,i))-w(i)*v(:,i))) < tol, 'symmetric eigenpair')
   end do
   call check(maxval(abs(linalg_eigvalsh(a)-w)) < tol, 'symmetric eigenvalues')
   call check(abs(linalg_cond(a)-maxval(w)/minval(w)) < tol, 'condition number')
   call check(abs(matrix_norm2(a)-maxval(w)) < tol, 'spectral norm')
   call linalg_eig(a, cw, cv)
   do i = 1, 3
      call check(maxval(abs(matmul(cmplx(a,0.0_dp,dp),cv(:,i))-cw(i)*cv(:,i))) < tol, 'eigenpair')
   end do
   cw = linalg_eigvals(a)
   call check(abs(sum(cw)-9.0_dp) < tol, 'eigenvalue trace')

   tall = reshape([1.0_dp, 2.0_dp, 3.0_dp, 4.0_dp, &
                   2.0_dp, -1.0_dp, 1.0_dp, 3.0_dp], [4,2])
   call linalg_qr_reduced(tall, q, r)
   call check(maxval(abs(matmul(q,r)-tall)) < tol, 'tall QR reconstruction')
   call check(maxval(abs(matmul(transpose(q),q)-identity(:2,:2))) < tol, 'QR orthogonality')
   call linalg_qr_reduced(transpose(tall), q, r)
   call check(maxval(abs(matmul(q,r)-transpose(tall))) < tol, 'wide QR reconstruction')
   call linalg_svd(tall, u, s, vt)
   allocate(sigma(size(u,2),size(vt,1)), source=0.0_dp)
   do i = 1, size(s)
      sigma(i,i) = s(i)
   end do
   call check(maxval(abs(matmul(matmul(u,sigma),vt)-tall)) < tol, 'full SVD')
   deallocate(sigma)
   call linalg_svd_econ(tall, u, s, vt)
   allocate(sigma(size(s),size(s)), source=0.0_dp)
   do i = 1, size(s)
      sigma(i,i) = s(i)
   end do
   call check(maxval(abs(matmul(matmul(u,sigma),vt)-tall)) < tol, 'economy SVD')
   call linalg_lstsq(tall, matmul(tall,[2.0_dp,-1.0_dp]), x, residuals, rank, s)
   call check(rank == 2, 'least-squares rank')
   call check(maxval(abs(x-[2.0_dp,-1.0_dp])) < tol, 'least squares')
   pinv = linalg_pinv(tall)
   call check(maxval(abs(matmul(pinv,tall)-identity(:2,:2))) < tol, 'pseudoinverse')
   print '(a)', 'PASS python_mod LAPACK operations'
contains
   subroutine check(condition, label)
      logical, intent(in) :: condition
      character(*), intent(in) :: label
      if (.not. condition) then
         print '(a)', 'FAIL '//label
         error stop 1
      end if
   end subroutine check
end program xpython_lapack_test
