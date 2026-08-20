! Small adapter generated for xp2f.py's scipy.optimize.curve_fit support.
! Bridges a synthesized Python-style residual callback
! `def resid(p): ... return y` (translated to a Fortran
! `function resid(p) result(y)` with an assumed-shape real(dp) input and an
! allocatable real(dp) result the length of the fitted data) to the callback
! shape MINPACK's lmdif1 expects: `subroutine fcn(m, n, x, fvec, iflag)`.
! See minpack.f90 (vendored alongside this file, from fortran-lang/minpack)
! for the actual least-squares solver.
!
! Also provides a finite-difference-Jacobian covariance-matrix helper used
! to approximate curve_fit's `pcov` return value, following the standard
! asymptotic formula `pcov = inv(J^T J) * s_sq` (the same formula
! scipy/MINPACK use for the unscaled-sigma case), computed here via a
! direct central-difference Jacobian rather than reusing MINPACK's internal
! QR factors.
module curvefit_bridge_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none

   abstract interface
      function curvefit_residfunc_iface(p) result(y)
         import :: dp
         real(kind=dp), intent(in) :: p(:)
         real(kind=dp), allocatable :: y(:)
      end function curvefit_residfunc_iface
   end interface

   procedure(curvefit_residfunc_iface), pointer :: curvefit_user_fn => null()

contains

   subroutine curvefit_generic_wrapper(m, n, x, fvec, iflag)
      integer, intent(in) :: m, n
      real(kind=dp), intent(in) :: x(n)
      real(kind=dp), intent(out) :: fvec(m)
      integer, intent(inout) :: iflag
      fvec = curvefit_user_fn(x)
   end subroutine curvefit_generic_wrapper

   subroutine curvefit_covariance(popt, m, pcov)
      real(kind=dp), intent(in) :: popt(:)
      integer, intent(in) :: m
      real(kind=dp), intent(out) :: pcov(size(popt), size(popt))
      real(kind=dp), parameter :: h = 1.0e-6_dp
      integer :: n, j
      real(kind=dp), allocatable :: jac(:, :), p_pert(:), r0(:), r_plus(:), r_minus(:), jtj(:, :)
      real(kind=dp) :: s_sq

      n = size(popt)
      allocate (jac(m, n), p_pert(n), r0(m), r_plus(m), r_minus(m), jtj(n, n))

      r0 = curvefit_user_fn(popt)
      do j = 1, n
         p_pert = popt
         p_pert(j) = popt(j) + h
         r_plus = curvefit_user_fn(p_pert)
         p_pert(j) = popt(j) - h
         r_minus = curvefit_user_fn(p_pert)
         jac(:, j) = (r_plus - r_minus)/(2.0_dp*h)
      end do

      jtj = matmul(transpose(jac), jac)
      call curvefit_invert_matrix(jtj, pcov, n)

      if (m > n) then
         s_sq = sum(r0**2)/real(m - n, dp)
      else
         s_sq = 0.0_dp
      end if
      pcov = pcov*s_sq
   end subroutine curvefit_covariance

   subroutine curvefit_invert_matrix(a_in, a_inv, n)
      ! Gauss-Jordan elimination with partial pivoting.
      integer, intent(in) :: n
      real(kind=dp), intent(in) :: a_in(n, n)
      real(kind=dp), intent(out) :: a_inv(n, n)
      real(kind=dp) :: a(n, n), tmp
      integer :: i, j, k, piv

      a = a_in
      a_inv = 0.0_dp
      do i = 1, n
         a_inv(i, i) = 1.0_dp
      end do
      do k = 1, n
         piv = k
         do i = k + 1, n
            if (abs(a(i, k)) > abs(a(piv, k))) piv = i
         end do
         if (piv /= k) then
            do j = 1, n
               tmp = a(k, j); a(k, j) = a(piv, j); a(piv, j) = tmp
               tmp = a_inv(k, j); a_inv(k, j) = a_inv(piv, j); a_inv(piv, j) = tmp
            end do
         end if
         tmp = a(k, k)
         a(k, :) = a(k, :)/tmp
         a_inv(k, :) = a_inv(k, :)/tmp
         do i = 1, n
            if (i == k) cycle
            tmp = a(i, k)
            a(i, :) = a(i, :) - tmp*a(k, :)
            a_inv(i, :) = a_inv(i, :) - tmp*a_inv(k, :)
         end do
      end do
   end subroutine curvefit_invert_matrix

end module curvefit_bridge_mod
