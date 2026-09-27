# Discarded NumPy sort/flip results

Burkardt's `subset_sum_swap/subset_sum_swap.py` contains:

```python
# Sort into descending order.
np.sort(a)
np.flip(a)
```

Those calls do not implement the comment: Python discards the results without
changing `a`. The translator must preserve the executed Python, not silently
implement the apparent intent of its comments.

## Confirmed wrong-result reproduction

Before the fix, `probe.py` compiled and ran but disagreed with Python:

| Output | Python | Fortran before fix |
|---|---|---|
| After discarded sort | 3, 1, 2 | 1, 2, 3 |
| After discarded flip | 3, 1, 2 | 3, 2, 1 |

## Fix

Standalone `np.sort` and `np.flip` now operate on block-local copies. Inputs
are evaluated once, including calls with side effects. This preserves input
arrays, slices, and read-only function arguments. `a.sort()` remains in-place;
assigned NumPy calls are unchanged.

The standalone path supports rank-1/rank-2 inputs and constant integer or None
axes. Unsupported options, dynamic axes, and out-of-range axes are diagnosed
rather than silently ignored. Sort supports integer, real, and character
payloads; flip additionally supports logical and complex payloads. This is not
an expansion of the separate assigned-call implementation's axis support.

## Validation

- The original minimal reproduction now compiles, runs, and reports
  `Run diff: MATCH`.
- All **12 focused tests** pass after corrections: 8 new tests plus 4 existing
  in-place/self-assignment sort and nested-flip tests. Coverage includes empty
  inputs, matrices, axes, aliases, temporary-name collisions, slices, multiple
  element types, and single evaluation of side-effecting input calls.
- The full pytest suite was not run.

```bat
python -m pytest -q -n 2 --reruns 0 tests\test_xp2f_cli.py -k "discarded_numpy or handles_self_referential_np_sort or flips_result_of_nested_numpy_call or list_sort_in_place or numpy_self_assignment_repeat_sort"
```

## Full corpus status

The original sort-call compilation failure is gone. The unchanged full program
still fails later at `subset_sum_swap_try`'s call to `subset_sum_swap`: the caller
declares `xindex` as a scalar although it subsequently uses `xindex(i)` and
passes it as an output array. Gfortran reports `Invalid procedure argument`.
That separate selection-index output declaration issue is not fixed here, and full
program numerical agreement has not been claimed.
