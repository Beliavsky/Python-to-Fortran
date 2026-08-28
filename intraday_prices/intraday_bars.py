# TRANSLATION NOTES: the original resample_intraday_bars() groups rows by
# calendar date, then uses pandas' `.resample(freq, origin="start_day", ...)`
# with a dict-based `.agg({...})` (a different aggregator per column) and
# `pd.concat` to stitch the per-day results back together. None of
# groupby/resample/dict-agg/concat, or reading a datetime index's own
# hour/minute fields, or building a fresh DataFrame from computed arrays,
# are in xp2f.py's supported subset (only reading a DataFrame via
# `pd.read_csv` is well supported; datetime index elements are opaque
# outside of `.iloc`/printing). Rewritten as fixed-row-count bucketing
# (aggregate every `bars_per_bucket` consecutive rows into one bar) on
# plain 1-D arrays instead of pandas' calendar-time resampling on a
# DataFrame -- the OHLCV aggregation itself (Open=first, High=max, Low=min,
# Close=last, Volume=sum) is unchanged, only how bars are grouped and how
# the result is represented (parallel output arrays, not a DataFrame).
import pandas as pd


def resample_ohlcv_bars(open_, high, low, close, volume, bars_per_bucket):
    """Aggregate every `bars_per_bucket` consecutive rows into one OHLCV
    bar: Open=first, High=max, Low=min, Close=last, Volume=sum. Trailing
    rows that don't fill a whole bucket are dropped (matches pandas
    resample() dropping an incomplete final bin when there is no data to
    fill it)."""
    n = len(open_)
    n_out = n // bars_per_bucket
    out_open = [0.0] * n_out
    out_high = [0.0] * n_out
    out_low = [0.0] * n_out
    out_close = [0.0] * n_out
    out_volume = [0.0] * n_out
    for k in range(n_out):
        lo = k * bars_per_bucket
        hi = lo + bars_per_bucket
        out_open[k] = open_[lo]
        out_high[k] = max(high[lo:hi])
        out_low[k] = min(low[lo:hi])
        out_close[k] = close[hi - 1]
        out_volume[k] = sum(volume[lo:hi])
    return out_open, out_high, out_low, out_close, out_volume


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    open_ = list(df["Open"])
    high = list(df["High"])
    low = list(df["Low"])
    close = list(df["Close"])
    volume = list(df["Volume"])

    bars_per_bucket = 3
    out_open, out_high, out_low, out_close, out_volume = resample_ohlcv_bars(
        open_, high, low, close, volume, bars_per_bucket
    )
    n_out = len(out_open)
    print("resampled bars:", n_out)
    for k in range(min(5, n_out)):
        print(out_open[k], out_high[k], out_low[k], out_close[k], out_volume[k])


if __name__ == "__main__":
    main()
