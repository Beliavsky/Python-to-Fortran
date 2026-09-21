"""Separate follow-up: explicitly integer arrays built from real literals."""
import numpy as np


def show(x):
    print(x[0, 0])


show(np.array([[1.5]], dtype=np.int64))
