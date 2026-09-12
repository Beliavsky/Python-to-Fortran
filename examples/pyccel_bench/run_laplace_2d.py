"""Driver for the pyccel 2D Laplace benchmark (recipe:
`x, y, phi, niter = laplace_2d(150, 150, 5e-5, 5000)`; grid reduced and
tolerance loosened for a fast correctness check)."""
from laplace_2d_mod import laplace_2d

x, y, phi, niter = laplace_2d(40, 40, 1.0e-4, 3000)
s = phi.sum()
lo = phi.min()
hi = phi.max()
c = phi[20, 20]
e = phi[10, 30]
print(niter, s, lo, hi, c, e)
