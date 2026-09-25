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

## Runtime-dependent result rank: diagnostic and alternative API

The original `dif_value` remains unsupported. Input-rank specialization is
not enough: even a vector input returns a scalar when its length is one,
and a vector when its length is zero or greater than one. Merely correcting
the scalar overload's dummy declaration would not make that result faithful.

The transpiler now rejects the terminal pattern `if condition: y = y[0]`
followed by `return y` when the inferred result variable is rank one. The
diagnostic identifies the function and the source assignment and suggests a
fixed-rank result or separate scalar and array entry points. This is a narrow
guard, not general detection or support for all dynamic-return-rank code.
String indexing, sliced vector results, and local changes not returned by
the function are not rejected by this guard.

The full source now fails translation with `runtime-dependent return rank
in function 'dif_value'` instead of proceeding to the ambiguous-interface
compiler error. Neither scalar/vector input normalization nor general
dynamic result support is claimed fixed by this change.

The checker additionally constructs an explicitly **adapted**
`dif_value_vector` from the original algorithm: the input must be a vector,
and the output always remains a vector. A separate `dif_value_scalar` wraps
one scalar in a length-one array and extracts the single result. This changes
the interface intentionally; it does not modify or validate the original
mixed-rank API. Both entry points match Python and known polynomial values,
including empty, singleton, and three-element vector cases.

Validation for this follow-up: 6 new diagnostic/unit cases passed on the
final run, and 7 existing real-sentinel and rank-rebinding cases passed.
The initial unit tests attempted to construct a translator without its
required global setup; those 4 test-setup failures were corrected by using
a minimal rank-query stub and all 4 passed on rerun. Reruns were disabled
in pytest. The adapted evaluator and original kernels report `Run diff:
MATCH`. Full pytest is the next checkpoint.

## Bounded singleton-result specialization

The unchanged `dif_value` is now supported when the caller's input is provably
a scalar or a vector of known length. A conservative AST prepass creates
separate scalar-input, singleton-vector-input, and other-vector-input entry
points as needed. It replaces the terminal length-dependent unwrapping with
the appropriate fixed-rank return. The incoming argument and the normalized
local vector have distinct names, so scalar input does not acquire the rank
from the original vector comment or from `np.atleast_1d`.

This is not general support for runtime-dependent return ranks. Unknown
lengths keep the original entry point and its diagnostic. The prepass does
not propagate vector-size assumptions across aliases, unknown calls, shape
mutations, or control-flow joins. Recognition is limited to the terminal
`if n == 1: y = y[0]` idiom, where `n` is derived from the normalized input.
It does not specialize arbitrary conditions or infer shapes through wrappers.

All seven calls in the full original source are statically classified: six
scalar calls and one call with an 11-element `linspace` vector. No edits to
the original Python source are required. The checker now also includes the
unchanged `dif_value`, comparing empty, singleton, three-element-vector and
scalar calls against Python and independently specified polynomial values.
This check passes with `Run diff: MATCH`; the previously adapted API remains
an additional check, not the evidence for the new support.

The full-source retry now reaches a different compiler error in
`dif_append_test`: original lines 827-828 set `xval = ntab + 1` and then call
`np.exp(xval)`. The generated `exp(xval)` passes an integer to a Fortran
intrinsic requiring real or complex. The full program has therefore **not**
yet compiled or had its Fortran execution validated. Integer-to-real
promotion for NumPy transcendental functions is the next blocker to examine.

Reproduce the bounded numerical check with:

```
python reports\divdif_validation_20260924\check.py
```

Add `--full` to retry the original full program; this intentionally fails
until its remaining blocker is fixed and saves the details in `full.log`.

