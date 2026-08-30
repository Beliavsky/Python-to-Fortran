"""Numerical methods suite: explicit Euler ODE integration.

Integrates dy/dt = -k*y (exponential decay, k=0.5) from y(0)=1 with
explicit Euler steps, and compares the final value against the exact
closed-form solution y(t) = exp(-k*t).
"""
import numpy as np

k = 0.5
t0 = 0.0
t_end = 2.0
n_steps = 2000
dt = (t_end - t0) / n_steps

y = 1.0
t = t0
for i in range(n_steps):
    y = y + dt * (-k * y)
    t = t + dt

y_exact = np.exp(-k * t_end)
err = abs(y - y_exact)

print("euler y(2) =", y)
print("exact y(2) =", y_exact)
print("abs error =", err)
