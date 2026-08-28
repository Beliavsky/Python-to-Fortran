# TRANSLATION NOTES: heavily simplified. The original compares realized
# volatility across sampling frequencies and vol estimators (close-to-close,
# open-to-close, Parkinson range-based) over many symbol files, all built on
# `.groupby("date").agg(...)`/`.apply(lambda ...)`, dict-of-DataFrames,
# `pd.concat`, and printed/written summary tables -- none of which are
# supported (see intraday_bars.py's and vendor_compare.py's own notes on
# why groupby/resample/DataFrame-construction aren't portable). Day
# boundaries in particular aren't recoverable post-read (the "date" column
# is dropped as non-numeric), so "one realized-vol number per day, then
# averaged/annualized across days" becomes "one realized-vol number
# treating the whole input series as a single session" -- the same
# simplification intraday_bars.py and vendor_compare.py already make.
#
# What's kept: annualized close-to-close realized vol computed at several
# resampling frequencies (by aggregating a fixed count of input bars per
# bucket, reusing intraday_bars.py's own bucket count in spirit), which is
# the actual "by frequency" comparison this script's name promises.
import math

import pandas as pd

TRADING_DAYS = 252


def resample_last_close(close, bars_per_bucket):
    """One value per bucket: the last Close in each `bars_per_bucket`
    consecutive rows."""
    n = len(close)
    n_out = n // bars_per_bucket
    out = [0.0] * n_out
    for k in range(n_out):
        out[k] = close[(k + 1) * bars_per_bucket - 1]
    return out


def annualized_realized_vol_pct(close, trading_days):
    """Annualized realized volatility (percent) from a close-price series,
    treating the whole series as one session's worth of returns."""
    n = len(close)
    ssq = 0.0
    for i in range(n - 1):
        r = math.log(close[i + 1]) - math.log(close[i])
        ssq = ssq + r * r
    return 100.0 * math.sqrt(trading_days * ssq)


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    close = list(df["Close"])

    bar_minutes = 5
    bucket_counts = [1, 2, 3, 4, 6, 12]
    print("freq_minutes, bars, annualized_vol_pct")
    for i in range(len(bucket_counts)):
        bpb = bucket_counts[i]
        resampled = resample_last_close(close, bpb)
        vol_pct = annualized_realized_vol_pct(resampled, TRADING_DAYS)
        print(bpb * bar_minutes, len(resampled), vol_pct)


if __name__ == "__main__":
    main()
