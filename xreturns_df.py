import numpy as np
import pandas as pd

price_file = "asset_class_etf_prices.csv"
scale_ret = 100

dat = pd.read_csv(price_file)
dates = pd.to_datetime(dat["Date"], errors="coerce")

price_names = [c for c in dat.columns if c != "Date"]
prices = dat[price_names].to_numpy(dtype=float)

print("\nPrice file:", price_file)
print("Asset columns read:", len(price_names))
print("Assets read:")
print(price_names)

print("\nFirst price date:", str(dates.iloc[0].date()))
print("Last price date :", str(dates.iloc[-1].date()))

# -----------------------------
# Compute scaled log returns
# -----------------------------

ret_dates = dates.iloc[1:].reset_index(drop=True)
rets = scale_ret * np.diff(np.log(prices), axis=0)

print("\nNumber of price observations:", prices.shape[0])
print("Number of return observations:", rets.shape[0])
print("First return date:", str(ret_dates.iloc[0].date()))
print("Last return date :", str(ret_dates.iloc[-1].date()))

# -----------------------------
# Build a DataFrame of returns
# -----------------------------

returns_df = pd.DataFrame(rets, index=ret_dates, columns=price_names)

print("\nReturns DataFrame:")
print("Number of rows:", rets.shape[0])
print("Number of columns:", rets.shape[1])
print("Columns:", price_names)
print("First date:", str(ret_dates.iloc[0].date()))
print("Last date :", str(ret_dates.iloc[-1].date()))
print(returns_df.corr().round(3).to_string())
print(returns_df.describe().to_string())
print(returns_df.shape)
xret = returns_df.to_numpy()
print(xret.shape)
print(returns_df[["SPY", "EFA"]].corr().round(3))
print(returns_df.loc[:, ["SPY", "EFA"]].corr().round(3))
print(returns_df.iloc[:100, :].corr().round(3))
print(returns_df.iloc[:, :4].corr().round(3))
print(returns_df.mean())
print(returns_df.std())
print(returns_df.min())
print(returns_df.max())
print(returns_df.median())
print(returns_df["SPY"].mean())
