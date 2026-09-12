module bellman_ford_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T
  use, intrinsic :: ISO_FORTRAN_ENV, only : stdout => output_unit

  implicit none

  public :: bellman_ford
  public :: bellman_ford_test

  private

  contains

  !........................................
  !______________________________________________________________!
  ! Calculate the shortest paths from a source vertex to all other!
  !    vertices in the weighted digraph                          !
  !                                                              !
  !______________________________________________________________!

  function bellman_ford(v_num, e_num, source, e, e_weight, v_weight, &
        predecessor) result(result_0001)

    implicit none

    integer(i64) :: result_0001
    integer(i64), value :: v_num
    integer(i64), value :: e_num
    integer(i64), value :: source
    integer(i64), intent(inout) :: e(0_i64:, 0_i64:)
    real(f64), intent(inout) :: e_weight(0_i64:)
    real(f64), intent(inout) :: v_weight(0_i64:)
    integer(i64), intent(inout) :: predecessor(0_i64:)
    real(f64) :: r8_big
    integer(i64) :: i
    integer(i64) :: j
    integer(i64) :: u
    integer(i64) :: v
    real(f64) :: t

    r8_big = 100000000000000.0_f64
    !Step 1: initialize the graph.
    do i = 0_i64, v_num - 1_i64
      v_weight(i) = r8_big
    end do
    v_weight(source) = 0.0_f64
    predecessor(:v_num - 1_i64) = -1_i64
    !Step 2: Relax edges repeatedly.
    do i = 1_i64, v_num - 1_i64
      do j = 0_i64, e_num - 1_i64
        u = e(j, 1_i64)
        v = e(j, 0_i64)
        t = v_weight(u) + e_weight(j)
        if (t < v_weight(v)) then
          v_weight(v) = t
          predecessor(v) = u
        end if
      end do
    end do
    !Step 3: check for negative-weight cycles
    do j = 0_i64, e_num - 1_i64
      u = e(j, 1_i64)
      v = e(j, 0_i64)
      if (v_weight(u) + e_weight(j) < v_weight(v)) then
        write(stdout, '(A)', advance="yes") ''
        write(stdout, '(A)', advance="yes") 'BELLMAN_FORD - Fatal error&
        &!'
        write(stdout, '(A)', advance="yes") '  Graph contains a cycle &
        &with negative weight.'
        result_0001 = 1_i64
        return
      end if
    end do
    result_0001 = 0_i64
    return

  end function bellman_ford
  !........................................

  !........................................
  !______________________________!
  ! Test bellman ford's algorithm!
  !                              !
  !______________________________!

  subroutine bellman_ford_test(v_weight) 

    implicit none

    real(f64), allocatable, intent(out) :: v_weight(:)
    integer(i64) :: e_num
    integer(i64) :: v_num
    integer(i64), allocatable :: e(:, :)
    real(f64), allocatable :: e_weight(:)
    integer(i64) :: idx
    integer(i64) :: i
    integer(i64) :: j
    integer(i64) :: source
    integer(i64), allocatable :: predecessor(:)
    integer(i64) :: Dummy_0000

    e_num = 19900_i64
    v_num = 200_i64
    allocate(e(0:e_num - 1_i64, 0:1_i64))
    e(:,:) = 0_i64
    allocate(e_weight(0:e_num - 1_i64))
    e_weight(:) = 0.0_f64
    idx = 0_i64
    do i = 0_i64, v_num - 1_i64
      do j = 0_i64, v_num - 1_i64
        if (i > j) then
          e(idx, 0_i64) = i
          e(idx, 1_i64) = j
          idx = idx + 1_i64
        end if
      end do
    end do
    do i = 0_i64, e_num - 1_i64
      e_weight(i) = cos(Real(i, kind = f64)) * i
    end do
    source = 0_i64
    allocate(v_weight(0:v_num - 1_i64))
    v_weight(:) = 0.0_f64
    allocate(predecessor(0:v_num - 1_i64))
    predecessor(:) = 0_i64
    Dummy_0000 = bellman_ford(v_num, e_num, source, e, e_weight, &
          v_weight, predecessor)
    if (allocated(predecessor)) deallocate(predecessor)
    if (allocated(e)) deallocate(e)
    if (allocated(e_weight)) deallocate(e_weight)
    return

  end subroutine bellman_ford_test
  !........................................

end module bellman_ford_mod
