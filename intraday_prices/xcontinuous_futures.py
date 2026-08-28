# TRANSLATION NOTES: heavily simplified, to a large degree. The original
# builds a continuous futures series from many individual contract files:
# discovering/parsing contract filenames and roll dates, `@dataclass`
# records (ContractFile/ContractData/RollAdjustment), overlap-window
# `.merge()` between consecutive contracts to compute a roll ratio/
# difference, symbol-name lookups, and writing price + manifest CSVs.
# None of dataclasses, file discovery/argparse, `.merge`, or building/
# writing new DataFrames are supported (see the other scripts' notes on
# each). What's kept is the one genuinely portable numeric algorithm --
# apply_backward_adjustments' cumulative back-adjustment -- rewritten to
# work on a flat price array plus a parallel "which contract segment does
# this row belong to" array (rather than a list of per-contract
# DataFrames, which would need ragged/jagged arrays Fortran doesn't have),
# with the per-roll ratios given directly instead of computed from an
# overlap-window merge.
import pandas as pd


def backward_adjust_ratio(close, segment_id, ratios):
    """Back-adjust `close` prices onto the newest segment's basis.
    segment_id[i] gives price i's contract segment (0 = oldest); ratios[k]
    is the new_close/old_close ratio at the roll from segment k to k+1."""
    n_segments = len(ratios) + 1
    factors = [1.0] * n_segments
    factor = 1.0
    for k in range(n_segments - 1, -1, -1):
        factors[k] = factor
        if k > 0:
            factor = factor * ratios[k - 1]
    n = len(close)
    adjusted = [0.0] * n
    for i in range(n):
        adjusted[i] = close[i] * factors[segment_id[i]]
    return adjusted


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    close = list(df["Close"])[:9]

    # Three synthetic contract segments (3 bars each) rolled at bars 3
    # and 6, with made-up roll ratios (in place of the original's
    # overlap-window-derived new_close/old_close).
    segment_id = [0, 0, 0, 1, 1, 1, 2, 2, 2]
    ratios = [1.01, 0.995]

    adjusted = backward_adjust_ratio(close, segment_id, ratios)
    print("raw close:", close)
    print("back-adjusted close:", adjusted)


if __name__ == "__main__":
    main()
