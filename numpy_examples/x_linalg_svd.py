"""Numerical methods suite: singular value decomposition.

np.linalg.svd on a fixed 4x3 matrix, reconstructed as U @ diag(s) @ Vt
and checked against the original for a small reconstruction error.
"""
import numpy as np

A = np.array(
    [
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        [7.0, 8.0, 10.0],
        [1.0, 0.0, 1.0],
    ]
)

U, s, Vt = np.linalg.svd(A, full_matrices=False)

S = np.diag(s)
recon = U.dot(S).dot(Vt)
err = recon - A
err_norm = np.sqrt((err * err).sum())

print("singular values =", s[0], s[1], s[2])
print("reconstruction error norm =", err_norm)
