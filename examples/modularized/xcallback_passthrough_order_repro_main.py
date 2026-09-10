import numpy as np
from xcallback_passthrough_order_repro_helpers import evaluate


def objective(x, n):
    return np.sum(x[0:n] ** 2)


def driver(f, x, n):
    return evaluate(f, x, n)


n = 3
x = np.array([1.0, 2.0, 3.0])
print(driver(objective, x, n))
