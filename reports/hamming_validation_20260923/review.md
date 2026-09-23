# Hamming: nested loops reusing a target

The original `hamming.py`, `ui4_to_ubvec_test`, uses `i` for both an outer
`range(11)` loop and an inner loop that prints binary-vector elements.
The former translation emitted nested `do i` loops, which Fortran rejects.

## Translation and warning

Affected range loops (including `enumerate(range(...))`) now have independent
block-local integer counters.
Each iteration assigns its counter to the Python-visible target. This allows
the inner loop to overwrite the visible value without changing the outer
iterator. An empty loop does not assign the target; normal completion leaves
the last assigned value rather than Fortran's post-loop counter value.

The CLI emits a nonfatal warning on stderr with the inner loop's source file,
line and column. It recommends a distinct variable name. Sequential loops,
comprehensions and loops in separate function scopes are not flagged. Tuple
targets are included in the diagnostic. This is not a general change to
all loop-target assignments or support for otherwise unsupported iterable types.

## Validation

Run `python reports\hamming_validation_20260923\check.py` to repeat the corpus
check (an optional argument supplies an alternative original source path).
The original source is not modified. The checker retains build/run logs and
creates a driver containing the original functions, omitting only the
top-level timestamp calls.

- The complete original program compiles with runtime checks enabled.
- Its original test suite matches Python after excluding version banners,
  whitespace, array brackets and equivalent numeric spellings.
- Seven initial pytest cases passed: ordinary/empty/descending inner ranges,
  target-dependent bounds, break/continue, inner list iteration, warning
  locations/counts, synthetic-name collisions and diagnostic scope checks.
- Ten follow-up cases passed, covering three-level nesting, an empty outer
  range, iterable outer loops, and existing renamed-target, enumeration and
  real-to-integer range-rebinding tests.
- The final nine nested-loop cases passed after adding reuse of either
  `enumerate(range(...))` tuple target and an enumerated outer loop.
  Across the three runs, 19 distinct selected cases passed (26 executions).

Full pytest has not been run for this change.
