"""Numerical methods suite (batch 2): convolution and correlation.

np.convolve (full and valid modes) and np.correlate on fixed,
small integer/float sequences with hand-checkable results.
"""
import numpy as np

a = np.array([1.0, 2.0, 3.0, 4.0])
k = np.array([0.5, 1.0, 0.5])

full = np.convolve(a, k)
valid = np.convolve(a, k, mode="valid")

print("full length =", full.shape[0])
print("full =", full[0], full[1], full[2], full[3], full[4], full[5])
print("valid length =", valid.shape[0])
print("valid =", valid[0], valid[1])

corr = np.correlate(a, k)
print("correlate length =", corr.shape[0])
print("correlate =", corr[0])
