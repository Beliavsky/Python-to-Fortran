project: Python-to-Fortran runtime
summary: Fortran helpers for translated Python programs and direct Fortran use.
display: public
         protected
graph: false
search: true
source: true
preprocess: false

# Python-to-Fortran runtime

`python_mod` supplies numerical, string, array, I/O and other runtime helpers.
Public generic interfaces select the appropriate argument types and ranks.
Expand their specific procedures to inspect the Fortran signatures.

The summaries are an initial API reference, not a promise of complete NumPy
compatibility. Consult the source for defaults, errors and unsupported cases
that are not yet described in the comments. Pure and elemental attributes,
argument intents, types and ranks are extracted from the Fortran declarations.

LAPACK-backed routines need `lapack_d.f90` (or compatible LAPACK symbols), and
some root-finding routines need `root.f90`. Documentation generation itself
does not compile or link those dependencies.

See the repository README's Third-Party Code section for provenance and licenses.
