# TRANSLATION NOTES: heavily simplified. The original returns a
# report DataFrame: boolean row-masks selected via `.loc[mask, cols]`,
# multiple reason-labeled pieces stitched together with `pd.concat`, a new
# mixed string+numeric "reason"/"detail" column appended via `.insert()` --
# none of that (row-count-changing boolean selection, `pd.concat`, mixed
# string/numeric DataFrame columns) is in xp2f.py's supported subset (its
# DataFrame model is a plain numeric matrix + index). The frequency-keyed
# threshold dicts (DEFAULT_MAX_RANGE = {"intraday": ..., "daily": ...}) are
# also dropped in favor of flat constants, since only "intraday" values are
# ever exercised here. Also dropped: normalize_ohlcv_columns/_id_columns
# (vendor column-name remapping via a dict comprehension over df.columns --
# moot once a script reads one fixed vendor format, as established in
# io_intraday.py's own notes) and _threshold (an override-or-default
# dict lookup that only existed to serve the now-dropped frequency dicts).
#
# What's kept is the actual per-row numeric quality logic, rewritten as a
# single array loop returning one reason code per row (0 = OK) instead of a
# report DataFrame. One behavior change: the original's checks are
# independent -- a row failing two checks appears twice, once per reason,
# in the concatenated report. The translated version keeps only the first
# failing reason per row (mutually exclusive), which is simpler to express
# as a loop and covers the same checks.
import math

import pandas as pd

MAX_RANGE = 0.05
MAX_OC_RETURN = 0.03
MAX_PREV_CLOSE_RETURN = 0.05
MIN_LOW_TO_OC = 0.95
MAX_HIGH_TO_OC = 1.05

REASON_OK = 0
REASON_NONPOSITIVE = 1
REASON_ORDER_VIOLATION = 2
REASON_EXTREME_RANGE = 3
REASON_EXTREME_OC_RETURN = 4
REASON_LOW_FAR_FROM_OC = 5
REASON_HIGH_FAR_FROM_OC = 6
REASON_EXTREME_PREV_CLOSE_RETURN = 7
REASON_BAD_VOLUME = 8


def find_bad_ohlcv_reasons(open_, high, low, close, volume):
    """Return one reason code per row (0 = OK); see REASON_* constants."""
    n = len(open_)
    reason = [0] * n
    for i in range(n):
        o = open_[i]
        h = high[i]
        l = low[i]
        c = close[i]
        if o <= 0.0 or h <= 0.0 or l <= 0.0 or c <= 0.0:
            reason[i] = REASON_NONPOSITIVE
            continue
        if h < l or h < o or h < c or l > o or l > c:
            reason[i] = REASON_ORDER_VIOLATION
            continue
        bar_range = h / l - 1.0
        if bar_range > MAX_RANGE:
            reason[i] = REASON_EXTREME_RANGE
            continue
        oc_return = abs(math.log(c / o))
        if oc_return > MAX_OC_RETURN:
            reason[i] = REASON_EXTREME_OC_RETURN
            continue
        oc_min = min(o, c)
        oc_max = max(o, c)
        if l / oc_min < MIN_LOW_TO_OC:
            reason[i] = REASON_LOW_FAR_FROM_OC
            continue
        if h / oc_max > MAX_HIGH_TO_OC:
            reason[i] = REASON_HIGH_FAR_FROM_OC
            continue
        if i > 0 and close[i - 1] > 0.0:
            prev_ret = abs(math.log(c / close[i - 1]))
            if prev_ret > MAX_PREV_CLOSE_RETURN:
                reason[i] = REASON_EXTREME_PREV_CLOSE_RETURN
                continue
        if volume[i] < 0.0:
            reason[i] = REASON_BAD_VOLUME
    return reason


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
        if reasons[i] != REASON_OK:
            n_bad = n_bad + 1
    print("rows:", n)
    print("flagged:", n_bad)


if __name__ == "__main__":
    main()
