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

    # Initial values:
    # means from evenly spaced sample quantiles
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

        # ----------------------------------------------------
        # E step
        # ----------------------------------------------------

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

        # Avoid division by zero
        row_sum = np.maximum(
            row_sum,
            np.finfo(float).tiny
        )

        responsibility = (
            weighted_density / row_sum
        )

        loglik = np.sum(
            np.log(row_sum[:, 0])
        )

        # ----------------------------------------------------
        # M step
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Convergence
        # ----------------------------------------------------

        if np.abs(loglik - old_loglik) < tol:
            break

        old_loglik = loglik

    return weights, means, sds, loglik, iteration


# ============================================================
# Example
# ============================================================

rng = np.random.default_rng(12345)

nobs = 10000

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

n_components = len(true_weights)


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
# Fit mixture
# ------------------------------------------------------------

fit_weights, fit_means, fit_sds, loglik, n_iter = (
    fit_normal_mixture(
        x=x,
        n_components=n_components,
        rng=rng
    )
)


# ------------------------------------------------------------
# Sort components by mean
#
# Mixture component labels are arbitrary, so sorting by mean
# allows true and fitted components to be compared directly.
# ------------------------------------------------------------

true_order = np.argsort(true_means)
fit_order = np.argsort(fit_means)

true_weights = true_weights[true_order]
true_means = true_means[true_order]
true_sds = true_sds[true_order]

fit_weights = fit_weights[fit_order]
fit_means = fit_means[fit_order]
fit_sds = fit_sds[fit_order]


# ------------------------------------------------------------
# DataFrames
# ------------------------------------------------------------

index = [
    f"component_{j + 1}"
    for j in range(n_components)
]

true_df = pd.DataFrame(
    {
        "weight": true_weights,
        "mean": true_means,
        "sd": true_sds
    },
    index=index
)

fit_df = pd.DataFrame(
    {
        "weight": fit_weights,
        "mean": fit_means,
        "sd": fit_sds
    },
    index=index
)

diff_df = true_df - fit_df


# ------------------------------------------------------------
# Combined comparison DataFrame
# ------------------------------------------------------------

comparison_df = pd.concat(
    {
        "true": true_df,
        "fit": fit_df,
        "true_minus_fit": diff_df
    },
    axis=1
)


# ------------------------------------------------------------
# Results
# ------------------------------------------------------------

print("True parameters")
print(true_df)

print("\nFitted parameters")
print(fit_df)

print("\nTrue - fitted")
print(diff_df)

print("\nCombined comparison")
print(comparison_df)

print(f"\nLog likelihood = {loglik:.6f}")
print(f"EM iterations  = {n_iter}")
