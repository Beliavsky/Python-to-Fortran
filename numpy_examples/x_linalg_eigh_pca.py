"""Numerical methods suite: symmetric eigendecomposition + PCA.

Builds a fixed covariance matrix from a small deterministic dataset,
runs np.linalg.eigh on it, and reports the leading principal
component's explained-variance fraction -- a standard PCA-by-hand
pipeline exercising symmetric eigendecomposition end to end.
"""
import numpy as np

X = np.array(
    [
        [2.5, 2.4],
        [0.5, 0.7],
        [2.2, 2.9],
        [1.9, 2.2],
        [3.1, 3.0],
        [2.3, 2.7],
        [2.0, 1.6],
        [1.0, 1.1],
        [1.5, 1.6],
        [1.1, 0.9],
    ]
)

mean = X.mean(axis=0)
Xc = X - mean
cov = (Xc.T.dot(Xc)) / (X.shape[0] - 1)

w, v = np.linalg.eigh(cov)

order = np.argsort(w)[::-1]
w = w[order]
v = v[:, order]

total_var = w.sum()
explained = w[0] / total_var

print("eigenvalues =", w[0], w[1])
print("explained variance ratio (PC1) =", explained)
print("PC1 direction =", v[0, 0], v[1, 0])
