# Optional None inputs to tuple-returning functions

The unchanged source is
`C:/python/public_domain/burkardt/persistence/abc.py`.
The current transpiler initially failed to compile its explicit
`abc(None, None, None)` calls: they became
`call abc(-1, -1, -1, a_out, b_out, c_out)`, passing integer sentinels
to optional real arguments. Casting the sentinels to real would be
incorrect: it would overwrite persistent values instead of leaving them
unchanged. The callee already used `optional` and `present()` correctly.

A shared tuple-call input renderer now omits explicit `None` (and names
currently known to be `None`) when the corresponding parameter defaults
to `None`. After a positional gap it uses keyword association for later
inputs and the generated output arguments. Actual values, including -1
and zero, retain the existing kind/rank coercion. The renderer is used by
tuple assignment, elementwise tuple-call lowering, ignored tuple results,
and direct printing of a tuple-returning call. Other defaults are not
treated as missing. General runtime-dependent optional-value forwarding
is not a new feature claimed by this change.

The generated original call is now:

```fortran
call abc(a_out=a_out, b_out=b_out, c_out=c_out)
```

`check.py` compiles and executes the original source with runtime checks,
then verifies all four reported state transitions against both Python
and independently specified values: initial `(1, 2, 3)`, partial update
to `(1, 19, 3)`, complete replacement with `(50, 60, 70)`, and persistence
of that replacement. The source is not rewritten. Version banners and
the exact spacing of printed numbers are not part of this state check.
The first checker run accidentally included the interface-description
line as a state row; its parser was corrected to require a numeric row.

Reproduce with:

```
python reports\abc_validation_20260925\check.py
```

The new regression cases exercise assigned, ignored, and printed tuple
results; omitted, positional, and keyword None inputs; partial updates;
negative and zero replacements; a None-valued name subsequently rebound
to a number; and non-None defaults. The direct-print case compares each
numeric output row, since the existing Fortran tuple printer omits
Python's parentheses and commas. Its initial `--run-diff` assertion failed
on that presentation difference despite matching numbers; no global
comparison policy or tuple-presentation code was changed.

Final validation: all 4 new regression cases and 10 existing focused
tuple/rank/aliasing/optional-forwarding cases passed, with automatic reruns
disabled. The unchanged original program's independent state checker also
passes. Full pytest has not been run for this change and is recommended
before the next transpiler fix.
