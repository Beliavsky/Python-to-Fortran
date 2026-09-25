# FILUM: string-or-None function results

Original source: `C:/python/public_domain/burkardt/filum/filum.py`.
The source is unchanged.

## Failure

`filename_inc` returns `None` for an empty input or a name without digits,
and otherwise returns a string. Previously its `filename2 = None` became
`filename2 = -1` in Fortran, failing compilation because the target was
character. Its caller prints, copies, and compares this result with `None`.
Replacing absence with an empty string would lose valid Python semantics.

## Fix and supported boundary

A bounded AST lowering represents the result as two outputs: string data and
a logical presence flag, using existing tuple-return code generation. The
string is always valid; its contents are ignored when the flag is false.
Thus absent values, present empty strings, and the literal string `"None"`
remain distinct. Fresh flags avoid collisions with existing identifiers.

Supported uses include simple named calls, local copies/reassignments,
forwarding through named local results, `is`/`is not`/`==`/`!=` comparisons
with literal `None`, and direct print arguments. Required string operations
such as `len` and `ord` get absence checks. Passing a nullable value into a
local function is supported conservatively when its first parameter use is
an unconditional `len(parameter)` assignment, as in `filename_inc`;
`None` is an error for that Python input too.

This is not a general union-type implementation. Unsupported consumers get
an explicit `unsupported string-or-None use` diagnostic. Boundaries include
containers, callable aliases, captured/global state, classes, arbitrary
nullable arguments, truth tests, and comparisons other than with `None`.
Calls need named assignments rather than nested expression positions.
Existing handling of other result families is untouched. Tagged results use
the general procedure generator, not the restricted structured-driver path.
The generated Fortran interface exposes both outputs; this change does not
add automatic reconstruction of a Python `None` result to external wrappers.

## Validation

Run:

```bat
python reports\filum_validation_20260925\check.py
```

- The unchanged `filename_inc` and original `filename_inc_test` match Python.
- Additional scalar calls cover empty/no-digit inputs, ordinary increments,
  repeated digits, trailing spaces, copies, and absence tests. Character
  lengths and code points are checked, so whitespace normalization cannot
  hide lost trailing spaces.
- `probe.py` distinguishes `None`, `""`, `"None"`, and a trailing-space value.
  A delimiter-based raw-output assertion verifies that printing does not pad
  an empty string or remove trailing spaces; display uses deferred-length
  temporaries rather than a padded character `merge` expression.
- The full unchanged program compiles with runtime checks and its execution
  matches Python with explicitly synthetic fixtures (3 columns, 2 rows).
  The checkout lacks `r8mat_write_test.txt` and `i4mat_write_test.txt`.
  Full-driver comparison ignores version/time banners and whitespace.
- Reproducible sources, helper copies, and binaries are generated in `work`;
  raw execution/build logs are saved beside this review.
- Focused pytest: **31 passed in 141.16 seconds**, covering nullable strings,
  existing optional-string selectors, void `return None`, and integer-to-
  character rebinding. The full pytest suite was not run.

## Independent findings, not changed

The Python implementation does not implement repeated-9 carry as its prose
claims: `a7to99.txt` becomes `a8to90.txt`, not `a8to00.txt`, and `a9to99.txt`
becomes `a9to90.txt`. The translation intentionally matches the code.

A diagnostic driver iterating over a mixed-length literal string list exposed
an independent fixed-width padding issue: a 10-character input acquired a
trailing space. The validation therefore uses separate scalar calls instead
of that list, and checks lengths/code points explicitly. The padding issue
remains a candidate for a subsequent fix.
