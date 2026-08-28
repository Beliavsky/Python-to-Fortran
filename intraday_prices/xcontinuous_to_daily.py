# TRANSLATION NOTES: heavily simplified. The original is a multi-file CLI
# (argparse, glob resolution, output-path derivation from pathlib) wrapped
# around `.groupby("TradingDate").agg(Open=("Open","first"), ...)` (with a
# string "Contract" column carried through the aggregation via "last" and
# "nunique"), `.dt.strftime`, and writing a formatted CSV via `.to_csv`.
# groupby+multi-output-.agg, string-typed DataFrame columns, and writing a
# new DataFrame are all unsupported. Also, day-boundary detection (used
# both for TradingDate grouping and the optional --session-close-time
# rollover) needs the "date" column or the datetime index's own
# year/month/day fields, neither accessible once xp2f.py's read_csv has
# read the file (see io_intraday.py's notes on the dropped "date" column;
# there's also no supported syntax for reading a datetime index element's
# own fields back out in Python source). Kept: the actual OHLCV collapse
# formula (Open=first, High=max, Low=min, Close=last, Volume=sum) applied
# to one full array (i.e. one day's worth of bars, assumed pre-split by
# the caller), and format_number's "trim a fixed-precision float to its
# shortest representation" string formatting, both genuinely portable.
import pandas as pd


def ohlcv_bar(open_, high, low, close, volume):
    """Collapse one day's bars into a single OHLCV bar."""
    return open_[0], max(high), min(low), close[-1], sum(volume)


def format_number(value):
    # real value, a price or volume to format.
    """Format a float, trimming trailing zeros (and a trailing dot)."""
    if value == int(value):
        return str(int(value))
    text = f"{value:.10f}"
    text = text.rstrip("0")
    text = text.rstrip(".")
    return text


def main():
    df = pd.read_csv("spy_5min_databento.csv", parse_dates=["Datetime"], index_col="Datetime")
    open_ = list(df["Open"])[:78]
    high = list(df["High"])[:78]
    low = list(df["Low"])[:78]
    close = list(df["Close"])[:78]
    volume = list(df["Volume"])[:78]

    day_open, day_high, day_low, day_close, day_volume = ohlcv_bar(open_, high, low, close, volume)
    print("day bar:", day_open, day_high, day_low, day_close, day_volume)
    print(format_number(day_open))
    print(format_number(day_volume))
    print(format_number(100.0))


if __name__ == "__main__":
    main()
