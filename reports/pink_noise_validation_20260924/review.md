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
`tuple_expression_probe.py` preserves this unresolved reproducer. The final
mutation regression uses named local results, matching the original `ranh`
structure. It passes without adding type hints. The expression-return case
is not claimed fixed by the mutation change.

Validation: 11 focused pytest cases passed with reruns disabled: 2 new
mutation cases, 7 existing tuple/section cases, and 2 parameter-rebinding
cases. The initial expression-return test failures are described above;
that separate case remains unresolved. Full pytest has not been rerun for
this change.
