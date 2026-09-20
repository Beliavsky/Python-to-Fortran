"""Reduced Burkardt lcrg_evaluate call pattern; original formula and hints."""
import numpy as np


def lcrg_evaluate(a, b, c, x):
    # integer A, the multiplier.
    # integer B, the added value.
    # integer C, the modulus.
    # integer X, the value to be processed.
    # integer Y, the processed value.
    y = ((a * x + b) % c)
    if y < 0:
        y = y + c
    return y


a = 16807
b = 0
c = 2147483647
an = 984943658
u = 12345
for k in range(1, 12):
    u = lcrg_evaluate(a, b, c, u)
    print('scalar', k, u)
x = np.zeros(4)
x[0] = 12345
for j in range(1, 4):
    x[j] = lcrg_evaluate(a, b, c, x[j-1])
for k in range(4, 12, 4):
    for j in range(4):
        y = lcrg_evaluate(an, b, c, x[j])
        print('array', j, k+j, x[j], y)
        x[j] = y
