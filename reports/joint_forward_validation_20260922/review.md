# Forwarding joint argument signatures through local calls

## Implementation

Caller bodies are rescanned separately for each observed specialization.
Complete signatures are propagated to local callees until stable, retaining
correlations between arguments rather than inventing their Cartesian product.
The existing rank-zero/one/two and stable-kind-per-position restrictions on
this specialization path remain; this does not add general recursion,
tuple/dictionary-result specialization, or arbitrary dynamic typing.

Result profiles are inferred in each specialization's call context, iterating
until callees and callers agree. Several older rank-recovery paths used the
shared array result even for a scalar specialization; they now respect the
matched result profile. Scalar calls no longer acquire artificial array
extents, and vector results no longer inherit a matrix result's rank.

## Validation

The probe's outer -> middle -> leaf chain uses all seven scalar/vector/matrix
pairings from the preceding report. None of the leaf calls is directly at
top level. Keyword forwarding is included. Loops prevent arithmetic inlining.
The executable compiles with runtime checks and matches Python's output.
The checker also inspects emitted specialization names.

Regression tests cover both caller-first and callee-first definition order,
all seven pairings, keyword arguments, result values/shapes, and a separate
forwarded reduction whose result must remain scalar. The former
unsupported-forwarding regression is replaced by these positive cases.

## Next corpus blocker

The complete test_int_2d.py passes the former p00_fun joint-forwarding blocker.
It now stops at p01_fun, line 637:

```python
i = np.where(1.0 - x * y != 0.0)
```

For matrix input, this requires a tuple of row and column index arrays.
The current one-argument where implementation supports only rank one.
It now reports that limitation explicitly rather than producing an invalid
PACK call with a rank-one ARRAY and rank-two MASK.
Three-argument np.where is unaffected. No corpus source was changed.

```cmd
python reports\joint_forward_validation_20260922\check.py
python -m pytest -q -n 0 --reruns 0 tests\test_xp2f_cli.py -k "forwards_joint_rank_profiles or rejects_multidimensional_where_indices or joint_scalar_vector_matrix_signatures or specializes_vector_matrix_calls or tridiagonal_vector_matrix_specializations or rejects_unspecialized_vector_rank3_calls"
```

The checker recreates probe.log, full.log and analysis.json. This is not a
claim that the full Burkardt program compiles or runs. Full pytest has not
been run for this change.

All 17 selected regression tests passed in 342.82 seconds, covering forwarding,
direct joint signatures, existing vector/matrix calls, the tridiagonal case,
and the two unsupported-rank/index diagnostics. A full-suite checkpoint is
recommended before extending matrix index tuples.
