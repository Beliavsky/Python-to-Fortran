# Python-to-Fortran

Python-to-Fortran is an experimental Python and NumPy to Fortran transpiler created using OpenAI Codex centered on `xp2f.py`.

The project is intended for numerical Python programs that use a Fortran-friendly subset of Python. It can infer many scalar, array, and string cases, emit Fortran source, optionally compile it with `gfortran`, and compare Python and Fortran output for regression testing.

## Status

This transpiler is useful on a substantial subset of numerical Python, but it is not a general Python compiler.

Known limitations include dynamic Python features, complex duck typing, irregular containers, reflection, and parts of NumPy that do not map directly to static Fortran. When a program does not transpile, a small reproducer is usually the best starting point for improving `xp2f.py`.

See [Timing Results](TIMING_RESULTS.md) for runtime measurements on fully passing translated numerical programs.

See [Comparison with Pyccel](PYCCEL_COMPARISON.md) for how this project differs from Pyccel.

## Requirements

- Python 3.11 or newer.
- NumPy for most translated numerical programs.
- `gfortran` on `PATH` for `--compile`, `--run`, and `--run-both`.
- `pytest` for the test suite.
- `pandas` for `xsummarize_xp2f_progress.py`.

## Basic Use

Emit Fortran:

```console
python xp2f.py path\to\program.py
```

Emit and compile:

```console
python xp2f.py path\to\program.py --compile
```

Run Python and translated Fortran and compare normalized output:

```console
python xp2f.py path\to\program.py --run-diff
```

Run a batch file list:

```console
python xp2f_batch.py @python_file_list.txt --blockers --jobs 4
```

Compare two batch result files:

```console
python xcompare_xp2f_batch_results.py baseline_results.txt newer_results.txt
```

Summarize historical batch progress files:

```console
python xsummarize_xp2f_progress.py
```

## Small Example

The file [examples/xprime.py](examples/xprime.py) counts primes up to one million. Running:

```console
python xp2f.py examples\xprime.py --time-both
```

emits, compiles, and runs the translated Fortran program. The generated Fortran output is shown in [examples/xprime_p.f90](examples/xprime_p.f90).

One run gave:

```text
Timing summary (seconds):
  stage         seconds    ratio(vs python run)
  python run   2.434409                1.000000
  transpile    0.028275                0.011615
  compile      0.341000                0.140075
  fortran run  0.253106                0.103970
  total        0.622381                0.255660
```

In this example, the generated Fortran executable ran about 9.6 times faster than the original Python script. Timings are machine, compiler, and workload dependent.

## Optional Type and Rank Hints in Comments

`xp2f.py` can translate many unannotated Python programs, but Python does not always expose enough static type and rank information for reliable Fortran generation. As an optional aid, the transpiler recognizes simple declaration-style comments near function arguments.

These comments are hints, not required syntax. They are useful when a function argument should be emitted as an integer, real, logical, complex, character, vector, or matrix dummy argument.

Example:

```python
def matvec(n, a, x):
    # integer N, the matrix order.
    # real A(N,N), the matrix.
    # real X(N), the vector.
    return a @ x
```

The comments above tell the transpiler that `n` is scalar integer, `a` is rank 2 real, and `x` is rank 1 real. The corresponding Fortran dummy arguments are expected to look like:

```fortran
integer, intent(in) :: n
real(kind=dp), intent(in) :: a(:,:)
real(kind=dp), intent(in) :: x(:)
```

Recognized type words include `integer`, `int`, `real`, `float`, `logical`, `bool`, `complex`, `character`, `string`, and `str`. Rank is inferred from dimensions in parentheses or brackets, such as `A(N,N)`, `X(N)`, or `name[k]`.

The parser handles comma-separated declarations and nested dimension expressions:

```python
# real A1(min(M-1,N)), A2(min(M,N)), A3(min(M,N-1)), the diagonals.
```

Important caveats:

- Comments are treated as hints and may be overridden by stronger evidence from the function body or call sites.
- Incorrect comments can produce incorrect Fortran.
- Vector-like shapes such as `Y(N,1)` or `Y(1,N)` may be treated as rank 1.
- The comment parser is intentionally simple; it is not a full Fortran declaration parser.
- Hints should refer to actual Python argument names. Descriptive prose alone is ignored.

## Repository Contents

- `xp2f.py`: main transpiler and command-line interface.
- `python.f90`: Fortran helper runtime used by translated programs.
- `lapack_d.f90`: bundled double-precision LAPACK helpers used by some translations.
- `xp2f_batch.py`: batch runner for many Python files.
- `xcompare_xp2f_batch_results.py`: compares batch result snapshots.
- `xsummarize_xp2f_progress.py`: summarizes progress from `burkardt_python_results*.txt` files.
- `tests/`: focused tests for the Python-to-Fortran tooling.

## Testing

Run a quick syntax check:

```console
python -m py_compile xp2f.py xp2f_batch.py xcompare_xp2f_batch_results.py xsummarize_xp2f_progress.py fortran_output.py
```

Run the pytest suite:

```console
python -m pytest
```
