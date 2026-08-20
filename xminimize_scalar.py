import numpy as np
from scipy.optimize import minimize_scalar


def f(x):
    return np.sin(x) + 0.1 * x ** 2 - 0.5 * np.cos(3.0 * x)


res = minimize_scalar(f, bounds=(0.0, 5.0))
print(res.x)
print(res.fun)
