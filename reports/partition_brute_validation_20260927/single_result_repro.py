"""Remaining single-result specialization limitation; Python prints 1 2 1 1."""
import numpy as np


def flip_first(a):
    # Input:
    # bool A(N), flags.
    a[0] = not a[0]
    return a


a = np.array([0, 2], dtype=int)
b = np.array([False, True], dtype=bool)
a = flip_first(a)
b = flip_first(b)
print(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
