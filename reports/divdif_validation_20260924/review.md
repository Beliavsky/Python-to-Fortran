# Divided-difference forwarding-rank inference

## Fixed blocker

The full original Burkardt `divdif.py` failed compilation because the
`data_to_dif` generic contained supposedly scalar and vector `ytab`
specializations, both actually declaring `ytab(:)`.

Tracing the early call scan identified the forwarding call in
`data_to_r8poly`: its `xtab` and `ytab` formals were reported as rank zero,
despite documented vector shapes. The helper for unassigned formal names
returned their numeric kind with a hard-coded rank zero. That provisional
scalar profile survived the later inference passes into specialization.

The helper now preserves rank evidence from the formal's observed callers,
body usage, and declaration-style comments. It does not use a same-named
global's rank. The corrected full translation emits a single `data_to_dif`
procedure; no duplicate overload is merely deleted after emission.

Four regression cases cover positional and keyword forwarding, with the
wrapper both called and uncalled. An uncalled wrapper still matters because
its source is analyzed and emitted. The original function copies the input
before indexing it, so direct indexing of the input itself cannot be relied
on to rescue the incorrect scalar inference.

## Numerical validation

`check.py` extracts four unchanged original functions: `data_to_dif`,
`data_to_r8poly`, `dif_to_r8poly`, and `r8vec_is_distinct`. It checks values
from the polynomial `1.25 - 0.5*x + 2*x*x` at `[-1, 0, 2]`.

The divided-difference coefficients are `[3.75, -2.5, 2]`; conversion to
ordinary coefficients gives `[1.25, -0.5, 2]`. Both input arrays remain
unchanged. Python agrees with these known values, and the generated program
compiles, runs, and reports `Run diff: MATCH`.

```console
python reports\divdif_validation_20260924\check.py
```

The checker saves `run.log` and generated artifacts under `work/`; those
generated files need not be committed.

## Next full-program blocker

The complete original program is **not yet validated**. Compilation now
reaches `dif_value`, whose real scalar and vector specializations both emit
vector formals and cause another ambiguous generic interface.

Unlike `data_to_dif`, `dif_value` genuinely receives both scalars and vectors.
It normalizes `xv` with `np.atleast_1d(xv)` and returns a scalar when the
result has length one. Its comments describe the normalized vector shape.
The next investigation must distinguish the input's rank from the rebound
local array's rank, and account for the size-dependent return rank; simply
discarding a valid scalar specialization would be incorrect.

Validation: 24 focused pytest cases passed with reruns disabled (14 new and
existing forwarding/specialization/tuple-expression cases, plus 10 scalar
broadcasting and scope-shadowing cases). Full pytest has not been rerun for
this change.
