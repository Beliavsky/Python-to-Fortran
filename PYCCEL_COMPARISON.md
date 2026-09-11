# Comparison with Pyccel

Python-to-Fortran and [Pyccel](https://github.com/pyccel/pyccel) both translate numerical Python toward compiled languages, but they have different goals and workflows. This document previously summarized the two projects from their own documentation; it now also reflects actually running both tools on the same programs -- the 15 files under `examples/pyccel_bench/`, adapted from [pyccel's own benchmark suite](https://github.com/pyccel/pyccel-benchmarks) -- comparing generated Fortran, correctness, and `-O2` runtime, and building `pyccel_wrap.py` (below) to make that comparison apples-to-apples in the first place.

## Summary

| Topic | Python-to-Fortran | Pyccel |
| --- | --- | --- |
| Main target | Fortran source from Python scripts | Fortran, C, or C++ extension modules and executables |
| Primary command | `python xp2f.py foo.py` | `pyccel compile foo.py` |
| One-step run/test | `--run`, `--run-both`, and `--run-diff` compile and execute translated code for *any* script shape | `pyccel compile` links a real executable, but only for a script using `if __name__ == "__main__":`; a bare top-level script (no guard) instead becomes a Python-importable extension module with no standalone entry point -- see [Workflow](#workflow-difference) |
| Type information | Tries to infer types and ranks from unannotated code; optional comments can help | Type annotations are central, especially function argument annotations |
| Typical use case | Batch testing and translating existing Fortran-friendly numerical Python scripts | Accelerating annotated scientific Python functions or modules |
| Output style | Standalone Fortran program plus helper runtime; only the code reachable from the script's own entry point | Python extension module (or an executable, with a `__main__` guard); translates every function in the source file, reachable or not |
| Array indexing | Rebased to natural 1-based Fortran indexing | Kept literally 0-based, matching the source |
| Integer/real kind | Plain `integer` / `real(kind=dp)` by default; `--int-kind {int32,int64}` opts into an explicit kind | Explicit `ISO_C_Binding` kinds (`i64`, `f64`) always |
| Maturity | Experimental project built around `xp2f.py` | Larger established project with broader compiler infrastructure |

## Workflow Difference

Python-to-Fortran is designed as both a transpiler and a regression-testing harness, for a Python script in whatever shape it's already in:

```console
python xp2f.py foo.py --run-diff
```

This runs the original Python program, transpiles it to Fortran, compiles the Fortran, runs the generated executable, and compares normalized output -- regardless of whether `foo.py` uses a `__main__` guard, imports a sibling module, or is just a flat sequence of top-level statements (the common shape of a quick script, and the shape every driver in `examples/pyccel_bench/` uses).

Pyccel's own one-step command is `pyccel compile foo.py`. It genuinely can produce a standalone native executable -- confirmed by testing it directly -- but *only* when the input script wraps its own entry point in `if __name__ == "__main__":`. Given that, `pyccel compile` generates a real Fortran `program` unit and links an executable that runs independently of Python, the same as `xp2f.py --compile` does. Without that guard, though -- the shape of every driver script this project actually tested pyccel against -- pyccel instead emits a plain Fortran `module` (named after the script) with a `<name>__init()` subroutine holding the top-level statements, and compiles it into a `.pyd`/`.so` Python extension module. There's no `program` unit and no way to run it without Python importing that extension.

`pyccel_wrap.py` (new in this project, alongside `xp2f.py`) closes that specific gap: it runs `pyccel compile FILE --convert-only` (stopping right after translation), then links a small generic `program` stub that calls the generated `<name>__init()` subroutine directly -- giving pyccel an `xp2f.py`-shaped `--compile`/`--run`/`--run-both`/`--numeric-diff` CLI for scripts that don't use the `__main__` convention. It also resolves one level of local sibling imports automatically; pyccel itself requires each imported local module to be pyccelized separately, in dependency order, before the script that imports it (`xp2f.py` inlines a sibling module automatically instead). See `pyccel_wrap.py`'s own module docstring for the details, including a real pyccel behavior it has to account for: pyccel names its own output directory `__pyccel__` plus whatever `PYTEST_XDIST_WORKER` is set to, when that environment variable is present.

## Type Information

Pyccel documentation states that type annotations are an integral part of Pyccel and that function argument annotations are compulsory. Array ranks are commonly supplied using string annotations such as:

```python
def f(x: 'float[:]', a: 'float[:,:]'):
    ...
```

Python-to-Fortran tries to translate many unannotated numerical scripts. It infers scalar and array types where possible and also recognizes optional comment hints such as:

```python
def matvec(n, a, x):
    # integer N, the matrix order.
    # real A(N,N), the matrix.
    # real X(N), the vector.
    return a @ x
```

This makes Python-to-Fortran more convenient for experimenting with existing unannotated code, but also less predictable. When inference is ambiguous, generated Fortran may fail to compile or may need better hints.

## Translation Output Differences

Comparing the two tools' actual output for the same 15 files surfaced several consistent, structural differences, independent of any one program:

- **Reachability.** `xp2f.py` translates only the functions actually reachable from the driver script's own call graph. Pyccel translates every function defined in the source file, whether the driver calls it or not. For a source file bundling many related functions (`cfd_python_test.py`, `ode_test.py` in the benchmark set -- each with 15-18 functions, only a few of which any one driver calls), this produces a large difference in output size: `cfd_cavity_flow_xp2f.f90` is 138 lines against `cfd_cavity_flow_pyccel.f90`'s 981, for the same driver script.
- **Array indexing base.** `xp2f.py` rebases every index to natural 1-based Fortran indexing (`arr(i+1)` becomes the loop's own `i` running `1..n`, not `0..n-1` with `+1` scattered through every access). Pyccel keeps Python's 0-based indexing literally (`arr(0_i64:)`, loops running `0, n-1`) -- a direct carryover from the source with no Fortran-side justification, and the one place in this comparison where "literal translation" is the fair description of pyccel's choice.
- **Integer/real kind defaults.** Pyccel always declares explicit `ISO_C_Binding` kinds (`integer(i64)`, `real(f64)`) -- necessary for its own C-ABI wrapper generation, and incidentally a real correctness margin: `xp2f.py`'s previous bare-`integer` default let `dijkstra_distance_test`'s own `sum()` silently overflow (32-bit wraparound) where Python's own arbitrary-precision `int` would not. `xp2f.py` now has an opt-in `--int-kind {int32,int64}` flag closing this specific gap (`fortran_int_kind.py`), rewriting declarations and literal constants to an explicit kind, with a small, source-derived exclusion list for the handful of external LAPACK/bridge calls that require plain default-kind arguments.
- **Class translation.** For `splines.py`'s `Spline` class, pyccel emits a genuine Fortran derived type with type-bound procedures and pointer-aliased array fields (avoiding a copy when constructing an instance, at the cost of manual `free`/lifetime bookkeeping). `xp2f.py` hoists each method to a free top-level function taking `self` as an explicit first argument, with plain `allocatable` (copied) fields -- simpler, no manual lifetime management, and in this specific benchmark's own hot path (`eval()` called many times after construction) measurably *faster* than pyccel's pointer-based version, since the compiler can reason more freely about a plain allocatable than a pointer that might alias. A genuine bug in pyccel's own generated code for this same class was also found in this comparison: an invalid `deallocate` on a temporary that was never declared allocatable, which fails to compile independent of anything `xp2f.py` or `pyccel_wrap.py` does.
- **Value vs. reference scalar arguments.** Pyccel declares scalar dummy arguments `value` (pass-by-value, avoiding a pointer indirection on every access -- and needed for its own C-callable ABI). `xp2f.py` previously always used `intent(in)` (ordinary Fortran pass-by-reference). For scalar-argument-heavy hot paths, especially deep recursion, this is a real, measured cost -- see [Performance](#performance) below. `xp2f.py` now has an opt-in `--value-args` flag closing this gap for read-only scalar arguments (`intent(in)` -> `value`), including fixing up the interface blocks of any callback (procedure-dummy) argument, which must match exactly.

## Performance

`-O2` timing on 7 of the 15 benchmark files, before any of the flags described above existed, with both tools' output built with the identical `gfortran` invocation:

| Benchmark | xp2f.py | pyccel | |
| --- | --- | --- | --- |
| `ackermann(3,8)` (deep recursion) | 0.028s | 0.004s | pyccel ~6.4x faster |
| `rk4_humps_test` (10⁶ ODE steps) | 0.260s | 0.065s | pyccel ~4.0x faster |
| `md(3,100,200,0.1)` (O(n²) particles) | 0.079s | 0.082s | about even |
| `dijkstra_distance_test` (nv=3000 graph) | 0.115s | 0.047s | pyccel ~2.5x faster |
| `laplace_2d(150,150,...)` (Jacobi stencil) | 0.302s | 0.279s | pyccel ~8% faster |
| `Spline.eval` (10⁵ points, class method) | 0.028s | 0.032s | xp2f.py ~13% faster |
| `cavity_flow_2d` (41x41 grid, nt=700) | 0.150s | 0.121s | pyccel ~24% faster |

Digging into *why* attributed each gap to a specific, reusable pattern rather than a fixed cost of translation in general, and led directly to three of the opt-in flags above and below:

- **`ackermann`**'s whole gap traced to the `value`-vs-`intent(in)` difference described above; `--value-args` closes it (confirmed directly: the same benchmark, rebuilt with `--value-args`, runs at parity with pyccel's own number).
- **`cavity_flow_2d`** and (in further, separate testing) **`poisson_2d`** both traced to a numpy-row-major-vs-Fortran-column-major nested-loop-nesting mismatch: `xp2f.py` preserves a Python nested loop's own outer/inner order literally, which is backwards for Fortran's column-major array storage. `fortran_loop_reorder.py` (`--optimize-loops`) detects a nested loop pair filling a 2D array and swaps which one is physically outer vs. inner, when doing so is provably safe (no array both read and written within the same nest -- the correctness gate that distinguishes an ordinary Jacobi-style stencil, where reordering is always safe, from an in-place Gauss-Seidel-style relaxation, where it isn't). Rebuilt with `--optimize-loops`, `cavity_flow_2d` measured consistently ~30-40% faster than its own un-reordered build (interleaved timing, to rule out ordinary system-load noise), and `poisson_2d` (not in the original 7-file comparison, but exercising the identical stencil pattern) measured ~2x faster.
- **`rk4`** and **`dijkstra`** trace to the *same* row-major/column-major root cause, but in a shape neither `--optimize-loops` nor a further storage-layout change can safely fix without materially larger, riskier engineering (reshaping an array's own declared layout): a row slice (`y(i, :)`, holding the first index fixed while sweeping the whole second dimension) and a single, non-nested loop's loop-invariant first index (`ohd(mv + 1, i)` inside `do i = ...`). These remain open. Rather than guess at an automatic fix, `fortran_perf_hints.py` (`--perf-hints`) detects and reports both shapes as a diagnostic -- never modifying the generated Fortran -- so the gap is visible rather than silent.
- **`md`** and **`splines`** needed none of the above and were already at parity or ahead.

None of this should be read as "xp2f.py is faster than pyccel" or vice versa in general -- these are seven specific, fairly narrow benchmarks, `-O2` timing on one machine has real noise (confirmed directly: a non-interleaved before/after comparison on `cavity_flow_2d` gave a misleading result until timings were interleaved to control for background system load drift), and the two tools' own default build flags differ (this comparison held the compiler invocation fixed rather than using either tool's own default). The concrete, reusable finding is the two *causes* -- scalar pass-by-reference and array-layout mismatch -- and that they account for essentially the whole gap in the cases where `xp2f.py` was slower.

## Feature Coverage

Running the same corpus both ways also surfaced real gaps in each direction:

- Pyccel's parser doesn't support f-string format specifiers (`f'{x:.6f}'`) or `np.set_printoptions` -- both used by most of this project's own driver scripts for readable output, which is why `tests/test_pyccel_wrap.py` only exercises the 3 of 15 drivers that happen not to use either.
- `xp2f.py` has no native support for pyccel's own type-annotation style (`x: 'float[:]'`) as the *primary* way of conveying types -- it works from unannotated code and optional comment hints instead (see [Optional Type and Rank Hints](README.md#optional-type-and-rank-hints-in-comments)).
- `xp2f.py` supports `pandas.DataFrame` (a real subset -- see [README](README.md#pandas-dataframe-support)) and `scipy.optimize`/`scipy.linalg` (via hand-written Fortran bridges); pyccel supports neither.

## When Pyccel Is a Better Fit

Pyccel is likely the better choice when:

- You can annotate the Python code explicitly.
- Your script already uses (or can easily adopt) the `if __name__ == "__main__":` convention, or you want compiled extension modules imported back into Python rather than a standalone program.
- You want a mature compiler project with support for Fortran, C, and C++ back ends.
- You are optimizing selected kernels inside a larger Python application.

## When Python-to-Fortran Is a Better Fit

Python-to-Fortran is likely the better choice when:

- You want readable standalone Fortran source from a Python script in whatever shape it's already in -- no `__main__` guard, no mandatory type annotations.
- You want to test existing unannotated numerical Python code with minimal editing.
- You want a command that runs Python and translated Fortran and reports whether outputs match.
- You are working through a large corpus and want batch summaries of transpile, compile, and run failures.
- Your code uses `pandas` or `scipy.optimize`/`scipy.linalg`.

## Practical Positioning

The projects are complementary rather than direct substitutes. Pyccel is a more mature Python-to-compiled-extension tool, with real performance advantages in this project's own testing that trace to two specific, well-understood causes (scalar pass-by-reference, array-layout mismatch) -- `xp2f.py` now has opt-in flags closing part of that gap (`--value-args`, `--optimize-loops`, `--int-kind`) and a diagnostic surfacing the rest (`--perf-hints`) rather than leaving it silent. Python-to-Fortran remains narrower and more experimental, but emphasizes standalone Fortran output for scripts in their original, unannotated shape, and automated comparison of Python and translated Fortran behavior -- including, now, against pyccel's own translation of the same code (`pyccel_wrap.py`).
