import numpy as np


def values_within_bounds(x, lower, upper):
    """Return the values of x that lie within [lower, upper] (inclusive)."""
    out = []
    for v in x:
        if lower <= v and v <= upper:
            out.append(v)
    return np.array(out)


x = np.array([-3.5, -1.0, 0.0, 0.5, 2.2, 4.9, 5.0, 7.1, 10.0])
lower = -1.0
upper = 5.0
result = values_within_bounds(x, lower, upper)
print("x:", x)
print("bounds:", lower, upper)
print("result:", result)

expected = np.array([-1.0, 0.0, 0.5, 2.2, 4.9, 5.0])
assert np.array_equal(result, expected), f"expected {expected}, got {result}"
print("test passed")
