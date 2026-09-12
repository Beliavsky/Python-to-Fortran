"""Driver for cfd_python_test.py's own cavity_flow_2d -- not one of
pyccel-benchmarks' own timed tests (no run_benchmarks.py recipe exists for
it), but the one function in this file that has genuinely NEW coverage
value: two functions (build_up_b, pressure_poisson) nested INSIDE
cavity_flow_2d, one of which (build_up_b) closure-captures `p` from the
enclosing scope's own parameter list rather than taking it as one of its
own arguments. Grid/step count kept small for a fast correctness check."""
import numpy as np
from cfd_python_test import cavity_flow_2d

nx = 8
ny = 8
nt = 5
dx = 2.0 / (nx - 1)
dy = 2.0 / (ny - 1)
dt = 0.001
rho = 1.0
nu = 0.1

u = np.zeros((ny, nx))
v = np.zeros((ny, nx))
p = np.zeros((ny, nx))

cavity_flow_2d(u, v, p, nt, dt, dx, dy, rho, nu)

print(f"{u.sum():.8f} {u.min():.8f} {u.max():.8f} "
      f"{v.sum():.8f} {v.min():.8f} {v.max():.8f} "
      f"{p.sum():.8f} {p.min():.8f} {p.max():.8f}")
