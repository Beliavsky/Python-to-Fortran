import numpy as np


def partition_by_bounds(x, lower, upper):
    """Split x into (below, within, above) relative to [lower, upper]."""
    below = []
    within = []
    above = []
    for v in x:
        if v < lower:
            below.append(v)
        elif v > upper:
            above.append(v)
        else:
            within.append(v)
    return np.array(below), np.array(within), np.array(above)


x = np.array([-3.5, -1.0, 0.0, 0.5, 2.2, 4.9, 5.0, 7.1, 10.0])
lower = -1.0
upper = 5.0
below, within, above = partition_by_bounds(x, lower, upper)
print("x:", x)
print("bounds:", lower, upper)
print("below:", below)
print("within:", within)
print("above:", above)

expected_below = np.array([-3.5])
expected_within = np.array([-1.0, 0.0, 0.5, 2.2, 4.9, 5.0])
expected_above = np.array([7.1, 10.0])
assert np.array_equal(below, expected_below), f"expected below {expected_below}, got {below}"
assert np.array_equal(within, expected_within), f"expected within {expected_within}, got {within}"
assert np.array_equal(above, expected_above), f"expected above {expected_above}, got {above}"
print("test passed")
