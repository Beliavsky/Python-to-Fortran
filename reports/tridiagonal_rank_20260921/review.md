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

The original cause was merging argument ranks into a shared signature.
The first change added a diagnostic; the follow-up now specializes
value-returning functions with one argument varying between rank 1 and rank 2,
of the same numeric kind, and fixed profiles for all other arguments. Separate
Fortran procedures are exposed through a generic interface. Result ranks are
inferred per specialization, and callers must bypass shared-signature rank
promotion. Forced argument kinds also take precedence over a range-use heuristic.

Both this reproducer and the original mixed-rank tridiagonal probe now compile
and pass. The tridiagonal checker additionally verifies the actual argument
and result ranks and lengths for sizes 1, 2, 5, and 9. Maximum solution error
remains 1.11e-16 and maximum scaled residual 1.39e-18 for both languages.
The diagnostic remains for unsupported observed rank combinations, including
the tested vector/rank-3 case. This is not general arbitrary-rank specialization.

Regression coverage checks positional/keyword calls at module scope and
inside a caller, either call order, and successful single-rank vector and matrix cases. Existing
supported specialization tests are also included in the focused test run.
