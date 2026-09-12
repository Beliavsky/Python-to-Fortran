"""Driver for the pyccel Ackermann benchmark (recipe from
pyccel-benchmarks/benchmarks/run_benchmarks.py: `a = ackermann(3, 8)`)."""
from ackermann_mod import ackermann

a = ackermann(3, 6)
print(a)
