import numpy as np
from scipy.optimize import fsolve


def equations(x):
    y = np.zeros(2)
    y[0] = x[0] ** 2 + x[1] ** 2 - 4.0
    y[1] = x[0] - x[1]
    return y


x0 = [1.0, 1.0]
sol = fsolve(equations, x0)
print(sol[0])
print(sol[1])
