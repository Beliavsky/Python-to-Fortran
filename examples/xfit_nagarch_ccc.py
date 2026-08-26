"""
Branched from xfit_nagarch_t.py: adds a CCC (constant conditional
correlation, Bollerslev 1990) multivariate-GARCH layer with multivariate-t
innovations on top of the existing per-asset NAGARCH(1,1)-t fits.

Two-step estimation (the standard/original CCC approach, not a one-shot
joint MLE):
  1. Fit NAGARCH(1,1)-t to each asset separately -- exactly
     xfit_nagarch_t.py's loop, unchanged. This gives mu_i and each asset's
     conditional variance path h_it (via nagarch_variance(), already
     imported from nagarch_t_model.py but previously only used internally
     by neg_loglik/neg_loglik_fixed_dof; it's called directly here too).
  2. Standardize: z_it = (r_it - mu_i) / sqrt(h_it). Fit a joint
     multivariate Student-t distribution to the z_t matrix (constant
     across time, hence "constant conditional correlation") -- this reuses
     xreturns_mv_t.py's Cholesky-covariance MLE machinery verbatim, just
     applied to the standardized residuals instead of raw returns, then
     rescaled to a correlation matrix (diag exactly 1) for reporting.

A one-shot joint MLE (all NAGARCH parameters and the correlation matrix
optimized together) would be more statistically efficient, but is a much
higher-dimensional, more fragile optimization -- and isn't how CCC was
originally formulated anyway. If useful later, this two-step fit's
estimates are a natural starting point for that joint refinement, but that
isn't attempted here.

As in xreturns_mv_t.py, the joint correlation fit is a single top-level
minimize() call (not nested in a helper function), avoiding the args=
scoping pitfall documented there and in xarma_aic_fit.py.
"""

import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln
from nagarch_t_model import logit, nagarch_variance, neg_loglik, neg_loglik_fixed_dof

price_file = "asset_class_etf_prices.csv"
scale_ret = 100
max_assets = 3  # 0 (or negative) means no limit; set positive to limit the number of asset columns read
fixed_dof = 0.0  # <= 0 means fit dof along with the other parameters; set positive to hold dof fixed at this value
max_prices = 200

dat = pd.read_csv(price_file, nrows=max_prices)
dates = pd.to_datetime(dat["Date"], errors="coerce")

price_names = [c for c in dat.columns if c != "Date"]
prices = dat[price_names].to_numpy(dtype=float)

if max_assets > 0:
    price_names = price_names[:max_assets]
    prices = prices[:, :max_assets]

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
rets = scale_ret * np.diff(np.log(prices), axis=0)

print("\nNumber of price observations:", prices.shape[0])
print("Number of return observations:", rets.shape[0])
print("First return date:", str(ret_dates.iloc[0].date()))
print("Last return date :", str(ret_dates.iloc[-1].date()))

# -----------------------------
# Step 1: fit NAGARCH(1,1)-t to each asset's return series
# -----------------------------

overall_start = time.perf_counter()

nassets = rets.shape[1]

mu_hat = np.empty(nassets)
omega_hat = np.empty(nassets)
alpha_hat = np.empty(nassets)
theta_hat = np.empty(nassets)
beta_hat = np.empty(nassets)
dof_hat = np.empty(nassets)
success = np.empty(nassets, dtype=bool)

for j in range(nassets):
    r = rets[:, j]

    if fixed_dof > 0.0:
        x0 = np.array([
            np.mean(r),
            np.log(np.var(r)),
            logit(0.05),
            0.3,
            logit(0.85)
        ])

        result = minimize(
            neg_loglik_fixed_dof,
            x0,
            args=(r, fixed_dof),
            method="L-BFGS-B",
            bounds=[
                (-1.0, 1.0),
                (-30.0, 5.0),
                (-30.0, 30.0),
                (-5.0, 5.0),
                (-30.0, 30.0)
            ]
        )

        dof_hat[j] = fixed_dof
    else:
        x0 = np.array([
            np.mean(r),
            np.log(np.var(r)),
            logit(0.05),
            0.3,
            logit(0.85),
            np.log(8.0 - 2.0)
        ])

        result = minimize(
            neg_loglik,
            x0,
            args=(r,),
            method="L-BFGS-B",
            bounds=[
                (-1.0, 1.0),
                (-30.0, 5.0),
                (-30.0, 30.0),
                (-5.0, 5.0),
                (-30.0, 30.0),
                (-5.0, 5.0)
            ]
        )

        dof_hat[j] = 2.0 + np.exp(result.x[5])

    mu_hat[j] = result.x[0]
    omega_hat[j] = np.exp(result.x[1])
    alpha_hat[j] = 1.0 / (1.0 + np.exp(-result.x[2]))
    theta_hat[j] = result.x[3]
    beta_hat[j] = 1.0 / (1.0 + np.exp(-result.x[4]))
    success[j] = result.success

