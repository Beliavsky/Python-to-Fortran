import numpy as np
import pandas as pd

price_file = "asset_class_etf_prices.csv"
scale_ret = 100

dat = pd.read_csv(price_file)
dates = pd.to_datetime(dat["Date"], errors="coerce")

price_names = [c for c in dat.columns if c != "Date"]
prices = dat[price_names].to_numpy(dtype=float)

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
# Return statistics
# -----------------------------


def return_stats(x):
    return {
        "mean": np.mean(x),
        "sd": np.std(x, ddof=1),
        "min": np.min(x),
        "max": np.max(x),
    }


stats = pd.DataFrame(
    [return_stats(rets[:, j]) for j in range(rets.shape[1])],
    index=price_names,
)

print("\nReturn statistics, scaled by scale_ret =", scale_ret)
print(stats.round(6))
