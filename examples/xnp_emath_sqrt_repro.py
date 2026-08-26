import numpy as np

x = -4.0
z = 1.0
lam = np.zeros(1, dtype=complex)
lam[0] = np.emath.sqrt(x * z)
print(lam[0])
