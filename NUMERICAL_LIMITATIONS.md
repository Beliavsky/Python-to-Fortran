# Numerical limitations

`xp2f.py` translates supported source operations; it does not make an unstable
source algorithm numerically reliable. Successful compilation, a zero exit status,
or agreement on one input does not prove numerical equivalence for other inputs.
Compare results against Python and, where possible, independent reference values
or mathematical checks. Output comparisons should account for printed precision,
random inputs, and differences in array display conventions.

## Integer comments conflicting with real scalar arguments

When a procedure parameter remains integer-typed from source comments but a
caller supplies a known real scalar, the transpiler rejects the conflicting
call instead of silently inserting an integer conversion. Specializing these
comment-conflicting integer/real calls is not yet supported generally. Integer
calls and explicit conversions remain supported, including an unconditional
`x = int(x)` before any other use in the callee.

This catches Burkardt's `uniform.py` LCRG case: `np.zeros` stores floating-point
seeds, but `lcrg_evaluate` documents integer parameters. Converting those seeds
to integers changes large-product rounding and subsequent modular arithmetic.
The former translation matched the exact integer generator but not Python's
floating-point computation. Use explicit `int(...)` only when integer arithmetic
is actually intended. `--ignore-comments` matches the reduced diagnostic's
floating-point results, but has not been validated as a whole-program workaround.

### A source-level congruence arithmetic failure

Burkardt's `uniform.py` uses a floating-point work array inside `congruence`.
Its 20 published cases agree with the saved Fortran output, and all 16 successful
cases satisfy exact integer residual checks. Larger inputs can fail in Python
itself: for `(a,b,c) = (1259289228,1358106529,1524307444)`, it returns
`x=603115968` with no error flag, but `(a*x-c) % b = 355665976` in exact arithmetic.
The correct canonical solution is `769316839`.

A rounded product causes a floor quotient in Euclidean back-substitution to be
off by one. An in-memory variant using arbitrary-precision integer work storage
returns the correct answer. This is a source arithmetic defect; preserving the
source's floating-point operations or casting the final result to integer cannot
fix it. The transpiler does not silently replace the source algorithm.

## Percent formatting without a conversion specifier

Expressions such as `'RMS error = ' % value` are rejected with an explicit
diagnostic when a supplied argument has no conversion specifier to consume it.
Ordinary Python scalars can raise `TypeError` here, while NumPy scalars can leave
the label unchanged. The transpiler does not retain enough scalar provenance to
reproduce that distinction; it must not silently append the value.

If displaying the value is intended, use `'RMS error = %g' % value` or
`print('RMS error = ', value)`. Literal-only formats with an empty argument tuple,
such as `'100%%' % ()`, remain supported. This conservative restriction catches
the two affected RMS-label statements in Burkardt's `jacobi_poisson_1d.py`.

## Text-file array rank: single-column `loadtxt`

NumPy normally returns a one-dimensional array when `np.loadtxt(path)` reads a
single-column file with multiple rows. The transpiler can infer a vector when a
direct, singly assigned load is passed to a local function parameter documented
as rank one (for example, `# real X(N), the vector.`). The generated reader checks
the actual file shape: a single row or column is accepted, but a matrix or a
single value (which NumPy would return as a scalar) produces an explicit error.
Explicit shape/column options and conflicting rank evidence are not overridden.

Without such evidence or scalar column selection, the default remains a matrix.
General data-dependent scalar/vector/matrix squeezing is not supported. This can
still change a vector dot product into matrix multiplication and cause a runtime
shape error in programs whose intended rank cannot be inferred.

For a known single-column file with multiple rows, explicitly selecting the column
is a tested workaround:

```python
x = np.loadtxt(path, usecols=0)
```

This selects column zero; it is not a general replacement for loading multicolumn
data. It also does not resolve all of NumPy's scalar/vector/matrix squeezing rules.
The limitation was reproduced in Burkardt's `chebyshev1_exactness` and
`chebyshev2_exactness`. With context-based inference, both original programs now
compile and run on four-point quadrature fixtures, and all 22 quadrature-error
rows match Python within 1e-14 absolute tolerance. Explicit column selection was
also tested successfully. These checks do not establish general support for all
file shapes or identical array display formatting.

## Gram-Schmidt on dependent columns

Burkardt's `gram_schmidt.py`, `cgs2` A3 test, tries to normalize four columns in
three dimensions. Its first three columns span the space; the fourth orthogonal
residual is mathematically zero. The source checks only whether its computed
norm is greater than zero, so roundoff can become a spurious unit vector.

On the fixed audit input, Python and Fortran produced identical first three
orthonormal columns, with relative reconstruction error about 2.5e-16. Their
fourth residual norms were about 1.88e-15 and 2.02e-15. After normalization, one
fourth-column entry differed by about 0.20, and neither fourth column was
orthogonal to the first three. Python with explicit sequential scalar reductions
reproduced the Fortran result, isolating this case to reduction-order sensitivity.

The source's tolerance-based `cgs4` variant discards the fourth column on this
input. Rank-aware tolerances or a rank-revealing method are algorithm choices,
not transformations the transpiler applies automatically. This diagnosis covers
the investigated `cgs2` case, not every Gram-Schmidt variant or input.

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
