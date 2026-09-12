! transpiled by xp2f.py from run_ackermann.py on 2026-09-11 08:29:19
module run_ackermann_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: ackermann, dp
contains

pure recursive function ackermann(m, n) result(func_res)
   !   Total computable function that is not primitive recursive.
   !     This function is useful for testing recursion
   !
   integer, intent(in) :: m, n
   integer :: func_res
   if (m == 0) then
      func_res = n + 1
      return
   else
      if (n == 0) then
         func_res = ackermann(m - 1, 1)
         return
      else
         func_res = ackermann(m - 1, ackermann(m, n - 1))
         return
      end if
   end if
end function ackermann

end module run_ackermann_proc_mod

program run_ackermann
   use run_ackermann_proc_mod, only: ackermann
   implicit none
   integer :: a
   
   a = ackermann(3, 6)
   print *, a
end program run_ackermann
