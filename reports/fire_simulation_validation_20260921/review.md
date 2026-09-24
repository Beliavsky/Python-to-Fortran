# Forest-fire validation (2026-09-21)

## Outcome

No simulation defect was found in the deterministic cases tested. Python and
generated Fortran both match an independent distance-based oracle for 11 cases,
61 complete forest snapshots, and 1,107 output records per language.
These endpoint checks alone do not establish equivalence of random ignition
or intermediate spread probabilities. The replay follow-up below covers
intermediate probabilities with fixed ignition.

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

## Follow-up: intermediate probabilities with shared draws

`probe_replay.py` retains the same six original function bodies and tests
10 fixed-ignition cases with probabilities 0.2, 0.5 and 0.8. It covers
1x1, 3x3 and 6x6 grids with corner, edge and interior ignition, using explicit
NumPy seeds 101 through 110. A tagged random marker is drawn after the initial
state and each subsequent step. These markers deliberately consume draws:
the probe is a controlled test, not the original corpus random trajectory.

`check_replay.py` runs the current transpiler with `--rng-replay` and
`--run-diff`, saves the combined log, and independently parses both outputs.
Every cell, activity flag, termination count and marker matches exactly;
burned fractions match within absolute tolerance 2e-15.

It independently counts expected spread draws from the previous snapshot:
each smoldering tree becomes burning and draws once for each in-bounds
neighbor, regardless of the neighbor's state. The next marker must exactly
match the corresponding recorded binary draw in both languages. The final
cursor must consume the entire recording. This checks per-step stream
alignment, including the final step, rather than just comparing final totals.
Legal state transitions, burned fractions, and complete output are also checked.

Result: **PASS**, 10 cases, 76 snapshots, 2,464 records per language,
517 spread draws and 76 marker draws (593 total). Outcomes include early
extinction, partial burning and a fully burnt grid. No new transpiler defect
was found, and no transpiler or runtime helper changes were needed.

```cmd
python reports\fire_simulation_validation_20260921\check_replay.py
```

Evidence is saved in `replay_run.log`, `replay_analysis.json`, and the
generated replay metadata/binary files; the command recreates them.
Random ignition via `rng.integers` and RNG distribution quality remain
outside this validation. No full pytest run was needed for this report-only
follow-up.
