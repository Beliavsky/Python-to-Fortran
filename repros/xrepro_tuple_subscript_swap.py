import numpy as np

klass = np.array([10, 20, 30])
npos = 0
imin = 2
klass[npos], klass[imin] = klass[imin], klass[npos]
print(klass)

