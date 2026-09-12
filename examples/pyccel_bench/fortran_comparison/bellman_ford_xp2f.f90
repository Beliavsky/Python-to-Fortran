! transpiled by xp2f.py from run_bellman_ford.py on 2026-09-11 08:28:12
module run_bellman_ford_proc_mod
   use, intrinsic :: ieee_arithmetic, only: ieee_is_nan
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: bellman_ford, bellman_ford_test, dp
contains

function bellman_ford_test() result(v_weight)
   !  Test bellman ford's algorithm
   !
   real(kind=dp), allocatable :: v_weight(:)
   integer, parameter :: e_num = 19900, v_num = 200
   integer :: i, idx, j, source
   integer, allocatable :: e(:,:), predecessor(:)
   real(kind=dp), allocatable :: e_weight(:)
   
   allocate(e(2,e_num), source=0)
   allocate(e_weight(e_num), source=0.0_dp)
   idx = 0
   do i = 0, v_num - 1
      do j = 0, v_num - 1
         if (i > j) then
            e(1:2,idx + 1) = [i, j]
            idx = idx + 1
         end if
      end do
   end do
   do i = 0, e_num - 1
      e_weight(i + 1) = cos(real(i, kind=dp)) * i
   end do
   source = 0
   allocate(v_weight(v_num), source=0.0_dp)
   allocate(predecessor(v_num), source=0)
   block
      integer :: ignored_bellman_ford_76
      ignored_bellman_ford_76 = bellman_ford(v_num, e_num, source, e, &
         & e_weight, v_weight, predecessor)
   end block
end function bellman_ford_test

function bellman_ford(v_num, e_num, source, e, e_weight, v_weight, &
   & predecessor) result(func_res)
   !  Calculate the shortest paths from a source vertex to all other
   !     vertices in the weighted digraph
   !
   integer, intent(in) :: v_num, e_num, source
   integer, intent(in) :: e(:,:)
   real(kind=dp), intent(in) :: e_weight(:)
   real(kind=dp), intent(inout) :: v_weight(:)
   integer, intent(inout) :: predecessor(:)
   integer :: func_res
   real(kind=dp), parameter :: r8_big = 100000000000000.0_dp
   real(kind=dp) :: t
   integer :: i, j, u, v
   
   do i = 0, v_num - 1
      v_weight(i + 1) = r8_big
   end do
   v_weight(source + 1) = 0.0_dp
   predecessor(1:v_num) = -1
   do i = 1, v_num - 1
      do j = 1, e_num
         u = e(2, j)
         v = e(1, j)
         t = v_weight(u + 1) + e_weight(j)
         if (merge(.false., merge(0.0_dp, t, ieee_is_nan(t)) < merge(0.0_dp, &
            & v_weight(v + 1), ieee_is_nan(v_weight(v + 1))), ieee_is_nan(t) &
            & .or. ieee_is_nan(v_weight(v + 1)))) then
            v_weight(v + 1) = t
            predecessor(v + 1) = u
         end if
      end do
   end do
   do j = 1, e_num
      u = e(2, j)
      v = e(1, j)
      if (merge(.false., merge(0.0_dp, v_weight(u + 1) + e_weight(j), &
         & ieee_is_nan(v_weight(u + 1) + e_weight(j))) < merge(0.0_dp, &
         & v_weight(v + 1), ieee_is_nan(v_weight(v + 1))), &
         & ieee_is_nan(v_weight(u + 1) + e_weight(j)) .or. &
         & ieee_is_nan(v_weight(v + 1)))) then
         write(*,"(a)") ""
         write(*,"(a)") "BELLMAN_FORD - Fatal error!"
         write(*,"(a)") "  Graph contains a cycle with negative weight."
         func_res = 1
         return
      end if
   end do
   func_res = 0
end function bellman_ford

end module run_bellman_ford_proc_mod

program run_bellman_ford
   use run_bellman_ford_proc_mod, only: bellman_ford_test, dp
   implicit none
   real(kind=dp) :: hi, last, lo, mid, total
   real(kind=dp), allocatable :: v(:)
   
   v = bellman_ford_test()
   total = sum(v)
   lo = minval(v)
   hi = maxval(v)
   mid = v(101)
   last = v(200)
   write(*,"(f0.6, 4(1x, f0.6))") total, lo, hi, mid, last
end program run_bellman_ford