Validation: 18 focused CLI regressions passed (new positional/keyword calls,
unknown-length diagnostics, joint rank signatures, documented vector
forwarding, and rank rebinding). The final specialization unit suite passed
all 22 cases, including evaluation order, alias/shape invalidation, dtype
restrictions, partial specialization, definition order, and Boolean
indexing. Reruns were disabled. The updated numerical checker passed again
after the conservative call-site checks were tightened. Run full pytest
before proceeding to the next transpiler fix.

## Integer-input transcendental promotion

Fixed the next compilation blocker: `np.exp(xval)` now converts integer
`xval` to `real(kind=dp)` before calling the Fortran intrinsic. The same
missing conversion affected `np.log`, `np.log2`, and `np.log10`, and was
fixed in their shared lowering. Existing real and complex arguments are
not coerced to real. Rank inference now explicitly preserves the input
rank for `log2` and `log10` as well.

Validation: 10 new CLI cases cover integer/real/complex scalars, vectors,
and matrices, plus integer expressions and an imported `exp` alias. The
complex cases cover `exp`, natural `log`, `sqrt`, and the trigonometric and
hyperbolic functions, not complex `log2`/`log10`. The existing NumPy math
smoke test also passes. The first integer-vector case exposed the missing
`log2` rank propagation; after the rank fix that case passed on a separate
rerun with automatic reruns disabled. All 11 distinct cases passed.

The unchanged full `divdif.py` now reports **Build: PASS** and **Run: PASS**
with runtime checking enabled. Its default comparison reports a version
banner difference first (`python version: 3.13.3` versus `unknown`). The
additional full-output audit in `check.py` filters only version banners,
timestamp lines, blank lines, and whitespace differences before checking
text and numbers (rtol 1e-5, atol 1e-10).

That audit reveals a genuine remaining presentation bug at normalized
line 62, in `data_to_dif_display`: Python prints separate `%14f` fields,
whereas Fortran emits `write(*,"(g0)", advance='no')` and concatenates
values such as `1.00000000000000002.0000000000000000...`. The audit rejects
this rather than guessing the numeric boundaries. Thus the complete
program's numerical output has **not** yet been certified as matching.
The independently checked interpolation kernels still pass their known
values and `Run diff: MATCH` checks. Preserving `%f` field widths with
`end=''` is the next concrete issue to fix; it is separate from the
integer-input promotion fixed here. `check.py --full` intentionally
continues to fail until that output mismatch is resolved.

## Default-precision fixed formatting: full validation passes

The `%14f` problem was an omitted-precision fallback, not a failure of
non-advancing writes themselves. `_percent_format_parts` previously
substituted `g0` when the floating-point format omitted precision. It now
routes scalar `%f`/`%F` formats with omitted precision through
`py_format_real` with Python's default six fractional digits. The helper's
fixed-format branch preserves minimum field width, flags, leading zero,
negative zero, and uppercase/lowercase non-finite spellings. Large values
expand beyond the requested width rather than becoming asterisks.
Explicit-precision fixed-format lowering and the optional integer-format
override are unchanged.

The unchanged full source now passes `check.py --full`: **636 normalized
lines and 1,254 numeric values match**, using rtol 1e-5 and atol 1e-10.
The audit excludes Python/NumPy version banners and timestamp-only lines,
ignores blank lines, and collapses whitespace; it checks the remaining
text as well as each numeric value. Both Python and Fortran complete,
and Fortran runtime checks remain enabled. The ordinary CLI `--run-diff`
still reports the version-banner difference; its comparison rules were
not weakened to make this corpus case pass.

The new integer and real formatting regressions compare raw stdout
against Python, including adjacent fields, default six-digit precision,
minimum-width overflow, sign/zero/left padding, negative zero, special
values, multi-argument output, and custom `end`/`sep`. These exact-output
checks supplement the whitespace-normalizing full-program audit.

All 7 focused tests passed with automatic reruns disabled: the 2 new
exact-output cases, 4 existing percent-format regressions, and the
`xpfunc2f` formatter-helper extraction/compilation regression. Full pytest
has not been run for this change and is the next checkpoint.
