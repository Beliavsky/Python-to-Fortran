import time
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from nagarch_t_model import logit, nagarch_variance, neg_loglik, neg_loglik_fixed_dof

# Branch of xfit_nagarch_t.py: reads a single asset's prices (SPY) into a
# pd.Series instead of pulling every asset column into a DataFrame/matrix,
# so the resulting fit can be compared directly against the SPY row of
# xfit_nagarch_t.py's DataFrame-based output -- a check that xp2f's
# pd.Series translation is comparable to its pd.DataFrame translation.

# Use the tracked common fixture; select only SPY below.
price_file = "asset_class_etf_prices.csv"
scale_ret = 100
fixed_dof = 0.0  # <= 0 means fit dof along with the other parameters; set positive to hold dof fixed at this value

dat = pd.read_csv(price_file)
dates = pd.to_datetime(dat["Date"], errors="coerce")
prices = pd.Series(dat["SPY"])

print("\nPrice file:", price_file)
print("Asset: SPY")

print("\nFirst price date:", str(dates.iloc[0].date()))
print("Last price date :", str(dates.iloc[-1].date()))

# -----------------------------
# Compute scaled log returns
# -----------------------------

ret_dates = dates.iloc[1:].reset_index(drop=True)
log_prices = np.log(prices)
rets = pd.Series(scale_ret * np.diff(log_prices))

print("\nNumber of price observations:", len(prices))
print("Number of return observations:", len(rets))
print("First return date:", str(ret_dates.iloc[0].date()))
print("Last return date :", str(ret_dates.iloc[-1].date()))

# -----------------------------
# Fit NAGARCH(1,1)-t to SPY's return series
# -----------------------------

overall_start = time.perf_counter()

r = rets

if fixed_dof > 0.0:
    x0 = np.array([
        np.mean(r),
        np.log(np.var(r)),
        logit(0.05),
        0.3,
        logit(0.85)
    ])

    result = minimize(
        neg_loglik_fixed_dof,
        x0,
        args=(r, fixed_dof),
        method="L-BFGS-B",
        bounds=[
            (-1.0, 1.0),
            (-30.0, 5.0),
            (-30.0, 30.0),
            (-5.0, 5.0),
            (-30.0, 30.0)
        ]
    )

    dof_hat = fixed_dof
else:
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

    dof_hat = 2.0 + np.exp(result.x[5])

mu_hat = result.x[0]
omega_hat = np.exp(result.x[1])
alpha_hat = 1.0 / (1.0 + np.exp(-result.x[2]))
theta_hat = result.x[3]
beta_hat = 1.0 / (1.0 + np.exp(-result.x[4]))
success = result.success

overall_end = time.perf_counter()

# -----------------------------
# Results
# -----------------------------

print("\nNAGARCH(1,1)-t fit, returns scaled by scale_ret =", scale_ret)
if fixed_dof > 0.0:
    print("dof held fixed at:", fixed_dof)
else:
    print("dof fitted")
print()
print(f"{'asset':10s} {'mu':>12s} {'omega':>12s} {'alpha':>12s} {'theta':>12s} {'beta':>12s} {'dof':>10s} {'persist':>12s} {'ok':>5s}")
print("-" * 92)
persistence = beta_hat + alpha_hat * (1.0 + theta_hat**2)
print(
    f"{'SPY':10s} {mu_hat:12.6g} {omega_hat:12.6g} "
    f"{alpha_hat:12.6g} {theta_hat:12.6g} {beta_hat:12.6g} "
    f"{dof_hat:10.4g} {persistence:12.6g} {str(success):>5s}"
)

fitting_time = overall_end - overall_start

print()
print("Timing")
print("-" * 40)
print(f"Fitting SPY: {fitting_time:.6f} seconds")
