"""
Branched from xarma_aic_fit.py: fit ARMA(p,q) models over a grid of orders
and select the best by AIC, exactly as before, but the simulated data is
now driven by NAGARCH(1,1) innovations (Engle & Ng's nonlinear asymmetric
GARCH: h_t = omega + alpha*(eps_{t-1} - theta*sqrt(h_{t-1}))**2 + beta*h_{t-1},
same recursion as nagarch_variance() in nagarch_t_model.py) instead of iid
standard-normal noise.

`objective` is unchanged from xarma_aic_fit.py: it still scores candidate
ARMA orders with a profile Gaussian likelihood that assumes iid errors.
That assumption is now deliberately wrong -- the true innovations are
conditionally heteroskedastic (and asymmetric, via theta) -- so this script
is a robustness check on AIC-based ARMA order selection when the noise
process is misspecified, not a correctly-specified fit. NAGARCH parameters
below (omega=0.05, alpha=0.08, theta=0.5, beta=0.85) are chosen so the
innovations' unconditional variance is 1 (omega / (1 - beta - alpha*(1 +
theta**2)) = 0.05 / 0.05 = 1), matching the unit-variance noise the
original script used, so the printed ACF/AIC numbers stay comparable.

As in xarma_aic_fit.py, the Fortran and Python fits are not guaranteed to
land on the same local optimum for every candidate order (same profile-
likelihood/finite-difference-gradient caveat), and the Powell retry is
kept for the same reason.
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


def simulate_nagarch_noise(n, omega, alpha, theta, beta):
    """Generate n zero-mean innovations from a NAGARCH(1,1) process."""
    h = np.empty(n)
    eps = np.empty(n)

    denom = 1.0 - beta - alpha * (1.0 + theta**2)
    h[0] = omega / denom
    z0 = rng.standard_normal()
    eps[0] = np.sqrt(h[0]) * z0

    for t in range(1, n):
        h[t] = (
            omega
            + alpha * (eps[t - 1] - theta * np.sqrt(h[t - 1]))**2
            + beta * h[t - 1]
        )
        zt = rng.standard_normal()
        eps[t] = np.sqrt(h[t]) * zt

    return eps


def simulate_arma_nagarch(n, ar, ma, burnin, omega, alpha, theta, beta):
    """Simulate a zero-mean stationary/invertible ARMA process driven by NAGARCH(1,1) noise."""
    eps = simulate_nagarch_noise(n + burnin, omega, alpha, theta, beta)
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

omega_true = 0.05
alpha_true = 0.08
theta_true = 0.5
beta_true = 0.85

xdata = np.asarray(
    simulate_arma_nagarch(
        n, ar_true, ma_true, 1000, omega_true, alpha_true, theta_true, beta_true
    )
)

print("#obs:", n)
print("ar_true:", ar_true)
print("ma_true:", ma_true)
print("nagarch omega/alpha/theta/beta:", omega_true, alpha_true, theta_true, beta_true)
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
