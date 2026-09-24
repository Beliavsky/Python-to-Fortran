"""Separate unresolved tuple-expression kind inference case found during testing."""
import numpy as np


def step(u, q):
    return u, u + 0.25, q - 1


def update(u, q, untouched):
    total = 0.0
    for i in range(len(u)):
        value, u[i], q[i] = step(u[i], q[i])
        total += value + untouched[i]
    return total


u = np.array([1.5, -2.5])
q = np.array([4, 7], dtype=int)
untouched = np.array([10.0, 20.0])
for repeat in range(2):
    print(update(u, q, untouched))
    for i in range(len(u)):
        print(u[i], q[i], untouched[i])
