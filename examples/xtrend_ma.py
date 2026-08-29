"""
Basic trend-following strategy: each day, be long an asset if its price is
above its n-day moving average, short if it's below. Positions are
equal-weighted (dollar-neutral) across the assets with an active signal
that day, and today's return is earned on yesterday's signal (no
lookahead). See examples/xma_persist.py for a richer (simulated-data,
numpy-only) version of the same idea with signal persistence and
transaction costs; this one uses real prices via pandas, in the style of
examples/xfit_nagarch_t.py and examples/xpandas_df_methods.py.
"""

import numpy as np
import pandas as pd

price_file = "asset_class_etf_prices.csv"
n = 50  # moving-average window, in trading days

dat = pd.read_csv(price_file)
dates = pd.to_datetime(dat["Date"], errors="coerce")
asset_names = [c for c in dat.columns if c != "Date"]
prices = dat[asset_names]

print("Price file:", price_file)
print("Assets:", asset_names)
print("Moving-average window (days):", n)
print("First price date:", str(dates.iloc[0].date()))
print("Last price date :", str(dates.iloc[-1].date()))

# -----------------------------
# Trend signal: +1 (long) above the n-day MA, -1 (short) below, 0 otherwise
# (0 only during the MA's own warm-up period, where it's still NaN)
# -----------------------------

ma = prices.rolling(n).mean()
above = prices > ma
below = prices < ma
signal = above.astype(float) - below.astype(float)

# -----------------------------
# Equal-weighted, dollar-neutral portfolio: each day, split +-0.5 evenly
# across the assets currently long/short (0 weight on an inactive day)
# -----------------------------

n_active = (signal != 0.0).sum(axis=1)
weights = signal.divide(n_active, axis=0).fillna(0.0)

asset_rets = prices.pct_change()
port_ret = (weights.shift(1) * asset_rets).sum(axis=1)
port_ret = port_ret.iloc[n:]

# -----------------------------
# Performance summary
# -----------------------------

mean_daily = port_ret.mean()
vol_daily = port_ret.std()
ann_ret = 252.0 * mean_daily
ann_vol = np.sqrt(252.0) * vol_daily
sharpe = ann_ret / ann_vol if ann_vol > 0.0 else np.nan
growth = (1.0 + port_ret).prod()
hit_rate = (port_ret > 0.0).mean()

print(f"\nStrategy: long/short by price vs {n}-day moving average")
print(f"Test period: {str(dates.iloc[n].date())} to {str(dates.iloc[-1].date())}")
print()
print(f"{'mean_daily':>12s} {'vol_daily':>12s} {'ann_ret':>10s} {'ann_vol':>10s} {'sharpe':>8s} {'growth':>10s} {'hit_rate':>9s}")
print(f"{mean_daily:12.6f} {vol_daily:12.6f} {ann_ret:10.4f} {ann_vol:10.4f} {sharpe:8.4f} {growth:10.4f} {hit_rate:9.4f}")

# -----------------------------
# Per-asset trend-signal accuracy: on days the asset had an active
# signal, was the sign of the signal the same as the sign of the next
# day's return?
# -----------------------------

print("\nPer-asset trend signal accuracy")
print(f"{'asset':10s} {'pct_days_long':>14s} {'hit_rate':>10s}")
for name in asset_names:
    sig = signal[name].iloc[n:]
    ret = asset_rets[name].shift(-1).iloc[n:]
    active = sig != 0.0
    correct = ((sig > 0.0) & (ret > 0.0)) | ((sig < 0.0) & (ret < 0.0))
    pct_long = (sig[active] > 0.0).mean()
    hit = correct[active].mean()
    print(f"{name:10s} {pct_long:14.4f} {hit:10.4f}")
