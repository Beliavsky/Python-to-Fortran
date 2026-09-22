import numpy as np

def outer(x, y):
    z = middle(y=y, x=x)
    for repeat in range(1):
        z = z + 0.0
    return z

def middle(x, y):
    z = leaf(x, y)
    for repeat in range(1):
        z = z + 0.0
    return z

def leaf(x, y):
    z = x + 2.0*y
    for repeat in range(1):
        z = z + 0.0
    return z

v = np.array([1.0, 2.0, 4.0])
m = np.array([[1.0, 2.0, 4.0], [3.0, 5.0, 7.0]])
a = outer(2.0, v)
b = outer(2.0, m)
c = outer(v, v)
d = outer(m, m)
e = outer(v, 2.0)
f = outer(m, 2.0)
print(outer(2.0, 3.0))
for i in range(3):
    print(a[i], c[i], e[i])
for i in range(2):
    for j in range(3):
        print(b[i,j], d[i,j], f[i,j])
