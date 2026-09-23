import numpy as np


def condition(a):
    print("condition evaluated")
    return a != 0.0


def evaluate(a):
    rows, cols = np.where(condition(a))
    result = np.zeros_like(a)
    result[rows, cols] = a[rows, cols] + np.sum(a[rows, cols])
    return result


a = np.array([[0.0, 2.0, 0.0], [3.0, 0.0, 4.0]])
v = evaluate(a)
for r in range(2):
    for c in range(3):
        print(v[r, c])

[xp2f_where_unpack, cols] = np.where(condition(a))
for k in range(len(cols)):
    print(xp2f_where_unpack[k], cols[k])

rows, cols = np.where(np.ones((2, 3)))
all_values = a[rows, cols]
for k in range(len(rows)):
    print(rows[k], cols[k], all_values[k])

r2 = rows
c2 = cols
copied = a[r2, c2] + 1.0
for k in range(len(copied)):
    print(copied[k])

# The RHS sees the original array throughout the scatter.
a[rows, cols] = a[rows, cols] + np.sum(a[rows, cols])
for r in range(2):
    for c in range(3):
        print(a[r, c])
