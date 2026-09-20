# uniform: comment-driven integer coercion changes LCRG semantics

Confirmed on the current transpiler using `probe.py`, a reduction of the original
MIT-licensed Burkardt lcrg_evaluate arithmetic and lcrg_anbn_test call pattern.
No source corpus or transpiler files were changed during this investigation.

The original Python lcrg_anbn coefficients for n=0,...,10 agree with exact
`pow(a,n,c)`, with b=0. In particular, the four-step multiplier is 984943658.
The discrepancy occurs later, in lcrg_evaluate calls with np.zeros array elements
(NumPy float64), not in computing those coefficients.

The generated function declares x and its result as integers, based on the
integer comments, and inserts `int(x(j+1))` at the call. Its widened int64
multiply-add/modulo correctly computes the integer generator on these inputs.
Python instead computes a rounded floating-point product before taking `%`.

| First divergent step | Input | Exact integer product | Rounded floating product | Python result | Fortran / exact result |
|---|---:|---:|---:|---:|---:|
| 5 | 207482415 | 204358488800774070 | 204358488800774080 | 24794541 | 24794531 |
| 7 | 2035175616 | 2004533315895443328 | 2004533315895443456 | 1644515548 | 1644515420 |

After another jump, step 9 is 1075097683 in Python versus 1963079340 in Fortran;
step 11 is 86679929 versus 715426902. These were the two large saved mismatches.
Smaller differences also exist (including step 10), so “two mismatches” was a
comparison-threshold count, not a count of every unequal result.

The reduced probe's eleven ordinary scalar steps and all eight Fortran jump-ahead
steps agree with arbitrary-precision integer arithmetic. That does not make the
translation semantically correct: it silently substitutes integer arithmetic
for the Python source's real arithmetic. This is a confirmed type-inference /
argument-coercion issue, not simply a numerical-sensitivity limitation.

## Diagnostic control and next fix

With `--ignore-comments`, the reduced probe infers x and the result as real,
removes the integer argument cast, and reproduces all eight Python array rows.
The scalar sequence also agrees for this input. This is a diagnostic control,
not a demonstrated workaround for the entire uniform.py corpus program, and
promoting every mixed-call function to real can lose integer precision elsewhere.

The next fix should ensure comment-derived integer hints cannot silently
override a known real actual argument. Prefer preserving distinct integer and
real call semantics where specialization is supported; otherwise provide a
clear unsupported mixed-type diagnostic. Add regression cases with fractional
actual arguments as well as large integer-valued floats, and preserve exact
integer-only modular arithmetic.

`check.py` builds and runs both inference modes, validates coefficients against
exact powers, and records products and remainders in `analysis.json`. Logs are
stored alongside the probe. A full pytest run is unnecessary for this
investigation-only change.

## Follow-up: reject unsafe comment-driven scalar narrowing

The translator now rejects observed real scalar arguments when the selected
procedure still declares that parameter integer based on comments. It does not
silently promote all calls to real, which could lose integer precision in other
call sites. Full specialization of this case remains future work.

Integer actual arguments, explicit caller-side int conversions, and an
unconditional callee-side `x = int(x)` before any other use remain supported.
A conditional or later conversion is not treated as permission to narrow at
entry. Existing array-handling paths are not changed by this scalar diagnostic.

`check.py --check-rejection` verifies the new diagnostic on the reduced case.
The default checker mode and existing logs describe the pre-fix behavior and
require the pre-fix translator. A full pytest checkpoint is recommended after
this inference validation change.

The full current uniform.py translation also encounters this conflict earlier:
line 1669 passes `a*x-c` to integer-comment parameter `i` of `i4_modp`, after
`x` is returned by congruence (whose general path uses a floating-point work
array). It now stops there with the explicit diagnostic. The isolated LCRG
probe separately verifies the intended lcrg_evaluate diagnostic; this change
does not claim the complete uniform.py now translates or runs successfully.
