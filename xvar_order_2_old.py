import numpy as np

np.random.seed(123)

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
        e = L @ np.random.randn(k)

        y[t] = (
            c
            + A1 @ y[t - 1]
            + A2 @ y[t - 2]
            + e
        )

    return y[burn + 2:]


def fit_var2(y):
    n, k = y.shape

    # Regressors:
    # [1, y_{t-1}', y_{t-2}']
    X = np.ones((n - 2, 1 + 2 * k))

    X[:, 1:1 + k] = y[1:-1]
    X[:, 1 + k:] = y[:-2]

    # Responses y_t
    Y = y[2:]

    # Multivariate OLS:
    #
    # B = argmin ||Y - X B||^2
    #
    B = np.linalg.lstsq(X, Y, rcond=None)[0]

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

y = simulate_var2(
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

def print_comparison(name, true, fit):
    print()
    print(name)
    print("-" * len(name))
    print("true:")
    print(true)
    print()
    print("fit:")
    print(fit)
    print()
    print("fit - true:")
    print(fit - true)


np.set_printoptions(precision=4, suppress=True)

print_comparison("Intercept c", c_true, c_fit)
print_comparison("A1", A1_true, A1_fit)
print_comparison("A2", A2_true, A2_fit)
print_comparison("Innovation covariance Sigma", Sigma_true, Sigma_fit)


# ------------------------------------------------------------
# Put all VAR coefficients into one vector for a compact
# comparison.
# ------------------------------------------------------------

true_params = np.concatenate([
    c_true,
    A1_true.ravel(),
    A2_true.ravel()
])

fit_params = np.concatenate([
    c_fit,
    A1_fit.ravel(),
    A2_fit.ravel()
])

print()
print("Compact coefficient comparison")
print("------------------------------")
print("parameter       true        fit       fit-true")

names = []

for i in range(k):
    names.append(f"c[{i + 1}]")

for i in range(k):
    for j in range(k):
        names.append(f"A1[{i + 1},{j + 1}]")

for i in range(k):
    for j in range(k):
        names.append(f"A2[{i + 1},{j + 1}]")

for name, true, fit in zip(names, true_params, fit_params):
    print(f"{name:10s} {true:10.4f} {fit:10.4f} {fit - true:10.4f}")
