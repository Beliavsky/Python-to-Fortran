import numpy as np
import pandas as pd

n = 10
z = np.random.normal(size=(n, 2))
print(z)
df = pd.DataFrame(z)
print(df)
