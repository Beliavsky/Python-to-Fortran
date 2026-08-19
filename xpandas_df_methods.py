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

sub3 = dat[["SPY", "EFA", "EEM"]]
dropped = sub3.drop(columns=["EFA"])
print("\ndropped columns.corr():")
print(dropped.corr().round(3))

renamed = sub3.rename(columns={"SPY": "SPX"})
print("\nrenamed.describe():")
print(renamed.describe().to_string())

roll_mean = sub.rolling(3).mean()
roll_mean_arr = roll_mean.to_numpy()
print("\nrolling(3).mean() row 2:", roll_mean_arr[2, 0], roll_mean_arr[2, 1])
print("rolling(3).mean() row 5:", roll_mean_arr[5, 0], roll_mean_arr[5, 1])
print("rolling(3).mean() row 0 (NaN):", roll_mean_arr[0, 0])

roll_std = sub.rolling(3).std()
roll_std_arr = roll_std.to_numpy()
print("rolling(3).std() row 2:", roll_std_arr[2, 0], roll_std_arr[2, 1])
print("rolling(3).std() row 5:", roll_std_arr[5, 0], roll_std_arr[5, 1])
