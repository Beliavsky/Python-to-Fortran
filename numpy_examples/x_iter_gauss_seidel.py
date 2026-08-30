"""Numerical methods suite: Gauss-Seidel iterative linear solver.

Hand-coded Gauss-Seidel iteration (in-place updates, unlike Jacobi's
full-sweep-then-swap) for the same fixed, diagonally-dominant 4x4
system, compared against np.linalg.solve.
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
n_iter = 25

for k in range(n_iter):
    for i in range(n):
        s = 0.0
        for j in range(n):
            if j != i:
                s = s + A[i, j] * x[j]
        x[i] = (b[i] - s) / A[i, i]

x_direct = np.linalg.solve(A, b)
err = x - x_direct
err_norm = np.sqrt((err * err).sum())

print("gauss-seidel x =", x[0], x[1], x[2], x[3])
print("error vs direct solve =", err_norm)
