project: Standalone NumPy-style Fortran helpers
summary: Numerical helpers extracted from the Python-to-Fortran runtime.
display: public
         protected
graph: false
search: true
source: true
preprocess: false

# Standalone numerical helpers

`numpy_fortran` is generated from the tagged numerical APIs in `python.f90`.
Documentation is maintained in that source, not in the generated module.
`fortran_lib/ROUTINES.md` lists the public APIs by topic.

Generic interfaces select argument types and ranks; expand their specifics
to inspect the signatures. The summaries are an initial reference, not a
complete description of defaults, errors or compatibility with NumPy.

LAPACK-backed routines require compatible external LAPACK procedures when
linking applications. See the original project's README for algorithm
provenance and third-party licensing.
