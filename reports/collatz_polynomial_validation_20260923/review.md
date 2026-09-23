# Collatz polynomial: resizing a rebound parameter

The current original `collatz_polynomial.py` failed to compile at
`call collatz_polynomial_sequence(real(p0, kind=dp))`: the generated callee
required an allocatable `intent(inout)` actual argument. Python's
`p = collatz_polynomial_next(p)` rebinds the local name, not the caller's array.

## Fix

Keep nonoptional rebound array parameters as assumed-shape inputs and reuse
the existing local allocatable shadow mechanism. Array growth/shrinkage occurs
in the local copy, not in the dummy argument. Count-mapped local rebinding also
must not impose an allocatable requirement on the caller. Optional-argument
handling and synthetic count-mapped output arguments retain their existing
paths. Ordinary element updates still use caller-visible mutation.

The old regression that required an allocatable INOUT dummy for `a = []` has
been corrected to require an input dummy and local allocation. It now compiles
and runs, checking that the caller retains its original length and elements.

## Validation

Run `python reports\collatz_polynomial_validation_20260923\check.py` (an
optional argument overrides the local Burkardt source path).

- The complete, unchanged original program compiles with runtime checks.
- All original test functions execute in a driver that omits only top-level
  timestamps; their output agrees after excluding version banners, whitespace,
  array brackets, and equivalent numeric spellings. Raw logs are retained.
- An added original-sequence call verifies the caller's polynomial stays intact.
- The focused ownership probe covers growth/shrinkage, integer-to-real input
  conversion, array sections, temporary expressions, and an ordinary in-place
  element update. Its integer-valued data match Python.
- Eleven selected pytest cases passed across the initial run and a focused
  rerun. These include empty rebinding, count-mapped outputs, shadow-copy
  elimination, reserved parameter names, and reshape rebinding.
- The full pytest suite has not been run; it is the recommended checkpoint.

This change does not implement general alias tracking when mutation and
rebinding are interleaved, nor new optional-parameter semantics.

## Separate wrong-result follow-up

A fractional version of the ownership probe exposed an independent kind-
inference problem. `grow` and `show` are given integer dummy arrays even when
their actual arguments contain real values; emitted `int(p_local)` conversions
truncate `7.25` to `7` and `1.5` to `1`. Adding annotations or explicit real casts
at those calls did not resolve it in exploratory checks.

The checker recreates `fractional_probe.py` by changing the focused probe's
values and saves its build/run output separately. This case is recorded as
`DIFF`, not a numerical success. The focused ownership regression uses
integer-valued data to isolate the rebinding fix; it does not establish general
fractional-value correctness. The fractional argument-kind bug is a higher-
priority follow-up than formatting differences because it silently changes
results.

No original Burkardt source was edited.
