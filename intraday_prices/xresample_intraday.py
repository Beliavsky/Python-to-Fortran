# TRANSLATION NOTES: heavily simplified. The original is a multi-file CLI
# (argparse, glob/symbol-template file resolution via file_utils, per-file
# output path derivation, `frame.to_csv(...)` writing) wrapped around two
# aggregation paths: `resample_intraday_bars` (calendar-time resampling,
# already simplified in intraday_bars.py's own notes) and `daily_ohlcv`
# (a `.groupby("date").agg(Datetime=("Datetime","first"), ...)` collapsing
# each day to one bar). groupby+multi-output-.agg, building/writing a new
# DataFrame, and pathlib are all unsupported. Kept: a small demo that reads
# one fixed file and calls intraday_bars.resample_ohlcv_bars's fixed-row-
# count bucketing (copied in rather than imported, since cross-file imports
# aren't supported -- see the top-level conversation about that). Argparse,
# multi-file resolution, output writing, and day-collapsing daily_ohlcv are
# all dropped.
import pandas as pd


def resample_ohlcv_bars(open_, high, low, close, volume, bars_per_bucket):
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

    bars_per_bucket = 12
    out_open, out_high, out_low, out_close, out_volume = resample_ohlcv_bars(
        open_, high, low, close, volume, bars_per_bucket
    )
    n_out = len(out_open)
    print("input rows:", len(open_))
    print("output rows:", n_out)
    for k in range(5):
        print(out_open[k], out_high[k], out_low[k], out_close[k], out_volume[k])


if __name__ == "__main__":
    main()
