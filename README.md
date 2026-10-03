# Python-to-Fortran

Python-to-Fortran is an experimental Python, NumPy, pandas, and (partial) SciPy to Fortran transpiler created using Codex by OpenAI and Claude Code by Anthropic centered on `xp2f.py`.

The project is intended for numerical Python programs that use a Fortran-friendly subset of Python. It can infer many scalar, array, string, and pandas DataFrame cases, emit Fortran source, optionally compile it with `gfortran`, and compare Python and Fortran output for regression testing.

## Why Fortran?

Fortran is a practical target for numerical Python: it combines native compilation with multidimensional arrays, whole-array expressions, array sections, and explicit procedure interfaces. Suitable Python loops can become efficient compiled loops, and generated routines can use established Fortran numerical libraries.

The output is inspectable source that can be compiled, profiled, modified, and reused in a Fortran project. Standalone translated programs do not require a Python interpreter at execution time, although they may require the project's Fortran helpers and other linked libraries. For workflows that should remain in Python, `xpfunc2f.py` can build supported individual functions into Python-callable extensions through NumPy's `f2py`.

Speedup is workload dependent, not guaranteed. NumPy and SciPy already perform much of their numerical work in compiled libraries; translating calls to those libraries may offer little benefit. Translation and compilation also have a cost. Translation time grows mainly with the number of functions reachable from the main program and with loop nesting depth, rather than with line count: small programs take seconds, while single files of 25,000 to 40,000 lines that exercise hundreds of functions can take a minute or more (see [Keep translation units focused](writing_python_for_fortran.md#keep-translation-units-focused)). See [Timing Results](TIMING_RESULTS.md) for runtime measurements and the [small example](#small-example) below for a loop-heavy case.

For side-by-side examples and important semantic differences, see the [Python To Fortran Syntax Guide](python_to_fortran_syntax_guide.md). It distinguishes conceptual equivalents from the transpiler's supported subset.

For practical source-code advice, see [Writing Python for Fortran Translation](writing_python_for_fortran.md): stable types and ranks, clear naming and interfaces, array ownership, focused translation units, and validation. These are recommendations for easier translation, not blanket restrictions on valid Python.

## Status

Use `--report-specializations` to print informational notes on stderr when a
local function is specialized for different argument ranks. These notes are
off by default: accepting a vector on one call and a matrix on another is not
itself a warning. Unsupported rank combinations still produce diagnostics;
the option does not enable general dynamic-rank variables.

This transpiler is useful on a substantial subset of numerical Python, but it is not a general Python compiler.

Known limitations include dynamic Python features (`isinstance` dispatch, `Union`/duck-typed parameters), complex/irregular containers, reflection, and parts of NumPy that do not map directly to static Fortran. The transpiler uses static analysis to infer types, array ranks, and procedure interfaces. It handles some type/rank changes through scoped declarations and specialized procedures, but not arbitrary dynamic rebinding. Array extents can be determined at runtime using allocatable arrays; their rank and element type still need to be inferable. When a program does not transpile, a small reproducer is usually the best starting point for improving `xp2f.py`.

Successful compilation or execution does not establish numerical equivalence. Different numerical-library implementations can produce different results for sensitive algorithms even when the translation preserves the source operations. See [Numerical Limitations](NUMERICAL_LIMITATIONS.md), including a diagnosed eigenvector-based matrix-exponential example.

See [Timing Results](TIMING_RESULTS.md) for runtime measurements on fully passing translated numerical programs.

See [Comparison with Pyccel](PYCCEL_COMPARISON.md) for how this project differs from Pyccel.

Another related project is [Numeta](https://gitlab.com/andrea_bianchi/numeta), which generates compiled numerical kernels using tracing and an explicit Python API, with Fortran and C backends. In contrast, `xp2f.py` analyzes ordinary Python source and aims to translate existing numerical programs with fewer source changes.

### Class support

A user-defined class is lowered to a Fortran derived type with plain `allocatable` (copied, not pointer-aliased) fields; each method is hoisted to a free top-level function taking `self` as an explicit first argument rather than a type-bound procedure. See [Comparison with Pyccel](PYCCEL_COMPARISON.md) for how this compares to pyccel's own pointer-based, type-bound-procedure translation.

Supported, and covered by regression tests in `tests/test_xp2f_cli.py`:

- Construction (including a stateless, empty `__init__`), field assignment and mutation, and `del` on an instance.
- Composition (a class field that is itself another class instance, including one constructed inline from a nested class), and field mutation reached through nested composition.
- Optional (`None`-defaultable) struct-typed parameters, forward-referenced string type annotations, and literal-default fields.
- A computed field (including one built from a `dtype=` keyword) and a computed read-only property getter.
- Instance aliasing (`b = a` shares mutations, matching Python's own reference semantics rather than copying).
- Case-colliding field names, and a function that returns a class constructor call directly.

### pandas DataFrame support

A `pandas.DataFrame` is lowered to a small Fortran derived type (`dataframe_str_index.f90` / `dataframe_index_date.f90` / `dataframe_index_datetime.f90`, chosen by row-index kind) holding the column names, row index, and a single real matrix of values.

Supported, and covered by regression tests in `tests/test_xp2f_cli.py`:

- Construction from a dict of arrays, a matrix, or `pd.read_csv`.
- Column selection by a literal name, a runtime string (including a `str` function parameter), a literal list, or a list spliced with `*a_module_level_list_of_strings`.
- `.iloc[...]`, `.loc[:, col]` (single column or a literal list of columns).
- Row-wise reductions and cumulative ops, `.rank()` (`"average"`, `"min"`, `"max"`, `"first"`, `"dense"`), `.dropna()`, `.shift()`, `.pct_change()`.
- A DataFrame as a local function parameter or return value, including inside a tuple return (`-> tuple[pd.DataFrame, float]`) and tuple-unpacked at the call site.
- Chained subscripts on a single column, e.g. `df["col"][i]`.

Not supported, because each needs a genuine architecture extension rather than a self-contained fix (see the design notes above on static typing):

- `.groupby(...)` (no aggregation engine).
- String-*valued* columns (as opposed to string row labels, which work) — the underlying type stores one real matrix, so a column that is actually text needs a different storage model.
- `pandas.MultiIndex` columns (a hierarchical column schema the type doesn't model).
- A DataFrame's schema (its columns) determined only at runtime — e.g. a dict built up in a loop over a variable-length list and only later converted with `pd.DataFrame(the_dict)`. The transpiler determines every DataFrame's columns via static analysis before generating code.

### SciPy support

Partial, via hand-written Fortran bridges to real numerical codes rather than transpiling SciPy's own Python source — `scipy.optimize.minimize` (BFGS, L-BFGS-B, Powell), `scipy.optimize.brentq`/`minimize_scalar`, and LAPACK-backed `scipy.linalg` routines (`lapack_d.f90`). This is the natural next area to extend: SciPy's numerical core (`optimize`, `linalg`, `interpolate`, `integrate`, `special`, `stats` distributions) fits the transpiler's static-typing model well, in contrast to pandas' dynamic-schema gaps above.

`solution, ier = scipy.optimize.leastsq(residual, x0)` uses MINPACK's `lmdif` numerical-Jacobian solver. The residual must be a known local function (including supported imported functions and lifted nested callbacks). The result is a real vector; `ier` is the MINPACK status code, with 1–4 indicating success. Supported keyword options are `ftol`, `xtol`, `gtol`, `maxfev`, `epsfcn`, `factor`, and `diag`. Nonempty `args`, analytic Jacobians (`Dfun`), and `full_output=True` are not yet supported and produce translation errors. As with other callback bridges, nested/reentrant solver calls are not supported. Validate fitted values and convergence status against Python; floating-point differences can affect convergence near tolerance boundaries.

## Requirements

- Python 3.11 or newer.
- NumPy for most translated numerical programs.
- `pandas` to translate programs that use `pandas.DataFrame`, and for `xsummarize_xp2f_progress.py`.
- `gfortran` on `PATH` for `--compile`, `--run`, and `--run-both`.
- `pytest` for the test suite.

## Basic Use

Emit Fortran:

```console
python xp2f.py path/to/program.py
```

Emit and compile:

```console
python xp2f.py path/to/program.py --compile
```

Run Python and translated Fortran and compare normalized output:

```console
python xp2f.py path/to/program.py --run-diff
```

Also declare a procedure `elemental` (and vectorize a per-element loop that calls it) where provably safe:

```console
python xp2f.py path/to/program.py --elemental
```

A handful of further opt-in flags close specific performance and correctness gaps identified by comparing translations against [Pyccel](PYCCEL_COMPARISON.md) on the same source programs; each is a self-contained post-pass over the generated Fortran and defaults off, so ordinary output is unaffected:

```console
python xp2f.py path/to/program.py --optimize-loops   # swap a column-major-unfriendly nested loop's own order, where provably safe
python xp2f.py path/to/program.py --value-args        # declare read-only scalar dummy arguments VALUE instead of intent(in)
python xp2f.py path/to/program.py --int-kind int64     # declare integers with an explicit kind (int32 or int64) instead of the compiler default
python xp2f.py path/to/program.py --perf-hints          # print (never modify) a diagnostic for strided array-access patterns neither flag above can safely fix
```

### Translating a library module

Use `--module` for a Python file containing imports and function definitions,
without a main program:

```console
python xp2f.py path/to/library.py --module --compile
```

This emits `<stem>_p.f90` containing `<stem>_proc_mod`. Compilation produces an
object (`.o`) and a compiler module (`.mod`) file, not an executable. Helper
modules are compiled as needed; their object files must also be linked when
building a program that uses the library. Procedure names may be renamed to
avoid Fortran/helper-name collisions; consult the generated `public` list.

Arguments need known element types and ranks, from annotations (for example,
`x: float` or `x: 'float[:]'`), typed calls within the module, or supported
unambiguous body constraints such as an integer `range` bound. Ambiguous
interfaces are rejected rather than silently defaulted to real scalars.
`--require-annotations` lists the parameters that still lack annotations (see
[Type Annotations](#type-annotations)).
Explicit fallback options are available, with warnings:

```console
python xp2f.py path/to/library.py --module --assume-float --assume-scalar --compile
python xp2f.py examples/rndm.py --module --assume-float --elemental --compile
```

`--assume-float` alone does not imply scalar rank. With `--elemental`, unresolved
rank is accepted only for simple arithmetic-return functions proven elementwise,
such as `return 2.0*x`, and only if the generated procedure is eligible for
`elemental`. Array-result or impure procedures remain ordinary procedures when
their interfaces are already known. A reduction such as `np.sum(x)` is not an
elementwise operation.

This initial mode rejects top-level initialization/driver statements, decorated
functions, and variadic or positional-only interfaces. Execution options and
`--partial`, `--strict`, `--strict-fix`, and `--type` cannot be combined with
`--module`. The batch runner still skips definition-only modules by default.

### Sleeping

Standalone `time.sleep(seconds)` calls support integer and fractional seconds,
including aliases such as `from time import sleep as pause`. Negative, nonfinite,
and excessively large durations stop with a runtime diagnostic. Sleep is impure;
it is never omitted or implemented as a busy-wait or shell command.

The build automatically selects `time_sleep_windows.f90` on Windows or
`time_sleep_posix.f90` on POSIX LP64 systems (64-bit Linux/macOS). These provide
the same module: when building manually, compile only the appropriate helper.
The POSIX helper resumes an interrupted wait. Windows waits round up to
milliseconds and check elapsed time; actual waits may be longer due to scheduling.
Using sleep's `None` result in an expression is not supported.

### Batch translation

Run a batch file list:

```console
python xp2f_batch.py @python_file_list.txt --blockers --jobs 4
```

For this repository's CSV-backed examples, run from the repository root and
explicitly use the root as the working directory:

```console
python xp2f_batch.py "examples/*.py" --work-dir .
```

This makes the tracked `asset_class_etf_prices.csv` and `prices_no_dates.csv`
available both to translation-time schema inference and to Python/Fortran
execution. The single-asset NAGARCH example selects SPY from the same asset-class
fixture; a separate `spy.csv` is not required. To run an individual example from
the root, for example, use `python xp2f.py examples/xfit_hv_no_dates.py --run-both`.

Without `--work-dir`, each file still runs in its own source directory. The
option requires an existing directory and does not copy data or change input,
helper, or output-option path resolution relative to the invocation directory.
Generated Fortran/executables remain beside the source by default; relative
program outputs and compiler caches use the working directory. Use the default
serial execution for examples sharing output filenames; `--work-dir` does not
isolate outputs between parallel jobs. It does not fix unrelated translation or
helper-build failures.

The batch runner reports definition-only modules (imports, function/class definitions,
docstrings, or `pass`, without a top-level driver) as `SKIP`, not failures.
Skips are counted separately and do not consume `--limit`; `--skip` still counts
matched files. Detection does not execute the Python source. Assignments, calls,
and control flow remain translation candidates, and syntax errors remain failures.
The `--strict` and `--strict-fix` modes still process modules.

To test explicit integer widening across examples, use:

```console
python xp2f_batch.py "examples/*.py" --work-dir . --int-kind int64
```

`--int-kind int32` is also accepted. The option is forwarded to each `xp2f.py`
invocation, and the batch report records the selected kind (including in `--tee`
logs). When omitted, no integer-kind option is forwarded. Keep a separate
default-kind run as a baseline; external helpers still require their declared
integer kinds.

Compare two batch result files:

```console
python xcompare_xp2f_batch_results.py baseline_results.txt newer_results.txt
```

Summarize historical batch progress files:

```console
python xsummarize_xp2f_progress.py
```

## Interactive Python and Fortran

Start the terminal REPL:

```text
python xp2f_repl.py
```

Enter Python normally, ending an indented block with a blank line. Imports,
variables, and function definitions persist in a separate Python process.
Bare expressions display their values. Commands start with `:` so they do not
conflict with Python names:

```text
p2f> def square(x):
...>     return x * x
...>
p2f> square(3)
9
p2f> :diff
```

`:translate` generates Fortran (using module mode for source containing only
imports and function/class definitions); `:run` compiles and runs it; `:run-python` runs
fresh Python; `:run-both` runs both; `:diff` compares their outputs using the
existing transpiler checks. `:time`, `:time-python`, and `:time-both` report
timings. These commands replay **all saved source from the beginning**, including
file writes and random draws, without changing the live Python workspace.
Only explicit commands translate or run Fortran.

`:list` shows entered source. `:source` shows the replay version, which adds
explicit `print(...)` calls to top-level value expressions. Live Python uses
normal interactive `repr` display; replay uses `print` formatting. Existing
print calls and common calls for side effects are preserved. For unfamiliar
calls that return `None`, prefer explicit statements and inspect `:source`;
expression printing is a convenience, not complete return-type inference.
Use explicit prints inside loops and functions when comparing output. Python
input requiring responses through `input()` is not supported in this version.

`:fortran` displays the latest translation and marks it stale after source
changes. `:save PATH`, `:save-source PATH`, and `:save-fortran PATH` save original
Python, replay Python, and current Fortran respectively. `:load PATH` replaces
the source without executing it. `:replay` explicitly rebuilds the live Python
workspace. `:undo` removes the last entered block and resets the workspace;
`:clear` clears the whole session. Exiting with `:quit` or EOF does not run or
automatically save code.

Syntax errors are not saved. Runtime errors retain source, may leave partial
Python state changes, and require `:undo`/`:replay` or `:clear` before continuing.
Ctrl+C cancels input or execution; a timeout or interrupted evaluation discards
the live interpreter. Source remains available for inspection and replay.

Load a file, or execute one comparison and exit:

```text
python xp2f_repl.py examples/xprime.py
python xp2f_repl.py examples/xprime.py --batch --mode diff
python xp2f_repl.py --int-kind int64 --rng-replay --timeout 120
```

The working directory defaults to the loaded file's directory, or the current
directory. Override it with `--work-dir`. Local imports and data files resolve
there; temporary source files are placed there to preserve sibling-module
resolution and removed on exit. Fortran builds use the CLI's usual helper
compilation/cache behavior. `--compiler`, `--pretty`, `--round`, and
`--numeric-diff` forward the corresponding execution/display options. Run
`:help` or `python xp2f_repl.py --help` for details. Session management and local
execution live in `p2f_session.py`, separately from the terminal interface.

## Interfaces for manually implemented Fortran procedures

`xp2f_interface.py` generates a Fortran procedure contract without executing the
Python source or attempting to translate its body. This is useful when a human
or an LLM will implement a function that the transpiler cannot handle. It does
not require FPM. For example:

```console
python xp2f_interface.py examples/nagarch_t_model.py neg_loglik --arg "params=float[:]" --arg "r=float[:]" --intent params=in --intent r=in --result float --out-dir nagarch_interface
```

The output directory must be new. It contains:

- `interface.f90`: a parent module declaring the procedure's arguments and result.
- `implementation.f90`: an implementation submodule; edit its procedure body.
  Until implemented, it deliberately stops with an error when called.
- `contract.json`: Python/Fortran name mappings, types, ranks, intents, kind
  choices, source-function hash, and limitations.

The [separate module procedure](https://www.intel.com/content/www/us/en/docs/fortran-compiler/developer-guide-reference/2024-2/separate-module-procedures.html)
inherits its signature from the interface; there is no second set of declarations
to keep synchronized. Compile the interface before the implementation, for example
with `gfortran -c interface.f90 implementation.f90` from the generated directory.
A Fortran caller imports the procedure from the module named in `contract.json`.
Existing output directories are never overwritten, protecting manual work.

The initial version accepts scalar `float`, `int`, `bool`, and `complex`, and
fixed-rank numeric/logical arrays using quoted annotations such as `'float[:,:]'`.
Annotations provide types, or repeated `--arg NAME=TYPE` and `--result TYPE`
explicitly override them. Caller-based inference is not performed. Reals and
complex values use `real64`; integers use `int32`, or `--int-kind int64`.
Scalar arguments are `intent(in)`. Every array requires an explicit
`--intent NAME=in`, `out`, or `inout`; these are user assertions, not inferred
mutation guarantees. Array arguments have assumed shape and cannot be resized.
An array result requires `--result-storage allocatable`; the implementation is
responsible for allocating it with the correct extents. A `None` result generates
a subroutine.

Default arguments, decorators, variadic/keyword-only/positional-only parameters,
strings, objects, and tuple results are not supported yet. Missing signature
information is an error, not an assumed type. Fortran names are made legal and
distinct ignoring case; consult the JSON mapping. No `pure` or `elemental`
promise is made. The contract specifies a calling interface, not a proof of
equivalent behavior: indexing, fixed-width integer limits, aliasing, global state,
and error behavior still need review. Automatic integration of these implementations
into transpiled callers, stale-contract checks, and Python extension wrappers are
separate future work.

## Optional FPM projects

`xp2f_fpm.py` can package several drivers with a shared stateless Python module
into an [FPM project](https://fpm.fortran-lang.org/spec/manifest.html). The normal
`xp2f.py --compile` workflow is unchanged. For example, from the repository root:

```console
python xp2f_fpm.py examples/xsim_fit_nagarch_t.py examples/xfit_nagarch_t.py --shared examples/nagarch_t_model.py --data asset_class_etf_prices.csv --out-dir nagarch_fpm --build
cd nagarch_fpm
fpm run --target xfit_nagarch_t --flag "-ffree-line-length-none"
```

Omit `--build` to generate without invoking FPM. The initial build backend uses
gfortran. Output must be a new directory; existing projects are never overwritten.
Repeat `--data` for additional files. Data is copied both for translation-time
schema inference and for execution from the project root.

Each driver is translated using existing caller-based inference. Shared routines
must have identical generated implementations across drivers, allowing only
comments, formatting, and dummy/result-name differences. One copy goes in `src/`;
each driver in `app/` imports it. Helpers are copied once into `src/helpers/`.
Translation logs and standalone baseline sources remain under `translation/`.

This is a conservative first version, not general Python package translation:
shared modules must contain imports and functions only, imports must be explicit
and unaliased, and every shared function must have an inferred callable
implementation. Conflicting specializations are rejected rather than merged.
The six `nagarch_t_model` drivers have been built together; the initial simulation
and fitting drivers also matched direct-compiler output after excluding timing.

## Small Example

The file [examples/xprime.py](examples/xprime.py) counts primes up to one million. Running:

```console
python xp2f.py examples/xprime.py --time-both
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

## Type Annotations

Annotations are optional: `xp2f.py` infers types and ranks from how functions are called and used. When present, it accepts Python scalar annotations (`x: int`, `x: float`, `x: bool`, `x: complex`, `s: str`) and pyccel's array syntax as strings (`v: 'float[:]'`, `m: 'int[:,:]'`), plus user class names.

Python itself ignores annotations at run time, so `xp2f.py` treats them as contracts to check rather than conversions to apply:

- A call whose argument contradicts a parameter annotation is a translation error, for example `f(2.5)` for `def f(x: int)`, or a scalar passed to `v: 'float[:]'`. Previously such a call could be translated with a silent conversion (printing `4` where Python prints `5.0`) or rejected by the Fortran compiler. Numeric widening consistent with PEP 484 is allowed: an `int` for a `float` or `complex` parameter, a `bool` for an `int`.
- A return annotation that the function body contradicts produces a warning; the translation follows the value the body actually returns, as Python does.

The check uses only reliable evidence (a known kind, and a rank from a typed variable or a literal), so an unreported call is not proof that its annotation is correct.

Some workflows need annotations. `--module` libraries have no call sites to infer argument types from, and pyccel requires annotations on every function. To list what is missing without translating anything:

```console
python xp2f.py path/to/library.py --require-annotations
```

This reports parameters without annotations, annotations `xp2f.py` does not recognize, and value-returning functions without a return annotation, and exits nonzero if it finds any. Methods' `self` and `cls` are exempt. `xannotate_for_pyccel.py` can add annotations inferred from call sites; review them, since the contract check has found cases where its guesses are wrong (for example a scalar `float` for an array built with `np.random.random(n)`).

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
- `xp2f_repl.py`: interactive Python workspace with Fortran translation, fresh execution, output comparison, and timing commands.
- `p2f_session.py`: reusable REPL session controller and local execution backends.
- `xpfunc2f.py`: translates ONE function (and its dependency closure) from a Python script to Fortran, compiles it with `numpy.f2py`, and generates a thin Python wrapper -- same name, same call signature -- backed by the compiled Fortran, for use inside an otherwise-unchanged Python program.
- `fortran_scan.py`: shared Fortran source-scanning/rewriting utilities used by `xp2f.py`.
- `fortran_post.py`: shared post-processing rewrites (cleanup, simplification, formatting) applied to generated Fortran.
- `fortran_purity.py`: determines `pure`/`elemental` eligibility of generated procedures by examining the emitted Fortran text.
- `fortran_loop_reorder.py`: `--optimize-loops` post-pass; swaps a nested loop pair's own outer/inner order to match Fortran's column-major array storage, where provably safe.
- `fortran_int_kind.py`: `--int-kind` post-pass; rewrites bare `integer` declarations (and related literals/casts) to an explicit `int32`/`int64` kind, excluding external LAPACK/bridge call boundaries that require the compiler's own default kind.
- `fortran_perf_hints.py`: `--perf-hints` diagnostic; reports (never rewrites) strided-array-access patterns that neither `--optimize-loops` nor `--int-kind` can safely fix.
- `pyccel_wrap.py`: standalone wrapper giving [Pyccel](PYCCEL_COMPARISON.md) an `xp2f.py`-style `--compile`/`--run`/`--run-both`/`--numeric-diff` command-line interface, for comparing the two tools' translations of the same Python source.
- `xannotate_for_pyccel.py`: infers and injects pyccel-compatible type annotations (`x: int`, `x: "float[:,:]"`) into an unannotated script's top-level functions, by tracing call-site argument types through the whole file. Unlike `xp2f.py`, pyccel requires argument annotations to translate a function; `xp2f.py` already accepts pyccel's own annotation syntax as input, so a single annotated file can be fed to both tools to cross-check their translations (and plain Python) against each other. Conservative by design: it leaves a parameter unannotated, and says why, rather than guess wrong.
- `python.f90`: Fortran helper runtime used by translated programs.
- `dataframe_str_index.f90`, `dataframe_index_date.f90`, `dataframe_index_datetime.f90`: pandas `DataFrame` companion types (string-indexed, date-indexed, datetime-indexed), auto-included when a translated program uses pandas.
- `lapack_d.f90`: bundled double-precision LAPACK helpers used by some translations.
- `xp2f_batch.py`: batch runner for many Python files.
- `xpfunc2f_batch.py`: batch runner for `xpfunc2f.py` over many Python files, reporting outcomes by stage (`Target`/`Transpile`/`Extract`/`F2PY Build`/`Run`) and a blocker breakdown for `Extract: FAIL` reasons.
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

Every configured pytest run automatically saves timestamped reports under
`reports/pytest/`, including when using `pytest -q`. These generated files are
ignored by Git:

- `.txt`: session start/end times, elapsed wall time, counts, per-test timing,
  and failure tracebacks with captured output, including failed rerun attempts.
- `.jsonl`: events flushed as they arrive, plus a final machine-readable summary.
  Partial results remain available if the run is interrupted or terminated.

Reports include the invocation, configured options, Python/pytest versions, Git
commit, and whether tracked files were modified. Parallel workers send results
to the controller, which is the only report writer. Final test counts exclude
extra rerun attempts; setup/teardown failures count as failed tests. Per-test
duration sums setup, call, teardown, and all attempts, so summed test durations
can exceed session wall time during parallel runs. Deselected counts are unknown
(`null`) in parallel runs.

An interrupted or early-stopped run is marked incomplete. If pytest is forcibly
terminated, the text file retains its initial `running/incomplete` status and
the JSONL file has no final summary. Failures before pytest loads this reporting
plugin cannot be recorded. Logging I/O errors disable reporting with a diagnostic
without changing test outcomes. Logs may contain captured application output;
review them before sharing. No full terminal transcript is recorded.
