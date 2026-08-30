"""Numerical methods suite (batch 2): power iteration.

Hand-coded power iteration with Rayleigh-quotient eigenvalue estimate
for a fixed symmetric 3x3 matrix's dominant eigenpair, compared
against np.linalg.eigh's own top eigenvalue.
"""
import numpy as np

A = np.array(
    [
        [4.0, 1.0, 1.0],
        [1.0, 3.0, 0.5],
        [1.0, 0.5, 2.0],
    ]
)

v = np.array([1.0, 0.0, 0.0])
n_iter = 50
lam = 0.0

for k in range(n_iter):
    w = A.dot(v)
    w_norm = np.sqrt((w * w).sum())
    v = w / w_norm
    lam = v.dot(A.dot(v))

w_eigh, _ = np.linalg.eigh(A)
lam_exact = w_eigh[2]  # eigh returns ascending order; dominant is last

print("power iteration eigenvalue =", lam)
print("eigh dominant eigenvalue =", lam_exact)
print("abs error =", abs(lam - lam_exact))
