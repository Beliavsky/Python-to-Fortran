"""Driver for ode_test.py's own `euler`/`humps_deriv`/`humps_fun` (recipe
adapted from euler_humps_test, but calling euler() directly since that
function itself is side-effect-only and returns nothing). Exercises the
`Final[float[:]]` annotation style -- ode_test.py's callback dummies use
`'()(float, Final[float[:]], float[:])'`, unlike euler_mod.py's plain
`'()(float, float[:], float[:])'` -- and array-typed (not scalar) tspan/y0
driver arguments."""
import numpy as np
from ode_test import euler, humps_deriv, humps_fun

t0 = 0.0
t1 = 2000.0
n = 200

tspan = np.array([t0, t1])
y0 = np.array([humps_fun(t0)])
t = np.linspace(t0, t1, n + 1)
y = np.zeros((n + 1, 1))

euler(humps_deriv, tspan, y0, n, t, y)

err = y[-1, 0] - humps_fun(t1)
print(f"{err:.10e}")
