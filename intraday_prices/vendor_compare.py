# TRANSLATION NOTES: heavily simplified. The original's entire job is
# comparing two vendors' price histories: aligning them by timestamp via
# `.merge(..., how="inner")`, grouping by date via `.groupby("date").agg(...)`
# with lambda aggregators, dict comprehensions building a dict[str, DataFrame]
# per horizon, and `.rename(columns={...})`/`pd.concat(axis=1)`. None of
# merge, groupby+agg, or dict-of-DataFrames are in xp2f.py's supported
# subset. Since the alignment step (`align_bars`/`.merge`) can't be
# translated at all, everything downstream that depends on its output
# (compare_bars, compare_intraday_returns, realized_vol_by_day,
# compare_realized_vol, compare_realized_vol_horizons, resample_pair) is
# dropped too -- there would be nothing left to feed them.
#
# What's kept are the two genuinely reusable numeric formulas, rewritten to
# operate on plain arrays that the CALLER is assumed to have already
# aligned by timestamp (alignment itself is out of scope, as above):
# basis-point price differences between two vendors' OHLC arrays, and
# realized volatility from an array of log returns.
import math

import pandas as pd


def price_diff_bp(left, right):
    """Basis-point differences between two already-aligned price arrays."""
    n = len(left)
    out = [0.0] * n
    for i in range(n):
        avg = (abs(left[i]) + abs(right[i])) / 2.0
        out[i] = 10000.0 * (left[i] - right[i]) / avg
    return out


def realized_vol(returns, trading_days, annualize):
    """Realized volatility (sqrt of summed squared returns), optionally
    annualized by scaling the variance by trading_days."""
    n = len(returns)
    ssq = 0.0
    for i in range(n):
        ssq = ssq + returns[i] * returns[i]
    scale = trading_days if annualize else 1.0
    return math.sqrt(scale * ssq)


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    close = list(df["Close"])
    n = len(close)

    left = close[: n - 1]
    right = close[1:]
    diffs = price_diff_bp(left, right)
    print("price_diff_bp[0:5]:")
    for i in range(5):
        print(diffs[i])

    returns = [0.0] * (n - 1)
    for i in range(n - 1):
        returns[i] = math.log(close[i + 1]) - math.log(close[i])
    rv = realized_vol(returns, 252, True)
    print("realized_vol (annualized):", rv)


if __name__ == "__main__":
    main()
