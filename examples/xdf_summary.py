import numpy as np
import pandas as pd

rng = np.random.default_rng(12345)
n = 100

df = pd.DataFrame({
    "x": rng.normal(size=n),
    "y": rng.normal(size=n),
})

summary = pd.DataFrame([df.mean(), df.std()], index=["mean", "sd"])
print(summary)
