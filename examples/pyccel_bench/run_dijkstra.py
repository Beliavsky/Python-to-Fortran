"""Driver for the pyccel Dijkstra benchmark (recipe:
`d = dijkstra_distance_test()`). Graph size nv=3000 is fixed inside the
module. Individual distances are compared (a full sum would overflow
Fortran's default 32-bit integer while numpy's stays arbitrary-precision
-- a width difference, not a translation error)."""
from dijkstra import dijkstra_distance_test

d = dijkstra_distance_test()
print(int(d.min()), int(d.max()), int(d[1]), int(d[1000]), int(d[2000]), int(d[2999]))
