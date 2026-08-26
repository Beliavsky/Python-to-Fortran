"""
Branched from xreturn_stats_simple.py: same CSV/log-return setup, but
instead of simple mean/sd/min/max stats, fit a Student-t distribution by
MLE to each asset's return series (location, scale, degrees of freedom).

The per-asset fit is a top-level `for j in range(n_assets): ... minimize(...)`
loop (mirroring xarma_aic_fit.py's grid-search structure) rather than a
`fn(col)`-per-column helper function called from a DataFrame-building list
comprehension (xreturn_stats_simple.py's `return_stats` pattern): xp2f.py
synthesizes minimize()'s `args=` wrapper as a new top-level function that
re-embeds the args= expressions verbatim, so an extra argument that is
itself a parameter of an *enclosing* helper function (rather than a
top-level global) would not resolve correctly (no closures in Fortran).
Keeping the fit loop -- and the `x = rets[:, j]` slice `args=(x,)` refers
to -- at top level sidesteps that, the same way xarma_aic_fit.py's
`objective` only ever reads top-level `xdata`/`pq`, never a helper
function's own parameter.

Uses the same standardized Student-t log-likelihood (scale = the actual
standard deviation, via the `dof - 2` normalization) as
nagarch_t_model.py's neg_loglik, just without the GARCH variance
recursion (iid case). As in xarma_aic_fit.py/xarma_nagarch_fit.py, a
derivative-free Powell retry backstops non-convergence, and Fortran vs.
Python fits are not guaranteed to land on the same local optimum for
every asset (profile-likelihood/finite-difference-gradient caveat).

Plain iid Student-t MLE is known to be degenerate on series with a few
isolated extreme observations against an otherwise calm sample: as
dof -> 2+ (with sigma inflating to compensate) the likelihood increases
without bound for some data configurations. A dof >= 2.5 box constraint
(via bounds=) excludes that unbounded limit; a handful of assets in this
particular dataset (e.g. those with an isolated extreme-return day) still
pin exactly at that floor -- expected given the pathology, not a bug --
while most converge to a genuine interior optimum.
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
rets = scale_ret * np.diff(np.log(prices), axis=0)

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
