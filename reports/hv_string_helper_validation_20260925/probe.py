"""Minimal regression: output normalization removes a string helper's caller."""
import numpy as np


def format_float(x: float):
    headers = ["asset", "horizon"]
    for key in headers:
        width = len(key)
    if np.isnan(x):
        return "nan"
    return str(x)


print(format_float(0.25))
