program use_lib
   ! The routines of the extracted, standalone module (no python_mod).
   use numpy_fortran
   implicit none
   integer, parameter :: dp = kind(1.0d0)
   real(dp) :: x(5), c(3), m(2, 3)
   complex(dp), allocatable :: f(:,:)
   x = [0.0_dp, 0.25_dp, 0.5_dp, 0.75_dp, 1.0_dp]
   c = [1.0_dp, -2.0_dp, 0.5_dp]
   print "(*(es24.16))", chebval(x, c)
   print "(*(es24.16))", chebfit(x, chebval(x, c), 2)
   m = reshape([1.0_dp, 2.0_dp, 3.0_dp, 4.0_dp, 5.0_dp, 6.0_dp], [2, 3])
   f = fft2(m)
   print "(*(es24.16))", real(f), aimag(f)
   print "(*(es24.16))", np_pad_vec(x(1:3), 2, 1, 3)
   print "(*(es24.16))", legval2d(0.3_dp, -0.2_dp, reshape([1.0_dp, 0.5_dp, -1.0_dp, 2.0_dp], [2, 2]))
end program use_lib
