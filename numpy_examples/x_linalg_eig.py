"""Numerical methods suite: general eigenvalue decomposition.

np.linalg.eig on a fixed, non-symmetric 3x3 matrix with known real
eigenvalues; verified by checking A v - lambda v ~ 0 for each pair,
after sorting eigenvalues for a deterministic print order.
"""
import numpy as np

A = np.array(
    [
        [4.0, 1.0, 0.0],
        [2.0, 3.0, 0.0],
        [0.0, 0.0, 5.0],
    ]
)

w, v = np.linalg.eig(A)

order = np.argsort(w)
w = w[order]
v = v[:, order]

print("eigenvalues =", w[0], w[1], w[2])

resid_norms = np.zeros(3)
for i in range(3):
    r = A.dot(v[:, i]) - w[i] * v[:, i]
    resid_norms[i] = np.sqrt((r * r).sum())

print("residual norms =", resid_norms[0], resid_norms[1], resid_norms[2])
