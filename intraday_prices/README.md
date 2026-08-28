# intraday_prices

Copies of the scripts in `c:\python\intraday_prices`, adapted to be reasonable
targets for `xp2f.py`. The originals are untouched; every script modified here
carries a `# TRANSLATION NOTES:` header explaining what was changed and why
(dropped pandas/stdlib features, simplifications, etc.).

- 7 shared library modules (`market_constants.py`, `file_utils.py`,
  `io_intraday.py`, `intraday_bars.py`, `intraday_returns.py`,
  `data_quality.py`, `vendor_compare.py`) and 11 CLI scripts were rewritten
  and verified with `xp2f.py <file> --run-both` (Fortran output matches
  Python exactly).
- 5 scripts with no numeric content (network fetch, test harness, file
  wrangling) were copied as-is with just an exclusion note.

## Missing data file: `spy_5min_databento.csv`

Several `main()` demos (`xcontinuous_futures.py`, `xcompare_vendors.py`,
`xcheck_intraday.py`, `xrealized_vol_by_frequency.py`,
`xtime_boundary_effects.py`, `xcontinuous_to_daily.py`,
`xresample_intraday.py`, `vendor_compare.py`, `data_quality.py`,
`intraday_returns.py`, `intraday_bars.py`, `file_utils.py`) read
`spy_5min_databento.csv`, a 5-minute SPY bar file sourced from Databento.

That file is **not committed** to this repo — it's commercial market data
and is `.gitignore`d — so those demos will fail with a file-not-found /
`read_csv` error on a fresh clone. To run them, supply your own 5-minute
OHLCV CSV with columns `Datetime,Open,High,Low,Close,Volume` under that
filename, or point the script at a different CSV (e.g. one of the small
tracked fixtures below).

## Tracked CSV fixtures

- `sample_daily_prices.csv`, `sample_daily_prices2.csv` — small synthetic
  daily OHLC files (date-only index).
- `databento_intraday_sample.csv` — 6-row raw Databento-format sample
  (`ts_event,symbol,open,high,low,close,volume`).
- `asset_class_etf_prices.csv` — date-indexed multi-ETF daily prices.
