# TRANSLATION NOTES: heavily simplified. The original relies on
# groupby/diff/dropna/drop_duplicates, `.dt.total_seconds()` on datetime
# differences, `pd.Series`/`pd.concat` with a dict of per-asset series for
# cross-asset alignment, and `pathlib.Path` for labeling -- none of that is
# in xp2f.py's supported subset. Also dropped: `infer_bar_interval_minutes`/
# `steps_for_horizon`, which exist only to convert a "horizon in minutes"
# into a bar count from inferred spacing; a translated caller just passes
# the bar count (`step`) directly, as intraday_bars.py's bucket count is
# also hardcoded rather than inferred. And `cross_asset_returns` (aligning
# several different assets' return series via an inner join) is dropped
# entirely -- it needs a dict-of-Series and a multi-key join, neither
# supported, and everything else in this project already works with one
# asset's prices at a time. What's kept -- close-to-close log returns over
# a fixed bar step, and day-over-day log returns from daily closes -- is
# rewritten as plain array loops. One behavior change: the original only
# diffs *within* a trading day (via groupby("date")), skipping the return
# that would span the last bar of one day into the first bar of the next;
# the translated version does not skip day boundaries, since the "date"
# column needed to detect them is a non-numeric CSV column that xp2f.py's
# read_csv silently drops (see io_intraday.py's own notes).
import math

import pandas as pd


def asset_label(filename):
    """Return a compact asset label inferred from a price file name."""
    label = filename
    if "." in label:
        label = label[: label.index(".")]
    if label[-3:].lower() == ".us":
        label = label[:-3]
    return label.upper()


def log_returns_over_step(close, step):
    """Close-to-close log returns over `step` input bars."""
    n = len(close)
    n_out = n - step
    out = [0.0] * n_out
    for k in range(n_out):
        out[k] = math.log(close[k + step]) - math.log(close[k])
    return out


def daily_close_returns(daily_close):
    """Day-over-day log returns from one closing price per day."""
    n = len(daily_close)
    out = [0.0] * (n - 1)
    for k in range(n - 1):
        out[k] = math.log(daily_close[k + 1]) - math.log(daily_close[k])
    return out


def main():
    print("asset_label:", asset_label("SPY.US.csv"))

    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    close = list(df["Close"])

    step = 3
    intraday_ret = log_returns_over_step(close, step)
    print("intraday log returns (step =", step, "):", len(intraday_ret))
    for k in range(5):
        print(intraday_ret[k])

    daily_close = close[::500]
    day_ret = daily_close_returns(daily_close)
    print("daily log returns:", len(day_ret))
    for k in range(5):
        print(day_ret[k])


if __name__ == "__main__":
    main()
