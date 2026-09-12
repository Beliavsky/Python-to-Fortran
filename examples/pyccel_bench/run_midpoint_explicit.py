"""Driver for the pyccel explicit-midpoint ODE benchmark (recipe:
`err = midpoint_explicit_humps_test(0., 2000., 1000000)`; step count
reduced for a fast correctness check)."""
from midpoint_explicit_mod import midpoint_explicit_humps_test

err = midpoint_explicit_humps_test(0.0, 2000.0, 2000)
print(f"{err:.10e}")
