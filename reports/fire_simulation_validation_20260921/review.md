# Forest-fire validation (2026-09-21)

## Outcome

No simulation defect was found in the deterministic cases tested. Python and
generated Fortran both match an independent distance-based oracle for 11 cases,
61 complete forest snapshots, and 1,107 output records per language.
The original random case remains only partially validated: these checks do
not establish equivalence of random ignition or intermediate spread probabilities.

## Method

`probe.py` retains the six MIT-licensed Burkardt functions used by the
simulation without changing their bodies: `fire_spreads`, `forest_burns`,
`forest_initialize`, `forest_is_burning`, `get_proportion_burned`,
and `tree_ignite`, plus the original four state constants.
The driver uses fixed ignition positions and spread probabilities zero or one.
Random draws still occur inside the original functions, but cannot affect
the Boolean spread decision at these endpoint probabilities.

The cases cover singleton, 2x2, 4x4 and 5x5 forests; center, corner and edge
ignition; and a 3x3 forest with no ignition. Every cell is printed before
ignition and after every step, together with activity and burned fraction.
A step bound prevents a broken termination condition from running forever.

For probability one, the oracle uses Manhattan distance d from the ignition:
at step d a cell is smoldering, at d+1 burning, and from d+2 onward burnt.
For probability zero, only the ignited cell changes state. This avoids
duplicating the source's neighbor-update loops in the reference checker.
State values, activity, and termination counts are exact checks; burned
fractions use absolute tolerance 2e-15.

## Conversion defect found in the probe

The probe initially failed to compile at
`int(forest_is_burning(n, forest))`. The transpiler emitted Fortran
`int(logical_expression)`, which is invalid. This conversion was added by
the probe driver; it is not present in the original Burkardt simulation.

The built-in `int` conversion now emits `merge(1, 0, expression)` when
the argument is logical. A focused regression exercises constants, variables,
Boolean-array elements, comparisons, negation, and local Boolean-returning
function calls, alongside unchanged numeric conversions.

## Reproduction

```cmd
python reports\fire_simulation_validation_20260921\check.py
python -m pytest -q -n 0 --reruns 0 tests\test_xp2f_cli.py -k "int_converts_boolean_expressions or logical_numeric_comparisons"
```

The checker saves Python, compiler, and executable logs plus analysis.json.
Compilation uses runtime bounds checking and floating-point traps.
Missing records and STOP messages are failures even with exit status zero.
All three selected pytest cases passed in 51.42 seconds.
No full pytest run was performed.
