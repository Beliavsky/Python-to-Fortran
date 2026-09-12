"""Driver for the pyccel RK4 ODE benchmark (recipe:
`err = rk4_humps_test(0., 2000., 1000000)`; step count reduced for a fast
correctness check)."""
from rk4_mod import rk4_humps_test

err = rk4_humps_test(0.0, 2000.0, 2000)
print(f"{err:.10e}")
