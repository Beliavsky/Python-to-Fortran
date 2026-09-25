# Significant lengths of string-sequence elements

## Confirmed failure

```python
for text in ['', 'a', 'abc', 'a ']:
    print(len(text))
```

Python prints lengths `0, 1, 3, 2`. The previous translation compiled and ran
but printed `3, 3, 3, 3`: all elements inherited the Fortran array's common
character length. `len_trim` cannot repair this, because it also removes
intentional trailing spaces.

## Fix

Literal-defined, read-only Python string lists/tuples with unequal element
lengths now carry a companion integer length array. A generated scalar-string
accessor accepts the data, lengths, and one evaluated Python index. It handles
negative indices, checks bounds, and returns only the original characters.
Ordinary scalar-string consumers retain their existing interfaces.

The lowering supports direct and named sequences, scalar indexing, iteration,
`enumerate`, read-only aliases, slices (including reversal), and rebinding to
another literal sequence. Data and lengths are snapshotted together when
iterating or copying aliases, so rebinding the original name does not change
an existing alias. Generated names avoid case-insensitive collisions.

The accessor's scalar-character result is made explicit to existing call-site
type inference, and its index arithmetic remains integer. Fortran still uses
a conventional character array for storage; its padding is not discarded
with `trim` or confused with actual spaces.

## Boundaries

This is not a replacement for every string container representation. Dynamic
construction (such as append-built lists), NumPy string arrays, and arbitrary
whole-sequence function interfaces retain their existing paths. Equal-width
literals and unused/static DataFrame column-label lists are left alone.

For sequences that opt into length tracking, mutation, unsupported whole-list
consumers/returns, global rebinding, and side-effecting slice bounds receive
an explicit diagnostic instead of silently invalidating lengths. Scalar
index expressions may contain calls: the accessor evaluates that index once.

## Reproduction

```bat
python reports\string_lengths_validation_20260925\check.py
```

- `probe.py` compares empty, short, long, trailing-space, and all-space values.
  It covers named sequences, positive/negative indexing, `enumerate` with a
  nonzero start, scalar function arguments, aliases surviving rebinding,
  slices/reversal, and generated-name collisions.
- Raw output is compared with delimiters around the strings, ignoring only
  outer Fortran indentation. Thus extra or missing spaces inside the values
  cannot be hidden by the normal run-diff whitespace tolerance.
- The original, unchanged FILUM `filename_inc` is tested using the mixed-length
  list driver that first exposed this problem. Outputs, character lengths,
  and code points now match Python, including intentional trailing spaces.
- Build products and source copies go under `work`; reproducible logs are
  saved beside this review. The original Burkardt source is never modified.

Focused pytest: **24 passed in 174.32 seconds**, followed by **2 passed in
109.65 seconds** for the final snapshot change (one repeated test and one new
test, 25 distinct tests total). Coverage includes out-of-bounds indices,
single index evaluation, iterator rebinding, legacy character-list
preallocation, renamed loop targets, and nullable-string compatibility.
The full pytest suite was not run.

The separate carry/wraparound error in the original FILUM Python algorithm
is not changed; the translation continues to match the source code.

A stress test also exposed recursive Fortran I/O when an index function that
prints is nested inside an outer `print(len(values[index()]))`. General I/O
hoisting is not addressed here. The evaluation-count regression uses
`chosen = values[index()]` followed by `print(len(chosen))`, verifying that
the index function runs once without conflating that separate limitation.
