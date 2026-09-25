# CHRPAK integer-to-character rebinding

Source: `C:/python/public_domain/burkardt/chrpak/chrpak.py` (John Burkardt).
The corpus source is unchanged.

## Failure and fix

`ch_to_rot13` assigns integer arithmetic results to `value` in every branch,
then does `value = chr(value)` and returns the character. Previously the final
character type was applied to the earlier assignments, causing gfortran's
"Cannot convert INTEGER(4) to CHARACTER(0)" error.

The transpiler now gives the integer lifetime a collision-free local name
(`value_code` here), keeping `value` for the character result. It emits a
nonfatal source-line warning recommending separate names for the two types.
The conversion still happens exactly once, after the integer computation.

This is a bounded rewrite of a local variable's final straight-line `chr`
conversion, with a definitely integer value on all incoming branches. It does
not implement arbitrary mixed-type state, loop-carried conversions, captured
or global variables, or Unicode support. Later reassignment, early returns,
and shadowed builtins are excluded from this rewrite. Unsupported patterns
remain subject to the existing translator checks.

## Reproduction and validation

Run `python reports\chrpak_validation_20260925\check.py` (optionally pass a
different path to the corpus source). Generated sources/build products stay
in `work`; logs are generated beside this review.

- The original, unchanged `ch_to_rot13` function compiles and matches Python
  for all 95 printable ASCII characters, including digits (ROT5), letters
  (ROT13), spaces, and punctuation. Applying it twice restores each input.
- The full original `chrpak.py` now compiles with runtime checks enabled.
- The CLI regression also checks collision avoidance and a single warning.
  AST boundary tests cover incomplete branch assignment, noninteger values,
  subsequent reassignment, loops, globals, closures, early returns, and
  shadowed builtins.

- Both full-program executions (Python and generated Fortran) exit with code
  zero and report normal completion. This is a runtime smoke check, not a
  claim that all full-program output has been numerically/textually validated.
  Exact output comparison above applies to the isolated ROT13/ROT5 routine.
- Focused pytest: **20 passed in 129.40 seconds**, covering the new tests,
  existing `ord`/`chr` support, branch type rebinding, and enclosing-block
  rebinding. The full pytest suite was not run for this change.
