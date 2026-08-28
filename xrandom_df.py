import numpy as np
import pandas as pd

rng = np.random.default_rng(12345)
n = 100

df = pd.DataFrame({
    "x": rng.normal(size=n),
    "y": rng.normal(size=n),
})

df["sum"] = df["x"] + df["y"]
df["difference"] = df["x"] - df["y"]
df["product"] = df["x"] * df["y"]
df["ratio"] = df["x"] / df["y"]

print(df)
print(df.cumsum())

