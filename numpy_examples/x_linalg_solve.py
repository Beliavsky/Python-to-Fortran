"""Numerical methods suite: direct linear solve.

Solves a fixed, well-conditioned 4x4 linear system A x = b via
np.linalg.solve and checks the residual norm ||A x - b|| is ~0.
"""
import numpy as np

A = np.array(
    [
        [10.0, 2.0, 0.0, 1.0],
        [1.0, 8.0, 1.0, 0.0],
        [0.0, 1.0, 6.0, 2.0],
        [2.0, 0.0, 1.0, 9.0],
    ]
)
b = np.array([13.0, 10.0, 9.0, 12.0])

x = np.linalg.solve(A, b)
resid = A.dot(x) - b
resid_norm = np.sqrt((resid * resid).sum())

print("x =", x[0], x[1], x[2], x[3])
print("residual norm =", resid_norm)
