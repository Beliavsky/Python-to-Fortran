import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from nagarch_t_model import logit, nagarch_variance, neg_loglik

price_file = "asset_class_etf_prices.csv"
scale_ret = 100
max_assets = 2  # 0 (or negative) means no limit; set positive to limit the number of asset columns read

dat = pd.read_csv(price_file)
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
# Fit NAGARCH(1,1)-t to each asset's return series
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

    mu_hat[j] = result.x[0]
    omega_hat[j] = np.exp(result.x[1])
    alpha_hat[j] = 1.0 / (1.0 + np.exp(-result.x[2]))
    theta_hat[j] = result.x[3]
    beta_hat[j] = 1.0 / (1.0 + np.exp(-result.x[4]))
    dof_hat[j] = 2.0 + np.exp(result.x[5])
    success[j] = result.success

overall_end = time.perf_counter()

# -----------------------------
# Results
# -----------------------------

print("\nNAGARCH(1,1)-t fits, returns scaled by scale_ret =", scale_ret)
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

fitting_time = overall_end - overall_start

print()
print("Timing")
print("-" * 40)
print(f"Fitting all assets: {fitting_time:.6f} seconds")
