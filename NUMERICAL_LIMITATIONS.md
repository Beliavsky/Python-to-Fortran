# Numerical limitations

`xp2f.py` translates supported source operations; it does not make an unstable
source algorithm numerically reliable. Successful compilation, a zero exit status,
or agreement on one input does not prove numerical equivalence for other inputs.
Compare results against Python and, where possible, independent reference values
or mathematical checks. Output comparisons should account for printed precision,
random inputs, and differences in array display conventions.

## Text-file array rank: single-column `loadtxt`

NumPy normally returns a one-dimensional array when `np.loadtxt(path)` reads a
single-column file with multiple rows. The transpiler currently assumes a matrix
for this call without scalar column selection. This can change a vector dot
product into matrix multiplication and cause a runtime shape error.

For a known single-column file with multiple rows, explicitly selecting the column
is a tested workaround:

```python
x = np.loadtxt(path, usecols=0)
```

This selects column zero; it is not a general replacement for loading multicolumn
data. It also does not resolve all of NumPy's scalar/vector/matrix squeezing rules.
The limitation was reproduced in Burkardt's `chebyshev1_exactness` and
`chebyshev2_exactness`. Copies using explicit column selection matched Python's
22 quadrature-error rows within 1e-14 absolute tolerance. The original programs
still require a rank-handling fix; the workaround is not an automatic correction.

## Eigenvector-based matrix exponentials: a diagnosed example

Burkardt's `matrix_exponential.py`, test #10, uses the matrix

```text
4  1  1
2  4  1
0  1  4
```

Its eigenvalues are 3, 3, and 6. It is defective: the repeated eigenvalue has only
one independent eigenvector. The source's `r8mat_expm3()` computes eigenvalues and
eigenvectors, takes their real parts, and uses a least-squares calculation to
construct an approximation to the matrix exponential.

In the investigated Python and Fortran builds:

| Observation | Python/NumPy | Generated Fortran and its numerical helpers |
|---|---|---|
| Computed pair near 3 | Two nearby real values | A tiny complex-conjugate pair |
| Maximum eigenpair residual | About 1.8e-15 | About 1.6e-15 |
| Rank after taking the eigenvectors' real parts | 3 | 2 |
| First entry of the computed exponential | 147.86662227 | 134.47626450 |

These are observations from the tested builds, not guaranteed behavior for every
NumPy or Fortran library version. Small numerical differences in the eigensystem
are amplified by the source algorithm. In particular, taking the real parts of
the conjugate eigenvectors makes two columns identical.

Feeding the Fortran eigenvectors into NumPy's least-squares calculation reproduced
the Fortran exponential within 1.14e-13. An independent reference calculation gave
a first entry of 147.86662245. This isolates the observed discrepancy to the
sensitive eigen-based algorithm rather than demonstrating a translation or
least-squares implementation defect. The investigation was recorded on
September 20, 2026.

### Implications

- Do not discard imaginary parts solely because they look small; check their role
  in subsequent rank-sensitive calculations.
- For this kind of problem, validate the final matrix exponential, not only the
  accuracy of the eigenpairs. Small eigenpair residuals did not ensure an accurate
  exponential here.
- Retaining complex arithmetic improved this particular diagnostic, but is not a
  general remedy for an eigenvector-based exponential on defective matrices.
- This finding does not justify rejecting all `np.linalg.eig` calls or silently
  replacing the user's algorithm during translation. No such rejection or
  automatic algorithm replacement is provided for this case.

This example is a documented numerical-sensitivity limitation, not a blanket
explanation for output differences. Other discrepancies still require investigation.
