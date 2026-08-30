"""Numerical methods suite: QR factorization.

np.linalg.qr on a fixed 4x3 matrix; verified by checking Q @ R
reconstructs A and that Q has orthonormal columns (Q.T @ Q ~ I).
"""
import numpy as np

A = np.array(
    [
        [1.0, -1.0, 4.0],
        [1.0, 4.0, -2.0],
        [1.0, 4.0, 2.0],
        [1.0, -1.0, 0.0],
    ]
)

Q, R = np.linalg.qr(A)

recon = Q.dot(R)
err = recon - A
err_norm = np.sqrt((err * err).sum())

QtQ = Q.T.dot(Q)
orth_err = 0.0
for i in range(3):
    for j in range(3):
        target = 1.0 if i == j else 0.0
        orth_err = orth_err + abs(QtQ[i, j] - target)

print("reconstruction error norm =", err_norm)
print("orthonormality error =", orth_err)
