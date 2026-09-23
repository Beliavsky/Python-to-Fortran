import numpy as np

def integrand(x, y):
    fx = np.zeros_like(x)
    i = np.where(np.sqrt(3.0 - x - 2.0*y != 0.0))
    fx[i] = 1.0 / np.sqrt(3.0 - x[i] - 2.0*y[i])
    return fx

a = np.array([[0.0, 2.0, 0.0], [3.0, 0.0, 4.0]])
i = np.where(a)
rows = i[0]
cols = i[1]
values = a[i]
for k in range(len(rows)):
    print('index', rows[k], cols[k], values[k])
a[i] = a[i] + 10.0
for r in range(2):
    for c in range(3):
        print('cell', r, c, a[r,c])
x = np.array([[0.0, 0.25, 1.0], [0.5, 1.0, 0.0]])
y = np.array([[0.0, 0.5, 1.0], [0.25, 1.0, 0.5]])
z = integrand(x, y)
for r in range(2):
    for c in range(3):
        print('value', r, c, z[r,c])
