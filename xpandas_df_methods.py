import pandas as pd

dat = pd.read_csv("asset_class_etf_prices.csv")
sub0 = dat[["SPY", "EFA"]]
sub = sub0.iloc[:10, :]

pct = sub.pct_change()
pct_arr = pct.to_numpy()
print("\npct_change row 5:", pct_arr[5, 0], pct_arr[5, 1])

shifted = sub.shift(2)
shifted_arr = shifted.to_numpy()
print("shift(2) row 5:", shifted_arr[5, 0], shifted_arr[5, 1])

sorted_sub = sub.sort_index(ascending=False)
sorted_arr = sorted_sub.to_numpy()
print("sort_index(ascending=False) row 0:", sorted_arr[0, 0], sorted_arr[0, 1])
print("sort_index(ascending=False) row 9:", sorted_arr[9, 0], sorted_arr[9, 1])
