"""Regression for rebound array result dtype; Python prints 2.5 3.75.

The translation previously printed 2 3. Rebinding the parameter means this
is not an unchanged-array result; inference must track its type at return.
"""
import numpy as np


def changed(a):
    a[0] = 1
    a = np.array([2.5, 3.75])
    return a


a = np.array([0, 2], dtype=int)
b = changed(a)
print(b[0], b[1])
