"""Driver for the pyccel Euler ODE benchmark (recipe:
`err = euler_humps_test(0., 2000., 1000000)`; step count reduced for a
fast correctness check)."""
from euler_mod import euler_humps_test

err = euler_humps_test(0.0, 2000.0, 2000)
print(f"{err:.10e}")
