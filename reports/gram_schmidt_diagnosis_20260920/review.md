# Gram-Schmidt A3: normalization of roundoff, not a confirmed translation bug

The first substantial saved mismatch is in cgs2, on this fixed matrix:

```
-9  8  8  2
 6  7  7 -1
 9  9  1 -8
```

`probe.py` copies Burkardt's MIT-licensed cgs2 arithmetic unchanged and adds
diagnostic prints before normalization. Its deterministic driver removes RNG
differences. The Python result is checked against the original cgs2 function.
The current transpiler compiles and runs the probe with runtime checks enabled.

The input has rank three. Python and Fortran produce identical first three
columns, with ||Q.T Q-I||_F = 4.00e-16. For Q consisting of those columns, the
relative reconstruction error ||A-Q(Q.T A)||_F / ||A||_F is 2.49e-16 in both.

The fourth unnormalized residuals are:

- Python: [4.163336342344337e-16, 4.440892098500626e-16, 1.7763568394002505e-15],
  norm 1.87776264266391e-15.
- Fortran: [3.885780586188048e-16, 8.881784197001252e-16, 1.7763568394002505e-15],
  norm 2.023684124003798e-15.

The source normalizes any residual with norm > 0. Thus these small differences
produce unit vectors differing by as much as 0.2024. Neither fourth vector is
orthogonal to the first three: maximum absolute correlations are 0.736 and
0.761. Four orthonormal vectors in three dimensions are impossible.

A separate Python implementation using sequential scalar dot products and
sum-of-squares norms reproduces the Fortran result. This is strong evidence for
ordinary reduction-order differences amplified by the source algorithm, not a
matrix-layout, indexing or projection translation error. No transpiler change
is warranted from this case alone.

The original cgs4 variant with its test tolerance, 1000*machine epsilon, produces
a zero fourth column in Python. This illustrates the intended alternative for
this input, not a universally valid absolute rank threshold. The translator
must not silently replace the user's algorithm or impose such a tolerance.

Scope: this investigation isolates cgs2 on the saved A3 matrix. It does not
certify all ten routines in the full driver. Original corpus source and
transpiler were not modified. `check.py` reproduces the build and analysis;
`analysis.json` and build/Python/Fortran logs preserve the observations.
