"""Numerical methods suite: Jacobi iterative linear solver.

Hand-coded Jacobi iteration for a fixed, diagonally-dominant 4x4
system A x = b, run for a fixed number of iterations and compared
against np.linalg.solve's direct solution.
"""
import numpy as np

A = np.array(
    [
        [10.0, 1.0, 1.0, 0.0],
        [1.0, 12.0, 0.0, 2.0],
        [1.0, 0.0, 8.0, 1.0],
        [0.0, 2.0, 1.0, 9.0],
    ]
)
b = np.array([15.0, 20.0, 10.0, 18.0])

n = 4
x = np.zeros(n)
n_iter = 40

for k in range(n_iter):
    x_new = np.zeros(n)
    for i in range(n):
        s = 0.0
        for j in range(n):
            if j != i:
                s = s + A[i, j] * x[j]
        x_new[i] = (b[i] - s) / A[i, i]
    x = x_new

x_direct = np.linalg.solve(A, b)
err = x - x_direct
err_norm = np.sqrt((err * err).sum())

print("jacobi x =", x[0], x[1], x[2], x[3])
print("error vs direct solve =", err_norm)
