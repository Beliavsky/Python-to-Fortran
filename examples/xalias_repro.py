import numpy as np

def make_arr(n):
    return np.array([float(i) for i in range(n)])

a = make_arr(5)
b = a
print(np.sum(b))
