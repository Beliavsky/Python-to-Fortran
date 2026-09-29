! POSIX LP64 implementation (64-bit Linux/macOS); selected by xp2f.py.
! timespec uses a 64-bit time_t and C long on these targets.
module time_sleep_mod
   use, intrinsic :: iso_c_binding, only: c_long, c_int, c_sizeof
   use, intrinsic :: iso_fortran_env, only: real64
   use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
   implicit none
   private
   public :: py_sleep
   type, bind(c) :: timespec
      integer(c_long) :: tv_sec, tv_nsec
   end type timespec
   interface
      function nanosleep(request, remaining) bind(c, name="nanosleep") result(status)
         import timespec, c_int
         type(timespec), intent(in) :: request
         type(timespec), intent(inout) :: remaining
         integer(c_int) :: status
      end function nanosleep
   end interface
contains
   subroutine py_sleep(seconds)
      real(real64), intent(in) :: seconds
      type(timespec) :: request, remaining
      integer(c_int) :: status
      if (.not. ieee_is_finite(seconds)) error stop "time.sleep: duration must be finite"
      if (seconds < 0.0_real64) error stop "time.sleep: duration must be nonnegative"
      if (seconds > 9.0e9_real64) error stop "time.sleep: duration too large"
      if (c_sizeof(0_c_long) /= 8) error stop "time.sleep: POSIX helper requires LP64"
      request%tv_sec = int(seconds, c_long)
      request%tv_nsec = ceiling((seconds-real(request%tv_sec, real64))*1.0e9_real64, kind=c_long)
      if (request%tv_nsec >= 1000000000_c_long) then
         request%tv_sec = request%tv_sec + 1_c_long
         request%tv_nsec = 0_c_long
      end if
      do
         ! nanosleep only supplies a remaining interval on interruption.
         remaining = timespec(-1_c_long, -1_c_long)
         status = nanosleep(request, remaining)
         if (status == 0) exit
         if (remaining%tv_sec < 0 .or. remaining%tv_nsec < 0 .or. &
             remaining%tv_nsec >= 1000000000_c_long) error stop "time.sleep: nanosleep failed"
         request = remaining
      end do
   end subroutine py_sleep
end module time_sleep_mod
