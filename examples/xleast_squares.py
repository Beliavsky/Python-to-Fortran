import numpy as np
from scipy.optimize import least_squares


def resid(p):
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([1.1, 2.9, 5.2, 6.8, 9.3])
    return p[0] * x + p[1] - y


x0 = [1.0, 1.0]
result = least_squares(resid, x0, method="lm")
print(result.x[0])
print(result.x[1])
print(result.cost)
