! Windows implementation; selected automatically by xp2f.py.
module time_sleep_mod
   use, intrinsic :: iso_c_binding, only: c_int32_t
   use, intrinsic :: iso_fortran_env, only: real64, int64
   use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
   implicit none
   private
   public :: py_sleep
   interface
      subroutine win_sleep(milliseconds) bind(c, name="Sleep")
         import c_int32_t
         !GCC$ ATTRIBUTES STDCALL :: win_sleep
         integer(c_int32_t), value :: milliseconds
      end subroutine win_sleep
   end interface
contains
   subroutine py_sleep(seconds)
      real(real64), intent(in) :: seconds
      integer(int64) :: started, now, rate, maximum, ticks
      integer(c_int32_t) :: milliseconds
      real(real64) :: remaining
      if (.not. ieee_is_finite(seconds)) error stop "time.sleep: duration must be finite"
      if (seconds < 0.0_real64) error stop "time.sleep: duration must be nonnegative"
      if (seconds > 9.0e9_real64) error stop "time.sleep: duration too large"
      if (seconds == 0.0_real64) then
         call win_sleep(0_c_int32_t)
         return
      end if
      call system_clock(started, rate, maximum)
      if (rate <= 0_int64) error stop "time.sleep: monotonic clock unavailable"
      remaining = seconds
      do
         ! One-day chunks avoid DWORD overflow and the INFINITE sentinel.
         milliseconds = ceiling(min(remaining, 86400.0_real64)*1000.0_real64, kind=c_int32_t)
         call win_sleep(max(1_c_int32_t, milliseconds))
         call system_clock(now)
         if (now >= started) then
            ticks = now - started
         else
            ticks = (maximum - started) + now + 1_int64
         end if
         remaining = seconds - real(ticks, real64)/real(rate, real64)
         if (remaining <= 0.0_real64) exit
      end do
   end subroutine py_sleep
end module time_sleep_mod
