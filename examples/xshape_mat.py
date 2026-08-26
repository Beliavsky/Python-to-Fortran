import numpy as np
x = np.random.uniform(size=[3, 4])
print(x.shape)
print(x)
x.shape = (2, 6)
print(x.shape)
print(x)
