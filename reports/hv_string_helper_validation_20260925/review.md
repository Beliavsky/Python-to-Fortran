# HV regression: unused generated string accessor

The full pytest run reported one failure in
`test_xp2f_xfit_hv_no_dates_matches_python_numeric_results`:

```fortran
func_res = text(1:lengths(position + 1))
! Error: Unclassifiable statement
```

## Cause

The mixed-length headers in the original table printer cause
`rewrite_literal_string_sequence_lengths` to generate `xp2f_string_item`.
Later, the record-output normalization replaces the table printer, removing
every call to that accessor. The existing reachability pass runs before
these rewrites, leaving the now-unused helper in the procedure list.

With no callers to supply element types, the helper was emitted with
`items` as a real array and `text` as a real scalar. Its character substring
was consequently invalid Fortran. This is a regression in generated-code
handling, not a mismatch in the HV numerical results or a Jaccard set bug.

Inspecting the AST immediately after normalization confirmed the helper
had no remaining calls. `probe.py` isolates the same interaction using
the smaller `format_float` output normalization, without the financial
calculations or CSV input. With the cleanup deliberately disabled, it
reproduces the real declaration and invalid substring above.

## Fix and coverage

Mark the synthesized string accessor explicitly and, after normalization,
remove it only if no remaining executable statement or local function
references it. Function defaults and function-valued references count as
uses. User-written functions are never removed by this new cleanup, even
if their names resemble the generated helper. Deep copies preserve the
marker. No change to string padding or numerical calculations is needed.

Regression coverage includes:

- Compile and Python/Fortran output comparison of the reduced example.
- The actual full HV source through the normalization pipeline, with a
  fast assertion that the orphan has disappeared before expensive emission.
- Preservation of executable, local-function, and default-value references.
- Preservation of a user function with a colliding helper-like name.
- The existing full HV test, which compiles and runs both versions and
  compares asset labels and all numeric CSV fields at 1e-12 tolerance.

Validation: 43 focused helper-cleanup, string, nullable-string, and set tests
passed in 360.63 seconds with reruns disabled. The full HV numeric regression
also passed, in 568.32 seconds with reruns disabled: successful compilation,
execution, and CSV comparison at the existing 1e-12 tolerance. Total:
44 targeted tests passed.

The full project suite is not rerun for this change.
