"""
Branched from xreturns_t.py: keeps the per-asset univariate Student-t fits
unchanged, and adds a joint multivariate Student-t fit to all asset
returns together (location vector, scale/covariance matrix, one shared
degrees-of-freedom).

Multivariate Student-t log-density for a p-vector x, with location mu,
covariance-scaled matrix Sigma (via the same `dof - 2` standardization
used in the univariate case, so Sigma is directly the covariance matrix
for dof > 2), and shared dof:

    log f(x) = gammaln((dof+p)/2) - gammaln(dof/2) - 0.5*p*log(pi*(dof-2))
               - 0.5*log(det(Sigma)) - 0.5*(dof+p)*log(1 + Q/(dof-2))

where Q = (x-mu)' Sigma^-1 (x-mu). Sigma is parameterized through its
Cholesky factor L (Sigma = L @ L.T) with a log-transformed diagonal, which
both guarantees positive-definiteness during unconstrained optimization
and gives log(det(Sigma)) = 2*sum(log(diag(L))) for free (no separate
det/slogdet call needed). The batched Mahalanobis distance across all n
observations is computed with `np.einsum("ni,ij,nj->n", ...)`, which
xp2f.py already lowers to `sum(matmul(...) * ..., dim=2)`.

The joint fit is called once at top level (`args=(rets,)`), so the same
`x`-naming and helper-function-parameter-scoping pitfalls documented in
xreturns_t.py / xarma_aic_fit.py don't arise here -- there's no per-column
loop this time, just a single minimize() call over the whole return
matrix. As elsewhere, a Powell retry backstops L-BFGS-B non-convergence,
and small Fortran/Python differences in which local optimum is found are
possible on this 2*p + p*(p-1)/2 + 1 -dimensional, finite-difference-
gradient surface.
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

price_file = "asset_class_etf_prices.csv"
scale_ret = 100

dat = pd.read_csv(price_file)
dates = pd.to_datetime(dat["Date"], errors="coerce")

price_names = [c for c in dat.columns if c != "Date"]
prices = dat[price_names].to_numpy(dtype=float)

print("\nPrice file:", price_file)
print("Asset columns read:", len(price_names))
print("Assets read:")
print(price_names)

print("\nFirst price date:", str(dates.iloc[0].date()))
print("Last price date :", str(dates.iloc[-1].date()))

# -----------------------------
# Compute scaled log returns
# -----------------------------

ret_dates = dates.iloc[1:].reset_index(drop=True)
# Pre-allocate with a literal np.zeros((rows, cols)) shape tuple, then fill
# in place, rather than `rets = scale_ret * np.diff(...)` directly: the
# joint fit below passes the whole `rets` matrix as a minimize() args=
# extra, and xp2f.py's shared cross-function declaration inference only
# recognizes rank-2 from a handful of RHS shapes (a literal np.zeros/
# np.array((...)) shape tuple among them) -- a bare BinOp/Call expression
# like `scale_ret * np.diff(...)` isn't one of them and silently falls
# back to rank 1 (xreturns_t.py's `xret = rets[:, j]` slice didn't hit
# this, since a slice IS a recognized shape).
rets = np.zeros((prices.shape[0] - 1, prices.shape[1]))
rets[:, :] = scale_ret * np.diff(np.log(prices), axis=0)

print("\nNumber of price observations:", prices.shape[0])
print("Number of return observations:", rets.shape[0])
print("First return date:", str(ret_dates.iloc[0].date()))
print("Last return date :", str(ret_dates.iloc[-1].date()))

# -----------------------------
# Student-t MLE per asset
# -----------------------------


def neg_loglik_t(params, x):
    """Negative Student-t log-likelihood; params = (mu, log_sigma, log_dof_m2)."""
    mu = params[0]
    log_sigma = params[1]
    log_dof_m2 = params[2]

    sigma = np.exp(log_sigma)
    dof = 2.0 + np.exp(log_dof_m2)

    z = (x - mu) / sigma
    ll = np.sum(
        gammaln(0.5 * (dof + 1.0))
        - gammaln(0.5 * dof)
        - 0.5 * np.log(np.pi * (dof - 2.0))
        - np.log(sigma)
        - 0.5 * (dof + 1.0) * np.log(1.0 + z**2 / (dof - 2.0))
    )
    return -ll


n_assets = rets.shape[1]

mu_hat = np.empty(n_assets)
sigma_hat = np.empty(n_assets)
dof_hat = np.empty(n_assets)
loglik_hat = np.empty(n_assets)

for j in range(n_assets):
    # Named xret, not x: xp2f.py's minimize() args= wrapper synthesizes a
    # callback whose own parameter is always named `x`, and naming the
    # *data* variable `x` too collides with that (same pitfall documented
    # in xarma_aic_fit.py, there worked around by naming the data `xdata`).
    xret = rets[:, j]

    params0 = np.array([np.mean(xret), np.log(np.std(xret, ddof=1)), np.log(8.0 - 2.0)])

    # Unconstrained t-MLE can be degenerate (dof -> 2, sigma -> infinity) on
    # series with a few extreme outliers, since the likelihood is unbounded
    # at that boundary for some data configurations; a floor just above 2
    # excludes that degenerate limit without disturbing genuine interior
    # fits (daily asset returns often legitimately fit dof in the 2-4 range).
    result = minimize(
        neg_loglik_t,
        params0,
        args=(xret,),
        method="L-BFGS-B",
        bounds=[(None, None), (None, None), (np.log(0.5), np.log(58.0))],
        options={"maxiter": 1000, "ftol": 1.0e-11, "gtol": 1.0e-7},
    )

    if not result.success:
        retry = minimize(
            neg_loglik_t,
            result.x,
            args=(xret,),
            method="Powell",
            options={"maxiter": 3000, "ftol": 1.0e-8},
        )
        if retry.fun < result.fun:
            result = retry

    mu_hat[j] = result.x[0]
    sigma_hat[j] = np.exp(result.x[1])
    dof_hat[j] = 2.0 + np.exp(result.x[2])
    loglik_hat[j] = -result.fun

stats = pd.DataFrame(
    {
        "mu": mu_hat,
        "sigma": sigma_hat,
        "dof": dof_hat,
        "loglik": loglik_hat,
    },
    index=price_names,
)

print("\nFitted Student-t parameters, returns scaled by scale_ret =", scale_ret)
print(stats.round(4))

# -----------------------------
# Joint multivariate Student-t MLE
# -----------------------------


def neg_loglik_mvt(theta, X):
    """Negative multivariate Student-t log-likelihood for the joint returns X (n x p)."""
    p = X.shape[1]
    n_obs = X.shape[0]
    n_tri = (p * (p - 1)) // 2

    i0 = p
    i1 = 2 * p
    i2 = i1 + n_tri

    mu = theta[:i0]
    log_diag = theta[i0:i1]
    offdiag = theta[i1:i2]
    log_dof_m2 = theta[i2]

    dof = 2.0 + np.exp(log_dof_m2)

    chol = np.zeros((p, p))
    for i in range(p):
        chol[i, i] = np.exp(log_diag[i])

    k = 0
    for i in range(1, p):
        for jj in range(i):
            chol[i, jj] = offdiag[k]
            k += 1

    logdet = 2.0 * np.sum(log_diag)

    sigma_mat = chol @ chol.T
    sigma_inv = np.linalg.inv(sigma_mat)

    resid = X - mu
    quad = np.einsum("ni,ij,nj->n", resid, sigma_inv, resid)

    ll = n_obs * (
        gammaln(0.5 * (dof + p))
        - gammaln(0.5 * dof)
        - 0.5 * p * np.log(np.pi * (dof - 2.0))
        - 0.5 * logdet
    ) - 0.5 * (dof + p) * np.sum(np.log(1.0 + quad / (dof - 2.0)))

    return -ll


n_tri_mv = (n_assets * (n_assets - 1)) // 2
n_theta_mv = 2 * n_assets + n_tri_mv + 1

mean0 = np.mean(rets, axis=0)
# np.std(rets, axis=0, ...) isn't supported (xp2f.py's np.std lowering only
# handles a plain rank-1 array; the mean/sum/sqrt building blocks below are
# each independently axis-aware, so compose the column std from those).
sd0 = np.sqrt(np.sum((rets - mean0) ** 2, axis=0) / (rets.shape[0] - 1))

theta0 = np.zeros(n_theta_mv)
theta0[:n_assets] = mean0
theta0[n_assets:2 * n_assets] = np.log(sd0)
theta0[2 * n_assets + n_tri_mv] = np.log(8.0 - 2.0)

# Unlike the univariate fits above, theta's length depends on n_assets
# (only known at runtime, from the CSV column count), so a literal
# bounds= list -- whose length xp2f.py's L-BFGS-B bridge needs to know at
# transpile time -- isn't an option here. Left unconstrained: pooling all
# assets into one joint fit is far less prone to the single-outlier
# degenerate-dof pathology described above, and empirically converges well
# away from the dof -> 2 boundary.
result_mv = minimize(
    neg_loglik_mvt,
    theta0,
    args=(rets,),
    method="L-BFGS-B",
    options={"maxiter": 3000, "ftol": 1.0e-10, "gtol": 1.0e-6},
)

if not result_mv.success:
    retry_mv = minimize(
        neg_loglik_mvt,
        result_mv.x,
        args=(rets,),
        method="Powell",
        options={"maxiter": 5000, "ftol": 1.0e-8},
    )
    if retry_mv.fun < result_mv.fun:
        result_mv = retry_mv

mv_mu = result_mv.x[:n_assets]
mv_log_diag = result_mv.x[n_assets:2 * n_assets]
mv_offdiag = result_mv.x[2 * n_assets:2 * n_assets + n_tri_mv]
mv_dof = 2.0 + np.exp(result_mv.x[2 * n_assets + n_tri_mv])
mv_loglik = -result_mv.fun

mv_chol = np.zeros((n_assets, n_assets))
for i in range(n_assets):
    mv_chol[i, i] = np.exp(mv_log_diag[i])

k = 0
for i in range(1, n_assets):
    for jj in range(i):
        mv_chol[i, jj] = mv_offdiag[k]
        k += 1

mv_sigma = mv_chol @ mv_chol.T
mv_sd = np.sqrt(np.diag(mv_sigma))
mv_corr = mv_sigma / np.outer(mv_sd, mv_sd)

print()
print("Joint multivariate Student-t fit")
print("Optimization success:", result_mv.success)
print("Fitted dof:", mv_dof)
print("Log-likelihood:", mv_loglik)

print()
print("Fitted mean vector:")
print(np.round(mv_mu, 4))

print()
print("Fitted marginal std devs (from joint Sigma):")
print(np.round(mv_sd, 4))

print()
print("Implied correlation matrix:")
print(price_names)
print(np.round(mv_corr, 4))
