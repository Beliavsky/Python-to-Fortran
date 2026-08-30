"""Numerical methods suite: Newton's method root finding.

Hand-coded Newton-Raphson iteration for f(x) = x^3 - 2x - 5 (a
classic textbook example with a known real root near x = 2.0946),
starting from x0 = 2.0 and iterating a fixed number of steps.
"""
import numpy as np


def f(x):
    return x**3 - 2.0 * x - 5.0


def fprime(x):
    return 3.0 * x**2 - 2.0


x = 2.0
n_iter = 8
for k in range(n_iter):
    fx = f(x)
    x = x - fx / fprime(x)
    print(k, x, f(x))

print("root =", x)
print("f(root) =", f(x))
