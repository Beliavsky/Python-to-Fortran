# byname: scalar strings and the remaining mixed-type state blocker

The original `persistence/byname.py` initially declared `action` and `name`
as optional character arrays. Callers pass scalar strings; `action[0]` and
`name[0]` select characters, not array elements.

Two inference issues were corrected:

- Consistently observed scalar character actual arguments override the
  body-only array-indexing guess, provided the parameter is not rebound.
  Actual character-array arguments retain their array rank.
- `_extent_expr` returned the non-null string `"char"` for scalar string
  indexing/slicing. The assignment prescan interpreted this as array extent
  evidence, incorrectly promoting `action2` and `name2` to arrays. Scalar
  characters and substrings now have no array extent.

The generated function now declares scalar optional character arguments and
scalar character locals, using `action_opt(1:1)` and `name_opt(1:1)`.

## Validation

Run from the repository root:

```text
python reports\byname_validation_20260925\check.py
```

The checker extracts the original function without changing its body and uses
a separate numeric-only driver. It compiles with runtime checks, runs both
languages, and compares 13 output values against Python and an independently
specified state trace. The trace covers omitted and explicit-None optional
arguments, case-insensitive names/actions, keyword arguments, negative and
zero updates, get, print, and reset. All 13 values match. No corpus source
was edited. This does not validate consumption of a None-valued return.

Focused pytest cases cover required/optional scalar string parameters,
indexed and sliced string locals, persistent named state, string-array
arguments, the existing ord case, and string-valued constructor dtype handling.
Eight focused tests passed with reruns disabled (seven in the string/indexing
selection and one persistent-state test). `git diff --check` also passed.

## Full original program still blocked

The full original program was retried and its build log saved as `full.log`.
It now reaches this later call:

```python
beta = byname("set", "beta", "Shazam!")
```

The function stores numeric and string values in the same persistent slot.
Generated `value_in` and the persistent slots are currently real, so gfortran
rejects the character argument. Supporting the original heterogeneous store
requires a representation for mixed-type state and results; merely generating
another procedure overload would not provide shared heterogeneous storage.
This case is **partially fixed, not fully recovered**.

Another limitation encountered while designing a reduced test: checking
`text is None` on a required (non-optional) scalar string emits an invalid
`allocated(text)` test. That separate None-check issue is not fixed here;
the optional-string path used by byname is covered and passes.

Logs and generated work files are reproducible artifacts, not required source
files. Full pytest was not run for this change.
