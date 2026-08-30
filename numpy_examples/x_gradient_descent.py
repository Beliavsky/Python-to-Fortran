"""Numerical methods suite (batch 2): gradient descent.

Hand-coded gradient descent minimizing a fixed convex quadratic
bowl f(x, y) = (x - 3)^2 + 5*(y + 2)^2, whose exact minimum is
known to be at (3, -2) with f = 0, starting from (0, 0).
"""
import numpy as np


def f(v):
    x, y = v[0], v[1]
    return (x - 3.0) ** 2 + 5.0 * (y + 2.0) ** 2


def grad(v):
    x, y = v[0], v[1]
    return np.array([2.0 * (x - 3.0), 10.0 * (y + 2.0)])


v = np.array([0.0, 0.0])
lr = 0.08
n_iter = 200

for k in range(n_iter):
    g = grad(v)
    v = v - lr * g

print("minimizer =", v[0], v[1])
print("f(minimizer) =", f(v))
print("exact minimizer =", 3.0, -2.0)
