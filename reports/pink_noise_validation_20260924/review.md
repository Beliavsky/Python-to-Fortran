# Pink-noise tuple-target mutation

## Confirmed blocker and fix

The unchanged Burkardt `pink_noise.py` failed compilation in `ran1f`:

```python
y, u[i], q[i] = ranh(j, u[i], q[i], rng)
```

The emitted assignments wrote to `u(i)` despite declaring `u` with
`intent(in)`. Argument mutation detection inspected direct subscript and
attribute targets but did not descend into tuple/list assignment targets.
It now recursively checks those targets and marks affected arguments
`intent(inout)`. Bare names still mean local rebinding, not mutation of the
caller's object. Existing local-shadow handling is unchanged.

The new parameterized regression covers both tuple and list unpacking into
real and integer arrays, two consecutive calls, caller-visible array values,
and a separate read-only array which must retain `intent(in)`.

## Corpus validation

`check.py` copies the original source without modifying it, compiles with
runtime checks, and runs Python and Fortran using `--rng-replay`. The full
program compiled and ran successfully. All **2,279 output tokens matched**
at Python's displayed precision after excluding recognized timestamps and
Python/NumPy version banners and normalizing whitespace.

The stock `--run-diff` reports a version-banner difference (`3.13.3` versus
`unknown`). The checker separately verifies all remaining tokens, using
1e-6 relative / 1e-10 absolute tolerance, enlarged where necessary to half
a unit of the last printed decimal place of a Python floating token.
Integer-looking tokens receive no printed-decimal allowance.

Raw combined output is in `run.log`, with extracted program output in
`python.stdout` and `fortran.stdout`. Generated source, executable and RNG
recording files are in `work/`; these artifacts need not be committed.

```console
python reports\pink_noise_validation_20260924\check.py
python reports\pink_noise_validation_20260924\check.py --check-log
```

RNG replay validates the calculations using shared draws, not the statistical
quality of the generated random-number algorithm or all possible inputs.

## Separate follow-up identified

The initial small test used the direct expression return:

```python
def step(u, q):
    return u, u + 0.25, q - 1
```

That exposed another kind-inference problem: the call emitted `int(u(i+1))`
despite a real dummy argument, and tuple output kinds were inconsistent.
`tuple_expression_probe.py` preserves this reproducer. The initial
mutation regression uses named local results, matching the original `ranh`
structure. It passes without adding type hints. The expression-return case
was not fixed by the mutation change; see the follow-up below.

Validation: 11 focused pytest cases passed with reruns disabled: 2 new
mutation cases, 7 existing tuple/section cases, and 2 parameter-rebinding
cases. The initial expression-return test failures are described above.
Full pytest has not been rerun for this change.

## Tuple-expression inference follow-up

The call-site scan inside `update` did not seed its formal parameters from
already observed caller types. Thus `step(u[i], q[i])` lost the known real
and integer element kinds of the two arrays. Provisional tuple-result
guesses then reached the final call site, while the separately inferred
callee declarations disagreed.

The local call scan now seeds observed formal kinds and ranks before
prescanning the function body. Existing expression inference consequently
infers `step`'s components independently as real, real, integer. No blanket
tuple promotion or cast suppression is used. The generated call no longer
converts `u[i]` to integer, and the third output is declared integer in both
the callee and the caller's temporary.

New regression cases cover positional and keyword calls, both definition
orders, negative fractional inputs, and updates visible after repeated calls.

Validation for this follow-up: all 4 new cases passed, and all 19 selected
existing cases passed (reruns disabled). These cover tuple-target mutation,
resolved helper-return kinds, documented integer seeds, real sentinels,
parameter rebinding, and joint scalar/vector/matrix rank forwarding.
The saved expression probe compiled and reported `Run diff: MATCH`.
The complete original pink-noise program was rebuilt and rerun with RNG
replay; all 2,279 normalized tokens again matched at displayed precision.
Run full `pytest -q` before starting another corpus fix.
