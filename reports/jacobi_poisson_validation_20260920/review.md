# Jacobi Poisson output mismatch: formatting, not an observed solver defect

The current translator compiles and runs the original Burkardt source. Both
Python and Fortran complete 3088 iterations on its 33-node grid. Their reported
RMS residuals are respectively 9.985314566266483e-7 and 9.985314488863067e-7,
both below the source's 1e-6 tolerance.

All 33 solution-table rows match exactly at displayed precision. An independent
scalar Thomas solve of the tridiagonal finite-difference system confirms the
direct and Jacobi solutions within printed precision plus 1e-7 iteration error.
The exact-solution column also agrees with x*(x-1)*exp(x). The rounded table is
not sufficient for independently recomputing the full-precision residual; the
residual values above are reported values, not independent certifications.

## Confirmed formatting divergence

Source lines 140-143 apply `%` to label strings with no conversion specifier.
In this tested NumPy environment, `'label' % np.float64(1)` and the np.int64
variant return just `'label'`. An ordinary Python float or a one-element tuple
instead raises TypeError. No case appends the value.

The transpiler's `_percent_format_parts` explicitly handles an unused scalar
argument by appending an integer, real, logical or character descriptor. Thus
Fortran prints two additional RMS values where Python prints labels only.
This is a confirmed output-semantics bug, not merely display precision.

## Recommended next change

Remove the silent append fallback and issue a clear unsupported-format diagnostic
when arguments are supplied but no conversion consumes them. This conservatively
rejects the legal NumPy-scalar case as well as ordinary-Python errors, rather than
pretending scalar provenance is known. Check expression formatting as well as
single/multiple-argument print paths, and preserve valid escaped percent signs
and empty argument tuples.

For users intending to print the RMS values, explicitly adding `%g` to the labels
or using `print(label, value)` expresses that intent. The transpiler must not
silently repair the source. Neither the original source nor the transpiler was
changed during this investigation. `check.py` reproduces the diagnostics and
numerical checks; build and both run logs are retained here.

## Follow-up: conservative diagnostic implemented

The preceding numerical validation records the pre-fix translation. The silent
append fallback has now been removed. Both print formatting and ordinary
expression formatting reject supplied arguments with no consuming conversion.
The original source now receives `Transpile: FAIL` at line 140 with advice to
use an explicit conversion or multi-argument print if a value is intended.
The original source has not been modified. This is an unsupported-case
diagnostic, not implementation of NumPy's special scalar formatting behavior.

Run `check.py --check-rejection` to verify the new diagnostic. The script's
original default mode remains a historical numerical reproduction requiring
the pre-fix transpiler; its saved logs retain that evidence.
