import numpy as np
import pandas as pd


def multivariate_normal_logpdf(x, mean, covariance):
    """Multivariate normal log density for every row of x."""
    dimension = x.shape[1]
    centered = x - mean
    sign, log_determinant = np.linalg.slogdet(covariance)

    if sign <= 0:
        raise ValueError("covariance matrix must be positive definite")

    solved = np.linalg.solve(covariance, centered.T).T
    mahalanobis = np.sum(centered * solved, axis=1)

    return -0.5 * (
        dimension * np.log(2.0 * np.pi)
        + log_determinant
        + mahalanobis
    )


def simulate_normal_mixture(n, weights, means, covariances, rng):
    """Simulate observations from a multivariate normal mixture."""
    n_components = len(weights)
    dimension = means.shape[1]

    component = rng.choice(
        n_components,
        size=n,
        p=weights
    )

    x = np.empty((n, dimension))

    for j in range(n_components):
        selected = component == j
        count = np.sum(selected)

        if count > 0:
            x[selected, :] = rng.multivariate_normal(
                mean=means[j, :],
                cov=covariances[j, :, :],
                size=count
            )

    return x, component


def fit_normal_mixture(
    x,
    n_components,
    max_iter=1000,
    tol=1.0e-8,
    min_covar=1.0e-6,
    rng=None
):
    """
    Fit a multivariate mixture of normals using EM.

    Returns
    -------
    weights     : ndarray, shape (n_components,)
    means       : ndarray, shape (n_components, dimension)
    covariances : ndarray, shape (n_components, dimension, dimension)
    loglik      : float
    n_iter      : int
    """
    x = np.asarray(x, dtype=float)
    n, dimension = x.shape

    if rng is None:
        rng = np.random.default_rng()

    # Initialize means with observations spread across the first coordinate.
    order = np.argsort(x[:, 0])
    positions = np.linspace(
        0,
        n - 1,
        n_components + 2
    )[1:-1]
    positions = positions.astype(int)
    means = x[order[positions], :].copy()

    weights = np.full(
        n_components,
        1.0 / n_components
    )

    sample_covariance = np.cov(
        x,
        rowvar=False,
        ddof=1
    )

    covariances = np.empty(
        (n_components, dimension, dimension)
    )

    for j in range(n_components):
        covariances[j, :, :] = sample_covariance

    identity = np.eye(dimension)
    old_loglik = -np.inf

    for iteration in range(1, max_iter + 1):

        # E step, evaluated on the log scale for numerical stability.
        log_weighted_density = np.empty(
            (n, n_components)
        )

        for j in range(n_components):
            log_weighted_density[:, j] = (
                np.log(weights[j])
                + multivariate_normal_logpdf(
                    x,
                    means[j, :],
                    covariances[j, :, :]
                )
            )

        row_maximum = np.max(
            log_weighted_density,
            axis=1,
            keepdims=True
        )

        scaled_density = np.exp(
            log_weighted_density - row_maximum
        )

        scaled_sum = np.sum(
            scaled_density,
            axis=1,
            keepdims=True
        )

        responsibility = scaled_density / scaled_sum

        loglik = np.sum(
            row_maximum[:, 0]
            + np.log(scaled_sum[:, 0])
        )

        # M step.
        nk = np.sum(responsibility, axis=0)
        weights = nk / n
        means = (responsibility.T @ x) / nk[:, None]

        for j in range(n_components):
            centered = x - means[j, :]
            weighted_centered = (
                responsibility[:, j, None]
                * centered
            )

            covariances[j, :, :] = (
                weighted_centered.T @ centered
            ) / nk[j]

            covariances[j, :, :] = (
                covariances[j, :, :]
                + min_covar * identity
            )

        # Convergence.
        if np.abs(loglik - old_loglik) < tol:
            break

        old_loglik = loglik

    return weights, means, covariances, loglik, iteration


def parameter_dataframe(weights, means, covariances):
    """Collect two-dimensional mixture parameters in a table."""
    n_components = len(weights)
    index = [
        f"component_{j + 1}"
        for j in range(n_components)
    ]

    return pd.DataFrame(
        {
            "weight": weights,
            "mean_1": means[:, 0],
            "mean_2": means[:, 1],
            "cov_11": covariances[:, 0, 0],
            "cov_12": covariances[:, 0, 1],
            "cov_22": covariances[:, 1, 1]
        },
        index=index
    )


# ============================================================
# Example
# ============================================================

rng = np.random.default_rng(12345)

nobs = 10**5
print("#obs:", nobs)

true_weights = np.array([
    0.20,
    0.50,
    0.30
])

true_means = np.array([
    [-3.0, -2.0],
    [0.5, 1.0],
    [4.0, -1.0]
])

true_covariances = np.array([
    [
        [0.64, 0.20],
        [0.20, 1.00]
    ],
    [
        [1.44, -0.35],
        [-0.35, 0.81]
    ],
    [
        [0.36, 0.12],
        [0.12, 0.64]
    ]
])

n_components = len(true_weights)


# ------------------------------------------------------------
# Simulate data
# ------------------------------------------------------------

x, component = simulate_normal_mixture(
    n=nobs,
    weights=true_weights,
    means=true_means,
    covariances=true_covariances,
    rng=rng
)


# ------------------------------------------------------------
# Fit mixture
# ------------------------------------------------------------

fit_weights, fit_means, fit_covariances, loglik, n_iter = (
    fit_normal_mixture(
        x=x,
        n_components=n_components,
        rng=rng
    )
)


# ------------------------------------------------------------
# Sort components by their first mean coordinate.
# ------------------------------------------------------------

true_order = np.argsort(true_means[:, 0])
fit_order = np.argsort(fit_means[:, 0])

true_weights = true_weights[true_order]
true_means = true_means[true_order, :]
true_covariances = true_covariances[true_order, :, :]

fit_weights = fit_weights[fit_order]
fit_means = fit_means[fit_order, :]
fit_covariances = fit_covariances[fit_order, :, :]


# ------------------------------------------------------------
# Results
# ------------------------------------------------------------

true_df = parameter_dataframe(
    true_weights,
    true_means,
    true_covariances
)

fit_df = parameter_dataframe(
    fit_weights,
    fit_means,
    fit_covariances
)

diff_df = true_df - fit_df

print("True parameters")
print(true_df.to_string())

print("\nFitted parameters")
print(fit_df.to_string())

print("\nTrue - fitted")
print(diff_df.to_string())

print(f"\nLog likelihood = {loglik:.6f}")
print(f"EM iterations  = {n_iter}")
