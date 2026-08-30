"""Numerical methods suite: Cholesky factorization.

np.linalg.cholesky on a fixed symmetric positive-definite 3x3 matrix;
verified by checking L @ L.T reconstructs A.
"""
import numpy as np

A = np.array(
    [
        [6.0, 3.0, 4.0],
        [3.0, 6.0, 5.0],
        [4.0, 5.0, 10.0],
    ]
)

L = np.linalg.cholesky(A)
recon = L.dot(L.T)
err = recon - A
err_norm = np.sqrt((err * err).sum())

print("L[0,0], L[1,0], L[1,1] =", L[0, 0], L[1, 0], L[1, 1])
print("L[2,0], L[2,1], L[2,2] =", L[2, 0], L[2, 1], L[2, 2])
print("reconstruction error norm =", err_norm)
