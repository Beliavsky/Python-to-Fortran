"""Numerical methods suite: conjugate gradient solver.

Hand-coded conjugate gradient for a fixed symmetric positive-definite
4x4 system A x = b, compared against np.linalg.solve. CG on a
well-conditioned n=4 SPD system should converge to machine precision
in at most n iterations.
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
r = b - A.dot(x)
p = r.copy()
rs_old = r.dot(r)

for k in range(n):
    Ap = A.dot(p)
    alpha = rs_old / p.dot(Ap)
    x = x + alpha * p
    r = r - alpha * Ap
    rs_new = r.dot(r)
    if np.sqrt(rs_new) < 1.0e-12:
        break
    p = r + (rs_new / rs_old) * p
    rs_old = rs_new

x_direct = np.linalg.solve(A, b)
err = x - x_direct
err_norm = np.sqrt((err * err).sum())

print("cg x =", x[0], x[1], x[2], x[3])
print("error vs direct solve =", err_norm)
