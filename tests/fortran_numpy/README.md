# Direct Fortran tests of numpy_fortran

These are complete Fortran programs extracted from the helper tests. They use
`numpy_fortran`, not `python_mod`, and need no Python-to-Fortran translation.

| Program | Checks |
| --- | --- |
| polynomial_series.f90 | Polynomial evaluation, fitting, derivatives, integrals and Vandermonde matrices; compared with NumPy |
| polynomial_roots.f90 | Six polynomial families, roots, quadrature, arithmetic and conversions; compared with NumPy |
| standalone.f90 | Polynomial fitting, 2-D FFT, reflection padding and 2-D polynomial evaluation; compared with NumPy |
| elemental_arrays.f90 | Scalar and array calls, integer kinds and optional arguments; self-checking |
| pure_numerical_helpers.f90 | Numerical subset of the runtime purity test, including complex linear algebra and FFT; self-checking inside a pure procedure |
| error_probe.f90 | `valid` runs successful checks; `delete`, `gamma`, `binomial`, `cholesky_shape`, and `cholesky_definite` must fail with the expected diagnostic |

Run all programs and error modes from the repository root:

```text
python -m pytest -q tests/test_numpy_fortran_cases.py
```

The runner extracts a fresh module and builds it and LAPACK once per test
worker, without compiling or linking `python.f90`. Each program is then
compiled with Fortran 2018 checking and runtime bounds checks.

For a manual build, in a separate build directory (adjust paths as needed):

```text
python C:\python\Python-to-Fortran\xextract_fortran_lib.py --out . --no-compile
gfortran -O0 -c C:\python\Python-to-Fortran\lapack_d.f90 -o lapack.o
gfortran -std=f2018 -ffree-line-length-none -O0 -fcheck=all -c numpy_fortran.f90
gfortran -std=f2018 -ffree-line-length-none -O0 -fcheck=all C:\python\Python-to-Fortran\tests\fortran_numpy\elemental_arrays.f90 numpy_fortran.o lapack.o -o elemental_arrays.exe
elemental_arrays.exe
```

The polynomial, elemental and error tests also read these files when testing
`python_mod`, replacing just the module name. Runtime-only string, formatting
and command-line checks remain in the original runtime tests because those
APIs are intentionally absent from the numerical library. Keep the numerical
purity subset here synchronized when extending the larger runtime-purity test.
