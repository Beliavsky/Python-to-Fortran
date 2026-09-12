! transpiled by xp2f.py from run_md.py on 2026-09-11 08:31:00
module run_md_proc_mod
   use, intrinsic :: iso_fortran_env, only: real64
   implicit none
   private
   integer, parameter :: dp = real64
   public :: compute, compute_kinetic_energy, dp, initialize, md, &
      & r8mat_uniform_ab, update
contains

subroutine md(d_num, p_num, step_num, dt, potential, kinetic)
   !
   !     Run a molecular dynamics simulation. This consists of an N-body
   !     problem in 3D, where N identical particles of unit mass
   !     interact through a given potential and accelerate according
   !     to Newton's 2nd law of motion.
   !
   !     Parameters
   !     ----------
   !     d_num : int
   !         Number of dimensions, i.e. number of components of
   !         position and velocity vectors.
   !
   !     p_num : int
   !         Number of particles.
   !
   !     dt : float
   !         Time step size.
   !
   !     step_num : int
   !         Number of time steps to be taken.
   !
   !     Returns
   !     -------
   !     potential : float
   !         Total potential energy of the system.
   !
   !     kinetic : float
   !         Total kinetic energy of the system.
   !
   !
   integer, intent(in) :: d_num, p_num, step_num
   real(kind=dp), intent(in) :: dt
   real(kind=dp), intent(out) :: potential, kinetic
   real(kind=dp), parameter :: mass = 1.0_dp
   integer :: i_
   real(kind=dp), allocatable :: acc(:,:), force(:,:), pos(:,:), vel(:,:)
   
   allocate(pos(d_num,p_num), source=0.0_dp)
   allocate(vel(d_num,p_num), source=0.0_dp)
   allocate(acc(d_num,p_num), source=0.0_dp)
   allocate(force(d_num,p_num), source=0.0_dp)
   call initialize(pos)
   potential = compute(mass, pos, vel, force)
   do i_ = 0, step_num - 1
      call update(dt, mass, force, pos, vel, acc)
      potential = compute(mass, pos, vel, force)
   end do
   kinetic = compute_kinetic_energy(vel, mass)
end subroutine md

pure function compute_kinetic_energy(vel, mass) result(func_res)
   !  Compute the kinetic energy associated with the current configuration.
   !
   real(kind=dp), intent(in) :: vel(:,:)
   real(kind=dp), intent(in) :: mass
   real(kind=dp) :: func_res
   real(kind=dp) :: kinetic
   integer :: d_num, j, k, p_num
   
   d_num = size(vel,1)
   p_num = size(vel,2)
   kinetic = 0.0_dp
   do k = 0, d_num - 1
      do j = 0, p_num - 1
         kinetic = kinetic + (vel(k + 1, j + 1) ** 2)
      end do
   end do
   func_res = (0.5_dp * mass) * kinetic
end function compute_kinetic_energy

function compute(mass, pos, vel, force) result(potential)
   !
   !     Calculate the potential energy and forces associated with the
   !     current configuration.
   !
   !
   real(kind=dp), intent(in) :: mass
   real(kind=dp), intent(in) :: pos(:,:), vel(:,:)
   real(kind=dp), intent(inout) :: force(:,:)
   real(kind=dp) :: potential
   real(kind=dp) :: d, d2
   integer :: d_num, i, j, k, p_num
   real(kind=dp), allocatable :: rij(:)
   
   d_num = size(pos,1)
   p_num = size(pos,2)
   allocate(rij(d_num), source=0.0_dp)
   potential = 0.0_dp
   force = 0.0_dp
   do i = 0, p_num - 1
      do j = 0, p_num - 1
         if (i /= j) then
            do k = 0, d_num - 1
               rij(k + 1) = pos(k + 1, i + 1) - pos(k + 1, j + 1)
            end do
            d = 0.0_dp
            do k = 0, d_num - 1
               d = d + (rij(k + 1) ** 2)
            end do
            d = sqrt(d)
            d2 = min(d, acos(-1.0_dp) / 2.0_dp)
            potential = potential + (0.5_dp * sin(d2)) * sin(d2)
            do k = 0, d_num - 1
               force(k + 1, i + 1) = force(k + 1, i + 1) - ((rij(k + 1) * &
                  & sin(2.0_dp * d2)) / d)
            end do
         end if
      end do
   end do
end function compute

subroutine initialize(pos)
   !  Initialise the positions of the particles
   !
   real(kind=dp), intent(inout) :: pos(:,:)
   integer :: seed
   seed = 123456789
   seed = r8mat_uniform_ab(pos, 0.0_dp, 10.0_dp, seed)
end subroutine initialize

pure subroutine update(dt, mass, force, pos, vel, acc)
   !  Update the position, velocity and acceleration of the particles
   !
   real(kind=dp), intent(in) :: dt, mass
   real(kind=dp), intent(in) :: force(:,:)
   real(kind=dp), intent(inout) :: pos(:,:), vel(:,:), acc(:,:)
   real(kind=dp) :: rmass
   
   rmass = 1.0_dp / mass
   pos = pos + (vel * dt + (((0.5_dp * acc) * dt) * dt))
   vel = vel + ((0.5_dp * dt) * (force * rmass + acc))
   acc = force * rmass
end subroutine update

function r8mat_uniform_ab(r, a, b, seed) result(func_res)
   !  Fill r with random numbers with a uniform distribution
   !
   real(kind=dp), intent(inout) :: r(:,:)
   real(kind=dp), intent(in) :: a, b
   integer, intent(in) :: seed
   integer :: func_res
   integer :: i, j, k, m, n, seed_local
   integer, parameter :: i4_huge = 2147483647
   seed_local = seed
   
   m = size(r,1)
   n = size(r,2)
   if (seed_local <= 0) then
      seed_local = seed_local + i4_huge
   else
      if (seed_local > 0) then
         do j = 0, n - 1
            do i = 0, m - 1
               k = seed_local / 127773
               seed_local = 16807 * (seed_local - k * 127773) - k * 2836
               seed_local = modulo(seed_local, i4_huge)
               if (seed_local <= 0) seed_local = seed_local + i4_huge
               r(i + 1, j + 1) = a + (((b - a) * seed_local) * &
                  & 4.656612875e-10_dp)
            end do
         end do
      end if
   end if
   func_res = seed_local
end function r8mat_uniform_ab

end module run_md_proc_mod

program run_md
   use run_md_proc_mod, only: dp, md
   implicit none
   real(kind=dp) :: kinetic, potential
   
   call md(3, 40, 30, 0.1_dp, potential, kinetic)
   write(*,"(f0.10, 1x, f0.10)") potential, kinetic
end program run_md
