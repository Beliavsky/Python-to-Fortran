"""
Python translation of xarma_aic.r.

Dependencies:
    numpy
    scipy

The ARMA fits use a Gaussian conditional likelihood with stationary/invertible
parameterizations. For a long series (the example uses n=10,000), this is very
close to exact Gaussian ML; unlike R's stats::arima(method="ML"), it does not
use R's exact state-space initialization.
"""

from dataclasses import dataclass

import numpy as np
from scipy import optimize, signal


@dataclass
class ArmaFit:
    p: int
    q: int
    ar_params: np.ndarray
    ma_params: np.ndarray
    mean: float
    sigma2: float
    residuals: np.ndarray
    loglik: float
    aic: float
    success: bool
    message: str


def _reflection_to_ar(kappa):
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


def _unpack_params(raw, p, q):
    """Convert unconstrained optimizer parameters to AR, MA, and mean."""
    raw = np.asarray(raw, dtype=float)

    ar_raw = raw[:p]
    ma_raw = raw[p:p + q]
    mean = raw[p + q]

    ar = _reflection_to_ar(np.tanh(ar_raw))

    # If psi is stationary for 1 - psi_1 z - ... - psi_q z^q,
    # theta = -psi makes 1 + theta_1 z + ... + theta_q z^q invertible.
    ma = -_reflection_to_ar(np.tanh(ma_raw))

    return ar, ma, mean


def _arma_residuals(x, ar, ma, mean):
    """
    Compute conditional ARMA innovations.

    For centered x:
        (1 - phi_1 B - ... - phi_p B^p) x_t
          = (1 + theta_1 B + ... + theta_q B^q) e_t
    """
    y = np.asarray(x, dtype=float) - mean

    ar_poly = np.r_[1.0, -np.asarray(ar, dtype=float)]
    ma_poly = np.r_[1.0, np.asarray(ma, dtype=float)]

    return signal.lfilter(ar_poly, ma_poly, y)


def _profile_loglik(x, ar, ma, mean):
    """Gaussian conditional log-likelihood with sigma^2 profiled out."""
    resid = _arma_residuals(x, ar, ma, mean)

    # Use the same number of observations for every candidate model so that
    # AIC values are directly comparable. The initial filter state is zero.
    sigma2 = np.mean(resid * resid)
    if not np.isfinite(sigma2) or sigma2 <= 0.0:
        return -np.inf, np.nan, resid

    n_eff = resid.size
    loglik = -0.5 * n_eff * (np.log(2.0 * np.pi) + 1.0 + np.log(sigma2))
    return loglik, sigma2, resid


def _fit_arma(x, p, q):
    """Fit one stationary/invertible ARMA(p,q) model with a mean."""
    x = np.asarray(x, dtype=float)

    raw0 = np.zeros(p + q + 1, dtype=float)
    raw0[-1] = np.mean(x)

    def objective(raw):
        ar, ma, mean = _unpack_params(raw, p, q)
        loglik, _, _ = _profile_loglik(x, ar, ma, mean)
        return 1.0e100 if not np.isfinite(loglik) else -loglik

    result = optimize.minimize(
        objective,
        raw0,
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1.0e-11, "gtol": 1.0e-7},
    )

    # A derivative-free retry can help for difficult ARMA likelihood surfaces.
    if not result.success:
        retry = optimize.minimize(
            objective,
            result.x,
            method="Powell",
            options={"maxiter": 3000, "xtol": 1.0e-8, "ftol": 1.0e-8},
        )
        if retry.fun < result.fun:
            result = retry

    ar, ma, mean = _unpack_params(result.x, p, q)
    loglik, sigma2, residuals = _profile_loglik(x, ar, ma, mean)

    # p AR + q MA + mean + variance.
    n_params = p + q + 2
    aic = -2.0 * loglik + 2.0 * n_params

    return ArmaFit(
        p=p,
        q=q,
        ar_params=ar,
        ma_params=ma,
        mean=float(mean),
        sigma2=float(sigma2),
        residuals=residuals,
        loglik=float(loglik),
        aic=float(aic),
        success=bool(result.success),
        message=str(result.message),
    )


def fit_arma_aic(x, p_max=4, q_max=4):
    """
    Fit ARMA(p,q) models for 0 <= p <= p_max and 0 <= q <= q_max.

    This preserves the R code's model-selection rule: scanning p first and q
    second, replace the current best model only if AIC improves by more than 4.
    """
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]

    n = x.size
    max_order = max(p_max, q_max)
    if n <= max_order + 1:
        raise ValueError("time series is too short for p_max and q_max")

    n_fit = (p_max + 1) * (q_max + 1)
    fits = [None] * n_fit
    aic = np.empty(n_fit, dtype=float)

    best_idx = 0
    best_aic = np.inf
    best_p = 0
    best_q = 0
    aic_tol = 4.0

    for p in range(p_max + 1):
        for q in range(q_max + 1):
            idx = p * (q_max + 1) + q
            fit = _fit_arma(x, p, q)
            fits[idx] = fit
            aic[idx] = fit.aic

            if aic[idx] < best_aic - aic_tol:
                best_aic = aic[idx]
                best_idx = idx
                best_p = p
                best_q = q

    best_fit = fits[best_idx]

    return {
        "p": best_p,
        "q": best_q,
        "aic": aic,
        "ar_params": best_fit.ar_params.copy(),
        "ma_params": best_fit.ma_params.copy(),
        "mean": best_fit.mean,
        "sigma2": best_fit.sigma2,
        "residuals": best_fit.residuals.copy(),
        "fit": best_fit,
    }


def arima_sim(n, ar=None, ma=None, rng=None, burnin=1000):
    """Simulate a zero-mean stationary/invertible ARMA process."""
    ar = np.asarray([] if ar is None else ar, dtype=float)
    ma = np.asarray([] if ma is None else ma, dtype=float)

    if rng is None:
        rng = np.random.default_rng()

    eps = rng.standard_normal(n + burnin)
    ar_poly = np.r_[1.0, -ar]
    ma_poly = np.r_[1.0, ma]

    x = signal.lfilter(ma_poly, ar_poly, eps)
    return x[burnin:]


def acf(x, lag_max=10):
    """R-like sample ACF for lags 0..lag_max."""
    x = np.asarray(x, dtype=float)
    y = x - np.mean(x)
    denom = np.dot(y, y)

    ans = np.empty(lag_max + 1, dtype=float)
    ans[0] = 1.0

    for lag in range(1, lag_max + 1):
        ans[lag] = np.dot(y[:-lag], y[lag:]) / denom

    return ans


if __name__ == "__main__":
    rng = np.random.default_rng(123)

    n = 10**4
    ar_true = np.array([0.0])
    ma_true = np.array([-0.8])

    x = arima_sim(
        n=n,
        ar=ar_true,
        ma=ma_true,
        rng=rng,
    )

    print("#obs:", n)
    print("ar_true:", ar_true)
    print("ma_true:", ma_true)
    print("acf:")
    print(np.round(acf(x, lag_max=10), 4))

    ans = fit_arma_aic(x, p_max=4, q_max=4)

    print("Chosen ARMA order:", ans["p"], ans["q"])
    print("AR parameters:")
    print(ans["ar_params"])
    print("MA parameters:")
    print(ans["ma_params"])

    print("First residuals:")
    print(ans["residuals"][:6])
