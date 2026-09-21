# Mixed vector/matrix local-function calls

Follow-up to the tridiagonal solver validation of September 20, 2026.
The solver values matched after the negative-base power fix, but the vector
right-hand side and result had silently become one-column matrices.

`probe.py` isolates the issue with a copy-and-scale function called with a
vector and a matrix from a common caller. Before the diagnostic was added,
`python ../../xp2f.py probe.py --compile --run-diff` compiled and ran, but:

| Observation | Python | Fortran |
| --- | --- | --- |
| Vector and matrix result ranks | 1, 2 | 2, 2 |
| Checked dimension lengths | 3, 3, 2 | 3, 3, 2 |
| Sum after adding `np.arange(3)` to the vector result | 4.5 | 10.5 |

Matching dimension lengths and individual solver values therefore did not
establish equivalent shapes or broadcasting behavior.

The transpiler merges argument ranks into a shared signature. Existing
specialization handles selected cases, but does not provide general
vector/matrix specialization for value-returning functions. A new guard
rejects observed conflicting positive array ranks when no specialization
has been selected. It names the function, argument, and observed ranks and
recommends separate functions for vector and matrix inputs. This is a
conservative unsupported-case diagnostic, not a rank-specialization fix.

Both this reproducer and the original mixed-rank tridiagonal probe now fail
translation explicitly. The earlier tridiagonal numerical results remain
historical evidence; that combined-rank checker is no longer expected to
compile until rank-preserving specialization is implemented or its callers
use separate rank-specific routines.

Regression coverage checks positional/keyword calls at module scope and
inside a caller, and successful single-rank vector and matrix cases. Existing
supported specialization tests are also included in the focused test run.
