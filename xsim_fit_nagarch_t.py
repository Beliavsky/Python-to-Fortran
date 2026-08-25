import time
import numpy as np
from scipy.optimize import minimize
from nagarch_t_model import logit, nagarch_variance, neg_loglik

rng = np.random.default_rng(12345)


def simulate_nagarch_t(n, mu, omega, alpha, theta, beta, dof):
    """Simulate n observations from a NAGARCH(1,1) process with standardized Student-t shocks."""
    r = np.empty(n)
    h = np.empty(n)
    scale = np.sqrt((dof - 2.0) / dof)

    denom = 1.0 - beta - alpha * (1.0 + theta**2)
    h[0] = omega / denom
    z0 = rng.standard_t(dof)
    r[0] = mu + np.sqrt(h[0]) * (scale * z0)

    for t in range(1, n):
        shock = r[t - 1] - mu

        h[t] = (
            omega
            + alpha * (shock - theta * np.sqrt(h[t - 1]))**2
            + beta * h[t - 1]
        )

        zt = rng.standard_t(dof)
        r[t] = mu + np.sqrt(h[t]) * (scale * zt)

    return r, h


# --------------------------------------------------
# Overall timer
# --------------------------------------------------

overall_start = time.perf_counter()


# --------------------------------------------------
# True parameters
# --------------------------------------------------

true_mu = 0.0005
true_omega = 0.000002
true_alpha = 0.06
true_theta = 0.7
true_beta = 0.88
true_dof = 6.0

n = 5000
print("#obs:", n)

# --------------------------------------------------
# Simulation
# --------------------------------------------------

sim_start = time.perf_counter()

r, h_true = simulate_nagarch_t(
    n,
    true_mu,
    true_omega,
    true_alpha,
    true_theta,
    true_beta,
    true_dof
)

sim_end = time.perf_counter()


# --------------------------------------------------
# Starting values
# --------------------------------------------------

x0 = np.array([
    np.mean(r),
    np.log(1.0e-6),
    logit(0.05),
    0.3,
    logit(0.85),
    np.log(8.0 - 2.0)
])


# --------------------------------------------------
# Fitting
# --------------------------------------------------

fit_start = time.perf_counter()

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

fit_end = time.perf_counter()


# --------------------------------------------------
# Transform fitted parameters
# --------------------------------------------------

mu_hat, log_omega_hat, la_hat, theta_hat, lb_hat, log_dof_m2_hat = result.x

omega_hat = np.exp(log_omega_hat)
alpha_hat = 1.0 / (1.0 + np.exp(-la_hat))
beta_hat = 1.0 / (1.0 + np.exp(-lb_hat))
dof_hat = 2.0 + np.exp(log_dof_m2_hat)


# --------------------------------------------------
# Results
# --------------------------------------------------

print("Optimization success:", result.success)
print("Message:", result.message)
print()

print(f"{'parameter':10s} {'true':>14s} {'fitted':>14s}")
print("-" * 40)
print(f"{'mu':10s} {true_mu:14.6g} {mu_hat:14.6g}")
print(f"{'omega':10s} {true_omega:14.6g} {omega_hat:14.6g}")
print(f"{'alpha':10s} {true_alpha:14.6g} {alpha_hat:14.6g}")
print(f"{'theta':10s} {true_theta:14.6g} {theta_hat:14.6g}")
print(f"{'beta':10s} {true_beta:14.6g} {beta_hat:14.6g}")
print(f"{'dof':10s} {true_dof:14.6g} {dof_hat:14.6g}")

print()

print(
    "True persistence:  ",
    true_beta + true_alpha * (1.0 + true_theta**2)
)

print(
    "Fitted persistence:",
    beta_hat + alpha_hat * (1.0 + theta_hat**2)
)


# --------------------------------------------------
# Timing
# --------------------------------------------------

overall_end = time.perf_counter()

simulation_time = sim_end - sim_start
fitting_time = fit_end - fit_start
overall_time = overall_end - overall_start

print()
print("Timing")
print("-" * 40)
print(f"Simulation: {simulation_time:.6f} seconds")
print(f"Fitting:    {fitting_time:.6f} seconds")
print(f"Overall:    {overall_time:.6f} seconds")
