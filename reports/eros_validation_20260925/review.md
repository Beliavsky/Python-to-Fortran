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
