# test_int_2d: Boolean square roots and numeric where conditions

## Reproduction

The saved audit failed while compiling `p04_fun`, which contains:

```python
i = np.where(np.sqrt(3.0 - x - 2.0*y != 0.0))
fx[i] = 1.0 / np.sqrt(3.0 - x[i] - 2.0*y[i])
```

The comparison inside sqrt is deliberate in this validation: the original
MIT-licensed Burkardt function bodies are copied unchanged into probe.py.
The similar p03_fun is included too. NumPy accepts Boolean sqrt input,
produces numeric zero/one values, and where selects their nonzero indices.

The current transpiler reproduced the invalid Fortran REAL(logical_array)
on this reduced probe. After conversion to real zero/one values, the
one-argument where path also needs an explicit numeric-to-logical conversion
for Fortran PACK's mask.

## Fix and validation

- NumPy sqrt now uses the existing kind-coercion helper for integer and
  Boolean inputs, emitting MERGE(1.0_dp, 0.0_dp, mask) for Boolean input.
- One-argument np.where now converts real/integer conditions to nonzero
  logical masks before PACK. Existing logical conditions remain logical.
- The reduced p03_fun/p04_fun probe compiles with runtime checks and
  floating-point traps and its output matches Python. The fixture includes
  a singular corner that must remain excluded (both results zero).
- Parametrized regressions cover Boolean sqrt, real/integer where conditions,
  negative nonzero values, direct and stored conditions, empty and all-zero
  selections, and tuple-style indexing of the result.

The transpiler uses its real(dp) numerical representation for these exact
0/1 values; this change concerns values and indexing, not dtype fidelity.

## Full-program status

The current full test_int_2d.py stops earlier with an explicit unsupported
mixed-rank diagnostic: p00_fun argument x is observed at ranks 1 and 2,
and rank-preserving specialization is unsupported for this function.
Thus this fix does not claim the full program compiles or runs. The reported
source location is line 1342 (return xlo, xhi, ylo, yhi); the diagnostic names
p00_fun, so that displayed location should not be mistaken for the offending call.
No original corpus file was changed.

## Reproduce

```cmd
python reports\test_int_2d_validation_20260921\check.py
python -m pytest -q -n 0 --reruns 0 tests\test_xp2f_cli.py -k "where_numeric_condition_and_boolean_sqrt or int_converts_boolean_expressions"
```

The checker recreates probe.log, full.log and analysis.json.
All four selected pytest cases passed in 179.36 seconds.
Full pytest was not run.
