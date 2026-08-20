from scipy.optimize import brentq


def f(x):
    return x ** 2 - 2.0


root = brentq(f, 0.0, 2.0)
print(root)
