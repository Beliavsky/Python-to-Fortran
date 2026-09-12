"""Driver for the pyccel Spline benchmark (recipe:
`s = Spline(5, knots=np.linspace(0,1,1000), coeffs=np.ones(1000));
x = np.random.rand(100000); y = np.empty(100000); s.eval(x, y)`).
A small, deterministic `x` is used here for a fast correctness check;
np.random.rand's own stream isn't expected to match between the Python
and Fortran sides anyway (see this project's own established
RNG-divergence-is-not-a-bug scoping)."""
import numpy as np
from splines import Spline

s = Spline(3, np.linspace(0.0, 1.0, 20), np.linspace(1.0, 2.0, 20 - 3 - 1))
x = np.array([0.05, 0.2, 0.35, 0.5, 0.65, 0.8, 0.95])
y = np.empty(len(x))
s.eval(x, y)
print(y)
