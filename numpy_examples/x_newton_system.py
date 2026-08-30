"""Numerical methods suite (batch 2): multivariate Newton's method.

Hand-coded Newton's method for a 2x2 nonlinear system:
  f1(x, y) = x^2 + y^2 - 4      = 0
  f2(x, y) = x*y - 1            = 0
using an analytic Jacobian and np.linalg.solve for the linear step
each iteration, starting from (x0, y0) = (1.5, 1.0).
"""
import numpy as np


def residual(v):
    x, y = v[0], v[1]
    return np.array([x**2 + y**2 - 4.0, x * y - 1.0])


def jacobian(v):
    x, y = v[0], v[1]
    return np.array([[2.0 * x, 2.0 * y], [y, x]])


v = np.array([1.5, 1.0])
n_iter = 10
for k in range(n_iter):
    F = residual(v)
    J = jacobian(v)
    delta = np.linalg.solve(J, -F)
    v = v + delta
    print(k, v[0], v[1], np.sqrt((F * F).sum()))

print("solution =", v[0], v[1])
print("residual norm =", np.sqrt((residual(v) ** 2).sum()))
