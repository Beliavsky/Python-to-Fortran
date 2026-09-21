import numpy as np


def solve_copy(scale, d):
    x = d.copy()
    for i in range(len(d)):
        x[i] = x[i] / scale
    return x


def exercise():
    rhs = np.ones((3, 2))
    d1 = rhs[:, 0].copy()
    d2 = rhs.copy()
    x1 = solve_copy(2.0, d1)
    x2 = solve_copy(2.0, d2)
    print(x1.ndim, x2.ndim)
    print(x1.shape[0], x2.shape[0], x2.shape[1])
    print((x1 + np.arange(3)).sum())


exercise()
