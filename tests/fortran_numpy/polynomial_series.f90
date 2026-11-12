program direct
   ! Calling the np.polynomial routines directly from Fortran.
   use numpy_fortran, only: chebval, chebfit, chebder, chebint, chebvander, legval, legfit, hermval, hermeval, &
      lagval, powval, powfit, powder, powint, lagfit, hermfit, hermefit, legder, legint, hermder, hermint, &
      hermeder, hermeint, lagder, lagint
   implicit none
   integer, parameter :: dp = kind(1.0d0)
   real(dp) :: x(7), y(7), c(4), v(7, 4)
   integer :: i
   x = [(-1.0_dp + 2.0_dp * (i - 1) / 6.0_dp, i = 1, 7)]
   y = exp(x) * cos(3.0_dp * x)
   c = [0.5_dp, -1.0_dp, 2.0_dp, 0.25_dp]
   print "(*(es24.16))", chebval(0.3_dp, c), legval(0.3_dp, c), hermval(0.3_dp, c), hermeval(0.3_dp, c), &
      lagval(0.3_dp, c), powval(0.3_dp, c)
   print "(*(es24.16))", chebval(x, c)
   print "(*(es24.16))", chebfit(x, y, 3), legfit(x, y, 4), powfit(x, y, 2)
   print "(*(es24.16))", hermfit(x, y, 3), hermefit(x, y, 3), lagfit(x, y, 3)
   print "(*(es24.16))", chebder(c), chebint(c), chebint(c, m=2, k=[1.0_dp, 2.0_dp], lbnd=0.5_dp, scl=2.0_dp)
   print "(*(es24.16))", legder(c, 2), legint(c), hermder(c), hermint(c, k=[3.0_dp]), hermeder(c, scl=3.0_dp)
   print "(*(es24.16))", hermeint(c, m=2), lagder(c), lagint(c, lbnd=1.0_dp), powder(c), powint(c, m=3)
   v = chebvander(x, 3)
   print "(*(es24.16))", v(3, :), sum(v)
   print "(*(es24.16))", chebfit(x, y, 2, w=[(1.0_dp + i, i = 1, 7)])
end program direct
