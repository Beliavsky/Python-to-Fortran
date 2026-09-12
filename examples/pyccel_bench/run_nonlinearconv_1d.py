"""Driver for the pyccel 1D nonlinear-convection benchmark (recipe:
`x, u = nonlinearconv_1d(2001, 0.00035, 3000)`; grid and step count
reduced, dt rescaled to keep dt/dx ~0.35 for a fast correctness check)."""
import numpy as np
from nonlinearconv_1d_mod import nonlinearconv_1d

x, u = nonlinearconv_1d(201, 0.0035, 300)
np.set_printoptions(precision=8, threshold=10_000)
print(np.round(u, 8))
