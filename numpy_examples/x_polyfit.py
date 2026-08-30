"""Numerical methods suite (batch 2): polynomial fitting.

np.polyfit on fixed, noisy-but-deterministic data generated from a
known quadratic, np.poly1d to evaluate the fitted polynomial, and
np.roots on a fixed cubic with known integer roots.
"""
import numpy as np

x = np.array([-2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0])
# y = 2*x^2 - 3*x + 1, plus a small fixed perturbation (no RNG)
noise = np.array([0.05, -0.03, 0.02, -0.04, 0.01, -0.02, 0.03])
y = 2.0 * x**2 - 3.0 * x + 1.0 + noise

coeffs = np.polyfit(x, y, 2)
p = np.poly1d(coeffs)

print("fitted coeffs =", coeffs[0], coeffs[1], coeffs[2])
print("p(0) =", p(0.0))
print("p(2) =", p(2.0))

# (x - 1)(x - 2)(x - 3) = x^3 - 6x^2 + 11x - 6
cubic_coeffs = np.array([1.0, -6.0, 11.0, -6.0])
r = np.roots(cubic_coeffs)
r_sorted = np.sort(r)
print("roots =", r_sorted[0], r_sorted[1], r_sorted[2])
