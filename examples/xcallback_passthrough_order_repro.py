import numpy as np


def objective(x, n):
    return np.sum(x[0:n] ** 2)


def evaluate(f, x, n):
    value = f(x, n)
    return value


def driver(f, x, n):
    return evaluate(f, x, n)


n = 3
x = np.array([1.0, 2.0, 3.0])
print(driver(objective, x, n))
