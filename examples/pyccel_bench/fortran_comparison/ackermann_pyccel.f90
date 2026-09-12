module ackermann_mod

  use, intrinsic :: ISO_C_Binding, only : i64 => C_INT64_T

  implicit none

  public :: ackermann

  private

  contains

  !........................................
  !____________________________________________________________!
  !  Total computable function that is not primitive recursive.!
  !    This function is useful for testing recursion           !
  !                                                            !
  !____________________________________________________________!

  recursive function ackermann(m, n) result(result_0001)

    implicit none

    integer(i64) :: result_0001
    integer(i64), value :: m
    integer(i64), value :: n

    if (m == 0_i64) then
      result_0001 = n + 1_i64
      return
    else if (n == 0_i64) then
      result_0001 = ackermann(m - 1_i64, 1_i64)
      return
    else
      result_0001 = ackermann(m - 1_i64, ackermann(m, n - 1_i64))
      return
    end if

  end function ackermann
  !........................................

end module ackermann_mod
