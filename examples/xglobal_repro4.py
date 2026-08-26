import numpy as np

def make_arr(n):
    return np.array([float(i) for i in range(n)])

a = make_arr(5)
b = np.asarray(a)

def f(x):
    return x + np.sum(b)

print(f(10.0))
