# R8BB deterministic validation, September 21, 2026

No transpiler defect was found in these checks. A matrix-vector product bug
was identified in the original Python source and reproduced by its translation.

`probe.py` contains the dependency closure of `r8bb_fa`, `r8bb_sl`,
`r8bb_mv`, `r8bb_mtv`, and `r8bb_to_r8ge`, copied from
`C:\python\public_domain\burkardt\r8bb\r8bb.py` (John Burkardt, MIT license).
The deterministic driver is new. Following the initial investigation, the two
product bounds were corrected in this local copy at the user's request.
The external corpus source and transpiler remain unchanged.

## Source bug

Both `r8bb_mv` and `r8bb_mtv` set `jhi = min(i + mu, n1)` and then iterate
through `jhi` inclusively. The last banded-block column is `n1 - 1`.
The extra column `n1` is therefore counted once in the banded-block loop and
again in the border-block loop. Without a border, the same access is invalid.

Before correction, for the 4+2 bordered case with bandwidths (1,2), the maximum
product error was 1.875 and the maximum transpose-product error was 1.125 in
both languages. The initial checker verified that all discrepancies were the
extra column contributions predicted by the off-by-one error. A minimal
no-border identity matrix raised the original source's invalid-column exception.

The local source correction is `jhi = min(i + mu, n1 - 1)` in both routines.
`reproduce_mv.py` now checks that both corrected products return the expected
identity-matrix result. The checker requires both products to match the dense
reference in every case, including the previously skipped no-border case.

## Factorization and solver checks

Right-hand sides come from an independently checked dense product, avoiding
the matrix-vector routines under test. The six cases cover:

- Bordered matrices with asymmetric bandwidths.
- A pure banded matrix (no border).
- A pure dense block (n1=0, with unused bandwidths set to zero).
- A one-element banded block and a diagonal banded block.
- A matrix requiring a nontrivial banded pivot, checked explicitly.

Dense unpacking, pivot agreement, solutions against known vectors and
`numpy.linalg.solve`, and scaled residuals all pass for both languages.
Maximum solution error is 2.85e-14; maximum scaled residual is 9.97e-17.
Python and Fortran agree on all recorded entries to the checker's tolerances.
After correction, both products match the dense references exactly on all six
fixtures in both languages (maximum product error 0). The corrected probe
translates, compiles, and runs successfully, and both identity regressions pass.

Run `python check.py` to rebuild and validate. It stores `python.log`,
`build.log`, `fortran.log`, and `analysis.json`. `python check.py --saved`
rechecks those saved outputs without rebuilding.

Scope: these are deterministic nonsingular examples, not proof for all inputs.
Singularity handling, every pivot pattern, and the original randomized driver
are not certified. No transpiler or runtime helper changes were needed.
