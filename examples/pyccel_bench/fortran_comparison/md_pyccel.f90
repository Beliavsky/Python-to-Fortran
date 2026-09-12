module md_mod

  use, intrinsic :: ISO_C_Binding, only : f64 => C_DOUBLE , i64 => &
        C_INT64_T
  use pyc_math_f90

  implicit none

  public :: compute_kinetic_energy
  public :: compute
  public :: update
  public :: r8mat_uniform_ab
  public :: initialize
  public :: md

  private

  contains

  !........................................
  !______________________________________________________________________!
  ! Compute the kinetic energy associated with the current configuration.!
  !                                                                      !
  !______________________________________________________________________!

  function compute_kinetic_energy(vel, mass) result(result_0001)

    implicit none

    real(f64) :: result_0001
    real(f64), intent(inout) :: vel(0_i64:, 0_i64:)
    real(f64), value :: mass
    integer(i64) :: d_num
    integer(i64) :: p_num
    real(f64) :: kinetic
    integer(i64) :: k
    integer(i64) :: j

    d_num = size(vel, 2_i64, i64)
    p_num = size(vel, 1_i64, i64)
    kinetic = 0.0_f64
    do k = 0_i64, d_num - 1_i64
      do j = 0_i64, p_num - 1_i64
        kinetic = kinetic + vel(j, k) ** 2_i64
      end do
    end do
    result_0001 = 0.5_f64 * mass * kinetic
    return

  end function compute_kinetic_energy
  !........................................

  !........................................
  !________________________________________________________________!
  !                                                                !
  !    Calculate the potential energy and forces associated with the!
  !    current configuration.                                      !
  !                                                                !
  !                                                                !
  !________________________________________________________________!

  function compute(mass, pos, vel, force) result(potential)

    implicit none

    real(f64) :: potential
    real(f64), value :: mass
    real(f64), intent(inout) :: pos(0_i64:, 0_i64:)
    real(f64), intent(inout) :: vel(0_i64:, 0_i64:)
    real(f64), intent(inout) :: force(0_i64:, 0_i64:)
    integer(i64) :: d_num
    integer(i64) :: p_num
    real(f64), allocatable :: rij(:)
    integer(i64) :: i
    integer(i64) :: j
    integer(i64) :: k
    real(f64) :: d
    real(f64) :: d2

    d_num = size(pos, 2_i64, i64)
    p_num = size(pos, 1_i64, i64)
    allocate(rij(0:d_num - 1_i64))
    rij(:) = 0.0_f64
    potential = 0.0_f64
    force(:, :) = 0.0_f64
    do i = 0_i64, p_num - 1_i64
      !
      !Compute the potential energy and forces.
      !
      do j = 0_i64, p_num - 1_i64
        if (i /= j) then
          !Compute RIJ, the displacement vector.
          do k = 0_i64, d_num - 1_i64
            rij(k) = pos(i, k) - pos(j, k)
          end do
          !Compute D and D2, a distance and a truncated distance.
          d = 0.0_f64
          do k = 0_i64, d_num - 1_i64
            d = d + rij(k) ** 2_i64
          end do
          d = sqrt(d)
          d2 = minval([d, 3.141592653589793_f64 / 2.0_f64])
          !Attribute half of the total potential energy to particle J.
          potential = potential + 0.5_f64 * sin(d2) * sin(d2)
          !Add particle J's contribution to the force on particle I.
          do k = 0_i64, d_num - 1_i64
            force(i, k) = force(i, k) - rij(k) * sin(2.0_f64 * d2) / d
          end do
        end if
      end do
    end do
    if (allocated(rij)) deallocate(rij)
    return

  end function compute
  !........................................

  !........................................
  !________________________________________________________________!
  ! Update the position, velocity and acceleration of the particles!
  !                                                                !
  !________________________________________________________________!

  subroutine update(dt, mass, force, pos, vel, acc) 

    implicit none

    real(f64), value :: dt
    real(f64), value :: mass
    real(f64), intent(inout) :: force(0_i64:, 0_i64:)
    real(f64), intent(inout) :: pos(0_i64:, 0_i64:)
    real(f64), intent(inout) :: vel(0_i64:, 0_i64:)
    real(f64), intent(inout) :: acc(0_i64:, 0_i64:)
    real(f64) :: rmass

    rmass = 1.0_f64 / mass
    !
    !Update positions.
    !
    pos(:,:) = pos + (vel * dt + 0.5_f64 * acc * dt * dt)
    !
    !Update velocities.
    !
    vel(:,:) = vel + 0.5_f64 * dt * (force * rmass + acc)
    !
    !Update accelerations.
    !
    acc(:, :) = force * rmass

  end subroutine update
  !........................................

  !........................................
  !______________________________________________________!
  ! Fill r with random numbers with a uniform distribution!
  !                                                      !
  !______________________________________________________!

  function r8mat_uniform_ab(r, a, b, seed) result(result_0001)

    implicit none

    integer(i64) :: result_0001
    real(f64), intent(inout) :: r(0_i64:, 0_i64:)
    real(f64), value :: a
    real(f64), value :: b
    integer(i64), value :: seed
    integer(i64) :: m
    integer(i64) :: n
    integer(i64) :: i4_huge
    integer(i64) :: j
    integer(i64) :: i
    integer(i64) :: k

    m = size(r, 2_i64, i64)
    n = size(r, 1_i64, i64)
    i4_huge = 2147483647_i64
    if (seed <= 0_i64) then
      seed = seed + i4_huge
    else if (seed > 0_i64) then
      do j = 0_i64, n - 1_i64
        do i = 0_i64, m - 1_i64
          k = pyc_floor_div(seed, 127773_i64)
          seed = 16807_i64 * (seed - k * 127773_i64) - k * 2836_i64
          seed = MODULO(seed,i4_huge)
          if (seed <= 0_i64) then
            seed = seed + i4_huge
          end if
          r(j, i) = a + (b - a) * seed * 4.656612875e-10_f64
        end do
      end do
    end if
    result_0001 = seed
    return

  end function r8mat_uniform_ab
  !........................................

  !........................................
  !__________________________________________!
  ! Initialise the positions of the particles!
  !                                          !
  !__________________________________________!

  subroutine initialize(pos) 

    implicit none

    real(f64), intent(inout) :: pos(0_i64:, 0_i64:)
    integer(i64) :: seed
    integer(i64) :: Dummy_0000

    !Positions.
    seed = 123456789_i64
    Dummy_0000 = seed
    seed = r8mat_uniform_ab(pos, 0.0_f64, 10.0_f64, Dummy_0000)

  end subroutine initialize
  !........................................

  !........................................
  !__________________________________________________________________!
  !                                                                  !
  !    Run a molecular dynamics simulation. This consists of an N-body!
  !    problem in 3D, where N identical particles of unit mass       !
  !    interact through a given potential and accelerate according   !
  !    to Newton's 2nd law of motion.                                !
  !                                                                  !
  !    Parameters                                                    !
  !    ----------                                                    !
  !    d_num : int                                                   !
  !        Number of dimensions, i.e. number of components of        !
  !        position and velocity vectors.                            !
  !                                                                  !
  !    p_num : int                                                   !
  !        Number of particles.                                      !
  !                                                                  !
  !    dt : float                                                    !
  !        Time step size.                                           !
  !                                                                  !
  !    step_num : int                                                !
  !        Number of time steps to be taken.                         !
  !                                                                  !
  !    Returns                                                       !
  !    -------                                                       !
  !    potential : float                                             !
  !        Total potential energy of the system.                     !
  !                                                                  !
  !    kinetic : float                                               !
  !        Total kinetic energy of the system.                       !
  !                                                                  !
  !                                                                  !
  !__________________________________________________________________!

  subroutine md(potential, kinetic, d_num, p_num, step_num, dt) 

    implicit none

    real(f64), intent(out) :: potential
    real(f64), intent(out) :: kinetic
    integer(i64), value :: d_num
    integer(i64), value :: p_num
    integer(i64), value :: step_num
    real(f64), value :: dt
    real(f64) :: mass
    real(f64), allocatable :: pos(:, :)
    real(f64), allocatable :: vel(:, :)
    real(f64), allocatable :: acc(:, :)
    real(f64), allocatable :: force(:, :)
    integer(i64) :: Dummy_0000
    integer(i64) :: Dummy_0001

    !Set particles' mass
    mass = 1.0_f64
    !Allocate work arrays
    allocate(pos(0:p_num - 1_i64, 0:d_num - 1_i64))
    pos(:,:) = 0.0_f64
    allocate(vel(0:p_num - 1_i64, 0:d_num - 1_i64))
    vel(:,:) = 0.0_f64
    allocate(acc(0:p_num - 1_i64, 0:d_num - 1_i64))
    acc(:,:) = 0.0_f64
    allocate(force(0:p_num - 1_i64, 0:d_num - 1_i64))
    force(:,:) = 0.0_f64
    !Initialization
    call initialize(pos)
    potential = compute(mass, pos, vel, force)
    !Time stepping
    do Dummy_0000 = 0_i64, step_num - 1_i64
      call update(dt, mass, force, pos, vel, acc)
      potential = compute(mass, pos, vel, force)
    end do
    !Compute total kinetic energy at final time
    kinetic = compute_kinetic_energy(vel, mass)
    !Return total potential and kinetic energies
    if (allocated(vel)) deallocate(vel)
    if (allocated(pos)) deallocate(pos)
    if (allocated(force)) deallocate(force)
    if (allocated(acc)) deallocate(acc)
    return

  end subroutine md
  !........................................

end module md_mod
