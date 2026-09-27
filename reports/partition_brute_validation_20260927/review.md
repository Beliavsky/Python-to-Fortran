# Partition-brute integer and Boolean subset arrays

The unchanged `partition_brute/partition_brute.py` passed integer arrays to
`subset_next`, whose comments describe Boolean arrays. Other callers actually
pass Boolean arrays. Python permits both: assigning True/False to an integer
NumPy array stores 1/0 without changing its dtype.

Before the fix, translation failed with an INTEGER-to-LOGICAL argument mismatch.
Comment-based inference collapsed the observed integer and Boolean array calls
into a single logical signature. The overload selection now preserves observed
array kinds using the same comment-refinement rule as declaration emission.
Numeric array storage is not changed to logical solely because of a comment.
Scalar comment handling is unchanged.

This exposed an element-kind issue in a caller: a block-local logical array
shadowed an outer integer declaration, but indexed truth tests consulted the
outer declaration and emitted a logical-to-integer comparison. Indexed element
kind inference now honors active dtype-rebinding blocks, as whole-name inference
already did.

The integer specialization uses numeric truth tests and explicit Boolean-to-
integer conversion. The logical specialization uses logical tests/assignments.
No changes were made to the Burkardt source or the Fortran runtime.

## Full corpus validation

```cmd
python reports\partition_brute_validation_20260927\check.py
```

The original full driver compiles and runs. All six partition assignments,
their sums/discrepancies, all six solution counts, and the subset enumeration
match Python. Only timestamps, version banners, blank lines, and whitespace
are excluded from comparison. The checker preserves build and execution logs
in a fresh temporary directory and prints its location.

New regressions cover integer/Boolean callers with Boolean comments, integer
comments, or no type comments, and both named and expression-valued tuple
returns. Caller-side tuple metadata now preserves a returned, non-rebound
array argument's specialized dtype even when another tuple element is an
expression. Related tuple-array, rank-overload, and fractional-value regressions
are also checked. Full pytest is left to the user.

Final focused validation: **18 passed**, with reruns disabled (6 new cases in
179.26 seconds and 12 related cases in 199.28 seconds). The full corpus checker
also passed again after the final changes.

## Separate follow-up

`single_result_repro.py` records a distinct limitation found during testing:
a single-argument helper returning its mutated array to the same caller variable
can acquire a spurious real specialization and conflicting logical signatures.
The tuple-return fix here does not claim to resolve that single-result inference
path. Expected Python output is `1 2 1 1`.
