module dijkstra

  use, intrinsic :: ISO_C_Binding, only : b1 => C_BOOL , i64 => &
        C_INT64_T
  use, intrinsic :: ISO_FORTRAN_ENV, only : stdout => output_unit

  implicit none

  public :: find_nearest
  public :: update_mind
  public :: dijkstra_distance
  public :: init
  public :: dijkstra_distance_test

  private

  contains

  !........................................
  !______________________!
  ! Find the nearest node!
  !                      !
  !______________________!

  subroutine find_nearest(d, v, nv, mind, connected) 

    implicit none

    integer(i64), intent(out) :: d
    integer(i64), intent(out) :: v
    integer(i64), value :: nv
    integer(i64), intent(inout) :: mind(0_i64:)
    logical(b1), intent(inout) :: connected(0_i64:)
    integer(i64) :: i4_huge
    integer(i64) :: i

    i4_huge = 2147483647_i64
    d = i4_huge
    v = -1_i64
    do i = 0_i64, nv - 1_i64
      if (.not. connected(i) .and. mind(i) <= d) then
        d = mind(i)
        v = i
      end if
    end do
    return

  end subroutine find_nearest
  !........................................

  !........................................
  !____________________________!
  ! Update the minimum distance!
  !                            !
  !____________________________!

  subroutine update_mind(nv, mv, connected, ohd, mind) 

    implicit none

    integer(i64), value :: nv
    integer(i64), value :: mv
    logical(b1), intent(inout) :: connected(0_i64:)
    integer(i64), intent(inout) :: ohd(0_i64:, 0_i64:)
    integer(i64), intent(inout) :: mind(0_i64:)
    integer(i64) :: i4_huge
    integer(i64) :: i

    i4_huge = 2147483647_i64
    do i = 0_i64, nv - 1_i64
      if (.not. connected(i)) then
        if (ohd(i, mv) < i4_huge) then
          mind(i) = minval([mind(i), mind(mv) + ohd(i, mv)])
        end if
      end if
    end do

  end subroutine update_mind
  !........................................

  !........................................
  !________________________________________________!
  ! Find the shortest paths between nodes in a graph!
  !                                                !
  !________________________________________________!

  subroutine dijkstra_distance(nv, ohd, mind) 

    implicit none

    integer(i64), value :: nv
    integer(i64), intent(inout) :: ohd(0_i64:, 0_i64:)
    integer(i64), intent(inout) :: mind(0_i64:)
    logical(b1), allocatable :: connected(:)
    integer(i64) :: i
    integer(i64) :: Dummy_0000
    integer(i64) :: Dummy_0001
    integer(i64) :: Dummy_0002
    integer(i64) :: mv

    !Start out with only node 1 connected to the tree.
    allocate(connected(0:nv - 1_i64))
    connected(:) = .False._b1
    connected(0_i64) = .True._b1
    do i = 1_i64, nv - 1_i64
      connected(i) = .False._b1
    end do
    !Initialize the minimum distance to the one-step distance.
    do i = 1_i64, nv - 1_i64
      mind(i) = ohd(i, 0_i64)
    end do
    !Attach one more node on each iteration.
    do Dummy_0000 = 1_i64, nv - 1_i64
      !Find the nearest unconnected node.
      call find_nearest(Dummy_0002, mv, nv, mind, connected)
      if (mv == -1_i64) then
        write(stdout, '(A)', advance="yes") 'DIJKSTRA_DISTANCE - Fatal &
        &error!'
        write(stdout, '(A)', advance="yes") '  Search terminated early.&
        &'
        write(stdout, '(A)', advance="yes") '  Graph might not be &
        &connected.'
        !TODO exit
        !exit ( 'DIJKSTRA_DISTANCE - Fatal error!' )
      end if
      !Mark this node as connected.
      connected(mv) = .True._b1
      !Having determined the minimum distance to node MV, see if
      !that reduces the minimum distance to other nodes.
      call update_mind(nv, mv, connected, ohd, mind)
    end do
    if (allocated(connected)) deallocate(connected)

  end subroutine dijkstra_distance
  !........................................

  !........................................
  !____________________!
  ! Create a graph     !
  !                    !
  !____________________!

  subroutine init(nv, ohd) 

    implicit none

    integer(i64), value :: nv
    integer(i64), intent(inout) :: ohd(0_i64:, 0_i64:)
    integer(i64) :: i4_huge
    integer(i64) :: i
    integer(i64) :: j

    i4_huge = LSHIFT(1_i64, 20_i64)
    do i = 0_i64, nv - 1_i64
      do j = 0_i64, nv - 1_i64
        ohd(j, i) = i4_huge
      end do
      ohd(i, i) = 0_i64
    end do
    ohd(333_i64, 0_i64) = 33_i64

  end subroutine init
  !........................................

  !........................................
  !__________________________!
  ! Test Dijkstra's algorithm!
  !                          !
  !__________________________!

  subroutine dijkstra_distance_test(min_distance) 

    implicit none

    integer(i64), allocatable, intent(out) :: min_distance(:)
    integer(i64) :: nv
    integer(i64), allocatable :: ohd(:, :)

    !Initialize the problem data.
    nv = 3000_i64
    allocate(ohd(0:nv - 1_i64, 0:nv - 1_i64))
    ohd(:,:) = 0_i64
    call init(nv, ohd)
    !Carry out the algorithm.
    allocate(min_distance(0:nv - 1_i64))
    min_distance(:) = 0_i64
    call dijkstra_distance(nv, ohd, min_distance)
    if (allocated(ohd)) deallocate(ohd)
    return

  end subroutine dijkstra_distance_test
  !........................................

end module dijkstra
