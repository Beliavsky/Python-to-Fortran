# TRANSLATION NOTES: the original module dispatches across 10 intraday
# vendor formats (Yahoo, Stooq, Kibot, Polygon, QuantQuote, Portara,
# Databento, generic, Parquet, pickle) using dict-based column renaming,
# `set` membership tests, regex cleanup (`str.replace(..., regex=True)`),
# dynamic `out.columns = [...]` assignment, and manual `pd.to_datetime` /
# `.dt.tz_convert` / `.dt.date` calls after the fact -- none of that is in
# xp2f.py's supported subset (no regex, no set/dict-driven branching, no
# datetime accessor chains; date/time parsing is only supported as part of
# `pd.read_csv(..., parse_dates=[...], index_col=...)` itself). Trimmed to
# the single Databento path, which is also restructured so date parsing
# happens directly in the read_csv call (as xp2f.py requires) instead of
# via a follow-up pd.to_datetime/.dt.tz_convert pass. Column renaming still
# uses df.rename(columns={...}) with an inline string-literal dict, which
# xp2f.py does support. The non-numeric "symbol" column present in the raw
# Databento sample is silently dropped by the translated read (xp2f.py's
# read_csv only supports numeric data columns) rather than kept as pandas
# would.
import pandas as pd

CANONICAL_PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def read_databento_intraday(path):
    """Read and normalize a raw Databento intraday OHLCV CSV."""
    df = pd.read_csv(path, parse_dates=["ts_event"], index_col="ts_event")
    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    return df


def main():
    path = "databento_intraday_sample.csv"
    df = read_databento_intraday(path)
    print(df.head())
    print()
    print("shape:", df.shape)


if __name__ == "__main__":
    main()
