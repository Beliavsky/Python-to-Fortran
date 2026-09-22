# Joint scalar/vector/matrix signatures

The rank-specialization fallback now groups complete observed call signatures
instead of requiring exactly one argument to vary between ranks one and two.
It supports ranks zero, one and two, with one stable numeric/element kind per
argument position. It emits only observed combinations, not their Cartesian
product. Existing kind-specialization paths are unchanged.

The probe exercises (scalar, scalar), (scalar, vector), (scalar, matrix),
(vector, scalar), (matrix, scalar), (vector, vector), and (matrix, matrix).
Array results retain their observed ranks. Reductions infer scalar results
independently; np.sum(scalar) now uses the scalar directly (or integer zero/one
for Boolean input) instead of invoking Fortran SUM on a scalar.

The regression covers positional and keyword arguments, top-level calls and
calls inside a driver procedure, values, ndim and shape, and verifies that
unobserved vector/matrix pairings are not emitted. A loop prevents the
arithmetic function from being inlined so actual specialized procedures are
checked.

## Remaining limitation: forwarding through local functions

The full test_int_2d program still cannot translate. Specializing p00_fun alone
initially exposed calls to vector-only p01_fun from a matrix specialization.
Those shared callee signatures caused unwanted flattening and a result-rank
compile error. Propagating complete profiles through that call chain is not
implemented by this bounded change.

New joint specializations with multiple varying arguments that call a local
function now stop with an explicit unsupported-forwarding diagnostic rather
than emitting that broken code. This is conservative: even a local call
unrelated to the varying arguments is currently rejected in this new path.
Existing specialization paths are not broadened to support such forwarding.
The full corpus diagnostic names p00_fun and p01_fun.

## Reproduce

```cmd
python reports\joint_ranks_validation_20260922\check.py
```

The checker saves probe.log, full.log and analysis.json. The original corpus
is unchanged. Full pytest has not been run.

Validation: five new joint-signature/forwarding tests passed, and ten existing
vector/matrix, tridiagonal and unsupported-rank tests passed. The first run
of the new signature tests exposed the scalar SUM issue described above;
all four parametrized signature tests passed after that fix.
