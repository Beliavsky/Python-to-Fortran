import numpy as np

def combine(x, y):
    z = x + 2.0*y
    for repeat in range(1):
        z = z + 0.0
    return z

def reduced(x, y):
    return np.sum(x + y)

v = np.array([1.0, 2.0, 4.0])
m = np.array([[1.0, 2.0, 4.0], [3.0, 5.0, 7.0]])
a = combine(2.0, v)
b = combine(2.0, m)
c = combine(v, v)
d = combine(m, m)
e = combine(v, 2.0)
f = combine(m, 2.0)
print(combine(2.0, 3.0))
for i in range(3):
    print(a[i], c[i], e[i])
for i in range(2):
    for j in range(3):
        print(b[i,j], d[i,j], f[i,j])
print(reduced(2.0, v), reduced(2.0, m), reduced(v, v), reduced(m, m), reduced(2.0, 3.0))
