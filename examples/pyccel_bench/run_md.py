"""Driver for the pyccel molecular-dynamics benchmark (recipe:
`p, k = md(3, 100, 200, 0.1)`; particle count and step count reduced for a
fast correctness check). Exercises the in-place `pos += ...` / `vel += ...`
update and the seeded-LCG initializer, so a wrong intent or a lost
augmented-assignment shows up here as a numeric mismatch."""
from md_mod import md

potential, kinetic = md(3, 40, 30, 0.1)
print(f"{potential:.10f} {kinetic:.10f}")
