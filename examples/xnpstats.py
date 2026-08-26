import numpy as np
n = 1000
x = np.random.normal(size=n)
y = x + np.random.normal(size=n)
print(np.corrcoef(x, y))
print(np.cov(x,y))
