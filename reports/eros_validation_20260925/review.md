# EROS: numeric option default incorrectly overridden by a logical comment

`gauss_plu(A, wait=0)` documents `wait` as logical, but uses three distinct
numeric modes: 0 (silent), 1 (print progress), and 2 (print and pause).
The body tests `0 < wait` and `1 < wait`. Previously the translator emitted
an optional logical dummy and `optval(wait, 0)`, which has no matching helper
overload. Simply changing 0 to false would lose the three-mode semantics.

The shared comment/default reconciliation now preserves the kind of a numeric
literal default when the comment says logical. Both signature inference and
procedure emission apply the same rule. Signed numeric literals are included;
True and False are explicitly excluded because Python bool is a subclass of
int. Other comment kinds are unchanged. This is a bounded precedence rule,
not general inference from arbitrary default expressions or runtime values.

The complete unchanged EROS source now compiles with runtime checks. Focused
regressions cover defaults 0, -1, and 0.5; omitted, positional, and keyword
arguments; and the distinction between modes 0, 1, and 2. A Boolean-default
companion checks that the declaration remains logical.

## Execution audit

```text
python reports\eros_validation_20260925\check.py
```

The checker copies the original source unchanged, attempts the full driver
with Python RNG recording/Fortran replay, and saves `run.log`. Build success,
execution success, and numerical agreement must be assessed separately; the
script does not interpret an exit code of zero as proof of matching results.
Generated files, RNG recordings, and logs are reproducible artifacts.

## Result and next blocker

The unchanged Python driver completed with RNG recording. The generated
Fortran built successfully but failed in the first Gaussian-elimination test
with `scale(): Fatal error!`, reporting `Ab(1,0) = 0` in Python index notation.
This is not a full-program numerical recovery.

The next issue is optional-argument equality with None. Source `scale(Ab, i,
j=None)` starts with `if j == None: j = i`. Generated code instead uses:

```fortran
j_opt = optval(j, 0)
if (j_opt == -1) j_opt = i
```

When j is omitted, this fails to apply the source default-to-i rule and scales
column zero rather than the diagonal. The appropriate absence check for this
optional argument is `.not. present(j)`, not a numeric sentinel comparison.
That separate equality/None issue remains unfixed in this patch.

All four focused pytest cases passed with reruns disabled; `git diff --check`
passed. Full pytest was left for the user's overnight checkpoint.

## Follow-up: scalar optional equality with None

The equality/None blocker above is now fixed. For supported scalar optional
arguments, both operand orders of `== None` / `!= None` use Fortran presence
tests. This is deliberately not applied to array equality, which is
elementwise in NumPy, or to user-defined equality. Explicit None keyword
literal actuals are now omitted when the formal has
a None default, matching the existing positional omission behavior.

The full unchanged source now builds and executes with runtime checks and RNG
replay. Both Gaussian solve test sections match Python: 71 and 92 numeric
tokens, respectively, using rtol 1e-6 and atol 1e-8.

**Numerical agreement for the whole program is not established.** Its two
full numeric streams have 584 tokens, but contain significant mismatches.
The first deterministic 3x3 PLU example reports residual norm
20.846162716432968 in Python versus 16.156703330197036 in Fortran, with different
P/L/U matrices. Python's displayed P itself contains duplicate rows, so it
is not a valid permutation matrix. The source uses NumPy slice views as swap
temporaries (`T = P[j,:]`) and also uses an integer matrix in this example;
those semantics deserve separate investigation before changing either source
or generated code. Random ill-conditioned inverse tests also differ.

`check.py --check-log` reproduces the comparison from saved output. The checker
now returns failure for the remaining numerical discrepancies even though
compilation/execution pass. This is a run-time recovery, not a claim of full
correctness. No original corpus source was modified.

Scope note: a supplemental probe using a separate `absent = None` variable
also exposed an undeclared local-sentinel assignment. That local-None storage
case is deferred; the new omission handling and regression cases cover literal
None actuals, not arbitrary variables whose runtime value may be None.

Final focused validation: six pytest cases passed with reruns disabled,
covering both operand orders of equality/inequality, omitted and positional/
keyword literal None, legitimate 0/-1 values, falsey real/complex/logical/string
scalars, and the existing optional-string persistent-state case. Full pytest
was not run.
