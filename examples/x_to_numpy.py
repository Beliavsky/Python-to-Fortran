import numpy as np
import pandas as pd

rng = np.random.default_rng(12345)
n = 10

df = pd.DataFrame({
    "x1": rng.normal(size=n),
    "x2": rng.normal(size=n),
})

x1 = df["x1"].to_numpy()
print(df)
print(x1)
x = df[["x1", "x2"]].to_numpy()
print(x)

