# TRANSLATION NOTES: heavily simplified. The original is a multi-file CLI
# that validates several continuous-futures daily files (duplicate/gap/
# non-monotonic date detection, a string "Contract" column tracked through
# `.shift()`/change-counting, `pd.Series`/`pd.DataFrame` summary rows, a
# cross-symbol correlation matrix via `pd.concat` + `.corr()`, CSV output)
# -- almost none of that is supported: `.idxmin()`/`.idxmax()`,
# `.strftime()`, string-typed DataFrame columns, building/writing new
# DataFrames, and the datetime-diff-based gap/monotonicity checks (which
# need the "date" column or datetime-index fields, neither accessible
# post-read; see io_intraday.py's and xtime_boundary_effects.py's notes).
# What's kept is the actual statistical summary of daily log returns --
# annualized mean/std, and the min/max return with its position -- rewritten
# as plain array loops, which covers this script's numeric core. Also
# note: `math.sqrt(TRADING_DAYS)` (an int constant passed directly, with
# no arithmetic on it first) fails to compile -- Fortran's sqrt() intrinsic
# doesn't auto-promote an integer argument the way `*`/`/` do -- so it
# needs an explicit float(TRADING_DAYS) here.
import math

import pandas as pd

TRADING_DAYS = 252


def log_returns(close):
    n = len(close)
    out = [0.0] * (n - 1)
    for i in range(n - 1):
        out[i] = math.log(close[i + 1] / close[i])
    return out


def mean_std(values):
    n = len(values)
    total = 0.0
    for i in range(n):
        total = total + values[i]
    avg = total / n
    ssq = 0.0
    for i in range(n):
        d = values[i] - avg
        ssq = ssq + d * d
    std = math.sqrt(ssq / (n - 1))
    return avg, std


def argmin_argmax(values):
    n = len(values)
    imin = 0
    imax = 0
    for i in range(1, n):
        if values[i] < values[imin]:
            imin = i
        if values[i] > values[imax]:
            imax = i
    return imin, imax


def main():
    df = pd.read_csv("asset_class_etf_prices.csv", parse_dates=["Date"], index_col="Date")
    close = list(df["SPY"])

    returns = log_returns(close)
    mean_ret, std_ret = mean_std(returns)
    annualized_mean = mean_ret * TRADING_DAYS
    annualized_vol = std_ret * math.sqrt(float(TRADING_DAYS))
    imin, imax = argmin_argmax(returns)

    large_threshold = 0.05
    n_large = 0
    for i in range(len(returns)):
        if abs(returns[i]) > large_threshold:
            n_large = n_large + 1

    print("n_rows:", len(close))
    print("n_returns:", len(returns))
    print("annualized_mean_return:", annualized_mean)
    print("annualized_return_volatility:", annualized_vol)
    print("return_min:", returns[imin], "at row", imin)
    print("return_max:", returns[imax], "at row", imax)
    print("large_return_count:", n_large)


if __name__ == "__main__":
    main()
