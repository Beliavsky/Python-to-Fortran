# Matrix np.where indices

The previous explicit rejection of rank-2 one-argument `np.where` blocked
Burkardt's `test_int_2d.py`, after joint vector/matrix specialization was fixed.

## Implementation

- Store a named matrix index tuple as two rows of zero-based integer coordinates.
- Enumerate coordinates in NumPy row-major order, including empty selections.
- Gather paired coordinates for `a[indices]` and `a[np.where(condition)]`;
  do not use Fortran's Cartesian-product vector subscripts.
- Support real, integer, logical, and complex gathered values.
- Snapshot assignment values before scattering into the destination. Scalar
  values and length-one vectors broadcast; other vector lengths must match.
- Support named tuple components and direct `np.where(condition)[0]` / `[1]`.
- Retain the rank-1 path and three-argument elementwise `np.where` behavior.

## Corpus validation

Run `python reports\matrix_where_validation_20260923\check.py` (an optional
argument overrides the local Burkardt source path).

The focused probe matches Python. The complete original `test_int_2d.py`
compiles with runtime-checking compiler flags. All eight original integrands,
through their original `p00_fun` dispatcher, match Python on six deterministic
points supplied both as vectors and as nonsquare matrices. These include the
singular `(1, 1)` point excluded by the first four integrands. The checker saves
the extracted source, build/run logs, and `analysis.json` locally.

This does not claim validation of the complete integration driver, its random
sampling, or its largest grids.

Focused pytest validation: 12 tests passed across targeted runs (matrix
gather/scatter and diagnostics, existing three-argument where promotion, and
the three existing numeric-condition/Boolean-square-root vector cases).
Boolean and complex edge cases were rerun individually after adjustments.
The complete pytest suite was not run; it is the recommended next checkpoint.

## Remaining limits

This is support for local matrix index tuples, not general Python tuple support.
Direct tuple unpacking is now supported as described below.
Rank-3 conditions remain explicitly rejected. Tuple passing,
tuple returns, tuple display, and arbitrary independently constructed advanced
indices are not established by this validation.

Slicing a gathered expression directly, e.g. `a[indices][::-1]`, exposed a
separate expression-temporary limitation (a Fortran function result cannot be
subscripted that way). It remains outside this fix; assign the gathered vector
to a name before slicing it.

Additional exploratory Boolean tests exposed existing limitations in integer
literal construction with `dtype=bool` and in mixed Boolean/integer arithmetic.
The matrix-index regression uses Boolean literals and `np.logical_not` to
test logical gather/scatter independently of those issues.

## Tuple unpacking follow-up

Supports `rows, cols = np.where(matrix_condition)`, list targets, and unpacking
a named local matrix index tuple. Exactly two simple name targets are required;
starred/nested targets and incorrect arity receive an explicit diagnostic.
The complete right-hand side is evaluated once and saved before either target
is assigned, including when a target name is repeated.

Unpacked coordinates and their simple name aliases support paired reads inside
larger expressions and paired writes. Writes snapshot the RHS as before. The
coordinate helper checks incompatible lengths and supports length-one
broadcasting instead of silently truncating. This is still local matrix-where
support, not general tuple passing/returning or arbitrary advanced indexing.

`unpack_probe.py` checks a local function, a side-effecting condition (one
evaluation), list targets, temporary-name collision avoidance, all-selected
coordinates, coordinate aliases, and overlapping writes. Pytest also checks
direct/named tuple unpacking, empty selections, repeated targets, length-one
RHS broadcasting, and incorrect arity.

Follow-up validation: all 9 selected pytest cases passed across two runs.
The updated checker reports MATCH for both probes and all eight original
integrands on vector/matrix inputs; the complete original corpus program still
compiles. The full pytest suite has not been rerun.
