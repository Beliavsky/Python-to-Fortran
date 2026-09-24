! transpiled by xp2f.py from xprime.py on 2026-09-12 08:45:09
module xprime_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dp, is_prime
contains

pure function is_prime(n) result(func_res)
   integer, intent(in) :: n
   logical :: func_res
   integer :: d
   
   if (n < 2) then
      func_res = .false.
      return
   end if
   if (n == 2) then
      func_res = .true.
      return
   end if
   if (modulo(n, 2) == 0) then
      func_res = .false.
      return
   end if
   d = 3
   do while (d * d <= n)
      if (modulo(n, d) == 0) then
         func_res = .false.
         return
      end if
      d = d + 2
   end do
   func_res = .true.
end function is_prime

end module xprime_proc_mod

program xprime
   use xprime_proc_mod, only: is_prime
   implicit none
   integer, parameter :: limit = 10 ** 6 ! constant from python source
   integer :: max_prime, n, nprime
   
   nprime = 0
   do n = 2, limit
      if (is_prime(n)) then
         nprime = nprime + 1
         max_prime = n
      end if
   end do
   print *, "number of primes =", nprime
   print *, "largest prime    =", max_prime
end program xprime
