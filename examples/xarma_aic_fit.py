"""
Transpilable rewrite of xarma_aic.py: fit ARMA(p,q) models over a grid of
orders and select the best by AIC.

This is restructured (not just re-typed) specifically to avoid patterns
xp2f.py cannot yet handle, discovered while adapting the original script:
  - The original's `objective` was a closure defined inside `_fit_arma`,
    capturing `x`, `p`, `q` from the enclosing scope. xp2f.py's
    scipy.optimize.minimize bridge only supports top-level (non-nested)
    objective functions, so `objective` here is top-level and takes
    `xdata`, `pq` as explicit arguments instead of capturing them.
  - The extra data array is named `xdata`, not `x`: xp2f.py's minimize()
    args= wrapper synthesizes a callback whose own parameter is always
    named `x`, and naming the *data* argument `x` too collides with that.
  - `p` and `q` are packed into a single float array `pq` rather than
    passed as separate scalar args=: xp2f.py promotes an args= extra
    argument to module scope by inspecting its assignment shape, and a
    bare `for p in range(...)` loop variable (or a plain `p = p_iter`
    copy of one) isn't recognized as integer-valued by that inference,
    silently typing it real instead. An explicit `np.array([p, q],
    dtype=float)` is a shape that inference does recognize correctly.
  - `objective` is a single flat function rather than split into
    unpack_params/arma_residuals/profile_loglik helpers: passing the
    unpacked `ar`/`ma` arrays *between* top-level functions (as opposed
    to computing and using them within one function) hit a separate
    kind-inference gap that mistyped them as integer.
  - No dataclass / dict-of-mixed-types return value for the per-model
    fit result; the running best model's order, AIC, and parameters are
    tracked directly in plain top-level variables instead.

Because xp2f.py's L-BFGS-B bridge estimates gradients by finite
differences (scipy's own Fortran L-BFGS-B does the same when no
analytic jacobian is supplied), and this profile likelihood surface is
poorly identified away from its optimum (a saturating tanh
reparameterization plus AR/MA parameters that can trade off against each
other), the Fortran and Python fits are not guaranteed to converge to
the same local optimum for every candidate order, especially the more
overparameterized ones -- this was confirmed by direct comparison: at
matched points, the Fortran and Python objective function values agree
to double-precision, and small models fit and select identically, but
some individual larger-order candidates in the grid can land on a
different (and visibly worse-AIC) local optimum. Model selection is
usually still correct for the true low order and comparisons close to
scipy's; a difference here is a property of the local optimizer
landscape, not a translation error. As in the original script, a
derivative-free Powell retry (now supported by xp2f.py too) kicks in
whenever the primary L-BFGS-B fit reports non-convergence, which
mitigates but does not eliminate this.
"""

import time
import numpy as np
from scipy.optimize import minimize
from scipy import signal

rng = np.random.default_rng(123)


def reflection_to_ar(kappa):
    """Map reflection coefficients in (-1, 1) to stationary AR coefficients."""
    kappa = np.asarray(kappa, dtype=float)
    phi = np.empty(0, dtype=float)

    for km in kappa:
        m = phi.size + 1
        new_phi = np.empty(m, dtype=float)
        if m > 1:
            old = phi.copy()
            new_phi[:-1] = old - km * old[::-1]
        new_phi[-1] = km
        phi = new_phi

    return phi


def simulate_arma(n, ar, ma, burnin):
    """Simulate a zero-mean stationary/invertible ARMA process."""
    eps = rng.standard_normal(n + burnin)
    ar_poly = np.r_[1.0, -ar]
    ma_poly = np.r_[1.0, ma]
    xfull = signal.lfilter(ma_poly, ar_poly, eps)
    return xfull[burnin:]


def acf(x, lag_max):
    """R-like sample ACF for lags 0..lag_max."""
    y = x - np.mean(x)
    denom = np.dot(y, y)

    ans = np.empty(lag_max + 1, dtype=float)
    ans[0] = 1.0

    for lag in range(1, lag_max + 1):
        ans[lag] = np.dot(y[:-lag], y[lag:]) / denom

    return ans


