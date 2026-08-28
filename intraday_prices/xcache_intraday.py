# TRANSLATION NOTES: heavily simplified. The original's actual job is
# writing a normalized Parquet/pickle cache file per symbol plus a CSV
# manifest DataFrame (rows/days/bar-interval/first-last timestamp per
# symbol) -- `.to_parquet`/`.to_pickle`, building a manifest via
# `pd.DataFrame(rows)`, and file/glob/CLI resolution are all unsupported
# (see file_utils.py's and intraday_returns.py's own notes; Parquet/pickle
# I/O in particular has no Fortran equivalent at all). What's kept is a
# small per-file numeric summary (row count, min/max close) across a fixed
# list of files, which is the only genuinely computational part of what a
# manifest row reports -- everything about the caching itself is dropped.
# Both sample files are date-only (not intraday) for the same reason noted
# in xread_prices.py: date-vs-datetime index detection can't see through a
# `FILES[i]` runtime subscript, so a datetime-indexed file would wrongly
# get the date-only type and fail at runtime.
import pandas as pd

FILES = ["sample_daily_prices.csv", "sample_daily_prices2.csv"]


def summarize_prices(close):
    n = len(close)
    return n, min(close), max(close)


def main():
    n_files = len(FILES)
    for i in range(n_files):
        df = pd.read_csv(FILES[i])
        close = list(df["Close"])
        n_rows, lo, hi = summarize_prices(close)
        print(FILES[i], n_rows, lo, hi)


if __name__ == "__main__":
    main()
