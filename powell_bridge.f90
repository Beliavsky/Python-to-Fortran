! Bridge for xp2f.py's scipy.optimize.minimize(method='Powell') support.
! Implements the classic Numerical Recipes direction-set (Powell's)
! method: a sequence of derivative-free 1D line minimizations along a
! rotating set of directions, no analytic or finite-difference gradient
! required. Each line search brackets the minimum with the standard
! geometric-expansion bracketing algorithm (mnbrak) and refines it with
! Jacob Williams' vendored port of Brent's fmin (see fmin.f90) -- the
! same combination scipy's own reference implementations are built on.
!
! Reference: Press, Teukolsky, Vetterling, Flannery, "Numerical Recipes"
! (any edition), section on Powell's method (routines mnbrak/brent/
! linmin/powell).
module powell_bridge_mod
   use, intrinsic :: iso_fortran_env, only: dp => real64
   use fmin_module, only: fmin
   implicit none

   abstract interface
      function powell_scalarfunc_iface(x) result(y)
         import :: dp
         real(kind=dp), intent(in) :: x(:)
         real(kind=dp) :: y
      end function powell_scalarfunc_iface
   end interface

   procedure(powell_scalarfunc_iface), pointer :: powell_user_fn => null()

   ! Module-level state for the 1D "along a direction" line function
   ! fmin/mnbrak need (both require a plain scalar-in/scalar-out
   ! function, not one carrying extra context).
   real(kind=dp), allocatable :: powell_line_p(:), powell_line_dir(:)

contains

   function powell_line_func(alpha) result(y)
      real(kind=dp), intent(in) :: alpha
      real(kind=dp) :: y
      y = powell_user_fn(powell_line_p + alpha*powell_line_dir)
   end function powell_line_func

   subroutine powell_mnbrak(ax, bx, cx, fa, fb, fc)
      ! Given an initial (ax, bx), search outward in the downhill
      ! direction until a triplet (ax, bx, cx) brackets a minimum
      ! (fb < fa and fb < fc).
      real(kind=dp), intent(inout) :: ax, bx
      real(kind=dp), intent(out) :: cx, fa, fb, fc
      real(kind=dp), parameter :: gold = 1.618034_dp, glimit = 100.0_dp, tiny = 1.0e-20_dp
      real(kind=dp) :: fu, u, r, q, ulim, dum

      fa = powell_line_func(ax)
      fb = powell_line_func(bx)
      if (fb > fa) then
         dum = ax; ax = bx; bx = dum
         dum = fa; fa = fb; fb = dum
      end if
      cx = bx + gold*(bx - ax)
      fc = powell_line_func(cx)
      do while (fb >= fc)
         r = (bx - ax)*(fb - fc)
         q = (bx - cx)*(fb - fa)
         u = bx - ((bx - cx)*q - (bx - ax)*r)/(2.0_dp*sign(max(abs(q - r), tiny), q - r))
         ulim = bx + glimit*(cx - bx)
         if ((bx - u)*(u - cx) > 0.0_dp) then
            fu = powell_line_func(u)
            if (fu < fc) then
               ax = bx; fa = fb
               bx = u; fb = fu
               return
            else if (fu > fb) then
               cx = u; fc = fu
               return
            end if
            u = cx + gold*(cx - bx)
            fu = powell_line_func(u)
         else if ((cx - u)*(u - ulim) > 0.0_dp) then
            fu = powell_line_func(u)
            if (fu < fc) then
               bx = cx; cx = u; u = cx + gold*(cx - bx)
               fb = fc; fc = fu; fu = powell_line_func(u)
            end if
         else if ((u - ulim)*(ulim - cx) >= 0.0_dp) then
            u = ulim
            fu = powell_line_func(u)
         else
            u = cx + gold*(cx - bx)
            fu = powell_line_func(u)
         end if
         ax = bx; bx = cx; cx = u
         fa = fb; fb = fc; fc = fu
      end do
   end subroutine powell_mnbrak

   subroutine powell_linmin(p, xi, n, fret)
      ! Minimize powell_user_fn along the direction xi starting at p;
      ! overwrite p with the new minimum and xi with the actual
      ! displacement vector (direction scaled by the distance moved).
      integer, intent(in) :: n
      real(kind=dp), intent(inout) :: p(n), xi(n)
      real(kind=dp), intent(out) :: fret
      real(kind=dp) :: ax, bx, cx, fa, fb, fc, xmin, lo, hi

      powell_line_p = p
      powell_line_dir = xi
      ax = 0.0_dp
      bx = 1.0_dp
      call powell_mnbrak(ax, bx, cx, fa, fb, fc)
      lo = min(ax, cx)
      hi = max(ax, cx)
      xmin = fmin(powell_line_func, lo, hi, 1.0e-8_dp)
      fret = powell_line_func(xmin)
      xi = xmin*xi
      p = p + xi
   end subroutine powell_linmin

   subroutine powell_minimize(p, n, ftol, maxiter, fret, success)
      integer, intent(in) :: n
      real(kind=dp), intent(inout) :: p(n)
      real(kind=dp), intent(in) :: ftol
      integer, intent(in) :: maxiter
      real(kind=dp), intent(out) :: fret
      logical, intent(out), optional :: success

      real(kind=dp), allocatable :: xi(:, :), pt(:), ptt(:), xit(:)
      real(kind=dp) :: fp, fptt, del, t
      integer :: i, iter, ibig
      real(kind=dp), parameter :: tiny = 1.0e-25_dp

      allocate (xi(n, n), pt(n), ptt(n), xit(n))
      xi = 0.0_dp
      do i = 1, n
         xi(i, i) = 1.0_dp
      end do

      fret = powell_user_fn(p)
      pt = p

      if (present(success)) success = .false.
      do iter = 1, maxiter
         fp = fret
         ibig = 0
         del = 0.0_dp
         do i = 1, n
            xit = xi(:, i)
            fptt = fret
            call powell_linmin(p, xit, n, fret)
            xi(:, i) = xit
            if (fptt - fret > del) then
               del = fptt - fret
               ibig = i
            end if
         end do
         if (2.0_dp*(fp - fret) <= ftol*(abs(fp) + abs(fret)) + tiny) then
            if (present(success)) success = .true.
            exit
         end if
         ptt = 2.0_dp*p - pt
         xit = p - pt
         pt = p
         fptt = powell_user_fn(ptt)
         if (fptt < fp) then
            t = 2.0_dp*(fp - 2.0_dp*fret + fptt)*(fp - fret - del)**2 - del*(fp - fptt)**2
            if (t < 0.0_dp) then
               call powell_linmin(p, xit, n, fret)
               if (ibig > 0) then
                  xi(:, ibig) = xi(:, n)
                  xi(:, n) = xit
               end if
            end if
         end if
      end do
   end subroutine powell_minimize

end module powell_bridge_mod
