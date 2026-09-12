"""Driver for the pyccel 1D linear-convection benchmark (recipe:
`x, u = linearconv_1d(2001, 0.0003, 3000)`; grid and step count reduced,
dt rescaled to keep the same Courant number ~0.3 for a fast correctness
check)."""
import numpy as np
from linearconv_1d_mod import linearconv_1d

x, u = linearconv_1d(201, 0.003, 300)
np.set_printoptions(precision=8, threshold=10_000)
print(np.round(u, 8))
