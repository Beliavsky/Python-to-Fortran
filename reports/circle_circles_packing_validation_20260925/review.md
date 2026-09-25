# Circle packing: numeric while-condition truth conversion

The unchanged Burkardt `circle_circles_packing.py` initializes integer `guard`
to 5000 and loops with `while guard:`. A successful insertion resets the
counter; an unsuccessful trial decrements it. Python exits when it reaches
zero. Previously generated `do while (guard)` was rejected by gfortran because
Fortran requires a scalar logical condition.

`visit_While` now compares scalar integer, real, and complex conditions against
zero. Logical conditions are unchanged. The expression remains inside the
`do while` condition, so updates and function calls are reevaluated each time,
including after `continue` (Fortran `cycle`). Negative numbers are true, not
false. This change does not introduce array truth reductions or extend support
for strings, short-circuit compound conditions, or while-else clauses.

Regression coverage includes zero and positive/negative integer and real
counters, zero/nonzero complex counters, continue, a persistent-state numeric
function call, and a logical guard. A safety break bounds numeric-counter
tests if a future regression prevents termination.

## Full-source validation

Run:

```text
python reports\circle_circles_packing_validation_20260925\check.py
```

The checker copies the original source unchanged into its work directory,
builds with runtime checks, and records Python RNG draws for replay in Fortran.
It compares the parked-circle and trial counts exactly and both reported
densities with relative/absolute tolerance 1e-12. It also checks the trial
count includes the final 5000 unsuccessful attempts and the density equals
the parked count divided by 400 for the original R=20, r=1 case.

The comparison is of the four reported numerical results, not all intermediate
circle coordinates or byte-identical presentation. Timestamps and version
banners are not compared. Logs, copied source, RNG data, and generated files
are reproducible artifacts, not files required for commit.

The validation run passed: both languages reported 227 parked circles, 48,845
trials, observed density 0.5674999999999999, and reference jamming density
0.547. Counts match exactly; densities match within the stated tolerance.
The CLI's raw run-diff still reports the Python-version banner (`3.13.3`
versus `unknown`); the independent checker explicitly checks the four results.

All nine focused pytest cases passed with reruns disabled. `git diff --check`
passed. Full pytest was not run; it is the recommended next checkpoint.
