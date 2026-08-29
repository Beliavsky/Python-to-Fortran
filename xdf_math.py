import numpy as np
import pandas as pd

rng = np.random.default_rng(12345)
n = 5

df = pd.DataFrame({
    "x": rng.normal(size=n),
    "y": rng.normal(size=n),
})

print(df)
print(df.cumsum())
print(df * 10)
print(df / 10)
print(df + 10)
print(df - 10)
print(df + df)
print(df - df)
print(df * df)
print(df / df)
print(np.exp(df))
print(np.log(np.exp(df)) - df)

dfz = df.copy(deep=False)
dfz["z"] = df["x"] + df["y"]
print(df + dfz)

dfz = df
dfz["z"] = df["x"] + df["y"]
print(df + dfz)
print(df)