step1_end = time.perf_counter()

# -----------------------------
# Step 2: standardize by each asset's fitted variance path, then fit a
# joint multivariate Student-t (constant correlation) to the residuals
# -----------------------------


def neg_loglik_mvt(theta, X):
    """Negative multivariate Student-t log-likelihood for the joint sample X (n x p)."""
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


Z = np.zeros((rets.shape[0], nassets))
for j in range(nassets):
    r = rets[:, j]
    h = nagarch_variance(r, mu_hat[j], omega_hat[j], alpha_hat[j], theta_hat[j], beta_hat[j])
    Z[:, j] = (r - mu_hat[j]) / np.sqrt(h)

mean0 = np.mean(Z, axis=0)
sd0 = np.sqrt(np.sum((Z - mean0) ** 2, axis=0) / (Z.shape[0] - 1))

n_tri_mv = (nassets * (nassets - 1)) // 2
n_theta_mv = 2 * nassets + n_tri_mv + 1

theta0 = np.zeros(n_theta_mv)
theta0[:nassets] = mean0
theta0[nassets:2 * nassets] = np.log(sd0)
theta0[2 * nassets + n_tri_mv] = np.log(8.0 - 2.0)

result_mv = minimize(
    neg_loglik_mvt,
    theta0,
    args=(Z,),
    method="L-BFGS-B",
    options={"maxiter": 3000, "ftol": 1.0e-10, "gtol": 1.0e-6},
)

if not result_mv.success:
    retry_mv = minimize(
        neg_loglik_mvt,
        result_mv.x,
        args=(Z,),
        method="Powell",
        options={"maxiter": 5000, "ftol": 1.0e-8},
    )
    if retry_mv.fun < result_mv.fun:
        result_mv = retry_mv

mv_mu = result_mv.x[:nassets]
mv_log_diag = result_mv.x[nassets:2 * nassets]
mv_offdiag = result_mv.x[2 * nassets:2 * nassets + n_tri_mv]
mv_dof = 2.0 + np.exp(result_mv.x[2 * nassets + n_tri_mv])
mv_loglik = -result_mv.fun

mv_chol = np.zeros((nassets, nassets))
for i in range(nassets):
    mv_chol[i, i] = np.exp(mv_log_diag[i])

k = 0
for i in range(1, nassets):
    for jj in range(i):
        mv_chol[i, jj] = mv_offdiag[k]
        k += 1

mv_sigma = mv_chol @ mv_chol.T
mv_sd = np.sqrt(np.diag(mv_sigma))
ccc_corr = mv_sigma / np.outer(mv_sd, mv_sd)

overall_end = time.perf_counter()

# -----------------------------
# Results
# -----------------------------

print("\nNAGARCH(1,1)-t fits, returns scaled by scale_ret =", scale_ret)
if fixed_dof > 0.0:
    print("dof held fixed at:", fixed_dof)
else:
    print("dof fitted per asset")
print()
print(f"{'asset':10s} {'mu':>12s} {'omega':>12s} {'alpha':>12s} {'theta':>12s} {'beta':>12s} {'dof':>10s} {'persist':>12s} {'ok':>5s}")
print("-" * 92)
for j in range(nassets):
    persistence = beta_hat[j] + alpha_hat[j] * (1.0 + theta_hat[j]**2)
    print(
        f"{price_names[j]:10s} {mu_hat[j]:12.6g} {omega_hat[j]:12.6g} "
        f"{alpha_hat[j]:12.6g} {theta_hat[j]:12.6g} {beta_hat[j]:12.6g} "
        f"{dof_hat[j]:10.4g} {persistence:12.6g} {str(success[j]):>5s}"
    )

print()
print("CCC (constant conditional correlation) fit to standardized residuals")
print("Optimization success:", result_mv.success)
print("Fitted joint dof:", mv_dof)
print("Log-likelihood:", mv_loglik)
print("Standardized-residual location (sanity check, should be near 0):")
print(np.round(mv_mu, 4))

print()
print("Constant conditional correlation matrix R:")
print(price_names)
print(np.round(ccc_corr, 4))

step1_time = step1_end - overall_start
step2_time = overall_end - step1_end
overall_time = overall_end - overall_start

print()
print("Timing")
print("-" * 40)
print(f"Step 1 (per-asset NAGARCH fits): {step1_time:.6f} seconds")
print(f"Step 2 (CCC correlation fit):    {step2_time:.6f} seconds")
print(f"Overall:                         {overall_time:.6f} seconds")
