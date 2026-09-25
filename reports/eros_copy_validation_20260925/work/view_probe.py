"""NumPy's temporary is a live view, not a saved copy of the row."""
import numpy as np

a = np.array([[1.0, 2.0], [3.0, 4.0]])
t = a[0, :]
a[0, :] = a[1, :]
a[1, :] = t
for i in range(2):
    for j in range(2):
        print(a[i, j])
