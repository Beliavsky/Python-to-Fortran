! transpiled by xp2f.py from run_dijkstra.py on 2026-09-11 08:32:35
module run_dijkstra_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: dijkstra_distance, dijkstra_distance_test, dp, find_nearest, &
      & init, update_mind
contains

function dijkstra_distance_test() result(min_distance)
   !  Test Dijkstra's algorithm
   !
   integer, allocatable :: min_distance(:)
   integer, parameter :: nv = 3000
   integer, allocatable :: ohd(:,:)
   
   allocate(ohd(nv,nv), source=0)
   call init(nv, ohd)
   allocate(min_distance(nv), source=0)
   call dijkstra_distance(nv, ohd, min_distance)
end function dijkstra_distance_test

pure subroutine init(nv, ohd)
   !  Create a graph
   !
   integer, intent(in) :: nv
   integer, intent(inout) :: ohd(:,:)
   integer :: i, i4_huge, j
   
   i4_huge = ishft(1, 20)
   do i = 1, nv
      do j = 0, nv - 1
         ohd(i, j + 1) = i4_huge
      end do
      ohd(i, i) = 0
   end do
   ohd(1, 334) = 33
end subroutine init

subroutine dijkstra_distance(nv, ohd, mind)
   !  Find the shortest paths between nodes in a graph
   !
   integer, intent(in) :: nv
   integer, intent(in) :: ohd(:,:)
   integer, intent(inout) :: mind(:)
   integer :: i, i_, mv, v_name
   logical, allocatable :: connected(:)
   
   allocate(connected(nv), source=.false.)
   connected(1) = .true.
   do i = 1, nv - 1
      connected(i + 1) = .false.
   end do
   do i = 1, nv - 1
      mind(i + 1) = ohd(1, i + 1)
   end do
   do i_ = 1, nv - 1
      call find_nearest(nv, mind, connected, v_name, mv)
      if (mv == -1) then
         write(*,"(a)") "DIJKSTRA_DISTANCE - Fatal error!"
         write(*,"(a)") "  Search terminated early."
         write(*,"(a)") "  Graph might not be connected."
      end if
      connected(mv + 1) = .true.
      call update_mind(nv, mv, connected, ohd, mind)
   end do
end subroutine dijkstra_distance

pure subroutine update_mind(nv, mv, connected, ohd, mind)
   !  Update the minimum distance
   !
   integer, intent(in) :: nv, mv
   logical, intent(in) :: connected(:)
   integer, intent(in) :: ohd(:,:)
   integer, intent(inout) :: mind(:)
   integer :: i
   integer, parameter :: i4_huge = 2147483647
   
   do i = 1, nv
      if (.not. connected(i)) then
         if (ohd(mv + 1, i) < i4_huge) mind(i) = min(mind(i), mind(mv + 1) + &
            & ohd(mv + 1, i))
      end if
   end do
end subroutine update_mind

pure subroutine find_nearest(nv, mind, connected, d, v)
   !  Find the nearest node
   !
   integer, intent(in) :: nv
   integer, intent(in) :: mind(:)
   logical, intent(in) :: connected(:)
   integer, intent(out) :: d, v
   integer :: i
   integer, parameter :: i4_huge = 2147483647
   
   d = i4_huge
   v = -1
   do i = 0, nv - 1
      if (.not. connected(i + 1)) then
         if (mind(i + 1) <= d) then
            d = mind(i + 1)
            v = i
         end if
      end if
   end do
end subroutine find_nearest

end module run_dijkstra_proc_mod

program run_dijkstra
   use run_dijkstra_proc_mod, only: dijkstra_distance_test
   implicit none
   integer, allocatable :: d(:)
   
   d = dijkstra_distance_test()
   print *, int(minval(d)), int(maxval(d)), int(d(2)), int(d(1001)), &
      & int(d(2001)), int(d(3000))
end program run_dijkstra
