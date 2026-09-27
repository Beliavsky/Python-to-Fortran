# Partition-greedy argsort purity

The unchanged Burkardt `partition_greedy/partition_greedy.py` failed with:

```text
Error: Subroutine call to 'argsort_int' at (1) is not PURE
```

The generated partition function is pure, but the runtime's `argsort`
subroutines and recursive merge-sort workers lacked PURE declarations.
The sorting operation has no external side effects: it reads the input,
writes explicitly declared output/work arrays, and uses local allocation.

## Fix

Declare both integer and real argsort subroutines, their recursive workers,
and their array-returning wrappers pure. Replace the two undersized-output
STOP statements with ERROR STOP, which is permitted in pure procedures.
The diagnostic remains explicit and now terminates with error status.
No sorting algorithm or transpiler code changes are needed.

## Validation

The unchanged full driver compiles and runs. All six problems match Python,
including item assignments, subset sums, and discrepancies. Comparison
ignores only timestamps, version banners, blank lines, and whitespace.

```cmd
python reports\partition_greedy_validation_20260927\check.py
```

The checker copies the source into a fresh temporary directory and saves
build and execution logs there. The source is not modified.

New regressions cover integer and real local-function translation and
explicit pure Fortran callers of both helper APIs, stable duplicate-value
ordering, empty and singleton inputs, and undersized-output diagnostics.
The helpers retain stable sorting; this does not imply NumPy's default
quicksort promises the same tie ordering on every input or platform.

Final focused results: four new cases passed (two direct-helper tests in
109.42 seconds and two translation tests in 76.70 seconds), plus three
existing unique/sort regressions passed. Reruns were disabled. Initial
test-fixture issues (private kind import, missing LAPACK link dependency,
and an assertion on inlined-away functions) were corrected before the
final runs. The full pytest suite was not run.