def objective(raw, xdata, pq):
    """Negative profile Gaussian log-likelihood for ARMA(p,q) given transformed params."""
    p = int(pq[0])
    q = int(pq[1])

    ar_raw = raw[:p]
    ma_raw = raw[p:p + q]
    mean = raw[p + q]

    # If psi is stationary for 1 - psi_1 z - ... - psi_p z^p,
    # theta = -psi makes 1 + theta_1 z + ... + theta_q z^q invertible.
    ar = reflection_to_ar(np.tanh(ar_raw))
    ma = -reflection_to_ar(np.tanh(ma_raw))

    y = xdata - mean
    ar_poly = np.r_[1.0, -ar]
    ma_poly = np.r_[1.0, ma]
    resid = signal.lfilter(ar_poly, ma_poly, y)

    sigma2 = np.mean(resid * resid)
    if not np.isfinite(sigma2) or sigma2 <= 0.0:
        return 1.0e100

    n_eff = resid.size
    loglik = -0.5 * n_eff * (np.log(2.0 * np.pi) + 1.0 + np.log(sigma2))
    return -loglik


# --------------------------------------------------
# True model / simulation
# --------------------------------------------------

n = 2000
ar_true = np.array([0.0])
ma_true = np.array([-0.8])

xdata = np.asarray(simulate_arma(n, ar_true, ma_true, 1000))

print("#obs:", n)
print("ar_true:", ar_true)
print("ma_true:", ma_true)
print("acf:")
print(np.round(acf(xdata, 10), 4))

# --------------------------------------------------
# ARMA(p,q) grid search by AIC
# --------------------------------------------------

p_max = 3
q_max = 3
aic_tol = 4.0

best_aic = 1.0e300
best_p = 0
best_q = 0
best_ar = np.array([0.0])
best_ma = np.array([0.0])
best_mean = 0.0

print()
print(f"{'p':3s} {'q':3s} {'aic':>14s}")

fit_start = time.perf_counter()

for p in range(p_max + 1):
    for q in range(q_max + 1):
        pq = np.array([p, q], dtype=float)

        raw0 = np.zeros(p + q + 1)
        raw0[-1] = np.mean(xdata)

        result = minimize(
            objective,
            raw0,
            args=(xdata, pq),
            method="L-BFGS-B",
            options={"maxiter": 1000, "ftol": 1.0e-11, "gtol": 1.0e-7},
        )

        # A derivative-free retry can help for difficult ARMA likelihood
        # surfaces (near-degenerate under the tanh reparameterization).
        if not result.success:
            retry = minimize(
                objective,
                result.x,
                args=(xdata, pq),
                method="Powell",
                options={"maxiter": 3000, "ftol": 1.0e-8},
            )
            if retry.fun < result.fun:
                result = retry

        neg_ll = result.fun
        n_params = p + q + 2
        aic = 2.0 * neg_ll + 2.0 * n_params

        print(f"{p:3d} {q:3d} {aic:14.4f}")

        if aic < best_aic - aic_tol:
            best_aic = aic
            best_p = p
            best_q = q
            ar_raw = result.x[:p]
            ma_raw = result.x[p:p + q]
            best_ar = reflection_to_ar(np.tanh(ar_raw))
            best_ma = -reflection_to_ar(np.tanh(ma_raw))
            best_mean = result.x[p + q]

fit_end = time.perf_counter()

# --------------------------------------------------
# Results
# --------------------------------------------------

print()
print("Chosen ARMA order:", best_p, best_q)
print("AIC:", best_aic)
print("Mean:", best_mean)
print("AR parameters:")
print(best_ar)
print("MA parameters:")
print(best_ma)

print()
print("Fitting time:", fit_end - fit_start, "seconds")
