"""Numerical methods suite: bisection method root finding.

Hand-coded bisection for f(x) = x^3 - 2x - 5 on the bracket [2, 3]
(same root as x_root_newton.py, near x = 2.0946), run for a fixed
number of iterations.
"""
import numpy as np


def f(x):
    return x**3 - 2.0 * x - 5.0


lo = 2.0
hi = 3.0
n_iter = 30

for k in range(n_iter):
    mid = 0.5 * (lo + hi)
    fmid = f(mid)
    if f(lo) * fmid <= 0.0:
        hi = mid
    else:
        lo = mid

root = 0.5 * (lo + hi)
print("root =", root)
print("f(root) =", f(root))
