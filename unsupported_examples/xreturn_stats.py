import sys

import numpy as np
import pandas as pd

# -----------------------------
# User settings
# -----------------------------

price_file = "asset_class_etf_prices.csv"
scale_ret = 100

# Optional price date range.
# Use None to leave an endpoint unrestricted.
date_min = pd.Timestamp("2010-01-01")  # None
date_max = pd.Timestamp("2024-12-31")  # None

# Maximum number of asset columns to read.
# Set max_assets <= 0 to read all assets.
max_assets = 10**6
maxit = 2000
print_each_fit = True


def stop(msg):
    sys.exit("Error: " + msg)


# -----------------------------
# Read prices
# -----------------------------

dat = pd.read_csv(price_file)

if "Date" not in dat.columns:
    stop("The input file must have a Date column.")

dates = pd.to_datetime(dat["Date"], errors="coerce")

if dates.isna().any():
    stop("Some entries in the Date column could not be converted to Date.")

# Apply optional date range to prices before computing returns.
use_date = pd.Series(True, index=dat.index)

if date_min is not None:
    use_date = use_date & (dates >= date_min)

if date_max is not None:
    use_date = use_date & (dates <= date_max)

dat = dat[use_date].reset_index(drop=True)
dates = dates[use_date].reset_index(drop=True)

if len(dat) < 2:
    stop("Fewer than 2 price observations remain after applying date_min/date_max.")

all_price_names = [c for c in dat.columns if c != "Date"]

if len(all_price_names) == 0:
    stop("No asset price columns found.")

if max_assets > 0:
    nread = min(max_assets, len(all_price_names))
    price_names = all_price_names[:nread]
else:
    price_names = all_price_names

prices = dat[price_names].to_numpy(dtype=float)

if np.any(prices <= 0):
    stop("Prices must be positive to compute log returns.")

print("\nPrice file:", price_file)
print("date_min:", "none" if date_min is None else str(date_min.date()))
print("date_max:", "none" if date_max is None else str(date_max.date()))

print("\nAsset columns available:", len(all_price_names))
print("Asset columns read     :", len(price_names))
print("Assets read:")
print(price_names)

print("\nFirst price date:", str(dates.iloc[0].date()))
print("Last price date :", str(dates.iloc[-1].date()))

# -----------------------------
# Compute scaled log returns
# -----------------------------

ret_dates = dates.iloc[1:].reset_index(drop=True)
rets = scale_ret * np.diff(np.log(prices), axis=0)

good = ~np.isnan(rets).any(axis=1)

rets = rets[good, :]
ret_dates = ret_dates[good].reset_index(drop=True)

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
