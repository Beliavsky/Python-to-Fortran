import numpy as np
import pandas as pd


def normal_pdf(x, mean, sd):
    """Univariate normal density."""
    z = (x - mean) / sd
    return np.exp(-0.5 * z**2) / (np.sqrt(2.0 * np.pi) * sd)


def simulate_normal_mixture(n, weights, means, sds, rng):
    """Simulate observations from a univariate normal mixture."""
    k = len(weights)

    component = rng.choice(k, size=n, p=weights)
    x = rng.normal(
        loc=means[component],
        scale=sds[component],
        size=n
    )

    return x, component


def fit_normal_mixture(
    x,
    n_components,
    max_iter=1000,
    tol=1.0e-8,
    min_sd=1.0e-6,
    rng=None
):
    """
    Fit a univariate mixture of normals using EM.

    Returns
    -------
    weights : ndarray
    means   : ndarray
    sds     : ndarray
    loglik  : float
    n_iter  : int
    """
    x = np.asarray(x, dtype=float)
    n = len(x)

    if rng is None:
        rng = np.random.default_rng()

    # Initial values: means from evenly spaced sample quantiles.
    probs = np.linspace(
        0.0,
        1.0,
        n_components + 2
    )[1:-1]

    means = np.quantile(x, probs)

    weights = np.full(
        n_components,
        1.0 / n_components
    )

    sds = np.full(
        n_components,
        np.std(x, ddof=1)
    )

    old_loglik = -np.inf

    for iteration in range(1, max_iter + 1):

        # E step
        weighted_density = np.empty(
            (n, n_components)
        )

        for j in range(n_components):
            weighted_density[:, j] = (
                weights[j]
                * normal_pdf(
                    x,
                    means[j],
                    sds[j]
                )
            )

        row_sum = weighted_density.sum(
            axis=1,
            keepdims=True
        )

        # Avoid division by zero.
        row_sum = np.maximum(
            row_sum,
            np.finfo(float).tiny
        )

        responsibility = weighted_density / row_sum

        loglik = np.sum(
            np.log(row_sum[:, 0])
        )

        # M step
        nk = responsibility.sum(axis=0)

        weights = nk / n

        means = (
            responsibility.T @ x
        ) / nk

        for j in range(n_components):
            variance = np.sum(
                responsibility[:, j]
                * (x - means[j])**2
            ) / nk[j]

            sds[j] = np.sqrt(
                max(variance, min_sd**2)
            )

        # Convergence
        if np.abs(loglik - old_loglik) < tol:
            break

        old_loglik = loglik

    return weights, means, sds, loglik, iteration


def information_criteria(loglik, nobs, n_components):
    """Return AIC and BIC for a univariate normal mixture."""
    # m-1 independent weights, m means, and m standard deviations.
    n_parameters = 3 * n_components - 1
    aic = -2.0 * loglik + 2.0 * n_parameters
    bic = -2.0 * loglik + np.log(nobs) * n_parameters
    return n_parameters, aic, bic


# ============================================================
# Example
# ============================================================

rng = np.random.default_rng(12345)

nobs = 10000
print("#obs:", nobs)

true_weights = np.array([
    0.20,
    0.50,
    0.30
])

true_means = np.array([
    -3.0,
    0.5,
    4.0
])

true_sds = np.array([
    0.8,
    1.2,
    0.6
])

k = len(true_weights)


# ------------------------------------------------------------
# Simulate data
# ------------------------------------------------------------

x, component = simulate_normal_mixture(
    n=nobs,
    weights=true_weights,
    means=true_means,
    sds=true_sds,
    rng=rng
)


# ------------------------------------------------------------
# Fit mixtures with 1 through k + 2 components
# ------------------------------------------------------------

rows = []

for n_components in range(1, k + 3):
    fit_weights, fit_means, fit_sds, loglik, n_iter = (
        fit_normal_mixture(
            x=x,
            n_components=n_components,
            rng=rng
        )
    )

    n_parameters, aic, bic = information_criteria(
        loglik=loglik,
        nobs=nobs,
        n_components=n_components
    )

    rows.append(
        {
            "n_components": n_components,
            "n_parameters": n_parameters,
            "log_likelihood": loglik,
            "aic": aic,
            "bic": bic,
            "em_iterations": n_iter
        }
    )


ic_df = pd.DataFrame(rows).set_index("n_components")

aic_choice = int(ic_df["aic"].idxmin())
bic_choice = int(ic_df["bic"].idxmin())


# ------------------------------------------------------------
# Results
# ------------------------------------------------------------

print(f"True number of components: {k}")
print("\nInformation criteria")
print(ic_df.to_string())

print(f"\nNumber of components chosen by AIC: {aic_choice}")
print(f"Number of components chosen by BIC: {bic_choice}")
