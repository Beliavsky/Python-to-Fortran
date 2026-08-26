import numpy as np

r = np.array([1.0, 2.0, 3.0])

def f(x):
    return x + np.sum(r)

print(f(10.0))
