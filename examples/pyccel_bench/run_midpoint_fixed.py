"""Driver for the pyccel implicit-midpoint (fixed-iteration) ODE benchmark
(recipe: `err = midpoint_fixed_humps_test(0., 2000., 1000000)`; step count
reduced for a fast correctness check)."""
from midpoint_fixed_mod import midpoint_fixed_humps_test

err = midpoint_fixed_humps_test(0.0, 2000.0, 2000)
print(f"{err:.10e}")
