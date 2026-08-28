# TRANSLATION NOTES: dropped argparse (hardcoded a fixed list of input
# files instead of a directory + glob pattern + --limit/--combine flags),
# and file_utils.expand_file_patterns()/pathlib.Path along with it, per
# file_utils.py's own notes. Also dropped the --combine path
# (pd.concat of several frames plus a computed "symbol" column from
# path.stem) since it needs pd.concat and Path, neither supported; only
# the always-available row-counting benchmark is kept. Also note:
# `for path in FILES:` (iterating a list of strings directly) isn't
# supported either -- xp2f.py only supports `for i in range(...)` /
# `for x in sorted(...)` loops, so this indexes FILES by position instead.
# One more limitation surfaced here: date-vs-datetime index detection
# (see xp2f.py's _detect_pandas_index_kind) only works when the CSV path
# passed to pd.read_csv is statically resolvable to a literal string --
# `FILES[i]` (a runtime subscript) isn't, so it silently falls back to the
# date-only type, which then fails at runtime against a datetime-indexed
# file. Sidestepped here by using two date-only (not intraday) sample
# files, since this benchmark only cares about row counts.
"""Benchmark reading intraday price CSV files."""

import time

import pandas as pd

FILES = ["sample_daily_prices.csv", "asset_class_etf_prices.csv"]


def main():
    t0 = time.perf_counter()
    rows = 0
    n_files = len(FILES)
    for i in range(n_files):
        df = pd.read_csv(FILES[i])
        rows = rows + df.shape[0]
    elapsed = time.perf_counter() - t0

    print("files:", n_files)
    print("rows:", rows)
    print("avg rows/file:", rows / n_files)
    print("elapsed seconds:", elapsed)


if __name__ == "__main__":
    main()
