# Set comparisons and set_theory validation

## Fixed

Burkardt's `set_theory/set_theory.py` failed to compile at `if I < A:`:
the generated array comparison was not a scalar logical condition.

Set `<`, `<=`, `>`, `>=`, `==`, and `!=` now return scalar logical values.
Subset tests use an empty set difference; proper subsets additionally require
smaller cardinality. Equality requires inclusion and equal cardinality, not
matching array order. Superset tests reverse the operands.

The change preserves NumPy's elementwise comparisons and accounts for local
set arguments, scalar result ranks, helper imports, and procedure purity.
Character set difference/symmetric-difference expressions retain their element
kind. Integer/character sets are disjoint; empty sets compare correctly even
when their internal element types differ.

Testing reversed integer input also exposed an existing `unique_int` bounds
error: Fortran need not short-circuit `j >= 1 .and. tmp(j) > key`. Its insertion
sort now checks the bound before accessing `tmp(j)`. The pre-existing purity
edits to `append_strvec` and `str_split` were preserved, not changed by this fix.

## Validation

The unchanged full Burkardt source compiles and runs. Checks against Python
confirm 13 printed sets, cardinality, 11 membership results, and the proper
subset result. Set order, timestamps, and version banners are not compared.

```bat
python reports\set_theory_validation_20260926\check.py --allow-known-pop-bug
```

The script stores the copied source, generated Fortran, and build/run logs in
a newly created temporary directory printed at startup. Without the explicit
flag it fails on the remaining pop bug; it does not claim a complete pass.

Focused regression coverage includes all six operators, reversed ordering,
same-size unequal sets, empty sets, character sets, cross-kind sets, a local
function returning a comparison, named chained comparisons, ordinary NumPy
comparisons, and unsupported/ambiguous operand diagnostics.

Final focused runs: **18 passed** (7 in 222.93 seconds; 11 in 157.53 seconds).
The full pytest suite was not run.

```bat
python -m pytest -q -n 2 --reruns 0 tests\test_xp2f_cli.py -k "set_comparison or set_arguments_forwarded or set_results_and_local or set_analysis_preserves"
python -m pytest -q -n 2 --reruns 0 tests\test_xp2f_cli.py -k "set_comparison_limitations or ambiguous_set or set_provenance_tracks or local_function_named_set or logical_numeric_comparison or chained_comparison_expressions"
```

The first run preceded addition of the two diagnostic tests (now also selected
by its broader `set_comparison` filter); those two passed in the second run.

## Remaining runtime blocker: pop hoisted outside a loop

The original five `J.pop()` calls incorrectly return `41` five times. Generated
Fortran removes one element before entering the loop and reuses its saved value
on every iteration. Python must remove and return five distinct members of
`{1, 6, 11, 31, 41}`; their order is not prescribed.

`pop_repro.py` reduces this to three elements. Its generated Fortran likewise
executes the removal before the loop, then prints the saved `3` three times.
This separate statement-placement bug is not fixed here.

## Boundaries

- Set payloads remain homogeneous integers or characters; this does not add
  general Python object sets or floating-point sets.
- Existing fixed-width character helpers do not distinguish strings differing
  only in significant trailing blanks; that representation limitation remains.
- Arbitrary function calls in comparison operands are diagnosed: assign their
  results to variables first, so lowering does not duplicate side effects.
  Chained set comparisons currently require named operands.
- Set/non-set comparisons are diagnosed rather than emitted as array
  comparisons, including Python-valid equality against a list.
- Ambiguous set/array provenance across calls or branches is diagnosed.
