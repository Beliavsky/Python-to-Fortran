import numpy as np
from scipy.special import gammaln


def logit(x):
    """Log-odds transform of x in (0, 1)."""
    return np.log(x / (1.0 - x))


def nagarch_variance(r, mu, omega, alpha, theta, beta):
    """Recover the NAGARCH(1,1) conditional variance path for returns r, or None if invalid."""
    n = len(r)
    h = np.empty(n)

    denom = 1.0 - beta - alpha * (1.0 + theta**2)

    if denom <= 0.0:
        return None

    h[0] = omega / denom

    if h[0] <= 0.0 or not np.isfinite(h[0]):
        return None

    for t in range(1, n):
        shock = r[t - 1] - mu

        h[t] = (
            omega
            + alpha * (shock - theta * np.sqrt(h[t - 1]))**2
            + beta * h[t - 1]
        )

        if h[t] <= 0.0 or not np.isfinite(h[t]):
            return None

    return h


def neg_loglik(params, r):
    """Negative log-likelihood of the NAGARCH(1,1)-t model given transformed params."""
    mu, log_omega, logit_alpha, theta, logit_beta, log_dof_m2 = params

    omega = np.exp(log_omega)
    alpha = 1.0 / (1.0 + np.exp(-logit_alpha))
    beta = 1.0 / (1.0 + np.exp(-logit_beta))
    dof = 2.0 + np.exp(log_dof_m2)

    persistence = beta + alpha * (1.0 + theta**2)

    if persistence >= 0.9999:
        return 1.0e12

    h = nagarch_variance(
        r, mu, omega, alpha, theta, beta
    )

    if h is None:
        return 1.0e12

    resid = r - mu
    z = resid / np.sqrt(h)

    ll = np.sum(
        gammaln(0.5 * (dof + 1.0))
        - gammaln(0.5 * dof)
        - 0.5 * np.log(np.pi * (dof - 2.0))
        - 0.5 * np.log(h)
        - 0.5 * (dof + 1.0) * np.log(1.0 + z**2 / (dof - 2.0))
    )

    return -ll


def neg_loglik_fixed_dof(params, r, dof):
    """Negative log-likelihood of the NAGARCH(1,1)-t model given transformed params, with dof held fixed."""
    mu, log_omega, logit_alpha, theta, logit_beta = params

    omega = np.exp(log_omega)
    alpha = 1.0 / (1.0 + np.exp(-logit_alpha))
    beta = 1.0 / (1.0 + np.exp(-logit_beta))

    persistence = beta + alpha * (1.0 + theta**2)

    if persistence >= 0.9999:
        return 1.0e12

    h = nagarch_variance(
        r, mu, omega, alpha, theta, beta
    )

    if h is None:
        return 1.0e12

    resid = r - mu
    z = resid / np.sqrt(h)

    ll = np.sum(
        gammaln(0.5 * (dof + 1.0))
        - gammaln(0.5 * dof)
        - 0.5 * np.log(np.pi * (dof - 2.0))
        - 0.5 * np.log(h)
        - 0.5 * (dof + 1.0) * np.log(1.0 + z**2 / (dof - 2.0))
    )

    return -ll
