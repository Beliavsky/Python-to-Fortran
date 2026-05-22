! transpiled by xp2f.py from xprime.py
module xprime_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   real(kind=dp) :: max_prime
   integer :: nprime
   public :: dp, is_prime, max_prime, nprime
contains

pure function is_prime(n) result(is_prime_result)
   integer, intent(in) :: n
   logical :: is_prime_result
   integer :: d
   
   if (n < 2) then
      is_prime_result = .false.
      return
   end if
   if (n == 2) then
      is_prime_result = .true.
      return
   end if
   if (modulo(n, 2) == 0) then
      is_prime_result = .false.
      return
   end if
   d = 3
   do while (((d * d) <= n))
      if (modulo(n, d) == 0) then
         is_prime_result = .false.
         return
      end if
      d = d + 2
   end do
   is_prime_result = .true.
end function is_prime

end module xprime_proc_mod

program xprime
   use xprime_proc_mod, only: is_prime, max_prime, nprime
   implicit none
   integer, parameter :: limit = 10 ** 6 ! constant from python source
   integer :: n
   
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
