"""Numerical methods suite: numerical integration (quadrature).

Three classical quadrature rules -- trapezoidal, Simpson's, and
Gauss-Legendre (via np.polynomial.legendre.leggauss) -- all
estimating the same integral, integral of sin(x) dx from 0 to pi,
whose exact value is 2.0.
"""
import numpy as np

a = 0.0
b = np.pi
n = 1000  # subintervals for trapezoid/simpson (n must be even for simpson)


def f(x):
    return np.sin(x)


# Trapezoidal rule
h = (b - a) / n
xs = np.linspace(a, b, n + 1)
ys = f(xs)
trap = h * (0.5 * ys[0] + 0.5 * ys[n] + ys[1:n].sum())

# Simpson's rule
odd_sum = 0.0
even_sum = 0.0
for i in range(1, n):
    if i % 2 == 1:
        odd_sum = odd_sum + ys[i]
    else:
        even_sum = even_sum + ys[i]
simpson = (h / 3.0) * (ys[0] + ys[n] + 4.0 * odd_sum + 2.0 * even_sum)

# Gauss-Legendre quadrature, 5-point, mapped from [-1,1] to [a,b]
nodes, weights = np.polynomial.legendre.leggauss(5)
xm = 0.5 * (b - a) * nodes + 0.5 * (b + a)
gl = 0.5 * (b - a) * (weights * f(xm)).sum()

exact = 2.0

print("trapezoid =", trap, "error =", abs(trap - exact))
print("simpson   =", simpson, "error =", abs(simpson - exact))
print("gauss-leg =", gl, "error =", abs(gl - exact))
