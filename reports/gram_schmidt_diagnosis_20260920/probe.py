"""Burkardt cgs2 algorithm with residual diagnostics and fixed audit input.

Original algorithm: John Burkardt, MIT licensed, gram_schmidt/gram_schmidt.py.
Only diagnostic prints and deterministic driver input have been added.
"""
import numpy as np


def cgs2(A):
    m, n = A.shape
    U = np.zeros([m, n])
    for j in range(0, n):
        v = A[:, j]
        for j2 in range(0, j):
            v2 = U[:, j2]
            p = np.dot(v, v2) / np.linalg.norm(v2)
            v = v - p * v2
        vnorm = np.linalg.norm(v)
        print('norm', j, vnorm)
        for i in range(m):
            print('raw', i, j, v[i])
        if 0.0 < vnorm:
            v = v / vnorm
        U[:, j] = v
    return U


A = np.array([[-9., 8., 8., 2.], [6., 7., 7., -1.], [9., 9., 1., -8.]])
U = cgs2(A)
for i in range(3):
    for j in range(4):
        print('u', i, j, U[i, j])
