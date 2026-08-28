# TRANSLATION NOTES: heavily simplified. The original is a multi-file CLI
# that validates each file's OHLCV data quality (via data_quality.py),
# computes realized volatility, and optionally writes a
# per-symbol/per-day summary table (`.groupby(["symbol","date"]).agg(...)`,
# `pd.DataFrame(rows)`, `.to_csv`) -- see data_quality.py's, io_intraday.py's,
# and vendor_compare.py's own notes for why groupby/agg, file
# resolution, and DataFrame construction/writing aren't portable. What's
# kept: running the already-simplified data-quality check
# (data_quality.find_bad_ohlcv_reasons) and realized-vol calculation
# (vendor_compare.realized_vol) together over one file, which is this
# script's actual point -- "quickly validate and summarize one file" --
# with both numeric cores copied in rather than imported (cross-file
# imports aren't supported). Also note: a 3+ term `and` chain where a
# later term is only safe because an earlier term guarded it (e.g.
# `i > 0 and close[i - 1] > 0.0 and ...`) isn't safe in translated
# Fortran -- `.and.` doesn't guarantee short-circuit evaluation the way
# Python's `and` does, so the out-of-bounds `close[i - 1]` access can
# still happen at i == 0. Split into nested `if`s instead (as
# data_quality.py's very similar check already does).
import math

import pandas as pd

TRADING_DAYS = 252

MAX_RANGE = 0.05
MAX_OC_RETURN = 0.03
MAX_PREV_CLOSE_RETURN = 0.05
MIN_LOW_TO_OC = 0.95
MAX_HIGH_TO_OC = 1.05


def find_bad_ohlcv_reasons(open_, high, low, close, volume):
    """Return one reason code per row (0 = OK, nonzero = a specific
    quality-check failure)."""
    n = len(open_)
    reason = [0] * n
    for i in range(n):
        o = open_[i]
        h = high[i]
        l = low[i]
        c = close[i]
        if o <= 0.0 or h <= 0.0 or l <= 0.0 or c <= 0.0:
            reason[i] = 1
            continue
        if h < l or h < o or h < c or l > o or l > c:
            reason[i] = 2
            continue
        if h / l - 1.0 > MAX_RANGE:
            reason[i] = 3
            continue
        if abs(math.log(c / o)) > MAX_OC_RETURN:
            reason[i] = 4
            continue
        oc_min = min(o, c)
        oc_max = max(o, c)
        if l / oc_min < MIN_LOW_TO_OC:
            reason[i] = 5
            continue
        if h / oc_max > MAX_HIGH_TO_OC:
            reason[i] = 6
            continue
        if i > 0 and close[i - 1] > 0.0:
            if abs(math.log(c / close[i - 1])) > MAX_PREV_CLOSE_RETURN:
                reason[i] = 7
                continue
        if volume[i] < 0.0:
            reason[i] = 8
    return reason


def realized_vol_pct(close, trading_days):
    n = len(close)
    ssq = 0.0
    for i in range(n - 1):
        r = math.log(close[i + 1]) - math.log(close[i])
        ssq = ssq + r * r
    return 100.0 * math.sqrt(trading_days * ssq)


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    open_ = list(df["Open"])
    high = list(df["High"])
    low = list(df["Low"])
    close = list(df["Close"])
    volume = list(df["Volume"])

    reasons = find_bad_ohlcv_reasons(open_, high, low, close, volume)
    n = len(reasons)
    n_bad = 0
    for i in range(n):
        if reasons[i] != 0:
            n_bad = n_bad + 1

    vol_pct = realized_vol_pct(close, TRADING_DAYS)

    print("rows:", n)
    print("flagged:", n_bad)
    print("annualized realized vol (pct):", vol_pct)


if __name__ == "__main__":
    main()
