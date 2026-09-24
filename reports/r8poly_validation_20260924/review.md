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

## Scalar broadcasting follow-up

The `r8poly_lagrange_factor` mismatch above is now fixed. Two inference paths
incorrectly promoted a parameter to the rank of the other operand of `+` or
`-`. In `np.prod(xval - xpol[:])`, the expression is a vector but `xval` is
scalar; broadcasting does not impose equal operand ranks. Removing this
assumption preserves scalar `xval`, `term`, and the derivative result.
Direct indexing, documented array evidence and call-site argument ranks
continue to establish array shapes.

The checker now also runs the unchanged original
`r8poly_lagrange_factor_test`. All 256 normalized output tokens match Python,
using the same comparison exclusions and tolerances as above. New tests
cover both operand orders for addition/subtraction with vector and matrix
inputs, and verify that a separate scalar tuple result remains scalar.
All 14 selected broadcasting and joint-rank/forwarding regression cases passed
in 168.70 seconds. Full pytest has not been rerun for this follow-up.

The complete original program now stops at `r8poly_division_test`: its `nq`
actual is real while `r8poly_division` declares integer output `nq` (the same
disagreement exists for `nr`). These declarations also appear in the previous
generated file. Full-program compilation/execution remains unvalidated; the
focused Lagrange-factor and print/root tests above do pass.

## Tuple-output kind follow-up

The `nq`/`nr` mismatch above is now fixed. The final tuple-output refinement
used provisional helper-return profiles from before argument-kind inference.
It therefore widened the caller's output variables to real even though the
resolved degree helper and emitted division outputs were integer.

Refinement now uses the resolved scalar and tuple return kinds and ranks.
It does not force all documented integer outputs to integer or suppress real
evidence. The checker now includes the unchanged `r8poly_division_test`;
all 528 normalized tokens match Python using the comparison policy above.

Validation: 17 focused pytest cases passed (8 main tuple-output cases and 9
sentinel/feedback/callback/returned-parameter cases). The complete original
`r8poly.py` now compiles with runtime checks and runs successfully. Its 4,826
normalized tokens match Python at displayed precision. The source mixes `%f`
and `%g`; the full-program comparator permits half a unit in the last printed
decimal place of Python floating tokens, with the existing 1e-6 relative and
1e-10 absolute baseline. Integer-looking tokens get no decimal-rounding slack.
Recognized timestamp lines and version banners are excluded; raw outputs
remain in `full_python.stdout` and `full_fortran.stdout` (with separate stderr).

The checker's optional `--full-exe PATH` compares an already compiled original
executable in addition to rebuilding/running the focused probe. It does not
assert that an arbitrary supplied executable came from the current source.
The executable used here was freshly built from the unchanged original source
with the current transpiler. Full pytest is the next recommended checkpoint.
