"""Regression: both corrected products accept a no-border identity matrix."""
import numpy as np
from probe import r8bb_mv, r8bb_mtv

for product in (r8bb_mv, r8bb_mtv):
    result = product(2, 0, 0, 1, np.array([0., 1., 0., 1.]), np.ones(2))
    assert np.array_equal(result, np.ones(2))
    print(product.__name__, result)
