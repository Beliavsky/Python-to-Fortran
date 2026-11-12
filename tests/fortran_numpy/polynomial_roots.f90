program d2
   use numpy_fortran
   implicit none
   integer, parameter :: dp = kind(1.0d0)
   real(dp) :: c(4), c2(3)
   real(dp), allocatable :: x(:), w(:), q(:), r(:)
   complex(dp), allocatable :: z(:)
   c = [0.5_dp, -1.0_dp, 2.0_dp, 0.25_dp]
   c2 = [1.0_dp, 3.0_dp, -2.0_dp]
   z = powroots(c); print "(*(es24.16))", z
   z = chebroots(c); print "(*(es24.16))", z
   z = legroots(c); print "(*(es24.16))", z
   z = hermroots(c); print "(*(es24.16))", z
   z = hermeroots(c); print "(*(es24.16))", z
   z = lagroots(c); print "(*(es24.16))", z
   print "(*(es24.16))", chebcompanion(c), legcompanion(c), hermcompanion(c), hermecompanion(c), lagcompanion(c), powcompanion(c)
   call chebgauss(5, x, w); print "(*(es24.16))", x, w
   call hermgauss(6, x, w); print "(*(es24.16))", x, w
   call hermegauss(5, x, w); print "(*(es24.16))", x, w
   call laggauss(5, x, w); print "(*(es24.16))", x, w
   print "(*(es24.16))", powfromroots([1.0_dp, -2.0_dp, 3.0_dp]), chebfromroots([0.5_dp, -0.25_dp, 0.75_dp, 0.1_dp]), &
      legfromroots([1.0_dp, 2.0_dp]), hermfromroots([0.3_dp, -0.7_dp, 1.1_dp]), hermefromroots([1.0_dp]), &
      lagfromroots([0.5_dp, 2.0_dp, 4.0_dp])
   print "(*(es24.16))", powmulx(c), chebmulx(c), legmulx(c), hermmulx(c), hermemulx(c), lagmulx(c)
   print "(*(es24.16))", powadd(c, c2), chebsub(c2, c), powmul(c, c2), chebmul(c, c2), legmul(c, c2), hermmul(c, c2), &
      hermemul(c, c2), lagmul(c, c2)
   call powdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call chebdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call legdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call hermdiv(c, c2, q, r); print "(*(es24.16))", q, r
   call hermediv(c, c2, q, r); print "(*(es24.16))", q, r
   call lagdiv(c, c2, q, r); print "(*(es24.16))", q, r
   print "(*(es24.16))", powpow(c2, 3), chebpow(c2, 3), legpow(c2, 2), hermpow(c2, 2), hermepow(c2, 2), lagpow(c2, 3)
   print "(*(es24.16))", powline(1.5_dp, 2.0_dp), hermline(1.5_dp, 2.0_dp), lagline(1.5_dp, 2.0_dp), chebline(3.0_dp, 0.0_dp)
   print "(*(es24.16))", cheb2poly(c), poly2cheb(c), leg2poly(c), poly2leg(c), herm2poly(c), poly2herm(c), &
      herme2poly(c), poly2herme(c), lag2poly(c), poly2lag(c)
   print "(*(es24.16))", chebpts1(5), chebpts2(5), chebtrim([1.0_dp, 2.0_dp, 1.0e-12_dp, 0.0_dp], 1.0e-10_dp), powtrim([3.0_dp, 0.0_dp])
   print "(*(es24.16))", chebrealroots(chebfromroots([-0.5_dp, 0.25_dp, 0.75_dp])), powrealroots([2.0_dp, 0.0_dp, 1.0_dp]), &
      chebrealroots(c, lo=-1.0_dp, hi=1.0_dp)
end program d2
