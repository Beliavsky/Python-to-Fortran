"""Discarding np.sort/np.flip must not mutate their input."""
import numpy as np

a = np.array([3.0, 1.0, 2.0])
a[0] = 3.0
np.sort(a)
print(a[0], a[1], a[2])
np.flip(a)
print(a[0], a[1], a[2])
