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

## Burkardt validation and next blocker

`chuckaluck_simulation/chuckaluck_simulation.py` contains the same pattern:

```python
match = np.count_nonzero(dice == spot)
```

`check.py` extracts the unchanged `chuckaluck_payoff` function and supplies a
deterministic driver covering six chosen numbers and all 216 three-dice
rolls (1296 cases). It saves generated source and build/execution logs in
a printed temporary directory.

The default translation encounters a separate problem: comment inference
declares `dice` scalar despite the source comment `integer dice[3]` and the
array-valued actual argument. `--ignore-comments` makes it an array and
allows compilation. To isolate this reduction fix, run:

```bat
python reports\count_nonzero_validation_20260926\check.py --ignore-comments
```

With that flag, compilation and execution passed and all 1296 payoffs
matched Python exactly.

Omitting the flag reproduces the comment-rank blocker. This validation is
of the extracted payoff function, not the complete randomized simulation.
Neither the Burkardt source nor comment inference was changed.
