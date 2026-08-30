"""Numerical methods suite: classical RK4 ODE integration.

Integrates a 2D simple-harmonic-oscillator system
  dx/dt = v
  dv/dt = -omega^2 * x
from (x0, v0) = (1, 0) using classical 4th-order Runge-Kutta, and
compares the final state against the exact closed-form solution
x(t) = cos(omega t), v(t) = -omega sin(omega t).
"""
import numpy as np

omega = 2.0
t0 = 0.0
t_end = 3.0
n_steps = 600
dt = (t_end - t0) / n_steps


def deriv(state):
    x, v = state[0], state[1]
    return np.array([v, -omega**2 * x])


state = np.array([1.0, 0.0])
t = t0
for i in range(n_steps):
    k1 = deriv(state)
    k2 = deriv(state + 0.5 * dt * k1)
    k3 = deriv(state + 0.5 * dt * k2)
    k4 = deriv(state + dt * k3)
    state = state + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    t = t + dt

x_exact = np.cos(omega * t_end)
v_exact = -omega * np.sin(omega * t_end)

print("rk4 x, v =", state[0], state[1])
print("exact x, v =", x_exact, v_exact)
print("abs error x, v =", abs(state[0] - x_exact), abs(state[1] - v_exact))
