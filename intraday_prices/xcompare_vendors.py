# TRANSLATION NOTES: heavily simplified, in the same way as
# vendor_compare.py (its own notes explain why `.merge`/groupby-based
# alignment isn't portable, and why only the two numeric formulas --
# price_diff_bp and realized_vol -- survive as reusable array functions).
# This script is a thin CLI wrapper around those, comparing two vendors'
# price files; batch/directory comparison mode, CSV/report output, and
# --left-file/--right-file argparse handling are all dropped. What's kept
# is calling both vendor_compare kernels (copied in rather than imported)
# on two already-aligned price arrays.
import math

import pandas as pd


def price_diff_bp(left, right):
    n = len(left)
    out = [0.0] * n
    for i in range(n):
        avg = (abs(left[i]) + abs(right[i])) / 2.0
        out[i] = 10000.0 * (left[i] - right[i]) / avg
    return out


def realized_vol(returns, trading_days, annualize):
    n = len(returns)
    ssq = 0.0
    for i in range(n):
        ssq = ssq + returns[i] * returns[i]
    scale = trading_days if annualize else 1.0
    return math.sqrt(scale * ssq)


def main():
    left_df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    right_df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    left_close = list(left_df["Close"])
    right_close = list(right_df["Close"])

    diffs = price_diff_bp(left_close, right_close)
    max_abs_diff_bp = 0.0
    for i in range(len(diffs)):
        if abs(diffs[i]) > max_abs_diff_bp:
            max_abs_diff_bp = abs(diffs[i])
    print("max_abs_diff_bp:", max_abs_diff_bp)

    n = len(left_close)
    left_ret = [0.0] * (n - 1)
    right_ret = [0.0] * (n - 1)
    for i in range(n - 1):
        left_ret[i] = math.log(left_close[i + 1]) - math.log(left_close[i])
        right_ret[i] = math.log(right_close[i + 1]) - math.log(right_close[i])

    left_vol = realized_vol(left_ret, 252, True)
    right_vol = realized_vol(right_ret, 252, True)
    print("left realized_vol:", left_vol)
    print("right realized_vol:", right_vol)
    print("vol_ratio:", left_vol / right_vol)


if __name__ == "__main__":
    main()
