"""
Branched from xfit_nagarch_ccc.py: replaces the constant correlation
matrix with Engle (2002)'s DCC (dynamic conditional correlation) -- the
standard generalization of CCC that lets the conditional correlation
matrix move over time via its own GARCH-like recursion.

Step 1 (per-asset NAGARCH(1,1)-t fits, giving standardized residuals
z_it = (r_it - mu_i) / sqrt(h_it)) is unchanged from xfit_nagarch_ccc.py.

Step 2 replaces the static multivariate-t covariance fit with:
  - Correlation targeting: Qbar = (Z.T @ Z) / n, the sample second-moment
    matrix of the standardized residuals, used as a fixed target rather
    than re-estimated -- the standard DCC simplification (Engle & Sheppard
    2001) that keeps the free parameter count at just (a, b, dof) instead
    of also estimating O(p^2) unconditional-correlation entries.
  - The DCC(1,1) recursion Q_t = (1-a-b)*Qbar + a*z_{t-1}z_{t-1}' + b*Q_{t-1}
    (Q_1 = Qbar), normalized each period to a correlation matrix
    R_t = D_t^-1 Q_t D_t^-1 with D_t = diag(sqrt(diag(Q_t))).
  - a, b are parameterized as a = 0.999*sigmoid(p0), b = (0.999-a)*sigmoid(p1)
    so a, b >= 0 and a+b < 0.999 (stationarity) hold automatically, with no
    bounds= needed -- unlike xreturns_mv_t.py's Cholesky/CCC's covariance
    parameterization, no positivity trick is needed for a scalar pair.
  - The multivariate-t log-likelihood is summed period-by-period using
    each period's own R_t (mean 0, since z is already demeaned by the
    NAGARCH fit; scale is R_t directly since z has unit marginal variance
    by construction, so no separate location/diagonal-scale parameters are
    needed here, unlike neg_loglik_mvt in xreturns_mv_t.py/xfit_nagarch_ccc.py).

This is a much heavier objective than CCC's: R_t needs to be rebuilt and
inverted at every one of the ~n timesteps on every single likelihood
evaluation (a time-loop wrapping p x p linear algebra), rather than one
static p x p fit -- a genuinely different shape of computation from
anything transpiled so far in this line of scripts, so this is as much a
transpiler stress test as a modeling exercise.

After fitting, the recursion is replayed once more (dcc_final_corr) to
report the terminal R_T alongside the long-run (Qbar-normalized)
correlation, illustrating how far correlation has drifted from its
unconditional average -- the whole point of DCC over CCC.
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
# Step 2: standardize by each asset's fitted variance path, then fit the
# DCC(1,1) time-varying correlation recursion to the residuals
# -----------------------------


def neg_loglik_dcc(params, Z, Qbar):
    """Negative DCC(1,1)-t log-likelihood; params = (raw_a, raw_b, log_dof_m2)."""
    p = Z.shape[1]
    n_obs = Z.shape[0]

    a_frac = 1.0 / (1.0 + np.exp(-params[0]))
    b_frac = 1.0 / (1.0 + np.exp(-params[1]))
    a = 0.999 * a_frac
    b = (0.999 - a) * b_frac
    dof = 2.0 + np.exp(params[2])

    Q = Qbar

    ll = 0.0
    for t in range(n_obs):
        if t > 0:
            zt_prev = Z[t - 1, :]
            Q = (1.0 - a - b) * Qbar + a * np.outer(zt_prev, zt_prev) + b * Q

        d = np.sqrt(np.diag(Q))
        Rt = Q / np.outer(d, d)
        Rt_inv = np.linalg.inv(Rt)
        logdet = np.log(np.linalg.det(Rt))

        zt = Z[t, :]
        tmp = Rt_inv @ zt
        quad = np.dot(tmp, zt)

        ll = ll + (
            gammaln(0.5 * (dof + p))
            - gammaln(0.5 * dof)
            - 0.5 * p * np.log(np.pi * (dof - 2.0))
            - 0.5 * logdet
            - 0.5 * (dof + p) * np.log(1.0 + quad / (dof - 2.0))
        )

    return -ll


def dcc_final_corr(a, b, Z, Qbar):
    """Replay the fitted DCC(1,1) recursion once more and return the terminal R_T."""
    n_obs = Z.shape[0]
    Q = Qbar
    for t in range(n_obs):
        if t > 0:
            zt_prev = Z[t - 1, :]
            Q = (1.0 - a - b) * Qbar + a * np.outer(zt_prev, zt_prev) + b * Q
    d = np.sqrt(np.diag(Q))
    R = Q / np.outer(d, d)
    return R


Z = np.zeros((rets.shape[0], nassets))
for j in range(nassets):
    r = rets[:, j]
    h = nagarch_variance(r, mu_hat[j], omega_hat[j], alpha_hat[j], theta_hat[j], beta_hat[j])
    Z[:, j] = (r - mu_hat[j]) / np.sqrt(h)

Qbar = np.zeros((nassets, nassets))
Qbar[:, :] = (Z.T @ Z) / Z.shape[0]

dcc0 = np.array([
    logit(0.05 / 0.999),
    logit(0.90 / (0.999 - 0.05)),
    np.log(8.0 - 2.0),
])

result_dcc = minimize(
    neg_loglik_dcc,
    dcc0,
    args=(Z, Qbar),
    method="L-BFGS-B",
    options={"maxiter": 500, "ftol": 1.0e-10, "gtol": 1.0e-6},
)

if not result_dcc.success:
    retry_dcc = minimize(
        neg_loglik_dcc,
        result_dcc.x,
        args=(Z, Qbar),
        method="Powell",
        options={"maxiter": 1000, "ftol": 1.0e-8},
    )
    if retry_dcc.fun < result_dcc.fun:
        result_dcc = retry_dcc

a_hat = 0.999 / (1.0 + np.exp(-result_dcc.x[0]))
b_hat = (0.999 - a_hat) / (1.0 + np.exp(-result_dcc.x[1]))
dcc_dof = 2.0 + np.exp(result_dcc.x[2])
dcc_loglik = -result_dcc.fun

qbar_d = np.sqrt(np.diag(Qbar))
longrun_corr = Qbar / np.outer(qbar_d, qbar_d)
terminal_corr = dcc_final_corr(a_hat, b_hat, Z, Qbar)

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
print("DCC(1,1) fit to standardized residuals")
print("Optimization success:", result_dcc.success)
print("Fitted a:", a_hat)
print("Fitted b:", b_hat)
print("Persistence a+b:", a_hat + b_hat)
print("Fitted dof:", dcc_dof)
print("Log-likelihood:", dcc_loglik)

print()
print("Long-run (Qbar-implied) correlation:")
print(price_names)
print(np.round(longrun_corr, 4))

print()
print("Terminal (most recent) DCC correlation R_T:")
print(price_names)
print(np.round(terminal_corr, 4))

step1_time = step1_end - overall_start
step2_time = overall_end - step1_end
overall_time = overall_end - overall_start

print()
print("Timing")
print("-" * 40)
print(f"Step 1 (per-asset NAGARCH fits): {step1_time:.6f} seconds")
print(f"Step 2 (DCC correlation fit):    {step2_time:.6f} seconds")
print(f"Overall:                         {overall_time:.6f} seconds")
