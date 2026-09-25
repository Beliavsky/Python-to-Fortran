# EROS PLU investigation while the main pytest run is active

Work is isolated in `xp2f_copy.py`. At creation, both transpiler files had
SHA256 `43fd40ecb0b9603d485ac04b0c6bd73948c8990a6484c086a4a82302735ed3c1`.
The main transpiler, existing tests, and shared helper sources are not changed.
All compilation uses this report's work directory and local helper copies.

## Confirmed translation mismatch

`view_probe.py` demonstrates that a NumPy basic slice is a view:

```python
t = a[0, :]
a[0, :] = a[1, :]
a[1, :] = t
```

Starting from rows `[1,2]` and `[3,4]`, Python finishes with two `[3,4]` rows.
The original generated Fortran uses value assignments and instead finishes
with `[3,4]` and `[1,2]`. Both programs compile/run; their results differ.
This is a translator limitation, even though the Python pattern also fails
to implement the swap its author probably intended.

The working copy adds a bounded rejection for three consecutive assignments
with this multidimensional basic-slice swap shape. The error explains the
aliasing problem and recommends `.copy()` only if snapshot/swap semantics
are intended. It does not silently change Python semantics or implement
general view support. It recognizes literal indices and a small set of
provably scalar function-local index expressions (range targets and argmax/
argmin-derived arithmetic). Named advanced array indices and one-dimensional
Python-list slices are not treated as evidence for this diagnostic. Other
aliasing patterns can still be unsupported without being diagnosed.

Both the small probe and full original EROS source now receive that diagnostic
from the copy. The main transpiler remains unchanged.

## Independent source issues

Diagnostic variants of `gauss_plu` are generated under work; the corpus file
is never edited. On the deterministic 3x3 example:

- Original routine, floating-point input: residual 10.908712114635714 and
  duplicate rows in P.
- Explicit `.copy()` swap temporaries, floating-point input: residual
  16.156703330197036. This matches the earlier Fortran result but is still
  not a valid factorization.
- Also correct zero-based pivot offset from `p + j - 1` to `p + j`, and swap
  the previously computed L columns `0:j` rather than `1:j`: Python residual 0.

The original first driver uses integer input. Its `U = A.copy()` therefore
retains integer dtype in Python and truncates fractional row updates. The
diagnostic variants explicitly use floating-point input for elimination.
These source corrections are separate from preserving valid Python aliasing
semantics in the translator.

## Standalone checks

```text
python reports\eros_copy_validation_20260925\check_diagnostic.py
python reports\eros_copy_validation_20260925\check.py
```

The first checks diagnostic boundaries without pytest. The second checks
rejection of the unsafe view swap, successful explicit-copy translation, and
the corrected floating-point PLU example. It does not certify the full original
EROS suite or its ill-conditioned inverse tests. No new full pytest run is
started, and no patch has been transferred back to `xp2f.py`.

Results: all nine diagnostic boundary cases passed; the unsafe probe was
rejected; the explicit-copy swap compiled/ran with matching output; and the
corrected floating-point PLU example matched Python's residual and permutation
matrix (ten numerical values, residual below 1e-12). The main transpiler hash
still matched the value recorded above after this work.

## Transfer after the full pytest checkpoint

After the user reported a regression-free full pytest run, the diagnostic was
transferred to `xp2f.py`. Nine boundary cases plus CLI rejection and an
explicit-copy compile/run comparison were added to `tests/test_xp2f_cli.py`.
Both standalone checkers now use the main transpiler. The experimental copy
was retained, not deleted; it is no longer needed by these validation scripts.
This remains a diagnostic for the bounded unsafe pattern, not general NumPy
view support or a correction of the original EROS algorithm.

Transfer validation: all 11 focused pytest cases passed with reruns disabled.
The standalone compile/run checker passed using `xp2f.py`, and the original
EROS source received the expected diagnostic at its first unsafe swap. No
additional full-suite run was started. The two transpiler files have identical
text according to git diff (their raw hashes differ because of line endings).
