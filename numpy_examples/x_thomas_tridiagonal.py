"""Numerical methods suite (batch 2): Thomas algorithm.

Hand-coded Thomas algorithm (tridiagonal Gaussian elimination) for a
fixed diagonally-dominant tridiagonal system, compared against
np.linalg.solve on the same system expressed as a dense matrix.
"""
import numpy as np

n = 6
# sub-diagonal (a[1..n-1]), diagonal (b[0..n-1]), super-diagonal (c[0..n-2])
a = np.array([0.0, -1.0, -1.0, -1.0, -1.0, -1.0])
b = np.array([4.0, 4.0, 4.0, 4.0, 4.0, 4.0])
c = np.array([-1.0, -1.0, -1.0, -1.0, -1.0, 0.0])
d = np.array([3.0, 2.0, 2.0, 2.0, 2.0, 3.0])


def thomas_solve(a, b, c, d, n):
    cp = np.zeros(n)
    dp = np.zeros(n)
    x = np.zeros(n)
    cp[0] = c[0] / b[0]
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        m = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / m
        dp[i] = (d[i] - a[i] * dp[i - 1]) / m
    x[n - 1] = dp[n - 1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


x_thomas = thomas_solve(a, b, c, d, n)

A = np.zeros((n, n))
for i in range(n):
    A[i, i] = b[i]
    if i > 0:
        A[i, i - 1] = a[i]
    if i < n - 1:
        A[i, i + 1] = c[i]
x_direct = np.linalg.solve(A, d)

err = x_thomas - x_direct
err_norm = np.sqrt((err * err).sum())

print("thomas x =", x_thomas[0], x_thomas[1], x_thomas[2], x_thomas[3], x_thomas[4], x_thomas[5])
print("error vs direct solve =", err_norm)
