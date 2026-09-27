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

The original sort-call compilation failure exposed a second failure at
`subset_sum_swap_try`'s call to `subset_sum_swap`: the caller declared `xindex`
as scalar although it subsequently used `xindex(i)` and passed it as an output
array. Gfortran reported `Invalid procedure argument`.

That follow-up is now fixed. Comment-based tuple-result refinement retained
the array rank but changed its kind tag from `alloc_real` to `real`. Caller
declaration inference treats that plain kind as scalar and discarded the rank.
Refinement now retains the array-kind encoding for every positive-rank result,
across integer, real, logical, complex, and character kinds. The problem was
not specific to the reserved name `index`.

The unchanged full program now compiles, runs, and matches Python on **all seven
problems**, including available/selected weights, achieved sums, and defects.
Only timestamps, version banners, and whitespace are excluded from comparison.
The misleading source comments about sorting remain unchanged; comparison is
against the executed Python, not an amended algorithm.

```bat
python reports\subset_sum_swap_validation_20260926\check.py
```

The checker copies the original source into a fresh temporary directory and
saves build, Python, and Fortran logs there. It prints the artifact directory.
No changes are made to the Burkardt source.

Follow-up regression testing: **16 passed** (8 new vector cases in 158.83
seconds, then 8 matrix/character and related tuple/scalar cases in 164.71
seconds). Fractional matrix values check that an integer comment does not
truncate real results. Both `index` and an ordinary variable name are covered.
The full pytest suite was not run.
