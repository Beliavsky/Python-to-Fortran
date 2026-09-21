# Tridiagonal solver checks reveal a negative-base exponent bug

The solver and tridiagonal_mv functions in probe.py are copied unchanged from
Burkardt's MIT-licensed source. Only the fixed driver is new. It tests sizes
1, 2, 5 and 9 with strictly diagonally dominant matrices, nonzero off-diagonals,
one vector RHS and a two-column RHS. Separate b/d copies account for the source
solver's in-place modifications.

## Confirmed transpiler bug in the diagnostic driver

The driver originally constructed an alternating-sign solution with
`(i+1.0)*(-1.0)**i`. The translation loses required parentheses around the
negative base, generating `(i+1.0)*(-1.0_dp ** i)`. This changes even powers.
The failure occurs while constructing the intended solution, before the solver.

The independent two-line negative_power.py reproduces it:

```
for i in range(4):
    print(i, (-1.0)**i)
```

Before the fix, Python printed 1,-1,1,-1; Fortran printed -1,-1,-1,-1. Compilation and
execution succeed, but --run-diff reports DIFF at the first output line.

The active cause is `xp2f.simplify_narrow_redundant_arith_parens`, which
incorrectly assumed unary minus binds tighter than exponentiation. It now
preserves negative power bases and signed operands following arithmetic
operators (including negative exponents). Focused regressions cover literal
and variable bases, zero/even/odd powers, negative exponents, and nested powers.
The broader `fortran_scan.simplify_redundant_parens_in_line` also demonstrates
unsafe grouping removal, but is not wired into this pipeline and is unchanged.

## Solver numerical control

control.py differs from probe.py only by replacing the power-based sign with
an equivalent parity conditional. `check.py --control` passes for Python and
Fortran at all four sizes. Every matrix-vector product matches a separately
constructed dense matrix; solutions match the prescribed vectors and NumPy's
dense solve. Maximum solution error is 1.11e-16; maximum scaled matrix residual
is 1.39e-18. After the fix, the original power-based `check.py` probe also passes
at all four sizes, with the same errors and residuals for Python and Fortran.

Scope: these checks establish numerical values for the selected well-conditioned
systems, not general solver stability or singular/zero-pivot handling. They do
not certify shape preservation: the generated combined-rank driver represents
the vector result as a one-column matrix, though printed element values agree.
That rank behavior merits separate review. The randomized original full driver
was not rerun; its core routines were exercised directly with fixed inputs.

check.py stores per-run logs and probe_analysis.json/control_analysis.json.
No corpus source or runtime helper was modified; no full pytest run was performed.

## September 21: rank-preserving specialization

The mixed-rank limitation above is now fixed for this case. The transpiler
emits separate vector and matrix solver procedures. The original probe now
checks d1/d2/x1/x2 ranks and result dimensions explicitly at all four sizes;
these shape checks and all numerical checks pass. See
`../tridiagonal_rank_20260921/review.md` for the isolated broadcasting regression
and the remaining specialization limits.
