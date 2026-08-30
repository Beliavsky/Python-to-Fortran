"""Numerical methods suite (batch 2): bilinear interpolation.

Hand-coded bilinear interpolation on a fixed 2D grid sampled from a
known smooth function f(x, y) = x^2 + 2*x*y (exactly reproducible by
bilinear interpolation only at grid points; off-grid points are
compared against the true function value to bound the error).
"""
import numpy as np


def true_f(x, y):
    return x**2 + 2.0 * x * y


nx = 5
ny = 5
xs = np.linspace(0.0, 4.0, nx)
ys = np.linspace(0.0, 4.0, ny)

grid = np.zeros((nx, ny))
for i in range(nx):
    for j in range(ny):
        grid[i, j] = true_f(xs[i], ys[j])


def bilinear(xs, ys, grid, x, y):
    nx = xs.shape[0]
    ny = ys.shape[0]
    i = 0
    while i < nx - 2 and xs[i + 1] < x:
        i = i + 1
    j = 0
    while j < ny - 2 and ys[j + 1] < y:
        j = j + 1
    x0, x1 = xs[i], xs[i + 1]
    y0, y1 = ys[j], ys[j + 1]
    tx = (x - x0) / (x1 - x0)
    ty = (y - y0) / (y1 - y0)
    f00 = grid[i, j]
    f10 = grid[i + 1, j]
    f01 = grid[i, j + 1]
    f11 = grid[i + 1, j + 1]
    return (
        f00 * (1.0 - tx) * (1.0 - ty)
        + f10 * tx * (1.0 - ty)
        + f01 * (1.0 - tx) * ty
        + f11 * tx * ty
    )


# On-grid point: exact.
v1 = bilinear(xs, ys, grid, 2.0, 2.0)
print("on-grid value =", v1, "exact =", true_f(2.0, 2.0))

# Off-grid point: bilinear approximation (small error since f has a
# cross term x*y that bilinear interpolation cannot represent exactly).
v2 = bilinear(xs, ys, grid, 1.3, 2.7)
print("off-grid value =", v2, "exact =", true_f(1.3, 2.7))
