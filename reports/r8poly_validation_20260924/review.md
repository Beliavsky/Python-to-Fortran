# R8POLY: rank-guarded print helper

The original `r8vec_print(n, a, title)` handles vectors and column matrices
using `if a.ndim == 1`. Previously it was emitted with a rank-two dummy and
only the matrix branch, failing when called with the vector of polynomial roots.

## Fix

Print-only procedure specialization now accepts nested if/for/while bodies.
For a fixed argument-rank specialization, simple `a.ndim == integer` and
`a.ndim != integer` branches are selected before body inference and emission.
This prevents unreachable matrix subscripts from promoting vector arguments.
Arguments assigned within the function are excluded from this branch folding.
A rank-guarded helper is also specialized when only one input profile occurs.
Forced specialization kinds take precedence over descriptive comment hints.
Directly dispatched specifics are included in the main program's module
imports, including the integer-array print specialization.

`--report-specializations` prints informational notes on stderr for arguments
specialized at multiple ranks. It is off by default, does not alter generated
semantics, and does not claim general support for dynamic-rank variables.
Unsupported cases retain existing diagnostics.

## Validation and remaining blocker

The checker extracts original functions without modifying their bodies and
exercises `roots_to_r8poly_test`, `r8vec_even_test`, and the original printer
with real vectors, real column matrices, and integer vectors. It retains raw
Python/Fortran outputs and build diagnostics. Run:

```cmd
python reports\r8poly_validation_20260924\check.py
```

The affected original tests and added calls compile with runtime checks and
match Python: 168 normalized tokens, with numeric tolerances of 1e-6 relative
and 1e-10 absolute. Version banners, whitespace and array brackets are ignored.

The full original program passes the former print-helper blocker but does
not yet compile. The next compiler error is in `r8poly_lagrange_factor_test`:
scalar `xval` is passed to the rank-one `xval` dummy of
`r8poly_lagrange_factor`. That mismatch also exists in the pre-fix generated
Fortran; it is not a claim of full-corpus success.

Regression tests check both call orders, positional/keyword calls, integer
and real inputs, single-profile callers, and opt-in/default diagnostic output.
All four new cases passed after the final import fix (109.74 seconds).
The preceding run passed all 12 selected existing specialization regressions;
its new-case import failure was corrected and covered by the final rerun.
Full pytest has not been rerun after these changes.
