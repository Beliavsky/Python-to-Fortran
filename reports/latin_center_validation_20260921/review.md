# Latin-center validation (2026-09-21)

## Outcome

Found and fixed an empty-permutation runtime defect. The original audit's
nonempty random-output differences do not establish a translation defect.
After the fix, all 21 probe cases pass independently in Python and Fortran:
3,981 output records per language.

## Reproduction and fix

`probe.py` preserves John Burkardt's MIT-licensed `latin_center` function
from the local corpus and adds a tagged-output driver. Calling
`latin_center(3, 0)` returns an array of shape (0, 3) in Python, but generated
Fortran stopped with `STOP random_choice_norep: invalid sizes`.
The executable returned zero despite stopping early; the checker detected
the missing output records.

The shared `random_choice_norep` helper rejected population size zero
even when the requested sample count was also zero. Both `python.f90`
and the helper template in `xp2f.py` now allow zero population and return
immediately for zero samples, after validating sizes and output capacity.
Negative sizes and requesting more samples than the population remain rejected.

## Checks

Run from the repository root:

```cmd
python reports\latin_center_validation_20260921\check.py
```

The driver repeats these (dimensions, points) cases three times:
(1, 1), (5, 1), (1, 17), (2, 10), (7, 31), (3, 0), (4, 100).
The checker compiles with runtime checks and floating-point traps, then verifies:

- Correct matrix shape and complete output.
- Finite coordinates strictly inside (0, 1).
- Each column contains every midpoint (i + 0.5) / n exactly once,
  within absolute tolerance 2e-15.
- The corpus test's `x[np.lexsort(x.T[::-1])]` expression gives precisely
  the order computed independently by Python tuple sorting.

The pytest regression covers empty integer and array permutations, zero-size
sampling without replacement from empty and nonempty populations, and a
singleton permutation, through both NumPy's module API and Generator API.
Both new parametrized tests passed (59.03 seconds); the three existing
permutation-rank and real-key sorting tests also passed in the preceding run.
The runtime helper text was checked against its template and matches exactly.

This validates the stated invariants, not identical random streams or the
statistical uniformity of permutations. Generated logs and analysis.json are
recreated by the checker. The full pytest suite was not run for this change.
