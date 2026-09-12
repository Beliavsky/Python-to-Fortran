"""Driver for the pyccel 2D Poisson benchmark (recipe:
`x, y, phi = poisson_2d(150, 150, 200)`; grid and iteration count reduced
for a fast correctness check)."""
from poisson_2d_mod import poisson_2d

x, y, phi = poisson_2d(40, 40, 50)
print(f"{phi.sum():.8f} {phi.min():.8f} {phi.max():.8f} "
      f"{phi[20, 20]:.8f} {phi[10, 30]:.8f}")
