# Boolean inputs to np.count_nonzero

The Jaccard follow-up exposed a distinct reduction bug, still present after
commit `2f2b926`. For logical arrays `a` and `b`, this valid Python:

```python
np.count_nonzero(a & b)
```

became invalid Fortran:

```fortran
count((a .and. b) /= 0)
```

Fortran requires a logical array mask for COUNT. Boolean input is already
such a mask and must not be compared with integer zero. The lowering now
checks the input expression's inferred element kind, as the adjacent
ALL/ANY lowering already does. Numeric input retains the nonzero comparison.

## Regression coverage

Five new compile-and-Python-output-comparison tests passed in 116.03 seconds,
with reruns disabled. They cover:

- Boolean array names, local function arguments, inline AND/OR/NOT,
  comparisons, combined comparisons, and `np.isfinite` results.
- Directly imported/aliased `count_nonzero`.
- Boolean, integer, real, and complex matrix inputs.
- Keyword `axis=0` and `axis=1`, including `keepdims=True`; result shapes
  and each element are compared to Python on a nonsquare matrix.
- Empty Boolean vectors and zero-row matrices.

Ten related ALL/ANY, Boolean SUM/conversion/comparison, and set tests also
passed in 194.74 seconds with reruns disabled. Total: 15 focused tests passed.
The full pytest suite was not rerun.

This is a mask-type fix, not a generalization of the reduction API. Existing
handling of positional axes, negative/tuple axes, scalar inputs, and string
truthiness is outside this change. The axis tests use the explicit,
nonnegative keyword axes described above.

## Burkardt validation and the subsequent rank fix

`chuckaluck_simulation/chuckaluck_simulation.py` contains the same pattern:

```python
match = np.count_nonzero(dice == spot)
```

`check.py` extracts the unchanged `chuckaluck_payoff` function and supplies a
deterministic driver covering six chosen numbers and all 216 three-dice
rolls (1296 cases). It saves generated source and build/execution logs in
a printed temporary directory.

Initially the default translation encountered a separate problem: `dice`
was declared scalar despite the source comment `integer dice[3]` and the
array-valued actual argument. `--ignore-comments` made it an array and
allowed compilation. The initial reduction-only validation used:

```bat
python reports\count_nonzero_validation_20260926\check.py --ignore-comments
```

With that flag, compilation and execution passed and all 1296 payoffs
matched Python exactly.

### Comment-rank follow-up (2026-09-26)

The square-bracket parser already recognized `dice[3]` as rank 1. The bug
was later in procedure emission: a fallback intended to repair stale array
comments for scalar code reset the argument rank to zero. It used a list
of array operations that omitted `count_nonzero`, even when call-site
observations already established an array argument.

The fallback now preserves caller-observed array ranks. Explicit overload
signatures take precedence over observations belonging to other overloads,
and elemental procedures retain scalar dummies. This avoids growing the
list of recognized reductions for each similar case. User comments are
still hints: stale array comments do not prevent genuine scalar calls.

Default validation now passes without a workaround:

```bat
python reports\count_nonzero_validation_20260926\check.py
```

All 1296 payoffs match Python exactly with comment inference enabled.
Regression cases cover bracketed and parenthesized vector/matrix comments,
scalar-looking comments with array callers, ALL/ANY and an imported
COUNT_NONZERO alias, stale array comments on scalar calls, and mixed
scalar/vector specialization. The parser itself was not changed.

All 16 new rank-parser and compile/run regressions passed in 169.84 seconds,
with reruns disabled. Another 23 related reduction, broadcasting, comment,
loadtxt, overload, and elemental tests passed in 465.92 seconds, also with
reruns disabled: 39 targeted tests for this rank fix. No full-suite rerun.

This validation is of the extracted payoff function, not the complete
randomized simulation. The Burkardt source is unchanged.
