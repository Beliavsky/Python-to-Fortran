"""
Simulate a VAR(2) process and recover its parameters by multivariate OLS
using the normal equations.
"""

import numpy as np

rng = np.random.default_rng(123)

# ------------------------------------------------------------
# Simulate a VAR(2):
#
# y_t = c + A1 y_{t-1} + A2 y_{t-2} + e_t
#
# where y_t is a vector of length k.
# ------------------------------------------------------------

n = 5000
burn = 500
k = 3
p = 2

c_true = np.array([0.10, -0.20, 0.05])

A1_true = np.array([
    [ 0.50,  0.10,  0.00],
    [-0.10,  0.40,  0.10],
    [ 0.05, -0.10,  0.30]
])

A2_true = np.array([
    [-0.20,  0.05,  0.00],
    [ 0.00, -0.15,  0.05],
    [ 0.02,  0.00, -0.10]
])

Sigma_true = np.array([
    [1.00, 0.30, 0.10],
    [0.30, 0.80, 0.20],
    [0.10, 0.20, 0.60]
])


def simulate_var2(n, burn, c, A1, A2, Sigma):
    k = len(c)
    ntot = n + burn

    y = np.zeros((ntot + 2, k))

    # Cholesky factor for correlated innovations
    L = np.linalg.cholesky(Sigma)

    for t in range(2, ntot + 2):
        e = L @ rng.standard_normal(k)

        y[t] = (
            c
            + A1 @ y[t - 1]
            + A2 @ y[t - 2]
            + e
        )

    return y[burn + 2:, :]


def fit_var2(y):
    n, k = y.shape

    # Regressors:
    # [1, y_{t-1}', y_{t-2}']
    X = np.ones((n - 2, 1 + 2 * k))

    X[:, 1:1 + k] = y[1:-1, :]
    X[:, 1 + k:] = y[:-2, :]

    # Responses y_t (y[2:, :], not the bare y[2:] shorthand: a fresh
    # variable's rank is inferred from its own RHS shape, and a
    # single-slice row-shorthand on a 2D array wasn't picked up as 2D)
    Y = y[2:, :]

    # Multivariate OLS via the normal equations (np.linalg.lstsq(X, Y)[0]
    # reduces to exactly this anyway): B = (X'X)^-1 X'Y = argmin ||Y-XB||^2.
    # Solved directly rather than through lstsq's tuple-unpack lowering,
    # whose result rank isn't picked up correctly for a matrix (multi-
    # column) right-hand side like Y here.
    B = np.linalg.solve(X.T @ X, X.T @ Y)

    c_fit = B[0]

    # B stores coefficient vectors by regressor, so transpose
    # to recover the conventional VAR coefficient matrices.
    A1_fit = B[1:1 + k].T
    A2_fit = B[1 + k:].T

    resid = Y - X @ B

    # ML-style covariance estimate
    Sigma_fit = resid.T @ resid / resid.shape[0]

    return c_fit, A1_fit, A2_fit, Sigma_fit


# ------------------------------------------------------------
# Simulate
# ------------------------------------------------------------

y = np.zeros((n, k))
y[:, :] = simulate_var2(
    n,
    burn,
    c_true,
    A1_true,
    A2_true,
    Sigma_true
)

# ------------------------------------------------------------
# Fit
# ------------------------------------------------------------

c_fit, A1_fit, A2_fit, Sigma_fit = fit_var2(y)


# ------------------------------------------------------------
# Compare true and fitted parameters
# ------------------------------------------------------------

# Two near-identical functions, not one: xp2f.py infers a fixed array
# rank per function parameter from its call sites, and this same helper
# would otherwise be called with both a 1D array (c) and 2D arrays
# (A1/A2/Sigma), which it can't represent in one generated Fortran
# subroutine.
def print_comparison_vec(name, true, fit):
    print()
    print(name)
    print("-" * len(name))
    print("true:")
    print(np.round(true, 4))
    print()
    print("fit:")
    print(np.round(fit, 4))
    print()
    print("fit - true:")
    print(np.round(fit - true, 4))


def print_comparison_mat(name, true, fit):
    print()
    print(name)
    print("-" * len(name))
    print("true:")
    print(np.round(true, 4))
    print()
    print("fit:")
    print(np.round(fit, 4))
    print()
    print("fit - true:")
    print(np.round(fit - true, 4))


print_comparison_vec("Intercept c", c_true, c_fit)
print_comparison_mat("A1", A1_true, A1_fit)
print_comparison_mat("A2", A2_true, A2_fit)
print_comparison_mat("Innovation covariance Sigma", Sigma_true, Sigma_fit)
