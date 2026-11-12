# Building the helper API documentation

Install FORD 7.x and run from the repository root:

```text
python -m pip install "ford>=7,<8"
python xbuild_fortran_docs.py
python xbuild_fortran_docs.py --library
```

Open `docs/generated/runtime/index.html` or
`docs/generated/library/index.html`. `--output DIRECTORY` overrides the HTML
destination. The library command first regenerates `fortran_lib/numpy_fortran.f90`.
No compiler is required to build the documentation. Generated HTML is not committed.

The builder stages just the selected module in a temporary source directory;
it does not scan the examples, LAPACK sources or generated translations.
The two project files can also be passed directly to FORD with explicit
`--src_dir` and `--output_dir` arguments.

## Maintaining comments

Maintain documentation in `python.f90`; extraction preserves procedure,
type and interface documentation in the standalone module. Use `!!` after
the complete declaration, including all continuation lines:

```fortran
pure elemental function example(x) result(y)
   !! Explain the operation, its domain and important caveats.
   real, intent(in) :: x
      !! Explain the meaning of x, not just its declared type.
   real :: y
```

Keep implementation notes as ordinary `!` comments and retain `!@pyapi`
metadata for translator tooling. Extraction seeds missing summaries from
metadata descriptions, including generic specifics, but does not overwrite
handwritten FORD documentation. The initial summaries do not replace manual
documentation of optional defaults, indexing conventions, error conditions,
NumPy differences, examples or algorithm provenance.
