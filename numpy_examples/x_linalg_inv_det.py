"""Numerical methods suite: matrix inverse and determinant.

np.linalg.inv and np.linalg.det on a fixed 3x3 matrix, verified by
checking A @ inv(A) is close to the identity.
"""
import numpy as np

A = np.array(
    [
        [4.0, 3.0, 2.0],
        [1.0, 5.0, 3.0],
        [2.0, 1.0, 6.0],
    ]
)

Ainv = np.linalg.inv(A)
d = np.linalg.det(A)

I = A.dot(Ainv)
off_diag_err = abs(I[0, 1]) + abs(I[0, 2]) + abs(I[1, 0]) + abs(I[1, 2]) + abs(I[2, 0]) + abs(I[2, 1])
diag_err = abs(I[0, 0] - 1.0) + abs(I[1, 1] - 1.0) + abs(I[2, 2] - 1.0)

print("det =", d)
print("A @ inv(A) off-diagonal error =", off_diag_err)
print("A @ inv(A) diagonal error =", diag_err)
