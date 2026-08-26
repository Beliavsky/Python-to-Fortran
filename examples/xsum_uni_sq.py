import numpy as np
n = 2*10**6
fsum = 0.0
for i in range(n):
    fsum = fsum + np.random.uniform()**2
print(fsum/n)
