import numpy as np
import pandas as pd

rng = np.random.default_rng(12345)

n = 10
p = 4
thresh = 2.0

df = pd.DataFrame(
    rng.normal(size=(n, p)),
    columns=["x1", "x2", "x3", "x4"]
)

df[df.abs() > thresh] = np.nan

print(df)

# Number of NaN values in the entire dataframe
print("Total NaNs:", df.isna().sum().sum())

# Number of NaNs in each column
print("\nNaNs by column:")
print(df.isna().sum())

# Drop rows containing at least one NaN
df_drop_rows = df.dropna()

# Drop columns containing at least one NaN
df_drop_cols = df.dropna(axis=1)

print("\nShape after dropping rows with NaNs:")
print(df_drop_rows.shape)

print("Shape after dropping columns with NaNs:")
print(df_drop_cols.shape)
