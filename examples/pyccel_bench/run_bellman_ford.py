"""Driver for the pyccel Bellman-Ford benchmark (recipe:
`err = bellman_ford_test()`). Sizes are fixed inside the module
(v_num=200, e_num=19900). The result vector is summarised to plain
scalars so the compared output doesn't depend on numpy's array repr."""
from bellman_ford_mod import bellman_ford_test

v = bellman_ford_test()
total = float(v.sum())
lo = float(v.min())
hi = float(v.max())
mid = float(v[100])
last = float(v[199])
print(f"{total:.6f} {lo:.6f} {hi:.6f} {mid:.6f} {last:.6f}")
