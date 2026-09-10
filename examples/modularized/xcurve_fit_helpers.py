import numpy as np


def model(x, a, b, c):
    return a * np.exp(-b * x) + c
